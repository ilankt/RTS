import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.collision_system import CollisionSystem
from core.game import Game
from systems.gathering_manager import GatheringManager
from systems.movement_system import MovementSystem
from systems.pathfinding import Pathfinding
from systems.worker_task_system import (
    BUILDING,
    FAILED,
    MOVING_TO_DROPOFF,
    WorkerTaskSystem,
)


class FakeMap:
    width = 16
    height = 16

    def __init__(self):
        self.grid = [["grass" for _ in range(self.width)] for _ in range(self.height)]

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)

    def grid_to_world(self, col, row):
        return (col * 64, row * 64)


class FakePlayer:
    def __init__(self):
        self.name = "AI"
        self.human = False
        self.resources = {"wood": 0, "gold": 0, "stone": 0, "food": 0}
        self.gathering_rates = {"wood": 4.0, "gold": 1.0, "stone": 1.0, "food": 1.0}
        self.build_speed_bonus = 1.0


class FakeObject:
    def __init__(self, name, x, y, radius, player=None):
        self.name = name
        self.x = x
        self.y = y
        self.radius = radius
        self.size = [1, 1]
        self.player = player
        self.hp = 100


class FakeResource(FakeObject):
    def __init__(self, name, x, y, amount=100):
        super().__init__(name, x, y, 16)
        self.amount_remaining = amount
        self.gatherers = []


class FakeConstructionSite(FakeObject):
    def __init__(self, x, y, player):
        super().__init__("farm_construction", x, y, 32, player)
        self.building_name = "farm"
        self.builder = None


class FakeWorker:
    def __init__(self, player, x, y):
        self.name = "worker"
        self.player = player
        self.x = x
        self.y = y
        self.hp = 100
        self.radius = 8
        self.movement_speed = 120
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.destination = None
        self.status = "idle"
        self.is_gathering = False
        self.gathering_target = None
        self.resource_type = None
        self.resource_amount = 0
        self.max_capacity = {"wood": 4, "gold": 4, "stone": 4}
        self.gathering_timer = 0
        self.drop_off_target = None
        self.is_dropping_off = False
        self.drop_off_timer = 0.0
        self.previous_gathering_target = None
        self.is_building = False
        self.building_target = None
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        self.has_los = False
        self.is_fallback_movement = False
        self.collision = True

    def update_animation(self, delta_time=None):
        pass

    def get_target_tolerance(self, target_type="movement"):
        return 8


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.players = [FakePlayer()]
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.frame_counter = 0
        self.pathfinder = Pathfinding(self.game_map, self)
        self.gathering_manager = GatheringManager(self)
        self.collision_system = CollisionSystem(self)
        self.worker_task_system = WorkerTaskSystem(self)
        self.movement_system = MovementSystem(self)

    def _check_unit_collision_and_adjust(self, unit, new_pos, direction):
        return self.collision_system.check_unit_collision_and_adjust(unit, new_pos, direction)

    def _handle_blocked_unit(self, unit):
        return self.collision_system.handle_blocked_unit(unit)


def tick(game, count=1, delta_time=0.1):
    for _ in range(count):
        game.frame_counter += 1
        game.worker_task_system.update_pre_movement(delta_time)
        for unit in list(game.units):
            game.movement_system.update_unit_movement(unit, delta_time)
        game.worker_task_system.update_post_movement(delta_time)


def make_economy_game(worker_count=1):
    game = FakeGame()
    player = game.players[0]
    castle = FakeObject("castle", 128, 160, 42, player)
    wood = FakeResource("wood", 448, 160, amount=200)
    game.buildings.append(castle)
    game.resources.append(wood)
    for index in range(worker_count):
        worker = FakeWorker(player, 128, 220 + index * 24)
        game.units.append(worker)
    game.pathfinder.mark_dirty()
    return game, player, castle, wood


def test_worker_repeats_gather_dropoff_return_cycles():
    game, player, _, wood = make_economy_game()
    worker = game.units[0]

    assert game.worker_task_system.assign_gather(worker, wood)

    tick(game, count=500, delta_time=0.1)

    assert player.resources["wood"] >= 12
    assert game.worker_task_system.active_task(worker) is not None
    assert worker.resource_type in (None, "wood")
    assert getattr(worker, "worker_task_phase", None) != FAILED


def test_four_workers_share_resource_and_all_deliver():
    game, player, _, wood = make_economy_game(worker_count=4)
    wood.amount_remaining = 1000

    for worker in game.units:
        assert game.worker_task_system.assign_gather(worker, wood)

    tick(game, count=700, delta_time=0.1)

    assert player.resources["wood"] >= 16
    assert all(game.worker_task_system.active_task(worker).phase != FAILED for worker in game.units)


def test_resource_slots_are_distinct_and_reused():
    game, _, _, wood = make_economy_game(worker_count=3)

    for worker in game.units:
        assert game.worker_task_system.assign_gather(worker, wood)

    tasks = [game.worker_task_system.active_task(worker) for worker in game.units]
    slots = [task.resource_contact_point for task in tasks]
    assert len(set(slots)) == len(slots)

    old_slot = slots[0]
    game.worker_task_system.cancel(game.units[0])
    replacement = FakeWorker(game.players[0], game.units[0].x, game.units[0].y)
    game.units.append(replacement)

    assert game.worker_task_system.assign_gather(replacement, wood)
    assert game.worker_task_system.active_task(replacement).resource_contact_point == old_slot


def test_loaded_worker_without_dropoff_fails_cleanly():
    game = FakeGame()
    worker = FakeWorker(game.players[0], 128, 160)
    worker.resource_type = "wood"
    worker.resource_amount = 4
    game.units.append(worker)
    game.pathfinder.mark_dirty()

    assert not game.worker_task_system.assign_dropoff(worker)

    task = game.worker_task_system.active_task(worker)
    assert task.phase == FAILED
    assert task.failure_reason == "no_dropoff"
    assert worker.resource_amount == 4


def test_depleted_resource_cleanup_preserves_carried_cargo():
    game, player, _, wood = make_economy_game()
    worker = game.units[0]
    wood.amount_remaining = 0
    worker.resource_type = "wood"
    worker.resource_amount = 4
    worker.gathering_target = wood
    worker.previous_gathering_target = wood
    worker.is_gathering = True

    Game._cleanup_destroyed_objects(game)

    assert wood not in game.resources
    assert worker.resource_type == "wood"
    assert worker.resource_amount == 4
    assert game.worker_task_system.active_task(worker) is not None

    tick(game, count=240, delta_time=0.1)

    assert player.resources["wood"] >= 4
    assert worker.resource_amount == 0


def test_collision_blocked_worker_keeps_task_ownership():
    game, _, castle, wood = make_economy_game()
    worker = game.units[0]
    worker.y = 340
    worker.resource_type = "wood"
    worker.resource_amount = 4

    assert game.worker_task_system.assign_dropoff(worker, castle)
    task = game.worker_task_system.active_task(worker)
    assert task.phase == MOVING_TO_DROPOFF

    game.collision_system.handle_blocked_unit(worker)

    assert game.worker_task_system.owns(worker)
    assert game.worker_task_system.active_task(worker) is task
    assert worker.resource_amount == 4
    assert worker.path or worker.destination


def test_worker_reaches_construction_site_and_starts_building():
    game = FakeGame()
    player = game.players[0]
    worker = FakeWorker(player, 128, 160)
    site = FakeConstructionSite(448, 160, player)
    game.units.append(worker)
    game.construction_sites.append(site)
    game.pathfinder.mark_dirty()

    assert game.worker_task_system.assign_build(worker, site)

    tick(game, count=160, delta_time=0.1)

    assert worker.is_building
    assert worker.status == "build"
    assert site.builder is worker
    assert game.worker_task_system.active_task(worker).phase == BUILDING
