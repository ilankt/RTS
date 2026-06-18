"""Deterministic navigation pipeline for RTS units.

The public `Pathfinding.find_path(...)` method is kept for older callers, but
the implementation is now a small navigation system with explicit results and
command helpers. Pathfinding treats terrain/buildings/resources/construction
sites as static blockers; other units remain dynamic and are handled by the
collision system during movement.
"""

from __future__ import annotations

from collections import OrderedDict
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
    PATH_CACHE_MAX_ENTRIES,
    TILE_HEIGHT,
    TILE_WIDTH,
)
from utils.perf_stats import perf_stats


Point = Tuple[float, float]
Cell = Tuple[int, int]

NAV_CELL_SIZE = GRID_SIZE
CLEARANCE_BUFFER = 2.0
CONTACT_BUFFER = 4.0
MAX_NEAREST_CELLS = 24


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
        self._walkable_cache: Dict[Tuple, bool] = {}
        self._terrain_probe_cache: Dict[Tuple[float, float], bool] = {}
        self.world_width, self.world_height = self._calculate_world_bounds()
        self.rebuild()

    def rebuild(self):
        start_time = time.perf_counter()
        self._walkable_cache.clear()
        self._terrain_probe_cache.clear()
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
        self.revision += 1
        perf_stats.increment("path_mark_dirty")
        self.rebuild()

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

    def cell_walkable(self, cell: Cell, unit_radius: float, ignore: Sequence[object] = ()) -> bool:
        if cell[0] < 0 or cell[1] < 0:
            return False
        if not ignore:
            cache_key = (self.revision, cell, round(unit_radius, 2))
            if cache_key in self._walkable_cache:
                return self._walkable_cache[cache_key]
        point = self.cell_to_world(cell)
        walkable = self.point_walkable(point, unit_radius, ignore)
        if not ignore:
            self._walkable_cache[cache_key] = walkable
        return walkable

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

    def _terrain_clear(self, point: Point, unit_radius: float) -> bool:
        x, y = point
        diag = unit_radius * 0.7
        check_points = (
            (x, y),
            (x + unit_radius, y),
            (x - unit_radius, y),
            (x, y + unit_radius),
            (x, y - unit_radius),
            (x + diag, y + diag),
            (x - diag, y + diag),
            (x + diag, y - diag),
            (x - diag, y - diag),
        )
        for check_x, check_y in check_points:
            if not self._terrain_probe_walkable(check_x, check_y):
                return False
        return True

    def _terrain_probe_walkable(self, check_x: float, check_y: float) -> bool:
        key = (check_x, check_y)
        cached = self._terrain_probe_cache.get(key)
        if cached is not None:
            return cached
        grid_pos = self.game_map.world_to_grid(check_x, check_y)
        if grid_pos is None:
            self._terrain_probe_cache[key] = False
            return False
        col, row = grid_pos
        walkable = (
            0 <= row < self.game_map.height
            and 0 <= col < self.game_map.width
            and self.game_map.grid[row][col] not in {"water", "lava"}
        )
        self._terrain_probe_cache[key] = walkable
        return walkable


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
        self._astar_budget_frame = None
        self._astar_frame_spent_ms = 0.0
        self._path_budget_frame = None
        self._path_frame_spent_ms = 0.0

    def mark_dirty(self):
        self.grid.mark_dirty()
        self._path_cache.clear()

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
        if self._remaining_path_frame_budget() <= 0:
            return self._failed(mode, "too_expensive", target=target)
        started = time.perf_counter()
        request_budget_ms = min(PATHFINDING_MAX_REQUEST_MS, self._remaining_path_frame_budget())
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
        return self._apply_result(unit, result, "move", None)

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
        cache_key = (self.grid.revision, start_cell, goal_cell, round(unit_radius, 2), mode, id(target))
        cached = self._path_cache.get(cache_key)
        if cached and cached.ok and self.grid.segment_clear(start, cached.waypoints[0], unit_radius):
            self.cache_hits += 1
            perf_stats.increment("path_cache_hits")
            self._path_cache.move_to_end(cache_key)
            return NavigationResult("ok", cached.waypoints[:], cached.final_point, mode=mode, target=target, revision=self.grid.revision)

        self.cache_misses += 1
        perf_stats.increment("path_cache_misses")
        if self.grid.segment_clear(start, final_point, unit_radius):
            waypoints = [final_point]
            result = NavigationResult("ok", waypoints, final_point, mode=mode, target=target, revision=self.grid.revision)
            self._cache_result(cache_key, result)
            return result

        cells = self._astar(start_cell, goal_cell, unit_radius)
        if cells == "too_expensive":
            return self._failed(mode, "too_expensive", target=target)
        if not cells:
            return self._failed(mode, "no_path", target=target)

        raw_points = [self.grid.cell_to_world(cell) for cell in cells[1:]]
        if not raw_points or math.hypot(raw_points[-1][0] - final_point[0], raw_points[-1][1] - final_point[1]) > 1:
            raw_points.append(final_point)
        waypoints = self._smooth_path(start, raw_points, unit_radius)
        result = NavigationResult("ok", waypoints, final_point, mode=mode, target=target, revision=self.grid.revision)
        self._cache_result(cache_key, result)
        return result

    def _astar(self, start: Cell, goal: Cell, unit_radius: float):
        self.astar_calls += 1
        perf_stats.increment("astar_calls")
        remaining_budget_ms = self._remaining_astar_frame_budget()
        if remaining_budget_ms <= 0:
            self.astar_capped += 1
            perf_stats.increment("astar_capped")
            return "too_expensive"
        request_budget_ms = min(PATHFINDING_MAX_REQUEST_MS, remaining_budget_ms)
        started = time.perf_counter()
        deadline = started + (request_budget_ms / 1000.0)
        open_heap = []
        counter = 0
        g_score: Dict[Cell, float] = {start: 0.0}
        parent: Dict[Cell, Cell] = {}
        heapq.heappush(open_heap, (self._heuristic(start, goal), counter, start))
        closed = set()

        try:
            while open_heap:
                _, _, current = heapq.heappop(open_heap)
                if current in closed:
                    continue
                if len(closed) >= PATHFINDING_MAX_EXPANSIONS:
                    self.astar_capped += 1
                    perf_stats.increment("astar_capped")
                    self.astar_expanded_cells += len(closed)
                    perf_stats.increment("astar_expanded_cells", len(closed))
                    return "too_expensive"
                if len(closed) and len(closed) % 256 == 0 and time.perf_counter() >= deadline:
                    self.astar_capped += 1
                    perf_stats.increment("astar_capped")
                    self.astar_expanded_cells += len(closed)
                    perf_stats.increment("astar_expanded_cells", len(closed))
                    return "too_expensive"
                if current == goal:
                    self.astar_expanded_cells += len(closed)
                    perf_stats.increment("astar_expanded_cells", len(closed))
                    return self._reconstruct_cells(current, parent)
                closed.add(current)

                for neighbor, move_cost in self._neighbors(current, unit_radius):
                    if neighbor in closed:
                        continue
                    tentative = g_score[current] + move_cost
                    if tentative >= g_score.get(neighbor, float("inf")):
                        continue
                    parent[neighbor] = current
                    g_score[neighbor] = tentative
                    counter += 1
                    priority = tentative + self._heuristic(neighbor, goal)
                    heapq.heappush(open_heap, (priority, counter, neighbor))
            self.astar_expanded_cells += len(closed)
            perf_stats.increment("astar_expanded_cells", len(closed))
            return None
        finally:
            self._add_astar_frame_spent((time.perf_counter() - started) * 1000.0)

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
            self._path_cache.popitem(last=False)
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
        return candidates

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
