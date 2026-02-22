"""Worker assignment logic - finds idle workers and gives them jobs."""
import math
from systems.pathfinding import Pathfinding
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
        # Workers carrying resources or mid-drop-off are busy
        if worker.resource_amount > 0 or worker.is_dropping_off:
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
        # 1. Unattended construction site? -> Go build
        site = self._find_unattended_construction_site(worker, player)
        if site:
            debug_log.log(f"AI {player.name}: Worker assigned to build {site.building_name} at ({site.x:.0f}, {site.y:.0f})", "AI")
            self._command_build(worker, site)
            return

        # 3. Gather the resource we have least of
        resource = self._find_best_resource_to_gather(worker, player)
        if resource:
            debug_log.log(f"AI {player.name}: Worker assigned to gather {resource.name} at ({resource.x:.0f}, {resource.y:.0f})", "AI")
            self._command_gather(worker, resource)
            return

        # 4. Nothing to do -> idle near castle
        castle = self._get_castle(player)
        if castle:
            debug_log.log(f"AI {player.name}: Worker idle, moving near castle", "AI")
            pathfinder = Pathfinding(self.game.game_map, self.game)
            self.game.selection_manager._move_unit_to_position(
                worker, (castle.x + 50, castle.y + 50), pathfinder
            )

    def _find_dropoff(self, worker, player):
        """Find nearest building that accepts resource drop-off."""
        best = None
        best_dist = float("inf")
        for building in self.game.buildings:
            if building.player != player:
                continue
            # Castle and resource buildings accept drop-offs
            if building.name in ("castle", "mine", "quarry", "lumbermill", "farm"):
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
        """Pick the best resource to gather, spreading workers across types.

        Uses a simple score: lower stockpile = higher need, but penalizes
        types that already have many workers assigned.
        """
        # Count how many workers are already gathering each type
        gathering_counts = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        for unit in self.game.units:
            if unit.player == player and unit.name == "worker" and unit.gathering_target:
                res_name = getattr(unit.gathering_target, "name", None)
                if res_name in gathering_counts:
                    gathering_counts[res_name] += 1

        resources = player.resources
        best_type = None
        best_score = float("inf")

        for res_type in ["gold", "wood", "stone", "food"]:
            # Check if this resource actually exists on the map
            if not self._find_closest_resource(worker, res_type):
                continue
            # Score = stockpile + 100 per worker already assigned (lower is better)
            score = resources.get(res_type, 0) + gathering_counts[res_type] * 100
            if score < best_score:
                best_score = score
                best_type = res_type

        if best_type:
            return self._find_closest_resource(worker, best_type)
        return None

    def _find_closest_resource(self, worker, resource_type):
        """Find closest resource of given type."""
        best = None
        best_dist = float("inf")
        for res in self.game.resources:
            if res.name != resource_type or res.amount_remaining <= 0:
                continue
            dist = math.hypot(worker.x - res.x, worker.y - res.y)
            if dist < best_dist:
                best_dist = dist
                best = res
        return best

    def _command_gather(self, worker, resource):
        """Send a worker to gather a resource."""
        if not resource or getattr(resource, "amount_remaining", 0) <= 0:
            return
        pathfinder = Pathfinding(self.game.game_map, self.game)
        pathfinder.gathering_target = resource
        self.game.selection_manager._gather_from_target(worker, resource, pathfinder)

    def _command_build(self, worker, construction_site):
        """Send a worker to build at a construction site."""
        # Wipe ALL prior state so movement system doesn't hijack the worker
        worker.clear_all_movement_state()

        construction_site.builder = worker
        worker.building_target = construction_site
        worker.status = "run"

        pathfinder = Pathfinding(self.game.game_map, self.game)
        pathfinder.building_target = construction_site
        path = pathfinder.find_path(
            (worker.x, worker.y),
            (construction_site.x, construction_site.y),
            worker.radius,
            worker,
        )
        if path:
            worker.path = path
            worker.path_index = 0
            worker.path_target = (construction_site.x, construction_site.y)
            worker.destination = path[0] if path else None
        else:
            debug_log.log(f"AI: No path to construction site at ({construction_site.x:.0f}, {construction_site.y:.0f})", "AI")
        pathfinder.building_target = None

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
