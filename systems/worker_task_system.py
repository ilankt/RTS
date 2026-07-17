"""Reliable worker task state machine.

Workers used to split gathering, drop-off, building, movement, and recovery
decisions across several systems.  This module owns the worker task lifecycle
and lets MovementSystem only move along the currently assigned path.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Dict, Iterable, Optional, Tuple

from core.config import DROP_OFF_BUILDINGS
from utils.debug_logger import debug_log


Point = Tuple[float, float]

IDLE = "IDLE"
MOVING_TO_RESOURCE = "MOVING_TO_RESOURCE"
GATHERING = "GATHERING"
MOVING_TO_DROPOFF = "MOVING_TO_DROPOFF"
DROPPING_OFF = "DROPPING_OFF"
RETURNING_TO_RESOURCE = "RETURNING_TO_RESOURCE"
MOVING_TO_BUILD = "MOVING_TO_BUILD"
BUILDING = "BUILDING"
FAILED = "FAILED"

MOVING_PHASES = {
    MOVING_TO_RESOURCE,
    MOVING_TO_DROPOFF,
    RETURNING_TO_RESOURCE,
    MOVING_TO_BUILD,
}

ARRIVAL_RADIUS = 10.0
CONTACT_HOLD_EXTRA = 24.0
OUT_OF_RANGE_GRACE = 0.35
REPATH_COOLDOWN = 0.75
NO_PROGRESS_REROLL_TIME = 3.0
NO_PROGRESS_TIMEOUT = 5.0
FAILED_PATH_COOLDOWN = 2.0
SLOT_COUNT = 24
SLOT_EXTRA_RINGS = (0.0, 8.0, 16.0, 24.0, 40.0)
# §8.11 stuck-worker fix: the stationary phases (DROPPING_OFF / BUILDING)
# had NO timeout — a wedged worker there was invisible to both the AI
# idle-scan (task not FAILED) and the watchdog (is_dropping_off/is_building
# flags skip it). These caps make every wedge self-heal into FAILED, which
# the AI reassigns and the human sees on the idle badge.
DROPOFF_STALL_TIMEOUT = 6.0   # legit drop-off wait is DROP_OFF_DELAY (0.5s)
BUILD_STALL_TIMEOUT = 8.0     # construction progress frozen this long = wedged


@dataclass
class WorkerTask:
    """Runtime-only task state for one worker."""

    kind: str
    phase: str
    worker: object
    resource: object = None
    dropoff: object = None
    construction_site: object = None
    contact_point: Optional[Point] = None
    resource_contact_point: Optional[Point] = None
    dropoff_contact_point: Optional[Point] = None
    build_contact_point: Optional[Point] = None
    last_progress_pos: Optional[Point] = None
    last_progress_time: float = 0.0
    last_distance: float = float("inf")
    repath_cooldown: float = 0.0
    failure_reason: Optional[str] = None
    elapsed: float = 0.0
    no_progress_time: float = 0.0
    out_of_range_time: float = 0.0
    repath_attempts: int = 0
    blocked_contact_points: list = None
    stall_time: float = 0.0            # §8.11: stationary-phase wedge timer
    last_build_progress: float = -1.0  # §8.11: detects frozen construction


class WorkerTaskSystem:
    """Owns worker gather/drop-off/build phases and contact-slot reservations."""

    def __init__(self, game):
        self.game = game
        self.tasks: Dict[object, WorkerTask] = {}
        self._slots: Dict[Tuple[int, str], Dict[object, Point]] = {}
        self._failed_path_until: Dict[Tuple[int, int, str], float] = {}

    # ------------------------------------------------------------------
    # Public command API
    # ------------------------------------------------------------------
    def assign_gather(self, worker, resource) -> bool:
        if not self._valid_worker(worker) or not self._valid_resource(resource):
            return self._fail_new_task(worker, "invalid_resource")

        self.cancel(worker)
        task = WorkerTask(kind="gather", phase=MOVING_TO_RESOURCE, worker=worker, resource=resource)
        self.tasks[worker] = task

        resource_slot = self._reserve_slot(worker, resource, "gather")
        if not resource_slot:
            # §8.11: remember the slot failure so the AI doesn't re-pick this
            # same crowded node next tick (FAILED→reassign→FAILED thrash)
            self._remember_path_failure(worker, resource, "gather")
            return self._set_failed(task, "no_resource_slot")
        task.resource_contact_point = resource_slot

        if getattr(worker, "resource_amount", 0) > 0:
            dropoff = self._find_dropoff(worker)
            if not dropoff:
                return self._set_failed(task, "no_dropoff")
            task.phase = MOVING_TO_DROPOFF
            task.dropoff = dropoff
            worker.previous_gathering_target = resource
            return self._begin_path_to_dropoff(task)

        return self._begin_path_to_resource(task, MOVING_TO_RESOURCE)

    def assign_dropoff(self, worker, building=None) -> bool:
        if not self._valid_worker(worker) or getattr(worker, "resource_amount", 0) <= 0:
            return self._fail_new_task(worker, "nothing_to_dropoff")

        return_resource = getattr(worker, "gathering_target", None) or getattr(worker, "previous_gathering_target", None)
        if return_resource is not None and not self._valid_resource(return_resource):
            return_resource = None

        self.cancel(worker)
        task = WorkerTask(
            kind="gather" if return_resource is not None else "dropoff",
            phase=MOVING_TO_DROPOFF,
            worker=worker,
            resource=return_resource,
            dropoff=building or self._find_dropoff(worker),
        )
        self.tasks[worker] = task

        if task.resource is not None:
            task.resource_contact_point = self._reserve_slot(worker, task.resource, "gather")
        if not task.dropoff:
            return self._set_failed(task, "no_dropoff")
        return self._begin_path_to_dropoff(task)

    def assign_build(self, worker, site) -> bool:
        if not self._valid_worker(worker) or not self._valid_site(site):
            return self._fail_new_task(worker, "invalid_construction_site")

        self.cancel(worker)
        task = WorkerTask(kind="build", phase=MOVING_TO_BUILD, worker=worker, construction_site=site)
        self.tasks[worker] = task
        site.builder = worker

        build_slot = self._reserve_slot(worker, site, "build")
        if not build_slot:
            return self._set_failed(task, "no_build_slot")
        task.build_contact_point = build_slot
        return self._begin_path_to_build(task)

    def assign_move(self, worker, world_pos: Point) -> bool:
        self.cancel(worker)
        return self.game.pathfinder.issue_move(worker, world_pos)

    def cancel(self, worker) -> None:
        task = self.tasks.pop(worker, None)
        if task:
            self._release_worker_slots(worker)
        self._clear_motion(worker)
        self._clear_worker_task_fields(worker)

    def complete_build(self, worker, site=None) -> None:
        task = self.tasks.get(worker)
        if task and task.kind == "build" and (site is None or task.construction_site == site):
            self._release_worker_slots(worker)
            self.tasks.pop(worker, None)

    def owns(self, worker) -> bool:
        task = self.tasks.get(worker)
        return bool(task and task.phase not in (IDLE, FAILED))

    def active_task(self, worker) -> Optional[WorkerTask]:
        return self.tasks.get(worker)

    def request_repath(self, worker) -> bool:
        task = self.tasks.get(worker)
        if not task or task.phase not in MOVING_PHASES:
            return False
        task.repath_cooldown = 0.0
        return self._repath_current_phase(task)

    # ------------------------------------------------------------------
    # Game loop hooks
    # ------------------------------------------------------------------
    # §8.12 worker flee: how recent a hit must be to trigger flight, and how
    # long a fleeing worker ignores further triggers (frames).
    FLEE_TRIGGER_FRAMES = 45
    FLEE_COOLDOWN_FRAMES = 300

    def _flee_from_attackers(self) -> None:
        """§8.12: AI workers under attack run to their base instead of
        gathering while being murdered (raids get counterplay). Human
        workers stay under player control."""
        frame = getattr(self.game, "frame_counter", 0)
        for worker in self.game.units:
            if worker.name != "worker" or worker.hp <= 0:
                continue
            if getattr(worker, "_last_damage_frame", -1) < frame - self.FLEE_TRIGGER_FRAMES:
                continue
            if getattr(worker.player, "human", False):
                continue
            if getattr(worker, "_fleeing_until", 0) > frame:
                continue
            attacker = getattr(worker, "last_attacker", None)
            if attacker is None or getattr(attacker, "hp", 0) <= 0:
                continue
            worker._fleeing_until = frame + self.FLEE_COOLDOWN_FRAMES
            # §8.9: shelter INSIDE the castle/tower when there's room —
            # actual safety instead of loitering next to the walls
            from systems import garrison

            shelter = None
            best_sq = 600.0 ** 2
            for building in self.game.buildings:
                if building.player is not worker.player:
                    continue
                if not garrison.can_accept(building, worker):
                    continue
                d_sq = (building.x - worker.x) ** 2 + (building.y - worker.y) ** 2
                if d_sq < best_sq:
                    shelter, best_sq = building, d_sq
            if shelter is not None:
                self.cancel(worker)
                worker.garrison_target = shelter
                self.game.pathfinder.issue_move(worker, (shelter.x, shelter.y))
            else:
                self.assign_move(worker, self._find_refuge(worker, attacker))

    def _find_refuge(self, worker, attacker):
        """Nearest own building (castle preferred), else straight away."""
        own = [b for b in self.game.buildings
               if b.player is worker.player and b.hp > 0]
        if own:
            castles = [b for b in own if b.name == "castle"]
            anchor = castles[0] if castles else min(
                own, key=lambda b: (b.x - worker.x) ** 2 + (b.y - worker.y) ** 2)
            return (anchor.x + 60, anchor.y + 60)
        dx, dy = worker.x - attacker.x, worker.y - attacker.y
        norm = max(1.0, (dx * dx + dy * dy) ** 0.5)
        return (worker.x + dx / norm * 250, worker.y + dy / norm * 250)

    def update_pre_movement(self, delta_time: float) -> None:
        self._flee_from_attackers()
        self._remove_dead_worker_tasks()
        for task in list(self.tasks.values()):
            if task.phase == FAILED:
                continue
            task.elapsed += delta_time
            task.repath_cooldown = max(0.0, task.repath_cooldown - delta_time)
            self._sync_fields(task)

            if task.phase in MOVING_PHASES:
                if not self._current_target_valid(task):
                    # §8.13.1 sibling path: a gather node that vanished while
                    # we walked to it continues onto a nearby node, exactly
                    # like depletion at the node itself. Everything else
                    # (razed dropoff/site) still fails for reassignment.
                    if (task.kind == "gather"
                            and task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE)
                            and task.resource is not None):
                        self._continue_or_complete(task)
                    else:
                        self._set_failed(task, "target_invalid")
                    continue
                if self._at_current_contact(task, arrival=True):
                    continue
                if not task.worker.path and not task.worker.destination and task.repath_cooldown <= 0:
                    self._repath_current_phase(task)

    def update_post_movement(self, delta_time: float) -> None:
        for task in list(self.tasks.values()):
            if task.phase == FAILED:
                continue
            if task.phase in MOVING_PHASES:
                self._update_movement_progress(task, delta_time)
                if self._at_current_contact(task, arrival=True):
                    self._arrive_current_phase(task)
                elif task.no_progress_time >= NO_PROGRESS_TIMEOUT:
                    self._set_failed(task, "movement_no_progress")
                elif task.no_progress_time >= NO_PROGRESS_REROLL_TIME and task.repath_cooldown <= 0:
                    if not self._reroll_current_phase(task):
                        self._set_failed(task, "movement_no_progress")
            elif task.phase == GATHERING:
                self._update_gathering(task, delta_time)
            elif task.phase == DROPPING_OFF:
                self._update_dropoff(task, delta_time)
            elif task.phase == BUILDING:
                self._update_building(task, delta_time)

    # ------------------------------------------------------------------
    # Phase transitions
    # ------------------------------------------------------------------
    def _begin_path_to_resource(self, task: WorkerTask, phase: str) -> bool:
        task.phase = phase
        task.contact_point = task.resource_contact_point
        task.dropoff = None
        if self._recent_path_failure(task.worker, task.resource, "gather"):
            # Backoff instead of retrying every frame (§8.11 churn fix)
            task.repath_cooldown = max(task.repath_cooldown, REPATH_COOLDOWN)
            return False
        if not task.contact_point:
            task.contact_point = self._reserve_slot(task.worker, task.resource, "gather", self._blocked_points(task))
            task.resource_contact_point = task.contact_point
        if not task.contact_point:
            self._remember_path_failure(task.worker, task.resource, "gather")
            return self._set_failed(task, "no_resource_slot")
        return self._path_to_contact(task, task.resource, "gather", task.contact_point)

    def _begin_path_to_dropoff(self, task: WorkerTask) -> bool:
        task.phase = MOVING_TO_DROPOFF
        task.dropoff = task.dropoff or self._find_dropoff(task.worker)
        if not task.dropoff:
            return self._set_failed(task, "no_dropoff")
        if self._recent_path_failure(task.worker, task.dropoff, "dropoff"):
            task.repath_cooldown = max(task.repath_cooldown, REPATH_COOLDOWN)
            return False
        task.dropoff_contact_point = self._reserve_slot(task.worker, task.dropoff, "dropoff", self._blocked_points(task))
        if not task.dropoff_contact_point:
            return self._set_failed(task, "no_dropoff_slot")
        task.contact_point = task.dropoff_contact_point
        return self._path_to_contact(task, task.dropoff, "dropoff", task.contact_point)

    def _begin_path_to_build(self, task: WorkerTask) -> bool:
        task.phase = MOVING_TO_BUILD
        task.contact_point = task.build_contact_point
        if self._recent_path_failure(task.worker, task.construction_site, "build"):
            task.repath_cooldown = max(task.repath_cooldown, REPATH_COOLDOWN)
            return False
        if not task.contact_point:
            task.contact_point = self._reserve_slot(task.worker, task.construction_site, "build", self._blocked_points(task))
            task.build_contact_point = task.contact_point
        if not task.contact_point:
            return self._set_failed(task, "no_build_slot")
        return self._path_to_contact(task, task.construction_site, "build", task.contact_point)

    def _arrive_current_phase(self, task: WorkerTask) -> None:
        self._clear_motion(task.worker)
        task.no_progress_time = 0.0
        task.out_of_range_time = 0.0

        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE):
            task.phase = GATHERING
            task.worker.gathering_position = task.resource_contact_point
            task.worker.is_gathering = True
            task.worker.gathering_target = task.resource
            task.worker.is_engaging = False
            task.worker.status = "gather"
        elif task.phase == MOVING_TO_DROPOFF:
            task.phase = DROPPING_OFF
            task.worker.drop_off_target = task.dropoff
            task.worker.is_dropping_off = True
            task.worker.drop_off_timer = 0.0
            task.worker.is_gathering = False
            task.worker.status = "idle"
        elif task.phase == MOVING_TO_BUILD:
            task.phase = BUILDING
            task.worker.building_target = task.construction_site
            task.worker.is_building = True
            task.worker.status = "build"
            task.construction_site.builder = task.worker

    def _update_gathering(self, task: WorkerTask, delta_time: float) -> None:
        worker = task.worker
        resource = task.resource
        if not self._valid_resource(resource):
            if getattr(worker, "resource_amount", 0) > 0:
                dropoff = self._find_dropoff(worker)
                if dropoff:
                    task.dropoff = dropoff
                    worker.is_gathering = False
                    self._begin_path_to_dropoff(task)
                    return
            self._continue_or_complete(task)
            return

        if not self._at_contact(task, resource, "gather", task.resource_contact_point, hold=True):
            task.out_of_range_time += delta_time
            if task.out_of_range_time >= OUT_OF_RANGE_GRACE:
                worker.is_gathering = False
                self._begin_path_to_resource(task, RETURNING_TO_RESOURCE)
            return
        task.out_of_range_time = 0.0

        result = self.game.gathering_manager.gather_resource_tick(worker, resource, delta_time)
        if result == "full":
            worker.is_gathering = False
            worker.previous_gathering_target = resource
            task.dropoff = self._find_dropoff(worker)
            self._begin_path_to_dropoff(task)
        elif result == "depleted":
            self._continue_or_complete(task)

    def _update_dropoff(self, task: WorkerTask, delta_time: float) -> None:
        worker = task.worker
        building = task.dropoff
        if not self._valid_dropoff(worker, building):
            task.dropoff = self._find_dropoff(worker)
            if not task.dropoff:
                self._set_failed(task, "dropoff_invalid")
                return
            self._begin_path_to_dropoff(task)
            return

        if not self._at_contact(task, building, "dropoff", task.dropoff_contact_point, hold=True):
            task.out_of_range_time += delta_time
            if task.out_of_range_time >= OUT_OF_RANGE_GRACE:
                worker.is_dropping_off = False
                self._begin_path_to_dropoff(task)
            return
        task.out_of_range_time = 0.0

        if self.game.gathering_manager.drop_off_resources(worker, building, delta_time):
            task.stall_time = 0.0
            self._release_slot(worker, building, "dropoff")
            task.dropoff_contact_point = None
            task.dropoff = None
            if task.kind == "gather" and self._valid_resource(task.resource):
                worker.previous_gathering_target = None
                self._begin_path_to_resource(task, RETURNING_TO_RESOURCE)
            else:
                # Original node died while we hauled — continue on a neighbor
                self._continue_or_complete(task)
        else:
            # §8.11: a drop-off that never completes (cargo/building desync)
            # used to freeze the worker forever — fail it so recovery runs.
            task.stall_time += delta_time
            if task.stall_time >= DROPOFF_STALL_TIMEOUT:
                self._set_failed(task, "dropoff_stalled")

    def _update_building(self, task: WorkerTask, delta_time: float) -> None:
        site = task.construction_site
        if not self._valid_site(site):
            self._complete_task(task)
            return
        if not self._at_contact(task, site, "build", task.build_contact_point, hold=True):
            task.out_of_range_time += delta_time
            if task.out_of_range_time >= OUT_OF_RANGE_GRACE:
                task.worker.is_building = False
                self._begin_path_to_build(task)
            return
        task.out_of_range_time = 0.0
        task.worker.is_building = True
        task.worker.status = "build"
        site.builder = task.worker
        # §8.11: frozen construction progress = wedged build; self-heal it.
        # No progress attribute (minimal test doubles) -> no signal to judge.
        progress = getattr(site, "construction_progress", None)
        if progress is None or progress != task.last_build_progress:
            task.last_build_progress = progress if progress is not None else -1.0
            task.stall_time = 0.0
        else:
            task.stall_time += delta_time
            if task.stall_time >= BUILD_STALL_TIMEOUT:
                self._set_failed(task, "build_stalled")

    # ------------------------------------------------------------------
    # Navigation and slots
    # ------------------------------------------------------------------
    def _path_to_contact(self, task: WorkerTask, target, mode: str, contact: Point) -> bool:
        worker = task.worker
        self._sync_fields(task)
        if self._point_distance((worker.x, worker.y), contact) <= ARRIVAL_RADIUS:
            self._clear_motion(worker)
            return True

        result = self.game.pathfinder.find_result((worker.x, worker.y), contact, worker.radius, worker, mode="move")
        if not result.ok:
            if result.failure_reason == "too_expensive":
                # Out of frame budget, not unreachable: keep the task alive and
                # let the cooldown retry (jittered so a cache event doesn't
                # align every worker onto the same frame).
                task.contact_point = contact
                task.repath_cooldown = 0.3 + self._worker_jitter(worker)
                return True
            self._remember_path_failure(worker, target, mode)
            return False

        worker.path = result.waypoints[:]
        worker.path_index = 0
        worker.path_target = contact
        worker.destination = result.waypoints[0]
        worker.status = "run"
        worker.last_task = {"type": task.kind, "target": target}
        worker.path_target_object = target
        worker.path_target_object_pos = (target.x, target.y)
        worker.path_target_mode = mode
        task.contact_point = contact
        if task.last_progress_pos is None:
            task.last_progress_pos = (worker.x, worker.y)
            task.last_progress_time = task.elapsed
            task.no_progress_time = 0.0
        task.last_distance = self._point_distance((worker.x, worker.y), contact)
        task.repath_cooldown = REPATH_COOLDOWN + self._worker_jitter(worker)
        task.repath_attempts += 1
        return True

    def _worker_jitter(self, worker) -> float:
        """Deterministic per-worker cooldown jitter (0-0.35s)."""
        return (id(worker) % 8) * 0.05

    def _repath_current_phase(self, task: WorkerTask) -> bool:
        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE):
            return self._begin_path_to_resource(task, task.phase)
        if task.phase == MOVING_TO_DROPOFF:
            return self._begin_path_to_dropoff(task)
        if task.phase == MOVING_TO_BUILD:
            return self._begin_path_to_build(task)
        return False

    def _reroll_current_phase(self, task: WorkerTask) -> bool:
        old_point = task.contact_point
        if old_point:
            if task.blocked_contact_points is None:
                task.blocked_contact_points = []
            task.blocked_contact_points.append(old_point)

        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE):
            self._release_slot(task.worker, task.resource, "gather")
            task.resource_contact_point = None
        elif task.phase == MOVING_TO_DROPOFF:
            self._release_slot(task.worker, task.dropoff, "dropoff")
            task.dropoff_contact_point = None
        elif task.phase == MOVING_TO_BUILD:
            self._release_slot(task.worker, task.construction_site, "build")
            task.build_contact_point = None

        task.contact_point = None
        return self._repath_current_phase(task)

    def _reserve_slot(self, worker, target, mode: str, avoid_points: Iterable[Point] = ()) -> Optional[Point]:
        if target is None:
            return None
        key = self._slot_key(target, mode)
        slots = self._slots.setdefault(key, {})
        if worker in slots:
            return slots[worker]

        distance = self.game.pathfinder.get_interaction_distance(worker, target, mode)
        base_angle = math.atan2(worker.y - target.y, worker.x - target.x)
        for extra_radius in SLOT_EXTRA_RINGS:
            for angle in self._candidate_angles(base_angle):
                point = (
                    target.x + math.cos(angle) * (distance + extra_radius),
                    target.y + math.sin(angle) * (distance + extra_radius),
                )
                if self._slot_occupied(list(slots.values()) + list(avoid_points), point, worker):
                    continue
                if not self.game.pathfinder.is_position_walkable(point, worker.radius):
                    continue
                slots[worker] = point
                return point
        return None

    def _blocked_points(self, task: WorkerTask) -> Iterable[Point]:
        return task.blocked_contact_points or ()

    def _candidate_angles(self, base_angle: float) -> Iterable[float]:
        yield base_angle
        for step in range(1, SLOT_COUNT // 2 + 1):
            delta = step * (2 * math.pi / SLOT_COUNT)
            yield base_angle + delta
            yield base_angle - delta

    def _slot_occupied(self, reserved_points: Iterable[Point], point: Point, worker) -> bool:
        min_dist = max(getattr(worker, "radius", 8) * 2 + 6, 22)
        return any(self._point_distance(point, other) < min_dist for other in reserved_points)

    def _can_reach_point(self, worker, point: Point) -> bool:
        if self._point_distance((worker.x, worker.y), point) <= ARRIVAL_RADIUS:
            return True
        result = self.game.pathfinder.find_result((worker.x, worker.y), point, worker.radius, worker, mode="move")
        return result.ok

    def _release_worker_slots(self, worker) -> None:
        for key in list(self._slots.keys()):
            self._slots[key].pop(worker, None)
            if not self._slots[key]:
                del self._slots[key]

    def _release_slot(self, worker, target, mode: str) -> None:
        key = self._slot_key(target, mode)
        slots = self._slots.get(key)
        if not slots:
            return
        slots.pop(worker, None)
        if not slots:
            del self._slots[key]

    def _slot_key(self, target, mode: str) -> Tuple[int, str]:
        return (id(target), mode)

    def _path_failure_key(self, worker, target, mode: str) -> Tuple[int, int, str]:
        return (id(worker), id(target), mode)

    def recently_failed(self, worker, target, mode: str = "gather") -> bool:
        """Public: did this worker recently fail to reach/slot this target?
        The AI's resource picker consults it to break the FAILED→re-pick-the-
        same-node→FAILED loop (§8.11)."""
        return self._recent_path_failure(worker, target, mode)

    def _recent_path_failure(self, worker, target, mode: str) -> bool:
        if target is None:
            return False
        until = self._failed_path_until.get(self._path_failure_key(worker, target, mode), 0)
        return until > time.monotonic()

    def _remember_path_failure(self, worker, target, mode: str) -> None:
        if target is None:
            return
        self._failed_path_until[self._path_failure_key(worker, target, mode)] = time.monotonic() + FAILED_PATH_COOLDOWN

    # ------------------------------------------------------------------
    # Validation, progress, and compatibility fields
    # ------------------------------------------------------------------
    def _update_movement_progress(self, task: WorkerTask, delta_time: float) -> None:
        worker = task.worker
        if not task.contact_point:
            return
        current_pos = (worker.x, worker.y)
        distance = self._point_distance(current_pos, task.contact_point)
        moved = task.last_progress_pos is None or self._point_distance(current_pos, task.last_progress_pos) > 2.0
        if moved:
            task.last_progress_pos = current_pos
            task.last_distance = distance
            task.last_progress_time = task.elapsed
            task.no_progress_time = 0.0
        else:
            task.no_progress_time += delta_time

    def _at_current_contact(self, task: WorkerTask, arrival: bool = False) -> bool:
        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE):
            return self._at_contact(task, task.resource, "gather", task.resource_contact_point, hold=not arrival)
        if task.phase == MOVING_TO_DROPOFF:
            return self._at_contact(task, task.dropoff, "dropoff", task.dropoff_contact_point, hold=not arrival)
        if task.phase == MOVING_TO_BUILD:
            return self._at_contact(task, task.construction_site, "build", task.build_contact_point, hold=not arrival)
        return False

    def _at_contact(self, task: WorkerTask, target, mode: str, contact: Optional[Point], hold: bool) -> bool:
        worker = task.worker
        if target is None:
            return False
        point_radius = ARRIVAL_RADIUS if not hold else CONTACT_HOLD_EXTRA
        if contact and self._point_distance((worker.x, worker.y), contact) <= point_radius:
            return True
        required = self.game.pathfinder.get_interaction_distance(worker, target, mode)
        tolerance = 8.0 if not hold else CONTACT_HOLD_EXTRA
        return math.hypot(worker.x - target.x, worker.y - target.y) <= required + tolerance

    def _current_target_valid(self, task: WorkerTask) -> bool:
        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE):
            return self._valid_resource(task.resource)
        if task.phase == MOVING_TO_DROPOFF:
            return self._valid_dropoff(task.worker, task.dropoff)
        if task.phase == MOVING_TO_BUILD:
            return self._valid_site(task.construction_site)
        return True

    def _valid_worker(self, worker) -> bool:
        return worker is not None and getattr(worker, "name", None) == "worker" and getattr(worker, "hp", 1) > 0

    def _valid_resource(self, resource) -> bool:
        return (
            resource is not None
            and getattr(resource, "in_world", True)
            and getattr(resource, "amount_remaining", 0) > 0
        )

    def _valid_site(self, site) -> bool:
        return site is not None and getattr(site, "in_world", True) and getattr(site, "hp", 1) > 0

    def _valid_dropoff(self, worker, building) -> bool:
        if building is None or not getattr(building, "in_world", True) or getattr(building, "hp", 1) <= 0:
            return False
        valid_names = DROP_OFF_BUILDINGS.get(getattr(worker, "resource_type", None), [])
        return building.player == worker.player and building.name in valid_names

    def _find_dropoff(self, worker):
        valid_names = DROP_OFF_BUILDINGS.get(getattr(worker, "resource_type", None), [])
        best = None
        best_dist = float("inf")
        for building in self.game.buildings:
            if building.player != worker.player or building.name not in valid_names or getattr(building, "hp", 1) <= 0:
                continue
            dist = math.hypot(worker.x - building.x, worker.y - building.y)
            if dist < best_dist:
                best_dist = dist
                best = building
        return best

    def _sync_fields(self, task: WorkerTask) -> None:
        worker = task.worker
        if task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE, GATHERING):
            worker.gathering_target = task.resource
            worker.drop_off_target = None
            worker.is_dropping_off = False
            worker.building_target = None
            worker.is_building = False
            worker.current_target = None
            worker.in_combat = False
            worker.is_engaging = task.phase in (MOVING_TO_RESOURCE, RETURNING_TO_RESOURCE)
        elif task.phase in (MOVING_TO_DROPOFF, DROPPING_OFF):
            worker.drop_off_target = task.dropoff
            worker.previous_gathering_target = task.resource
            worker.gathering_target = None
            worker.is_gathering = False
            worker.building_target = None
            worker.is_building = False
            worker.current_target = None
            worker.in_combat = False
            worker.is_engaging = False
        elif task.phase in (MOVING_TO_BUILD, BUILDING):
            worker.building_target = task.construction_site
            worker.is_gathering = False
            worker.gathering_target = None
            worker.is_dropping_off = False
            worker.drop_off_target = None
            worker.current_target = None
            worker.in_combat = False
            worker.is_engaging = False
        if task.phase in MOVING_PHASES:
            worker.status = "run" if (worker.path or worker.destination) else worker.status
        worker.worker_task_phase = task.phase
        worker.worker_task_kind = task.kind

    def _clear_worker_task_fields(self, worker) -> None:
        if worker is None:
            return
        if getattr(worker, "gathering_target", None) is not None:
            resource = worker.gathering_target
            if hasattr(resource, "gatherers") and worker in resource.gatherers:
                resource.gatherers.remove(worker)
        worker.is_gathering = False
        worker.gathering_target = None
        worker.is_dropping_off = False
        worker.drop_off_timer = 0.0
        worker.drop_off_target = None
        worker.is_building = False
        worker.building_target = None
        worker.current_target = None
        worker.in_combat = False
        worker.is_engaging = False
        worker.has_los = False
        worker.is_fallback_movement = False
        for attr in (
            "worker_task_phase",
            "worker_task_kind",
            "worker_task_failed_reason",
            "gathering_position",
            "path_target_object",
            "path_target_object_pos",
            "path_target_mode",
        ):
            if hasattr(worker, attr):
                delattr(worker, attr)

    def _clear_motion(self, worker) -> None:
        worker.path = None
        worker.path_index = 0
        worker.path_target = None
        worker.destination = None
        for attr in ("path_target_object", "path_target_object_pos", "path_target_mode"):
            if hasattr(worker, attr):
                delattr(worker, attr)

    # §8.11: how far a worker looks for the next same-type node when its
    # current one runs dry ("move to a close tree nearby, don't idle").
    RESOURCE_CONTINUE_RADIUS = 400.0

    def _find_continuation_resource(self, depleted_resource, player=None):
        """Nearest live same-type node near the one that just ran dry.
        Prefers un-crowded nodes so continuation doesn't stack a node past
        the saturation cap. Rare event (a few per minute) — linear scan."""
        from core.config import WORKER_SATURATION_CAP

        name = depleted_resource.name
        cx, cy = depleted_resource.x, depleted_resource.y
        radius_sq = self.RESOURCE_CONTINUE_RADIUS ** 2
        fog = getattr(self.game, "fog_of_war", None)
        best = None
        best_key = None
        for res in self.game.resources:
            if res is depleted_resource or res.name != name:
                continue
            if not getattr(res, "in_world", True) or getattr(res, "amount_remaining", 0) <= 0:
                continue
            d_sq = (res.x - cx) ** 2 + (res.y - cy) ** 2
            if d_sq > radius_sq:
                continue
            # §8.11 fair perception: only continue onto nodes the worker's
            # player has actually revealed
            if fog is not None and player is not None and not fog.is_explored(player, res.x, res.y):
                continue
            crowded = len(getattr(res, "gatherers", ()) or ()) >= WORKER_SATURATION_CAP
            key = (crowded, d_sq)
            if best_key is None or key < best_key:
                best, best_key = res, key
        return best

    def _continue_or_complete(self, task: WorkerTask) -> None:
        """§8.11 worker continuation: when a gather task's node depletes,
        retarget to a nearby same-type node instead of idling — human and
        AI workers both. Falls back to idle when nothing is in range."""
        replacement = None
        if task.kind == "gather" and task.resource is not None:
            replacement = self._find_continuation_resource(
                task.resource, getattr(task.worker, "player", None))
        worker = task.worker
        self._complete_task(task)
        if replacement is not None:
            # assign_gather natively handles a carrying worker (dropoff first)
            self.assign_gather(worker, replacement)
        elif getattr(worker, "resource_amount", 0) > 0:
            # No continuation node in range but cargo aboard — deliver it
            # instead of idling with a full backpack (§8.13.1 sibling path:
            # node drained by someone else mid-carry, nothing nearby).
            self.assign_dropoff(worker)

    def _complete_task(self, task: WorkerTask) -> None:
        worker = task.worker
        self._release_worker_slots(worker)
        self.tasks.pop(worker, None)
        self._clear_motion(worker)
        self._clear_worker_task_fields(worker)
        worker.status = "idle"

    def _set_failed(self, task: WorkerTask, reason: str) -> bool:
        task.phase = FAILED
        task.failure_reason = reason
        worker = task.worker
        self._release_worker_slots(worker)
        if task.kind == "build" and task.construction_site and getattr(task.construction_site, "builder", None) is worker:
            task.construction_site.builder = None
        self._clear_motion(worker)
        self._clear_worker_task_fields(worker)
        worker.status = "idle"
        worker.worker_task_phase = FAILED
        worker.worker_task_kind = task.kind
        worker.worker_task_failed_reason = reason
        debug_log.log(f"Worker task failed: {task.kind} reason={reason}", "WORKER_TASK")
        return False

    def _fail_new_task(self, worker, reason: str) -> bool:
        if worker is None:
            return False
        self.cancel(worker)
        task = WorkerTask(kind="unknown", phase=FAILED, worker=worker, failure_reason=reason)
        self.tasks[worker] = task
        worker.worker_task_phase = FAILED
        worker.worker_task_failed_reason = reason
        return False

    def _remove_dead_worker_tasks(self) -> None:
        for worker in list(self.tasks.keys()):
            if not getattr(worker, "in_world", True) or getattr(worker, "hp", 1) <= 0:
                self.cancel(worker)

    def _point_distance(self, a: Point, b: Point) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])
