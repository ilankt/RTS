import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.pathfinding import CLEARANCE_BUFFER, Pathfinding


class FakeMap:
    def __init__(self, width=8, height=8, fill="grass"):
        self.width = width
        self.height = height
        self.grid = [[fill for _ in range(width)] for _ in range(height)]

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)

    def grid_to_world(self, col, row):
        return (col * 64, row * 64)


class FakeGame:
    def __init__(self, game_map):
        self.game_map = game_map
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.units = []


class FakeObject:
    def __init__(self, name="object", x=0, y=0, radius=16, hp=100):
        self.name = name
        self.x = x
        self.y = y
        self.radius = radius
        self.hp = hp


class FakeResource(FakeObject):
    def __init__(self, name="wood", x=0, y=0, radius=16):
        super().__init__(name, x, y, radius, hp=0)
        self.amount_remaining = 100
        self.gatherers = []


class FakeUnit:
    def __init__(self, x=0, y=0, radius=8):
        self.name = "worker"
        self.x = x
        self.y = y
        self.radius = radius
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.destination = None
        self.status = "idle"
        self.is_gathering = False
        self.gathering_target = None
        self.is_dropping_off = False
        self.drop_off_timer = 0
        self.drop_off_target = None
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        self.is_building = False
        self.building_target = None
        self.has_los = False
        self.is_fallback_movement = False
        self.resource_amount = 0
        self.attack_range = 48


def make_pathfinder(game_map=None):
    game_map = game_map or FakeMap()
    game = FakeGame(game_map)
    return Pathfinding(game_map, game), game


def test_open_terrain_returns_direct_path():
    pathfinder, _ = make_pathfinder()

    result = pathfinder.find_result((40, 96), (320, 96), unit_radius=8)

    assert result.ok
    assert result.waypoints == [(320, 96)]
    assert result.final_point == (320, 96)


def test_water_barrier_returns_clean_failure():
    game_map = FakeMap(width=8, height=5)
    for row in range(game_map.height):
        game_map.grid[row][3] = "water"
    pathfinder, _ = make_pathfinder(game_map)

    result = pathfinder.find_result((80, 160), (420, 160), unit_radius=8)

    assert not result.ok
    assert result.failure_reason == "no_path"


def test_static_blocker_inflates_for_unit_radius():
    pathfinder, game = make_pathfinder()
    blocker = FakeObject("house", x=192, y=96, radius=32)
    game.buildings.append(blocker)
    pathfinder.mark_dirty()

    result = pathfinder.find_result((40, 96), (360, 96), unit_radius=8)

    assert result.ok
    assert not pathfinder.grid.segment_clear((40, 96), (360, 96), 8)
    for point in result.waypoints:
        distance = math.hypot(point[0] - blocker.x, point[1] - blocker.y)
        assert distance >= blocker.radius + 8 + CLEARANCE_BUFFER


def test_blocked_move_goal_resolves_to_reachable_point():
    pathfinder, game = make_pathfinder()
    blocker = FakeObject("house", x=192, y=160, radius=32)
    game.buildings.append(blocker)
    pathfinder.mark_dirty()

    result = pathfinder.find_result((64, 160), (192, 160), unit_radius=8)

    assert result.ok
    assert result.final_point != (192, 160)
    assert math.hypot(result.final_point[0] - blocker.x, result.final_point[1] - blocker.y) >= blocker.radius + 8


def test_unreachable_enclosed_goal_fails():
    game_map = FakeMap(width=7, height=7)
    for row in (2, 4):
        for col in range(2, 5):
            game_map.grid[row][col] = "water"
    for row in range(2, 5):
        for col in (2, 4):
            game_map.grid[row][col] = "water"
    pathfinder, _ = make_pathfinder(game_map)

    result = pathfinder.find_result((64, 224), (224, 224), unit_radius=4)

    assert not result.ok
    assert result.failure_reason == "no_path"


def test_mark_dirty_rebuilds_static_occupancy():
    pathfinder, game = make_pathfinder()
    start = (40, 96)
    goal = (360, 96)

    direct = pathfinder.find_result(start, goal, unit_radius=8)
    game.buildings.append(FakeObject("house", x=192, y=96, radius=40))
    pathfinder.mark_dirty()
    detour = pathfinder.find_result(start, goal, unit_radius=8)

    assert direct.ok
    assert direct.waypoints == [goal]
    assert detour.ok
    assert detour.waypoints != [goal]
    assert pathfinder.grid.revision == 1


def test_issue_interact_build_sets_contact_target_metadata():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    site = FakeObject("farm_construction", x=224, y=160, radius=32)
    game.construction_sites.append(site)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, site, "build") is True

    assert unit.status == "run"
    assert unit.building_target is site
    assert unit.path_target_object is site
    assert unit.path_target_mode == "build"
    assert math.hypot(unit.path_target[0] - site.x, unit.path_target[1] - site.y) >= site.radius + unit.radius


def test_issue_interact_gather_uses_resource_ring_not_center():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    resource = FakeResource(x=224, y=160, radius=16)
    game.resources.append(resource)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, resource, "gather") is True

    assert unit.gathering_target is resource
    assert unit in resource.gatherers
    assert unit.path_target != (resource.x, resource.y)
    assert math.hypot(unit.path_target[0] - resource.x, unit.path_target[1] - resource.y) > resource.radius


def test_issue_interact_gather_honors_reachable_preferred_slot():
    pathfinder, game = make_pathfinder()
    unit = FakeUnit(x=64, y=160)
    resource = FakeResource(x=224, y=160, radius=16)
    preferred = (224, 224)
    game.resources.append(resource)
    pathfinder.mark_dirty()

    assert pathfinder.issue_interact(unit, resource, "gather", preferred_point=preferred) is True

    assert unit.gathering_target is resource
    assert unit.path_target == preferred
