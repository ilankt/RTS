"""Human worker shelter and job resumption, timed in game seconds."""
from dataclasses import dataclass
import math

from systems import garrison


@dataclass
class ShelterTrip:
    task: object = None
    host: object = None
    safe_since: float = None
    retry_at: float = 0.0


class WorkerSafety:
    SCAN_INTERVAL = 0.5
    SAFE_DELAY = 6.0
    DANGER_RADIUS = 280.0
    SHELTER_RADIUS = 1000.0

    def __init__(self, tasks):
        self.tasks = tasks
        self.game = tasks.game
        self.trips = {}
        self.next_scan = 0.0

    def forget(self, worker):
        self.trips.pop(worker, None)
        worker._auto_shelter = False

    def _threat(self, worker, x, y, radius=None):
        radius = radius or self.DANGER_RADIUS
        collision = self.game.collision_system
        nearby = collision.query_nearby_units(x, y, radius, exclude=worker)
        nearby += collision.query_nearby_static(
            x, y, radius, include_resources=False, include_construction_sites=False)
        fog = getattr(self.game, 'fog_of_war', None)
        for enemy in nearby:
            if (getattr(enemy, 'player', None) in (None, worker.player)
                    or getattr(enemy, 'hp', 0) <= 0
                    or not getattr(enemy, 'in_world', True)
                    or not getattr(enemy, 'can_attack_flag', getattr(enemy, 'can_attack', False))
                    or getattr(enemy, 'building_only_attack', False)):
                continue
            if fog is not None and not fog.is_visible(worker.player, enemy.x, enemy.y):
                continue
            if math.hypot(enemy.x - x, enemy.y - y) <= radius:
                return enemy
        return None

    def update(self):
        now = self.tasks._task_time
        if now < self.next_scan:
            return
        self.next_scan = now + self.SCAN_INTERVAL
        workers = [u for u in self.game.units if u.name == 'worker'
                   and getattr(u.player, 'human', False) and u.hp > 0]
        for worker in workers:
            if worker in self.trips:
                continue
            if now < getattr(worker, '_safety_manual_until', 0.0):
                continue
            threat = self._threat(worker, worker.x, worker.y)
            # Actual damage also warns about a shooter just beyond normal sight.
            hit_at = getattr(worker, '_last_damage_sim_time', -999.0)
            sim_time = getattr(self.game, 'sim_time_elapsed', now)
            if threat is None and sim_time - hit_at <= 2.0:
                attacker = getattr(worker, 'last_attacker', None)
                if attacker is not None and getattr(attacker, 'hp', 0) > 0:
                    threat = attacker
            if threat is None:
                continue
            task = self.tasks.active_task(worker)
            self.tasks.cancel(worker)
            self.trips[worker] = ShelterTrip(task=task)
            worker._auto_shelter = True
            self._seek_shelter(worker, self.trips[worker], threat, now)

        for worker, trip in list(self.trips.items()):
            if worker.hp <= 0:
                self.forget(worker)
                continue
            host = getattr(worker, 'garrisoned_in', None)
            anchor = host or worker
            threat = self._threat(worker, anchor.x, anchor.y,
                                  self.DANGER_RADIUS + (host.radius if host else 0))
            job = trip.task
            target = (getattr(job, 'resource', None)
                      or getattr(job, 'construction_site', None))
            if threat is None and target is not None:
                threat = self._threat(worker, target.x, target.y)
            if threat is not None:
                trip.safe_since = None
            elif trip.safe_since is None:
                trip.safe_since = now
            elif now - trip.safe_since >= self.SAFE_DELAY:
                if host is not None:
                    garrison.eject_units(self.game, host, [worker])
                self.forget(worker)
                self._resume(worker, job)
                continue
            if host is not None:
                continue
            if trip.host is not None and garrison.try_enter(self.game, worker, trip.host):
                continue
            if (now >= trip.retry_at and not getattr(worker, '_pending_path_seq', None)
                    and not worker.path and not worker.destination):
                self._seek_shelter(worker, trip, threat, now)

    def _seek_shelter(self, worker, trip, threat, now):
        trip.retry_at = now + 2.0
        candidates = []
        for building in self.game.buildings:
            if not garrison.can_accept(building, worker):
                continue
            reservations = sum(t.host is building for u, t in self.trips.items()
                               if u is not worker and getattr(u, 'garrisoned_in', None) is None)
            if len(garrison.garrison_list(building)) + reservations >= garrison.capacity(building):
                continue
            distance = math.hypot(building.x - worker.x, building.y - worker.y)
            if distance <= self.SHELTER_RADIUS:
                candidates.append((building.name != 'castle', distance, building))
        trip.host = None
        for _, _, building in sorted(candidates, key=lambda row: row[:2]):
            if garrison.try_enter(self.game, worker, building):
                trip.host = building
                return
            # Move to an external contact; the building center is a blocker.
            point = self.tasks._reserve_slot(worker, building, 'dropoff')
            if point and self.game.pathfinder.issue_move(worker, point):
                trip.host = building
                # issue_move clears this field, so attach only AFTER it accepts.
                worker.garrison_target = building
                return
            self.tasks._release_slot(worker, building, 'dropoff')
        if threat is not None:
            dx, dy = worker.x - threat.x, worker.y - threat.y
            length = math.hypot(dx, dy) or 1.0
            self.game.pathfinder.issue_move(worker, (worker.x + dx / length * 200,
                                                    worker.y + dy / length * 200))

    def _resume(self, worker, task):
        self.tasks._release_worker_slots(worker)
        if task is not None and task.kind == 'gather':
            if self.tasks._valid_resource(task.resource):
                self.tasks.assign_gather(worker, task.resource)
            else:
                self.tasks._continue_or_complete(task)
        elif (task is not None and task.kind == 'build'
              and task.construction_site in self.game.construction_sites
              and self.tasks._valid_site(task.construction_site)):
            self.tasks.assign_build(worker, task.construction_site)
        elif getattr(worker, 'resource_amount', 0) > 0:
            self.tasks.assign_dropoff(worker)
        else:
            self.tasks.cancel(worker)

    def manual_order(self, worker):
        self.forget(worker)
        worker._safety_manual_until = self.tasks._task_time + 4.0
