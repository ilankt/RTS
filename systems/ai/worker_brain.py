"""Worker assignment logic - finds idle workers and gives them jobs."""
import math
from core.config import DROP_OFF_BUILDINGS
from systems.ai.economy_helpers import (
    CRITICAL_STOCKPILE,
    RESOURCE_SERVICE_RADIUS,
    find_nearest_dropoff,
    known_resources,
)
from utils.debug_logger import debug_log


class WorkerBrain:
    """Every tick: find idle workers, send them to the most useful thing."""

    def __init__(self, game):
        self.game = game

    def assign_idle_workers(self, player):
        """Find all idle workers for this player and give them jobs."""
        workers = [u for u in self.game.units if u.player == player and u.name == "worker"]

        for worker in workers:
            if not self._is_idle(worker):
                continue
            self._assign_worker(worker, player)

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
            if worker.gathering_target in self.game.resources and worker.gathering_target.amount_remaining > 0:
                return False
            # Target is gone/depleted - clean up
            worker.gathering_target = None

        # Worker has a building target - check if still valid
        if worker.building_target:
            if worker.building_target in self.game.construction_sites:
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

    def _assign_worker(self, worker, player):
        """Assign a single idle worker to a task, in priority order."""
        # 0. Carrying resources without a current route? Deposit first.
        if worker.resource_amount > 0:
            dropoff = self._find_dropoff(worker, player)
            if dropoff:
                debug_log.log(f"AI {player.name}: Worker carrying {worker.resource_type}, returning to {dropoff.name}", "AI")
                worker_tasks = getattr(self.game, "worker_task_system", None)
                if worker_tasks:
                    worker_tasks.assign_dropoff(worker, dropoff)
                else:
                    self.game.pathfinder.issue_interact(worker, dropoff, "dropoff")
                return

        # 1. Unattended construction site? -> Go build
        site = self._find_unattended_construction_site(worker, player)
        if site:
            debug_log.log(f"AI {player.name}: Worker assigned to build {site.building_name} at ({site.x:.0f}, {site.y:.0f})", "AI")
            self._command_build(worker, site)
            return

        # 3. Gather the best known resource for short gather/drop-off loops.
        resource = self._find_best_resource_to_gather(worker, player)
        if resource:
            debug_log.log(f"AI {player.name}: Worker assigned to gather {resource.name} at ({resource.x:.0f}, {resource.y:.0f})", "AI")
            self._command_gather(worker, resource)
            return

        # 4. Nothing to do -> idle near castle
        castle = self._get_castle(player)
        if castle:
            debug_log.log(f"AI {player.name}: Worker idle, moving near castle", "AI")
            self.game.selection_manager._move_unit_to_position(
                worker, (castle.x + 50, castle.y + 50), self.game.pathfinder
            )

    def _find_dropoff(self, worker, player):
        """Find nearest building that accepts resource drop-off."""
        best = None
        best_dist = float("inf")
        for building in self.game.buildings:
            if building.player != player:
                continue
            if building.name in DROP_OFF_BUILDINGS.get(worker.resource_type, []):
                dist = math.hypot(worker.x - building.x, worker.y - building.y)
                if dist < best_dist:
                    best_dist = dist
                    best = building
        return best

    def _find_unattended_construction_site(self, worker, player):
        """Find a construction site that has no builder assigned."""
        best = None
        best_dist = float("inf")
        for site in self.game.construction_sites:
            if site.player != player:
                continue
            # Check if no worker is assigned or the assigned worker is dead/gone
            has_builder = False
            if site.builder and site.builder in self.game.units and site.builder.building_target == site:
                has_builder = True
            if not has_builder:
                dist = math.hypot(worker.x - site.x, worker.y - site.y)
                if dist < best_dist:
                    best_dist = dist
                    best = site
        return best

    def _find_best_resource_to_gather(self, worker, player):
        """Pick the best known resource, preferring serviced short loops."""
        # Count how many workers are already gathering each type
        gathering_counts = {"gold": 0, "wood": 0, "stone": 0}
        for unit in self.game.units:
            if unit.player == player and unit.name == "worker" and unit.gathering_target:
                res_name = getattr(unit.gathering_target, "name", None)
                if res_name in gathering_counts:
                    gathering_counts[res_name] += 1

        candidates = [
            resource
            for resource in known_resources(self.game, player)
            if resource.name in gathering_counts and resource.amount_remaining > 0
        ]
        if not candidates:
            return None

        has_serviced_option = False
        for resource in candidates:
            dropoff, dropoff_dist = find_nearest_dropoff(
                self.game,
                player,
                resource.name,
                (resource.x, resource.y),
            )
            if dropoff and dropoff_dist <= RESOURCE_SERVICE_RADIUS:
                has_serviced_option = True
                break

        best_resource = None
        best_score = float("inf")
        for resource in candidates:
            stockpile = player.resources.get(resource.name, 0)
            is_critical = stockpile <= CRITICAL_STOCKPILE.get(resource.name, 0)

            dropoff, dropoff_dist = find_nearest_dropoff(
                self.game,
                player,
                resource.name,
                (resource.x, resource.y),
            )
            if not dropoff:
                continue
            serviced = dropoff_dist <= RESOURCE_SERVICE_RADIUS
            if not serviced and has_serviced_option and not is_critical:
                continue

            worker_dist = math.hypot(worker.x - resource.x, worker.y - resource.y)
            assigned = self._count_workers_at_resource(resource)
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

    def _count_workers_at_resource(self, resource):
        """Count how many workers are gathering or returning to a specific resource."""
        count = 0
        for unit in self.game.units:
            if unit.name != "worker":
                continue
            if getattr(unit, 'gathering_target', None) == resource:
                count += 1
            elif getattr(unit, 'previous_gathering_target', None) == resource:
                count += 1
        return count

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

    def _get_castle(self, player):
        """Find the player's castle."""
        for building in self.game.buildings:
            if building.player == player and building.name == "castle":
                return building
        return None

    def get_worker_counts(self, player):
        """Return (idle, gathering, building) worker counts for debug display."""
        workers = [u for u in self.game.units if u.player == player and u.name == "worker"]
        idle = 0
        gathering = 0
        building = 0
        for w in workers:
            if w.is_building or (w.building_target and w.building_target in self.game.construction_sites):
                building += 1
            elif w.is_gathering or w.gathering_target:
                gathering += 1
            else:
                idle += 1
        return idle, gathering, building
