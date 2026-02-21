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
        """A worker is idle if it has nothing useful to do."""
        # Explicitly idle
        if worker.status == "idle" and not worker.destination and not worker.path:
            # But also check it doesn't have a valid gathering/building target
            if worker.is_gathering and worker.gathering_target:
                return False
            if worker.is_building and worker.building_target:
                return False
            return True

        # Has a gathering target that no longer exists or is depleted
        if worker.gathering_target:
            if worker.gathering_target not in self.game.resources:
                worker.gathering_target = None
                worker.is_gathering = False
                worker.status = "idle"
                return True
            if getattr(worker.gathering_target, "amount_remaining", 0) <= 0:
                worker.gathering_target = None
                worker.is_gathering = False
                worker.status = "idle"
                return True

        # Has a building target that no longer exists
        if worker.building_target:
            if worker.building_target not in self.game.construction_sites:
                worker.building_target = None
                worker.is_building = False
                worker.status = "idle"
                return True

        # Stuck: has destination/path but isn't actually moving (status still "run" but no path progress)
        # We rely on the unit watchdog for deep stuck detection; here just check simple staleness
        if worker.status == "run" and not worker.path and not worker.destination:
            worker.status = "idle"
            return True

        return False

    def _assign_worker(self, worker, player):
        """Assign a single idle worker to a task, in priority order."""
        # 1. Carrying resources? -> Drop off
        if worker.resource_amount > 0 and worker.resource_type:
            target = self._find_dropoff(worker, player)
            if target:
                debug_log.log(f"AI {player.name}: Worker dropping off {worker.resource_type} at {target.name}", "AI")
                self._command_gather(worker, worker.gathering_target or self._find_closest_resource(worker, worker.resource_type))
                return

        # 2. Unattended construction site? -> Go build
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
        """Find the resource type we have least of, then find the closest one."""
        resources = player.resources
        # Rank resource types by how little we have (lower = more urgent)
        resource_priority = sorted(
            ["gold", "wood", "stone", "food"],
            key=lambda r: resources.get(r, 0),
        )

        for res_type in resource_priority:
            resource = self._find_closest_resource(worker, res_type)
            if resource:
                return resource
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
        construction_site.builder = worker
        worker.building_target = construction_site
        worker.status = "run"
        worker.gathering_target = None
        worker.is_building = False

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
