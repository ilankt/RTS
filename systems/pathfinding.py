"""Deterministic navigation pipeline for RTS units.

The public `Pathfinding.find_path(...)` method is kept for older callers, but
the implementation is now a small navigation system with explicit results and
command helpers. Pathfinding treats terrain/buildings/resources/construction
sites as static blockers; other units remain dynamic and are handled by the
collision system during movement.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
import heapq
import math
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.config import (
    GRID_SIZE,
    PATHFINDING_FRAME_BUDGET_MS,
    PATHFINDING_MAX_EXPANSIONS,
    PATHFINDING_MAX_REQUEST_MS,
    PATHFINDING_QUEUE_MAX_PER_FRAME,
    PATHFINDING_QUEUE_MAX_RETRIES,
    PATHFINDING_QUEUE_REQUEST_MAX_MS,
    PATHFINDING_QUEUE_REQUEST_MS,
    PATH_CACHE_MAX_ENTRIES,
    TILE_HEIGHT,
    TILE_WIDTH,
)
from systems.flow_field import FlowFieldManager
from utils.perf_stats import perf_stats


Point = Tuple[float, float]
Cell = Tuple[int, int]

NAV_CELL_SIZE = GRID_SIZE
CLEARANCE_BUFFER = 2.0
CONTACT_BUFFER = 4.0
MAX_NEAREST_CELLS = 24
# Upper bound on unit radii that can appear in walkable-cache queries; used to
# size the invalidation region around a changed blocker.
MAX_CACHED_UNIT_RADIUS = 32.0


def _segment_intersects_rect(a: Point, b: Point, rect) -> bool:
    """Liang-Barsky style test: does segment a-b touch the (x0,y0,x1,y1) rect?"""
    x0, y0, x1, y1 = rect
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    t_min, t_max = 0.0, 1.0
    for delta, low, high in ((dx, x0 - ax, x1 - ax), (dy, y0 - ay, y1 - ay)):
        if delta == 0.0:
            if low > 0.0 or high < 0.0:
                return False
            continue
        t_low = low / delta
        t_high = high / delta
        if t_low > t_high:
            t_low, t_high = t_high, t_low
        t_min = max(t_min, t_low)
        t_max = min(t_max, t_high)
        if t_min > t_max:
            return False
    return True


@dataclass
class NavigationResult:
    """Structured pathfinding result used internally and by tests."""

    status: str
    waypoints: List[Point]
    final_point: Optional[Point]
    failure_reason: Optional[str] = None
    mode: str = "move"
    target: object = None
    revision: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok" and bool(self.waypoints)

    def __bool__(self) -> bool:
        return self.ok


class NavigationGrid:
    """World-space square nav grid over the rendered hex map."""

    def __init__(self, game_map, game, cell_size: int = NAV_CELL_SIZE):
        self.game_map = game_map
        self.game = game
        self.cell_size = cell_size
        self.revision = 0
        self.blockers: List[object] = []
        self._blocker_buckets: Dict[Cell, List[object]] = {}
        # unit_radius -> {cell: walkable}; flat per-radius views so the search
        # inner loop is one dict lookup. Invalidated per-region on blocker
        # changes, fully cleared only by rebuild().
        self._walkable_cache: Dict[float, Dict[Cell, bool]] = {}
        self.world_width, self.world_height = self._calculate_world_bounds()
        self._terrain_cols = int(self.world_width // cell_size) + 2
        self._terrain_rows = int(self.world_height // cell_size) + 2
        self._terrain_bitmap = self._build_terrain_bitmap()
        self._terrain_components = self._build_terrain_components()
        # Share the O(1) terrain probe with collision/movement/LOS code that only
        # has a map reference.
        setattr(self.game_map, "nav_terrain_walkable", self.terrain_walkable)
        self.rebuild()

    def rebuild_terrain(self):
        """Rebuild the static terrain bitmap + its connected components.

        Terrain is treated as immutable in normal play, so the bitmap is built
        once here and mark_dirty()/rebuild() deliberately never wipe it. Save
        loading is the one case where the ground genuinely changes underfoot,
        so it has to say so explicitly.
        """
        self._terrain_bitmap = self._build_terrain_bitmap()
        self._terrain_components = self._build_terrain_components()
        setattr(self.game_map, "nav_terrain_walkable", self.terrain_walkable)
        self.rebuild()

    def rebuild(self):
        start_time = time.perf_counter()
        self._walkable_cache.clear()
        self.blockers = []
        self._blocker_buckets = {}
        for obj in (
            list(getattr(self.game, "buildings", []))
            + list(getattr(self.game, "resources", []))
            + list(getattr(self.game, "construction_sites", []))
        ):
            if self._blocks_navigation(obj):
                self.blockers.append(obj)
                self._index_blocker(obj)
        perf_stats.add_time("path_rebuild_ms", (time.perf_counter() - start_time) * 1000.0)

    def mark_dirty(self):
        """Full rebuild — bulk fallback (setup, load, restart, tests)."""
        self.revision += 1
        perf_stats.increment("path_mark_dirty")
        perf_stats.increment("path_full_rebuilds")
        self.rebuild()

    def add_blocker(self, obj):
        """Incrementally index a newly added blocker.

        Returns the invalidated world bbox, or None if the object doesn't
        block navigation (caller then needs no path invalidation)."""
        if not self._blocks_navigation(obj):
            return None
        if obj in self.blockers:
            return None
        self.blockers.append(obj)
        self._index_blocker(obj)
        self.revision += 1
        return self._invalidate_region(obj)

    def remove_blocker(self, obj):
        """Incrementally un-index a removed blocker (bbox or None)."""
        try:
            self.blockers.remove(obj)
        except ValueError:
            return None
        self._unindex_blocker(obj)
        self.revision += 1
        return self._invalidate_region(obj)

    def _unindex_blocker(self, obj):
        padding = getattr(obj, "radius", 0) + CLEARANCE_BUFFER
        min_cell = self.world_to_cell((obj.x - padding, obj.y - padding))
        max_cell = self.world_to_cell((obj.x + padding, obj.y + padding))
        for cell_x in range(min_cell[0], max_cell[0] + 1):
            for cell_y in range(min_cell[1], max_cell[1] + 1):
                bucket = self._blocker_buckets.get((cell_x, cell_y))
                if bucket and obj in bucket:
                    bucket.remove(obj)
                    if not bucket:
                        del self._blocker_buckets[(cell_x, cell_y)]

    def _invalidate_region(self, obj):
        """Drop walkable-cache entries around a changed blocker; return the
        world bbox that path caches must invalidate against."""
        pad = getattr(obj, "radius", 0) + CLEARANCE_BUFFER + MAX_CACHED_UNIT_RADIUS + self.cell_size
        min_x, min_y = obj.x - pad, obj.y - pad
        max_x, max_y = obj.x + pad, obj.y + pad
        min_cell = self.world_to_cell((min_x, min_y))
        max_cell = self.world_to_cell((max_x, max_y))
        for view in self._walkable_cache.values():
            for cell_x in range(min_cell[0], max_cell[0] + 1):
                for cell_y in range(min_cell[1], max_cell[1] + 1):
                    view.pop((cell_x, cell_y), None)
        return (min_x, min_y, max_x, max_y)

    def world_to_cell(self, point: Point) -> Cell:
        return (int(point[0] // self.cell_size), int(point[1] // self.cell_size))

    def cell_to_world(self, cell: Cell) -> Point:
        return (
            cell[0] * self.cell_size + self.cell_size / 2,
            cell[1] * self.cell_size + self.cell_size / 2,
        )

    def point_walkable(self, point: Point, unit_radius: float, ignore: Sequence[object] = ()) -> bool:
        x, y = point
        if x < 0 or y < 0 or x > self.world_width or y > self.world_height:
            return False
        if not self._terrain_clear(point, unit_radius):
            return False
        ignored = set(ignore or ())
        for obj in self._candidate_blockers(point, unit_radius):
            if obj in ignored:
                continue
            if math.hypot(obj.x - x, obj.y - y) < obj.radius + unit_radius + CLEARANCE_BUFFER:
                return False
        return True

    def walkable_view(self, unit_radius: float) -> Dict[Cell, bool]:
        """The lazily-filled {cell: walkable} view for one radius."""
        view = self._walkable_cache.get(unit_radius)
        if view is None:
            view = self._walkable_cache[unit_radius] = {}
        return view

    def cell_walkable(self, cell: Cell, unit_radius: float, ignore: Sequence[object] = ()) -> bool:
        if cell[0] < 0 or cell[1] < 0:
            return False
        if ignore:
            return self.point_walkable(self.cell_to_world(cell), unit_radius, ignore)
        view = self.walkable_view(unit_radius)
        cached = view.get(cell)
        if cached is None:
            cached = view[cell] = self.point_walkable(self.cell_to_world(cell), unit_radius)
        return cached

    def segment_clear(
        self,
        start: Point,
        end: Point,
        unit_radius: float,
        ignore: Sequence[object] = (),
    ) -> bool:
        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        if dist < 0.01:
            return self.point_walkable(end, unit_radius, ignore)
        steps = max(2, int(dist / (self.cell_size / 2)))
        for index in range(steps + 1):
            t = index / steps
            point = (start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t)
            if not self.point_walkable(point, unit_radius, ignore):
                return False
        return True

    def nearest_walkable_cell(
        self,
        point: Point,
        unit_radius: float,
        ignore: Sequence[object] = (),
        max_radius_cells: int = MAX_NEAREST_CELLS,
    ) -> Optional[Cell]:
        origin = self.world_to_cell(point)
        if self.cell_walkable(origin, unit_radius, ignore):
            return origin
        best = None
        best_dist = float("inf")
        for radius in range(1, max_radius_cells + 1):
            for dx in range(-radius, radius + 1):
                for dy in (-radius, radius):
                    candidate = (origin[0] + dx, origin[1] + dy)
                    best = self._nearest_walkable_candidate(point, candidate, unit_radius, ignore, best, best_dist)
                    if best:
                        best_dist = math.hypot(self.cell_to_world(best)[0] - point[0], self.cell_to_world(best)[1] - point[1])
            for dy in range(-radius + 1, radius):
                for dx in (-radius, radius):
                    candidate = (origin[0] + dx, origin[1] + dy)
                    best = self._nearest_walkable_candidate(point, candidate, unit_radius, ignore, best, best_dist)
                    if best:
                        best_dist = math.hypot(self.cell_to_world(best)[0] - point[0], self.cell_to_world(best)[1] - point[1])
            if best:
                return best
        return None

    def _nearest_walkable_candidate(
        self,
        point: Point,
        candidate: Cell,
        unit_radius: float,
        ignore: Sequence[object],
        current_best: Optional[Cell],
        current_best_dist: float,
    ) -> Optional[Cell]:
        if not self.cell_walkable(candidate, unit_radius, ignore):
            return current_best
        cx, cy = self.cell_to_world(candidate)
        dist = math.hypot(cx - point[0], cy - point[1])
        if dist < current_best_dist:
            return candidate
        return current_best

    def _calculate_world_bounds(self) -> Point:
        if hasattr(self.game_map, "grid_to_world"):
            max_x, max_y = self.game_map.grid_to_world(self.game_map.width - 1, self.game_map.height - 1)
            return max_x + TILE_WIDTH * 2, max_y + TILE_HEIGHT * 2
        return self.game_map.width * TILE_WIDTH, self.game_map.height * TILE_HEIGHT

    def _blocks_navigation(self, obj) -> bool:
        if getattr(obj, "passable", False):
            return False  # open gates (§8.10)
        if getattr(obj, "amount_remaining", None) is not None:
            return obj.amount_remaining > 0
        if getattr(obj, "hp", 1) <= 0:
            return False
        return hasattr(obj, "x") and hasattr(obj, "y") and hasattr(obj, "radius")

    def _index_blocker(self, obj):
        padding = getattr(obj, "radius", 0) + CLEARANCE_BUFFER
        min_cell = self.world_to_cell((obj.x - padding, obj.y - padding))
        max_cell = self.world_to_cell((obj.x + padding, obj.y + padding))
        for cell_x in range(min_cell[0], max_cell[0] + 1):
            for cell_y in range(min_cell[1], max_cell[1] + 1):
                self._blocker_buckets.setdefault((cell_x, cell_y), []).append(obj)

    def _candidate_blockers(self, point: Point, unit_radius: float) -> Iterable[object]:
        padding = unit_radius + CLEARANCE_BUFFER
        min_cell = self.world_to_cell((point[0] - padding, point[1] - padding))
        max_cell = self.world_to_cell((point[0] + padding, point[1] + padding))
        seen = set()
        for cell_x in range(min_cell[0], max_cell[0] + 1):
            for cell_y in range(min_cell[1], max_cell[1] + 1):
                for obj in self._blocker_buckets.get((cell_x, cell_y), ()):
                    obj_id = id(obj)
                    if obj_id in seen:
                        continue
                    seen.add(obj_id)
                    yield obj

    def terrain_connected(self, cell_a: Cell, cell_b: Cell) -> bool:
        """O(1): can cell_b ever be reached from cell_a given terrain alone?

        Different terrain components are provably unreachable for every unit
        radius (larger radii and object blockers only further restrict). Same
        component is necessary but not sufficient."""
        components = self._terrain_components
        ax, ay = cell_a
        bx, by = cell_b
        if not (0 <= ax < self._terrain_cols and 0 <= ay < self._terrain_rows):
            return False
        if not (0 <= bx < self._terrain_cols and 0 <= by < self._terrain_rows):
            return False
        label_a = components[ay][ax]
        label_b = components[by][bx]
        return label_a >= 0 and label_a == label_b

    def _build_terrain_components(self) -> List[List[int]]:
        """4-connected components over the terrain bitmap (once; terrain is
        static). With the no-corner-cut rule, diagonal connectivity implies
        4-connectivity, so 4-connected labels are exact."""
        cols = self._terrain_cols
        rows = self._terrain_rows
        bitmap = self._terrain_bitmap
        labels = [[-1] * cols for _ in range(rows)]
        next_label = 0
        for start_y in range(rows):
            bitmap_row = bitmap[start_y]
            for start_x in range(cols):
                if not bitmap_row[start_x] or labels[start_y][start_x] != -1:
                    continue
                stack = [(start_x, start_y)]
                labels[start_y][start_x] = next_label
                while stack:
                    x, y = stack.pop()
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < cols and 0 <= ny < rows and bitmap[ny][nx] and labels[ny][nx] == -1:
                            labels[ny][nx] = next_label
                            stack.append((nx, ny))
                next_label += 1
        return labels

    def terrain_walkable(self, x: float, y: float) -> bool:
        """O(1) static-terrain probe against the precomputed walkable bitmap."""
        if x < 0 or y < 0:
            return False
        cell_x = int(x // self.cell_size)
        cell_y = int(y // self.cell_size)
        if cell_x >= self._terrain_cols or cell_y >= self._terrain_rows:
            return False
        return bool(self._terrain_bitmap[cell_y][cell_x])

    def _terrain_clear(self, point: Point, unit_radius: float) -> bool:
        x, y = point
        diag = unit_radius * 0.7
        walkable = self.terrain_walkable
        return (
            walkable(x, y)
            and walkable(x + unit_radius, y)
            and walkable(x - unit_radius, y)
            and walkable(x, y + unit_radius)
            and walkable(x, y - unit_radius)
            and walkable(x + diag, y + diag)
            and walkable(x - diag, y + diag)
            and walkable(x + diag, y - diag)
            and walkable(x - diag, y - diag)
        )

    def _build_terrain_bitmap(self) -> List[bytearray]:
        """Precompute per-nav-cell terrain walkability once (terrain is static).

        A cell counts as walkable only if its center and four inset corners all
        land on walkable terrain — conservative at water/lava boundaries so the
        collision system never rejects a point the planner accepted.
        """
        cell = self.cell_size
        game_map = self.game_map
        grid = game_map.grid
        map_height = game_map.height
        map_width = game_map.width
        world_to_grid = game_map.world_to_grid
        blocked_terrain = {"water", "lava"}
        inset = 0.5
        bitmap: List[bytearray] = []
        for cell_y in range(self._terrain_rows):
            row = bytearray(self._terrain_cols)
            y0 = cell_y * cell
            for cell_x in range(self._terrain_cols):
                x0 = cell_x * cell
                walkable = True
                for sample_x, sample_y in (
                    (x0 + cell * 0.5, y0 + cell * 0.5),
                    (x0 + inset, y0 + inset),
                    (x0 + cell - inset, y0 + inset),
                    (x0 + inset, y0 + cell - inset),
                    (x0 + cell - inset, y0 + cell - inset),
                ):
                    grid_pos = world_to_grid(sample_x, sample_y)
                    if grid_pos is None:
                        walkable = False
                        break
                    col, row_index = grid_pos
                    if not (0 <= row_index < map_height and 0 <= col < map_width) or grid[row_index][col] in blocked_terrain:
                        walkable = False
                        break
                row[cell_x] = 1 if walkable else 0
            bitmap.append(row)
        return bitmap


class Pathfinding:
    """Compatibility wrapper plus command API for navigation."""

    def __init__(self, game_map, game):
        self.game_map = game_map
        self.game = game
        self.grid_size = NAV_CELL_SIZE
        self.grid = NavigationGrid(game_map, game, NAV_CELL_SIZE)
        self.cache_hits = 0
        self.cache_misses = 0
        self.astar_calls = 0
        self.astar_expanded_cells = 0
        self.astar_capped = 0
        self._path_cache: OrderedDict[Tuple, NavigationResult] = OrderedDict()
        self._negative_path_keys: set = set()
        self._astar_budget_frame = None
        self._astar_frame_spent_ms = 0.0
        self._path_budget_frame = None
        self._path_frame_spent_ms = 0.0
        # Cross-frame command queue: over-budget commands wait here instead of
        # failing. Human-owned units drain first.
        self._pending_high = deque()
        self._pending_low = deque()
        self._pending_seq = 0
        self._request_budget_override: Optional[float] = None
        # When True (AI ticks), every search fast-fails as too_expensive so
        # commands land in the queue instead of burning the tick's wall time.
        self._defer_paths = False
        # One shared flow field per group move order (Phase 5).
        self.flow_fields = FlowFieldManager(self.grid)

    def mark_dirty(self):
        """Full nav + path-cache rebuild. Bulk fallback only — runtime world
        changes should go through notify_blocker_added/removed instead."""
        self.grid.mark_dirty()
        self._path_cache.clear()
        self._negative_path_keys.clear()
        self.flow_fields.invalidate()

    def rebuild_terrain(self):
        """The ground itself changed (save loading). Rebuilds the static
        terrain bitmap — which mark_dirty deliberately never touches — and
        then drops every cached path/flow field, since they were all solved
        against the old map."""
        self.grid.rebuild_terrain()
        self._path_cache.clear()
        self._negative_path_keys.clear()
        self.flow_fields.invalidate()

    def notify_blocker_added(self, obj):
        """Incrementally register a new static blocker (building/site/resource)."""
        bbox = self.grid.add_blocker(obj)
        if bbox is not None:
            perf_stats.increment("path_incremental_updates")
            self._invalidate_paths_in_bbox(bbox)
            self.flow_fields.invalidate()

    def notify_blocker_removed(self, obj):
        """Incrementally unregister a removed/destroyed/depleted blocker."""
        bbox = self.grid.remove_blocker(obj)
        if bbox is not None:
            perf_stats.increment("path_incremental_updates")
            # A removal can make previously unreachable goals reachable.
            self._drop_negative_path_entries()
            self._invalidate_paths_in_bbox(bbox)
            self.flow_fields.invalidate()

    def request_group_move(self, units, goal: Point, slots: Sequence[Point]) -> bool:
        """Group move via ONE shared flow field instead of N searches (A7).

        Each unit follows the field, then peels off to its personal formation
        slot for the final approach. Returns False if no field is possible
        (caller falls back to per-unit moves)."""
        pairs = []
        worker_tasks = getattr(self.game, "worker_task_system", None)
        for unit, slot in zip(units, slots):
            if worker_tasks is not None and unit.name == "worker":
                worker_tasks.cancel(unit)
            self._clear_task_state_for_move(unit)
            unit.path = None
            unit.path_index = 0
            unit.path_target = None
            unit.destination = None  # wait in place while the field builds
            pairs.append((unit, slot))
        return self.flow_fields.request_group_field(goal, pairs)

    def _drop_negative_path_entries(self):
        for key in self._negative_path_keys:
            self._path_cache.pop(key, None)
        self._negative_path_keys.clear()

    def _invalidate_paths_in_bbox(self, bbox):
        """Drop cached paths whose polyline crosses the changed region."""
        stale_keys = []
        cell_to_world = self.grid.cell_to_world
        for key, result in self._path_cache.items():
            if not result.waypoints:
                continue
            start_point = cell_to_world(key[0])
            previous = start_point
            for waypoint in result.waypoints:
                if _segment_intersects_rect(previous, waypoint, bbox):
                    stale_keys.append(key)
                    break
                previous = waypoint
        for key in stale_keys:
            del self._path_cache[key]
            self._negative_path_keys.discard(key)

    def find_path(
        self,
        start: Point,
        goal: Point,
        unit_radius: float = 20,
        unit=None,
        gathering_target=None,
        building_target=None,
        drop_off_target=None,
        mode: str = "move",
        target=None,
    ) -> Optional[List[Point]]:
        result = self.find_result(
            start,
            goal,
            unit_radius,
            unit,
            gathering_target=gathering_target,
            building_target=building_target,
            drop_off_target=drop_off_target,
            mode=mode,
            target=target,
        )
        return result.waypoints[:] if result.ok else None

    def find_result(
        self,
        start: Point,
        goal: Point,
        unit_radius: float = 20,
        unit=None,
        gathering_target=None,
        building_target=None,
        drop_off_target=None,
        mode: str = "move",
        target=None,
    ) -> NavigationResult:
        perf_stats.increment("path_requests")
        mode, target = self._resolve_mode_and_target(mode, target, gathering_target, building_target, drop_off_target)
        if self._defer_paths:
            return self._failed(mode, "too_expensive", target=target)
        if self._request_budget_override is not None:
            # Queue-drained request: gets its full ceiling regardless of how
            # much of this frame's budget is left (the queue paces itself).
            request_budget_ms = self._request_budget_override
        else:
            if self._remaining_path_frame_budget() <= 0:
                return self._failed(mode, "too_expensive", target=target)
            request_budget_ms = min(self._request_budget_ms(), self._remaining_path_frame_budget())
        started = time.perf_counter()
        deadline = started + (request_budget_ms / 1000.0)
        try:
            if target is not None:
                return self._find_interaction_path(start, unit_radius, unit, mode, target, deadline)
            return self._find_move_path(start, goal, unit_radius, unit, mode)
        finally:
            self._add_path_frame_spent((time.perf_counter() - started) * 1000.0)

    def issue_move(self, unit, world_pos: Point) -> bool:
        self._clear_task_state_for_move(unit)
        result = self.find_result((unit.x, unit.y), world_pos, unit.radius, unit, mode="move")
        if not result.ok and result.failure_reason == "too_expensive":
            self._enqueue_command(unit, "move", world_pos, None, None)
            return True
        return self._apply_result(unit, result, "move", None)

    def deferred_paths(self):
        """Context manager: fast-fail searches so commands queue instead.

        Wrapped around AI ticks - a tick that hands out an army's worth of
        orders spends microseconds enqueueing, and the per-frame queue drain
        does the actual pathfinding on later frames."""
        pathfinder = self

        class _Deferred:
            def __enter__(self):
                self.previous = pathfinder._defer_paths
                pathfinder._defer_paths = True

            def __exit__(self, exc_type, exc, tb):
                pathfinder._defer_paths = self.previous
                return False

        return _Deferred()

    def process_pending(self):
        """Drain queued path commands and advance flow-field builds.

        Called once per frame (before the AI issues new commands) so that an
        AI tick handing out a whole army's worth of orders spreads its path
        cost across the following frames instead of spiking one."""
        self.flow_fields.process()
        if not self._pending_high and not self._pending_low:
            return
        processed = 0
        self._request_budget_override = PATHFINDING_QUEUE_REQUEST_MS
        try:
            while processed < PATHFINDING_QUEUE_MAX_PER_FRAME:
                if self._remaining_path_frame_budget() < PATHFINDING_FRAME_BUDGET_MS * 0.25:
                    break
                queue = self._pending_high if self._pending_high else self._pending_low
                if not queue:
                    break
                entry = queue.popleft()
                processed += 1
                self._process_pending_entry(entry)
        finally:
            self._request_budget_override = None

    def _process_pending_entry(self, entry):
        kind, unit, payload, mode, preferred_point, seq, retries = entry
        if getattr(unit, "hp", 1) <= 0 or not getattr(unit, "in_world", True):
            return
        if getattr(unit, "_pending_path_seq", None) != seq:
            return  # superseded by a newer command
        unit._pending_path_seq = None
        self._requeue_retries = retries
        # Escalate the budget per retry so genuinely long paths (e.g. a
        # cross-map army order) always complete eventually instead of burning
        # every retry against the same too-small ceiling.
        self._request_budget_override = min(
            PATHFINDING_QUEUE_REQUEST_MAX_MS, PATHFINDING_QUEUE_REQUEST_MS * max(1, retries)
        )
        try:
            if kind == "move":
                ok = self.issue_move(unit, payload)
            else:
                ok = self.issue_interact(unit, payload, mode, preferred_point)
        finally:
            self._requeue_retries = 0
        # If it queued again, issue_* already stamped a fresh seq. If it failed
        # outright (unreachable), the command was cleared - nothing to do.
        perf_stats.increment("path_queue_processed")
        if not ok:
            perf_stats.increment("path_queue_failed")

    def _enqueue_command(self, unit, kind, payload, mode, preferred_point):
        retries = getattr(self, "_requeue_retries", 0)
        if retries >= PATHFINDING_QUEUE_MAX_RETRIES:
            perf_stats.increment("path_queue_dropped")
            self._clear_failed_command(unit)
            return
        self._pending_seq += 1
        unit._pending_path_seq = self._pending_seq
        entry = (kind, unit, payload, mode, preferred_point, self._pending_seq, retries + 1)
        player = getattr(unit, "player", None)
        if player is not None and getattr(player, "human", False):
            self._pending_high.append(entry)
        else:
            self._pending_low.append(entry)
        perf_stats.increment("path_queue_enqueued")

    def issue_interact(self, unit, target, mode: str, preferred_point: Optional[Point] = None) -> bool:
        if target is None:
            return False

        previous_gathering_target = getattr(unit, "gathering_target", None)
        if mode == "gather":
            self._clear_task_state_for_gather(unit)
        elif mode == "build":
            self._clear_task_state_for_build(unit)
        elif mode == "dropoff":
            self._clear_task_state_for_dropoff(unit)
        elif mode == "attack":
            self._clear_task_state_for_attack(unit)

        if preferred_point is not None:
            result = self.find_result((unit.x, unit.y), preferred_point, unit.radius, unit, mode="move")
            if result.ok:
                result.mode = mode
                result.target = target
            else:
                result = self.find_result((unit.x, unit.y), (target.x, target.y), unit.radius, unit, mode=mode, target=target)
        else:
            result = self.find_result((unit.x, unit.y), (target.x, target.y), unit.radius, unit, mode=mode, target=target)
        if not result.ok:
            if result.failure_reason == "too_expensive":
                # Out of frame budget - queue the command instead of failing it.
                self._enqueue_command(unit, "interact", target, mode, preferred_point)
                return True
            return self._clear_failed_command(unit)

        if mode == "gather":
            unit.gathering_target = target
            unit.is_engaging = True
            if hasattr(target, "gatherers") and unit not in target.gatherers:
                target.gatherers.append(unit)
        elif mode == "build":
            unit.building_target = target
            target.builder = unit
        elif mode == "dropoff":
            unit.drop_off_target = target
            if previous_gathering_target is not None:
                unit.previous_gathering_target = previous_gathering_target
                unit.gathering_target = None
        elif mode == "attack":
            unit.current_target = target
            unit.is_engaging = True
            unit.has_los = False
            unit.is_fallback_movement = False

        return self._apply_result(unit, result, mode, target)

    def get_interaction_distance(self, unit, target, mode: str) -> float:
        return self._interaction_distance(unit, target, mode)

    def is_position_walkable(self, point: Point, unit_radius: float, ignore: Sequence[object] = ()) -> bool:
        return self.grid.point_walkable(point, unit_radius, ignore)

    # Compatibility helpers used by older movement code.
    def _is_walkable(self, x: float, y: float, unit_radius: float) -> bool:
        return self.is_position_walkable((x, y), unit_radius)

    def _simple_line_clear(self, start: Point, end: Point, unit_radius: float = 20) -> bool:
        return self.grid.segment_clear(start, end, unit_radius)

    def _path_segment_clear(self, start: Point, end: Point, unit_radius: float) -> bool:
        return self._simple_line_clear(start, end, unit_radius)

    def _is_position_permanently_blocked(self, x: float, y: float, unit_radius: float) -> bool:
        return not self.is_position_walkable((x, y), unit_radius)

    def _find_closest_reachable_position(self, start: Point, target: Point, unit_radius: float) -> Optional[Point]:
        result = self._find_move_path(start, target, unit_radius, None, "move")
        return result.final_point if result.ok else None

    def _find_move_path(self, start: Point, goal: Point, unit_radius: float, unit, mode: str) -> NavigationResult:
        start_cell = self.grid.nearest_walkable_cell(start, unit_radius)
        if not start_cell:
            return self._failed(mode, "invalid_start")

        final_point = goal
        goal_cell = self.grid.world_to_cell(goal)
        if not self.grid.point_walkable(goal, unit_radius):
            goal_cell = self.grid.nearest_walkable_cell(goal, unit_radius)
            if not goal_cell:
                return self._failed(mode, "invalid_goal")
            final_point = self.grid.cell_to_world(goal_cell)
        else:
            goal_cell = self.grid.nearest_walkable_cell(goal, unit_radius)
            if not goal_cell:
                return self._failed(mode, "invalid_goal")

        return self._build_path(start, start_cell, final_point, goal_cell, unit_radius, mode, None)

    def _find_interaction_path(self, start: Point, unit_radius: float, unit, mode: str, target, deadline=None) -> NavigationResult:
        start_cell = self.grid.nearest_walkable_cell(start, unit_radius)
        if not start_cell:
            return self._failed(mode, "invalid_start", target=target)

        candidates = self._interaction_candidates(start, unit, target, mode)
        for point in candidates:
            if deadline is not None and time.perf_counter() >= deadline:
                return self._failed(mode, "too_expensive", target=target)
            if not self.grid.point_walkable(point, unit_radius):
                continue
            goal_cell = self.grid.nearest_walkable_cell(point, unit_radius)
            if not goal_cell:
                continue
            result = self._build_path(start, start_cell, point, goal_cell, unit_radius, mode, target)
            if result.ok:
                return result
            if result.failure_reason == "too_expensive":
                return result
        return self._failed(mode, "no_reachable_interaction_point", target=target)

    def _build_path(
        self,
        start: Point,
        start_cell: Cell,
        final_point: Point,
        goal_cell: Cell,
        unit_radius: float,
        mode: str,
        target,
    ) -> NavigationResult:
        cache_key = (start_cell, goal_cell, round(unit_radius, 2), mode, id(target))
        cached = self._path_cache.get(cache_key)
        if cached is not None:
            if cached.ok and self.grid.segment_clear(start, cached.waypoints[0], unit_radius):
                self.cache_hits += 1
                perf_stats.increment("path_cache_hits")
                self._path_cache.move_to_end(cache_key)
                return NavigationResult("ok", cached.waypoints[:], cached.final_point, mode=mode, target=target, revision=self.grid.revision)
            if not cached.ok and cached.failure_reason == "no_path":
                # Negative cache: adding blockers can't open a path, and any
                # blocker removal drops these entries.
                self.cache_hits += 1
                perf_stats.increment("path_cache_hits")
                return self._failed(mode, "no_path", target=target)

        self.cache_misses += 1
        perf_stats.increment("path_cache_misses")
        if self.grid.segment_clear(start, final_point, unit_radius):
            waypoints = [final_point]
            result = NavigationResult("ok", waypoints, final_point, mode=mode, target=target, revision=self.grid.revision)
            self._cache_result(cache_key, result)
            return result

        # O(1) rejection of goals on terrain islands — the worst-case searches
        # otherwise flood the whole free region before hitting the deadline.
        if not self.grid.terrain_connected(start_cell, goal_cell):
            perf_stats.increment("astar_component_rejects")
            failure = self._failed(mode, "no_path", target=target)
            self._cache_result(cache_key, failure)
            self._negative_path_keys.add(cache_key)
            return failure

        # Bounded reverse flood fill: goals walled into a small pocket by
        # objects/radius are proven unreachable in a few hundred probes.
        if self._goal_pocket_reachable(start_cell, goal_cell, unit_radius) is False:
            perf_stats.increment("astar_pocket_rejects")
            failure = self._failed(mode, "no_path", target=target)
            self._cache_result(cache_key, failure)
            self._negative_path_keys.add(cache_key)
            return failure

        cells = self._astar(start_cell, goal_cell, unit_radius)
        if cells == "too_expensive":
            return self._failed(mode, "too_expensive", target=target)
        if not cells:
            failure = self._failed(mode, "no_path", target=target)
            self._cache_result(cache_key, failure)
            self._negative_path_keys.add(cache_key)
            return failure

        raw_points = [self.grid.cell_to_world(cell) for cell in cells[1:]]
        if not raw_points or math.hypot(raw_points[-1][0] - final_point[0], raw_points[-1][1] - final_point[1]) > 1:
            raw_points.append(final_point)
        waypoints = self._smooth_path(start, raw_points, unit_radius)
        result = NavigationResult("ok", waypoints, final_point, mode=mode, target=target, revision=self.grid.revision)
        self._cache_result(cache_key, result)
        return result

    def _astar(self, start: Cell, goal: Cell, unit_radius: float):
        """Jump Point Search over the uniform nav grid.

        Strict no-corner-cutting variant (diagonal step requires both adjacent
        cardinals walkable) mirroring PathFinding.js's
        JPFMoveDiagonallyIfNoObstacles — optimal w.r.t. the same neighbor rule
        the plain A* used. Returns a list of jump-point cells (colinear
        stretches are collapsed), None if unreachable, or "too_expensive"."""
        self.astar_calls += 1
        perf_stats.increment("astar_calls")
        if self._request_budget_override is not None:
            request_budget_ms = self._request_budget_override
        else:
            remaining_budget_ms = self._remaining_astar_frame_budget()
            if remaining_budget_ms <= 0:
                self.astar_capped += 1
                perf_stats.increment("astar_capped")
                return "too_expensive"
            request_budget_ms = min(self._request_budget_ms(), remaining_budget_ms)
        started = time.perf_counter()
        deadline = started + (request_budget_ms / 1000.0)

        grid = self.grid
        cell_walkable = grid.cell_walkable
        # Flat persistent per-radius view: the scan inner loop is one dict get.
        view = grid.walkable_view(unit_radius)

        def walkable(x: int, y: int) -> bool:
            cached = view.get((x, y))
            if cached is None:
                cached = x >= 0 and y >= 0 and cell_walkable((x, y), unit_radius)
            return cached

        # Shared scan-step counter for deadline checks inside line scans; the
        # counter stays a cheap local-int bump, time is polled every 2048 steps.
        scan_state = {"steps": 0, "next_check": 2048}

        class _Expensive(Exception):
            pass

        def check_budget():
            steps = scan_state["steps"] = scan_state["steps"] + 1
            if steps >= scan_state["next_check"]:
                scan_state["next_check"] = steps + 2048
                if time.perf_counter() >= deadline:
                    raise _Expensive

        def jump_straight(x: int, y: int, dx: int, dy: int):
            """Scan cardinally from (x, y) in (dx, dy); return jump point or None."""
            while True:
                check_budget()
                if not walkable(x, y):
                    return None
                if (x, y) == goal:
                    return (x, y)
                if dx != 0:
                    if (walkable(x, y - 1) and not walkable(x - dx, y - 1)) or (
                        walkable(x, y + 1) and not walkable(x - dx, y + 1)
                    ):
                        return (x, y)
                else:
                    if (walkable(x - 1, y) and not walkable(x - 1, y - dy)) or (
                        walkable(x + 1, y) and not walkable(x + 1, y - dy)
                    ):
                        return (x, y)
                x += dx
                y += dy

        def jump_diagonal(x: int, y: int, dx: int, dy: int):
            """Scan diagonally; jump point where a straight sub-scan hits one."""
            while True:
                check_budget()
                if not walkable(x, y):
                    return None
                if (x, y) == goal:
                    return (x, y)
                if jump_straight(x + dx, y, dx, 0) is not None:
                    return (x, y)
                if jump_straight(x, y + dy, 0, dy) is not None:
                    return (x, y)
                # No corner cutting: both cardinals must be open to continue.
                if not (walkable(x + dx, y) and walkable(x, y + dy)):
                    return None
                x += dx
                y += dy

        def successor_directions(x: int, y: int, direction):
            """Pruned successor directions given the arrival direction."""
            if direction is None:
                dirs = []
                for dx, dy in (
                    (-1, -1), (-1, 0), (-1, 1), (0, -1),
                    (0, 1), (1, -1), (1, 0), (1, 1),
                ):
                    if dx != 0 and dy != 0:
                        if walkable(x + dx, y) and walkable(x, y + dy) and walkable(x + dx, y + dy):
                            dirs.append((dx, dy))
                    elif walkable(x + dx, y + dy):
                        dirs.append((dx, dy))
                return dirs
            dx, dy = direction
            dirs = []
            if dx != 0 and dy != 0:
                side_v = walkable(x, y + dy)
                side_h = walkable(x + dx, y)
                if side_v:
                    dirs.append((0, dy))
                if side_h:
                    dirs.append((dx, 0))
                if side_v and side_h and walkable(x + dx, y + dy):
                    dirs.append((dx, dy))
            elif dx != 0:
                forward = walkable(x + dx, y)
                top = walkable(x, y + 1)
                bottom = walkable(x, y - 1)
                if forward:
                    dirs.append((dx, 0))
                    if top and walkable(x + dx, y + 1):
                        dirs.append((dx, 1))
                    if bottom and walkable(x + dx, y - 1):
                        dirs.append((dx, -1))
                if top:
                    dirs.append((0, 1))
                if bottom:
                    dirs.append((0, -1))
            else:
                forward = walkable(x, y + dy)
                right = walkable(x + 1, y)
                left = walkable(x - 1, y)
                if forward:
                    dirs.append((0, dy))
                    if right and walkable(x + 1, y + dy):
                        dirs.append((1, dy))
                    if left and walkable(x - 1, y + dy):
                        dirs.append((-1, dy))
                if right:
                    dirs.append((1, 0))
                if left:
                    dirs.append((-1, 0))
            return dirs

        open_heap = []
        counter = 0
        g_score: Dict[Cell, float] = {start: 0.0}
        parent: Dict[Cell, Cell] = {}
        heapq.heappush(open_heap, (self._heuristic(start, goal), counter, start))
        closed = set()

        def finish_counters():
            self.astar_expanded_cells += len(closed)
            perf_stats.increment("astar_expanded_cells", len(closed))
            perf_stats.increment("astar_scan_steps", scan_state["steps"])

        try:
            while open_heap:
                _, _, current = heapq.heappop(open_heap)
                if current in closed:
                    continue
                if len(closed) >= PATHFINDING_MAX_EXPANSIONS:
                    self.astar_capped += 1
                    perf_stats.increment("astar_capped")
                    finish_counters()
                    return "too_expensive"
                if current == goal:
                    finish_counters()
                    return self._reconstruct_cells(current, parent)
                closed.add(current)

                x, y = current
                parent_cell = parent.get(current)
                if parent_cell is None:
                    direction = None
                else:
                    px, py = parent_cell
                    direction = (
                        (x > px) - (x < px),
                        (y > py) - (y < py),
                    )

                current_g = g_score[current]
                for dx, dy in successor_directions(x, y, direction):
                    if dx != 0 and dy != 0:
                        jump_point = jump_diagonal(x + dx, y + dy, dx, dy)
                    else:
                        jump_point = jump_straight(x + dx, y + dy, dx, dy)
                    if jump_point is None or jump_point in closed:
                        continue
                    tentative = current_g + self._heuristic(current, jump_point)
                    if tentative >= g_score.get(jump_point, float("inf")):
                        continue
                    parent[jump_point] = current
                    g_score[jump_point] = tentative
                    counter += 1
                    priority = tentative + self._heuristic(jump_point, goal)
                    heapq.heappush(open_heap, (priority, counter, jump_point))
            finish_counters()
            return None
        except _Expensive:
            self.astar_capped += 1
            perf_stats.increment("astar_capped")
            finish_counters()
            return "too_expensive"
        finally:
            self._add_astar_frame_spent((time.perf_counter() - started) * 1000.0)

    GOAL_POCKET_SCAN_CAP = 2048
    POCKET_MEMO_MAX = 512

    def _goal_pocket_reachable(self, start_cell: Cell, goal_cell: Cell, unit_radius: float):
        """Bounded reverse reachability check from the goal.

        Returns False if the goal's enclosing free region provably excludes the
        start (exact — no-corner-cut connectivity equals 4-connectivity), True
        if the start was reached, None if inconclusive (region larger than the
        cap; let the real search decide).

        Memoized per (goal, radius, revision): open-region verdicts store
        True (start-independent "inconclusive"), and CLOSED pockets store the
        complete flooded cell set — the war-dominant case, where every unit
        attacking a sealed target used to re-flood the same pocket per path
        request (~2ms each, ~19% of a profiled 8-player war frame budget);
        with the set cached the verdict is one membership test for any start."""
        memo = getattr(self, "_pocket_memo", None)
        if memo is None:
            memo = self._pocket_memo = {}
        memo_key = (goal_cell, unit_radius, self.grid.revision)
        cached = memo.get(memo_key)
        if cached is not None:
            if cached is True:
                return None  # open region - inconclusive for every start
            return start_cell in cached  # complete pocket set
        cell_walkable = self.grid.cell_walkable
        seen = {goal_cell}
        stack = [goal_cell]
        while stack:
            if len(seen) > self.GOAL_POCKET_SCAN_CAP:
                if len(memo) > self.POCKET_MEMO_MAX:
                    memo.clear()
                memo[memo_key] = True  # open region - remember and skip next time
                return None
            x, y = stack.pop()
            if (x, y) == start_cell:
                return True
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor not in seen and neighbor[0] >= 0 and neighbor[1] >= 0 and cell_walkable(neighbor, unit_radius):
                    seen.add(neighbor)
                    stack.append(neighbor)
        # Flood exhausted without reaching the start: `seen` IS the goal's
        # whole enclosed pocket, valid for any future start at this revision.
        if len(memo) > self.POCKET_MEMO_MAX:
            memo.clear()
        memo[memo_key] = frozenset(seen)
        return False

    def _request_budget_ms(self) -> float:
        """Per-request wall-clock ceiling; queue-drained requests get more."""
        if self._request_budget_override is not None:
            return self._request_budget_override
        return PATHFINDING_MAX_REQUEST_MS

    def _remaining_astar_frame_budget(self) -> float:
        frame = getattr(self.game, "frame_counter", 0)
        if self._astar_budget_frame != frame:
            self._astar_budget_frame = frame
            self._astar_frame_spent_ms = 0.0
        return max(0.0, PATHFINDING_FRAME_BUDGET_MS - self._astar_frame_spent_ms)

    def _add_astar_frame_spent(self, milliseconds: float) -> None:
        frame = getattr(self.game, "frame_counter", 0)
        if self._astar_budget_frame != frame:
            self._astar_budget_frame = frame
            self._astar_frame_spent_ms = 0.0
        self._astar_frame_spent_ms += milliseconds

    def _remaining_path_frame_budget(self) -> float:
        frame = getattr(self.game, "frame_counter", 0)
        if self._path_budget_frame != frame:
            self._path_budget_frame = frame
            self._path_frame_spent_ms = 0.0
        return max(0.0, PATHFINDING_FRAME_BUDGET_MS - self._path_frame_spent_ms)

    def _add_path_frame_spent(self, milliseconds: float) -> None:
        frame = getattr(self.game, "frame_counter", 0)
        if self._path_budget_frame != frame:
            self._path_budget_frame = frame
            self._path_frame_spent_ms = 0.0
        self._path_frame_spent_ms += milliseconds

    def _cache_result(self, cache_key: Tuple, result: NavigationResult):
        self._path_cache[cache_key] = result
        self._path_cache.move_to_end(cache_key)
        while len(self._path_cache) > PATH_CACHE_MAX_ENTRIES:
            evicted_key, _ = self._path_cache.popitem(last=False)
            self._negative_path_keys.discard(evicted_key)
            perf_stats.increment("path_cache_evictions")

    def _neighbors(self, cell: Cell, unit_radius: float) -> Iterable[Tuple[Cell, float]]:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                candidate = (cell[0] + dx, cell[1] + dy)
                if not self.grid.cell_walkable(candidate, unit_radius):
                    continue
                if dx != 0 and dy != 0:
                    # No corner cutting through blocked cardinal cells.
                    if not self.grid.cell_walkable((cell[0] + dx, cell[1]), unit_radius):
                        continue
                    if not self.grid.cell_walkable((cell[0], cell[1] + dy), unit_radius):
                        continue
                    yield candidate, math.sqrt(2) * self.grid.cell_size
                else:
                    yield candidate, float(self.grid.cell_size)

    def _reconstruct_cells(self, current: Cell, parent: Dict[Cell, Cell]) -> List[Cell]:
        cells = [current]
        while current in parent:
            current = parent[current]
            cells.append(current)
        cells.reverse()
        return cells

    def _smooth_path(self, start: Point, raw_points: List[Point], unit_radius: float) -> List[Point]:
        if not raw_points:
            return []
        smoothed = []
        anchor = start
        index = 0
        while index < len(raw_points):
            farthest = index
            for candidate in range(len(raw_points) - 1, index - 1, -1):
                if self.grid.segment_clear(anchor, raw_points[candidate], unit_radius):
                    farthest = candidate
                    break
            waypoint = raw_points[farthest]
            smoothed.append(waypoint)
            anchor = waypoint
            index = farthest + 1
        return smoothed

    def _interaction_candidates(self, start: Point, unit, target, mode: str) -> List[Point]:
        distance = self._interaction_distance(unit, target, mode)
        base_angle = math.atan2(start[1] - target.y, start[0] - target.x)
        offsets = [0]
        for step in range(1, 17):
            delta = step * math.pi / 16
            offsets.extend([delta, -delta])

        candidates = []
        for offset in offsets:
            angle = base_angle + offset
            candidates.append((target.x + math.cos(angle) * distance, target.y + math.sin(angle) * distance))
        if mode == "attack":
            candidates = self._decluster_attack_candidates(candidates, unit)
        return candidates

    def _decluster_attack_candidates(self, candidates: List[Point], unit) -> List[Point]:
        """Free contact points first, crowded ones as a fallback: latecomers
        in a siege otherwise re-path forever into an arc already packed with
        friendly attackers while the far side of the target sits empty
        (user-reported: units 'stop trying' to reach attack positions)."""
        collision = getattr(self.game, "collision_system", None)
        player = getattr(unit, "player", None)
        if collision is None or player is None:
            return candidates
        spacing = max(12.0, getattr(unit, "radius", 8.0) * 1.8)
        free, crowded = [], []
        for point in candidates:
            # Only units ACTIVELY attacking count as occupiers — they hold
            # their spot until the target dies. Merely-engaging units are
            # still marching and will vacate (counting them made every arc
            # look full during a mass order).
            occupied = any(
                getattr(other, "player", None) is player
                and getattr(other, "in_combat", False)
                for other in collision.query_nearby_units(
                    point[0], point[1], spacing, exclude=unit)
            )
            (crowded if occupied else free).append(point)
        return free + crowded

    def _interaction_distance(self, unit, target, mode: str) -> float:
        unit_radius = getattr(unit, "radius", 8)
        target_radius = getattr(target, "radius", 0)
        if mode == "gather":
            from systems.gathering_manager import get_gathering_distance

            return get_gathering_distance(unit, target)
        if mode == "dropoff":
            from systems.gathering_manager import get_drop_off_distance

            return get_drop_off_distance(unit, target)
        if mode == "attack":
            attack_range = getattr(unit, "attack_range", unit_radius + CONTACT_BUFFER)
            preferred_range = attack_range * 0.85 if attack_range > unit_radius + CONTACT_BUFFER else unit_radius + CONTACT_BUFFER
            return target_radius + max(unit_radius + CONTACT_BUFFER, preferred_range)
        return target_radius + unit_radius + CONTACT_BUFFER

    def _resolve_mode_and_target(self, mode, target, gathering_target, building_target, drop_off_target):
        if target is not None:
            return mode, target
        if building_target is not None:
            return "build", building_target
        if gathering_target is not None:
            return "gather", gathering_target
        if drop_off_target is not None:
            return "dropoff", drop_off_target
        return mode, target

    def _apply_result(self, unit, result: NavigationResult, task_type: str, target) -> bool:
        if not result.ok:
            return False
        unit.path = result.waypoints[:]
        unit.path_index = 0
        unit.path_target = result.final_point
        unit.destination = result.waypoints[0]
        unit.status = "run"
        unit.last_task = {"type": task_type, "target": target or result.final_point}
        if target is not None:
            unit.path_target_object = target
            unit.path_target_object_pos = (target.x, target.y)
            unit.path_target_mode = task_type
        else:
            self._clear_path_target_object(unit)
        return True

    def _clear_failed_command(self, unit) -> bool:
        unit.path = None
        unit.path_index = 0
        unit.path_target = None
        unit.destination = None
        unit.status = "idle"
        self._clear_path_target_object(unit)
        return False

    def _clear_task_state_for_move(self, unit):
        self._unlink_gatherer(unit)
        unit.flow_field = None
        unit.flow_slot_target = None
        unit.is_gathering = False
        unit.gathering_target = None
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.current_target = None
        unit.in_combat = False
        unit.is_engaging = False
        unit.is_building = False
        unit.building_target = None
        unit.has_los = False
        unit.is_fallback_movement = False
        if hasattr(unit, "garrison_target"):
            unit.garrison_target = None

    def _clear_task_state_for_gather(self, unit):
        self._unlink_gatherer(unit)
        unit.current_target = None
        unit.in_combat = False
        unit.is_engaging = False
        unit.is_gathering = False
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.is_building = False
        unit.building_target = None
        if hasattr(unit, "garrison_target"):
            unit.garrison_target = None

    def _clear_task_state_for_build(self, unit):
        self._unlink_gatherer(unit)
        unit.is_gathering = False
        unit.gathering_target = None
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.current_target = None
        unit.in_combat = False
        unit.is_engaging = False
        unit.is_building = False
        unit.building_target = None
        unit.has_los = False
        unit.is_fallback_movement = False

    def _clear_task_state_for_dropoff(self, unit):
        self._unlink_gatherer(unit)
        unit.current_target = None
        unit.in_combat = False
        unit.is_engaging = False
        unit.is_gathering = False
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.has_los = False
        unit.is_fallback_movement = False

    def _clear_task_state_for_attack(self, unit):
        self._unlink_gatherer(unit)
        # §9 blind-march fix: an attack order must release a group-move flow
        # field (mirrors _clear_task_state_for_move) or the field keeps
        # dragging the unit and the order is silently swallowed.
        unit.flow_field = None
        unit.flow_slot_target = None
        unit.is_gathering = False
        unit.gathering_target = None
        unit.is_dropping_off = False
        unit.drop_off_timer = 0.0
        unit.drop_off_target = None
        unit.is_building = False
        unit.building_target = None
        unit.in_combat = False
        unit.is_engaging = False
        unit.has_los = False
        unit.is_fallback_movement = False
        if hasattr(unit, "garrison_target"):
            unit.garrison_target = None

    def _clear_path_target_object(self, unit):
        for attr in ("path_target_object", "path_target_object_pos", "path_target_mode"):
            if hasattr(unit, attr):
                delattr(unit, attr)

    def _unlink_gatherer(self, unit):
        resource = getattr(unit, "gathering_target", None)
        if resource and hasattr(resource, "gatherers") and unit in resource.gatherers:
            resource.gatherers.remove(unit)

    def _failed(self, mode: str, reason: str, target=None) -> NavigationResult:
        return NavigationResult(
            status="unreachable",
            waypoints=[],
            final_point=None,
            failure_reason=reason,
            mode=mode,
            target=target,
            revision=self.grid.revision,
        )

    def _heuristic(self, a: Cell, b: Cell) -> float:
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        straight = max(dx, dy) - min(dx, dy)
        diagonal = min(dx, dy)
        return (straight + math.sqrt(2) * diagonal) * self.grid.cell_size

    def _path_cost(self, start: Point, waypoints: List[Point]) -> float:
        cost = 0.0
        last = start
        for point in waypoints:
            cost += math.hypot(point[0] - last[0], point[1] - last[1])
            last = point
        return cost
