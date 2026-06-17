import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.movement_system import MovementSystem
from systems.pathfinding import Pathfinding


class FakeMap:
    width = 8
    height = 8

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


class FakeCollisionSystem:
    def get_safe_position(self, unit, target_pos):
        return target_pos

    def _is_on_unwalkable_terrain(self, x, y, radius):
        return False


class FakeGatheringManager:
    def start_gathering(self, worker, resource):
        worker.is_gathering = True
        worker.is_engaging = False
        worker.gathering_target = resource
        worker.status = "gather"
        return True


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.units = []
        self.frame_counter = 0
        self.collision_system = FakeCollisionSystem()
        self.gathering_manager = FakeGatheringManager()
        self.pathfinder = Pathfinding(self.game_map, self)

    def _check_unit_collision_and_adjust(self, unit, new_pos, direction):
        return new_pos

    def _handle_blocked_unit(self, unit):
        raise AssertionError("unit should not need blocked-unit recovery")


class FakeTarget:
    def __init__(self, name, x, y, radius):
        self.name = name
        self.x = x
        self.y = y
        self.radius = radius
        self.hp = 100


class FakeResource(FakeTarget):
    def __init__(self, x, y):
        super().__init__("wood", x, y, 16)
        self.hp = 0
        self.amount_remaining = 100
        self.gatherers = []


class FakeUnit:
    def __init__(self, x, y):
        self.name = "worker"
        self.x = x
        self.y = y
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
        self.is_dropping_off = False
        self.drop_off_timer = 0
        self.drop_off_target = None
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


def run_until(game, unit, predicate, max_ticks=120):
    movement = MovementSystem(game)
    for _ in range(max_ticks):
        game.frame_counter += 1
        movement.update_unit_movement(unit, 0.1)
        if predicate():
            return True
    return False


def test_worker_reaches_construction_ring_and_starts_building():
    game = FakeGame()
    worker = FakeUnit(64, 160)
    site = FakeTarget("farm_construction", 256, 160, 32)
    game.units.append(worker)
    game.construction_sites.append(site)
    game.pathfinder.mark_dirty()

    assert game.pathfinder.issue_interact(worker, site, "build")
    assert run_until(game, worker, lambda: worker.is_building)

    assert worker.status == "build"
    assert site.builder is worker


def test_worker_reaches_resource_ring_and_starts_gathering():
    game = FakeGame()
    worker = FakeUnit(64, 160)
    resource = FakeResource(256, 160)
    game.units.append(worker)
    game.resources.append(resource)
    game.pathfinder.mark_dirty()

    assert game.pathfinder.issue_interact(worker, resource, "gather")
    assert run_until(game, worker, lambda: worker.is_gathering)

    assert worker.status == "gather"
    assert worker.gathering_target is resource
