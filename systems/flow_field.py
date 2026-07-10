"""Flow fields for group move orders (MASTER_PLAN Phase 5, A7).

One Dijkstra integration field per group destination serves every unit in the
group, replacing N independent A* searches. Fields are built incrementally
across frames inside the pathfinding budget (never freeze the frame), cached
by (goal cell, radius), and invalidated whenever the nav grid changes.
"""
from __future__ import annotations

import heapq
import math
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from utils.perf_stats import perf_stats

Cell = Tuple[int, int]
Point = Tuple[float, float]

FIELD_CACHE_MAX = 8
BUILD_CELL_CAP = 40000        # absolute safety cap per field
BUILD_MS_PER_FRAME = 8.0      # time slice per frame for field construction
HANDOFF_DISTANCE = 90.0       # switch from field-following to personal slot path


class FlowField:
    """Direction-per-cell field flowing toward one goal."""

    __slots__ = ("goal_cell", "goal_point", "unit_radius", "revision", "directions")

    def __init__(self, goal_cell: Cell, goal_point: Point, unit_radius: float, revision: int):
        self.goal_cell = goal_cell
        self.goal_point = goal_point
        self.unit_radius = unit_radius
        self.revision = revision
        self.directions: Dict[Cell, Tuple[float, float]] = {}

    def direction_at(self, cell: Cell) -> Optional[Tuple[float, float]]:
        return self.directions.get(cell)


class _BuildJob:
    """Resumable Dijkstra expansion from the goal outward."""

    def __init__(self, manager, field: FlowField, needed_cells, waiters):
        self.manager = manager
        self.field = field
        self.needed = set(needed_cells)
        self.waiters = list(waiters)  # (unit, slot_target)
        grid = manager.grid
        goal = field.goal_cell
        self.dist: Dict[Cell, float] = {goal: 0.0}
        self.heap: List[Tuple[float, int, Cell]] = [(0.0, 0, goal)]
        self.counter = 0
        self.settled = set()

    def step(self, deadline) -> bool:
        """Expand until deadline or completion. Returns True when finished."""
        import time

        grid = self.manager.grid
        walkable_view = grid.walkable_view(self.field.unit_radius)
        cell_walkable = grid.cell_walkable
        radius = self.field.unit_radius
        cell_size = grid.cell_size
        diag_cost = math.sqrt(2) * cell_size
        directions = self.field.directions
        dist = self.dist
        heap = self.heap
        settled = self.settled

        def walkable(cell):
            cached = walkable_view.get(cell)
            if cached is None:
                cached = cell[0] >= 0 and cell[1] >= 0 and cell_walkable(cell, radius)
            return cached

        processed = 0
        while heap:
            processed += 1
            if processed % 256 == 0 and time.perf_counter() >= deadline:
                return False
            if len(settled) >= BUILD_CELL_CAP:
                break
            d, _, cell = heapq.heappop(heap)
            if cell in settled:
                continue
            settled.add(cell)
            self.needed.discard(cell)
            if not self.needed:
                break
            x, y = cell
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbor = (x + dx, y + dy)
                    if neighbor in settled or not walkable(neighbor):
                        continue
                    if dx != 0 and dy != 0:
                        # no corner cutting
                        if not walkable((x + dx, y)) or not walkable((x, y + dy)):
                            continue
                        cost = diag_cost
                    else:
                        cost = cell_size
                    tentative = d + cost
                    if tentative < dist.get(neighbor, float("inf")):
                        dist[neighbor] = tentative
                        # flow direction: from neighbor toward this (closer) cell
                        norm = math.hypot(-dx, -dy)
                        directions[neighbor] = (-dx / norm, -dy / norm)
                        self.counter += 1
                        heapq.heappush(heap, (tentative, self.counter, neighbor))
        return True


class FlowFieldManager:
    """Cache + incremental builder for flow fields."""

    def __init__(self, grid):
        self.grid = grid
        self.revision = 0
        self._fields: OrderedDict[Tuple[Cell, float], FlowField] = OrderedDict()
        self._jobs: List[_BuildJob] = []

    # -- invalidation ----------------------------------------------------
    def invalidate(self):
        """Nav grid changed: drop cached fields; in-flight jobs keep building
        against the fresh walkable views (their revision already matches)."""
        self.revision += 1
        self._fields.clear()
        for job in self._jobs:
            job.field.revision = self.revision  # keep followers attached

    # -- public API --------------------------------------------------------
    def request_group_field(self, goal_point: Point, units_with_slots) -> bool:
        """Queue (or reuse) a field toward goal_point for [(unit, slot)] pairs.

        Returns False if no walkable goal cell exists (caller falls back to
        per-unit paths)."""
        if not units_with_slots:
            return False
        unit_radius = max(getattr(u, "radius", 8) for u, _ in units_with_slots)
        goal_cell = self.grid.nearest_walkable_cell(goal_point, unit_radius)
        if goal_cell is None:
            return False

        key = (goal_cell, unit_radius)
        field = self._fields.get(key)
        if field is not None and field.revision == self.revision:
            self._fields.move_to_end(key)
            self._attach(field, units_with_slots)
            return True

        field = FlowField(goal_cell, goal_point, unit_radius, self.revision)
        self._fields[key] = field
        while len(self._fields) > FIELD_CACHE_MAX:
            self._fields.popitem(last=False)

        needed = {self.grid.world_to_cell((u.x, u.y)) for u, _ in units_with_slots}
        job = _BuildJob(self, field, needed, units_with_slots)
        self._jobs.append(job)
        perf_stats.increment("flow_fields_built")
        # Waiters idle in place until the job finishes (a few frames at most).
        for unit, slot in units_with_slots:
            unit.flow_field = None
            unit.flow_slot_target = slot
            unit.status = "idle"
        return True

    def process(self, budget_ms: float = BUILD_MS_PER_FRAME):
        """Advance the oldest build job within the frame's time slice."""
        if not self._jobs:
            return
        import time

        deadline = time.perf_counter() + budget_ms / 1000.0
        job = self._jobs[0]
        if job.step(deadline):
            self._jobs.pop(0)
            perf_stats.increment("flow_field_cells", len(job.settled))
            self._attach(job.field, job.waiters)

    def _attach(self, field: FlowField, units_with_slots):
        for unit, slot in units_with_slots:
            if getattr(unit, "hp", 1) <= 0 or not getattr(unit, "in_world", True):
                continue
            unit.flow_field = field
            unit.flow_slot_target = slot
            unit.last_task = {"type": "move", "target": slot}
            unit.status = "run"
