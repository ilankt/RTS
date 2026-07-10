"""Worker assignment logic - finds idle workers and gives them jobs.

Reads only the per-tick GoalContext blackboard; never rescans game lists.
"""
import math
from core.config import DROP_OFF_BUILDINGS
from systems.ai.economy_helpers import (
    CRITICAL_STOCKPILE,
    RESOURCE_SERVICE_RADIUS,
    find_nearest_dropoff_ctx,
)
from utils.debug_logger import debug_log


MAX_IDLE_WORKER_ASSIGNMENTS_PER_TICK = 2


class WorkerBrain:
    """Every tick: find idle workers, send them to the most useful thing."""

    def __init__(self, game):
        self.game = game

    def assign_idle_workers(self, ctx):
        """Find all idle workers for this player and give them jobs."""
        from systems.ai.utility.personality import difficulty_mods

        max_assignments = difficulty_mods(
            getattr(ctx.player, "ai_difficulty", "normal")
        ).get("worker_assignments", MAX_IDLE_WORKER_ASSIGNMENTS_PER_TICK)
        assignments = 0
        for worker in ctx.workers:
            if not self._is_idle(worker):
                continue
            self._assign_worker(worker, ctx)
            assignments += 1
            if assignments >= max_assignments:
                break

    def _is_idle(self, worker) -> bool:
        """A worker is idle if it has nothing useful to do.

        Workers in the gather->dropoff->return cycle are NOT idle even if
        they briefly appear idle between steps.
        """
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks:
            task = worker_tasks.active_task(worker)
            if task and task.phase != "FAILED":
                return False
            if task and task.phase == "FAILED":
                worker_tasks.cancel(worker)

        # Carriers are busy unless they lost their drop-off command.
        if worker.resource_amount > 0:
            if not worker.drop_off_target and not worker.destination and not worker.path and not worker.is_dropping_off:
                return True
            return False
        if worker.is_dropping_off:
            return False

        # Workers actively gathering or building are busy
        if worker.is_gathering or worker.is_building:
            return False

        # Workers with movement are busy
        if worker.destination or worker.path:
            # But check for stale movement (has movement but no actual target)
            if worker.is_engaging and not worker.gathering_target and not worker.current_target:
                worker.clear_all_movement_state()
                return True
            return False

        # Worker has a valid gathering target it will return to - let movement system handle it
        if worker.gathering_target:
            if getattr(worker.gathering_target, "in_world", True) and worker.gathering_target.amount_remaining > 0:
                return False
            # Target is gone/depleted - clean up
            worker.gathering_target = None

        # Worker has a building target - check if still valid
        if worker.building_target:
            if getattr(worker.building_target, "in_world", True) and getattr(worker.building_target, "hp", 1) > 0:
                return False
            # Site is gone - clean up
            worker.building_target = None

        # Check for stale is_engaging with no target
        if worker.is_engaging:
            worker.is_engaging = False

        # If we get here, worker has no movement, no valid targets -> idle
        if worker.status != "idle":
            worker.status = "idle"
        return True

    def _assign_worker(self, worker, ctx):
        """Assign a single idle worker to a task, in priority order."""
        player = ctx.player
        # 0. Carrying resources without a current route? Deposit first.
        if worker.resource_amount > 0:
            dropoff, _ = find_nearest_dropoff_ctx(ctx, worker.resource_type, (worker.x, worker.y))
            if dropoff:
                debug_log.log(f"AI {player.name}: Worker carrying {worker.resource_type}, returning to {dropoff.name}", "AI")
                worker_tasks = getattr(self.game, "worker_task_system", None)
                if worker_tasks:
                    worker_tasks.assign_dropoff(worker, dropoff)
                else:
                    self.game.pathfinder.issue_interact(worker, dropoff, "dropoff")
                return

        # 1. Unattended construction site? -> Go build
        site = self._find_unattended_construction_site(worker, ctx)
        if site:
            debug_log.log(f"AI {player.name}: Worker assigned to build {site.building_name} at ({site.x:.0f}, {site.y:.0f})", "AI")
            self._command_build(worker, site)
            return

        # 3. Gather the best known resource for short gather/drop-off loops.
        resource = self._find_best_resource_to_gather(worker, ctx)
        if resource:
            debug_log.log(f"AI {player.name}: Worker assigned to gather {resource.name} at ({resource.x:.0f}, {resource.y:.0f})", "AI")
            self._command_gather(worker, resource)
            return

        # 4. Nothing to do -> idle near castle
        if ctx.castle:
            debug_log.log(f"AI {player.name}: Worker idle, moving near castle", "AI")
            self.game.selection_manager._move_unit_to_position(
                worker, (ctx.castle.x + 50, ctx.castle.y + 50), self.game.pathfinder
            )

    def _find_unattended_construction_site(self, worker, ctx):
        """Find a construction site that has no builder assigned."""
        best = None
        best_dist = float("inf")
        for site in ctx.construction_sites:
            # Check if no worker is assigned or the assigned worker is dead/gone
            builder = site.builder
            has_builder = bool(
                builder
                and getattr(builder, "in_world", True)
                and getattr(builder, "hp", 1) > 0
                and builder.building_target == site
            )
            if not has_builder:
                dist = math.hypot(worker.x - site.x, worker.y - site.y)
                if dist < best_dist:
                    best_dist = dist
                    best = site
        return best

    def _find_best_resource_to_gather(self, worker, ctx):
        """Pick the best known resource, preferring serviced short loops."""
        gathering_counts = ctx.gathering_counts_by_type

        candidates = [
            resource
            for resource in ctx.known_resources()
            if resource.name in gathering_counts and resource.amount_remaining > 0
        ]
        if not candidates:
            return None

        # Nearest drop-off per candidate, computed once each.
        dropoff_distances = {}
        has_serviced_option = False
        for resource in candidates:
            dropoff, dropoff_dist = find_nearest_dropoff_ctx(ctx, resource.name, (resource.x, resource.y))
            dropoff_distances[id(resource)] = (dropoff, dropoff_dist)
            if dropoff and dropoff_dist <= RESOURCE_SERVICE_RADIUS:
                has_serviced_option = True

        best_resource = None
        best_score = float("inf")
        for resource in candidates:
            stockpile = ctx.resources.get(resource.name, 0)
            is_critical = stockpile <= CRITICAL_STOCKPILE.get(resource.name, 0)

            dropoff, dropoff_dist = dropoff_distances[id(resource)]
            if not dropoff:
                continue
            serviced = dropoff_dist <= RESOURCE_SERVICE_RADIUS
            if not serviced and has_serviced_option and not is_critical:
                continue

            worker_dist = math.hypot(worker.x - resource.x, worker.y - resource.y)
            assigned = ctx.count_workers_at_resource(resource)
            score = (
                stockpile
                + gathering_counts[resource.name] * 120
                + assigned * 160
                + worker_dist * 0.08
                + dropoff_dist * 0.25
            )
            if not serviced:
                score += 220 if is_critical else 450

            if score < best_score:
                best_score = score
                best_resource = resource

        return best_resource

    def _command_gather(self, worker, resource):
        """Send a worker to gather a resource."""
        if not resource or getattr(resource, "amount_remaining", 0) <= 0:
            return
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks:
            worker_tasks.assign_gather(worker, resource)
        else:
            spread_pos = self.game.gathering_manager.reserve_gathering_position(worker, resource)
            self.game.selection_manager._gather_from_target(worker, resource, self.game.pathfinder, new_destination=spread_pos)

    def _command_build(self, worker, construction_site):
        """Send a worker to build at a construction site."""
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks:
            success = worker_tasks.assign_build(worker, construction_site)
        else:
            success = self.game.pathfinder.issue_interact(worker, construction_site, "build")
        if not success:
            debug_log.log(f"AI: No path to construction site at ({construction_site.x:.0f}, {construction_site.y:.0f})", "AI")

    def get_worker_counts(self, ctx):
        """Return (idle, gathering, building) worker counts for debug display."""
        idle = 0
        gathering = 0
        building = 0
        for w in ctx.workers:
            if w.is_building or (w.building_target and getattr(w.building_target, "in_world", True)):
                building += 1
            elif w.is_gathering or w.gathering_target:
                gathering += 1
            else:
                idle += 1
        return idle, gathering, building
