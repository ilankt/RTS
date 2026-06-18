import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.collision_system import CollisionSystem


class FakeMap:
    width = 12
    height = 12

    def __init__(self):
        self.grid = [["grass" for _ in range(self.width)] for _ in range(self.height)]

    def world_to_grid(self, x, y):
        col = int(x // 64)
        row = int(y // 64)
        if col < 0 or row < 0 or col >= self.width or row >= self.height:
            return None
        return (col, row)


class FakeObject:
    def __init__(self, name, x, y, radius):
        self.name = name
        self.x = x
        self.y = y
        self.radius = radius
        self.hp = 100
        self.collision = True


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.frame_counter = 1
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []


def test_spatial_collision_candidates_cover_full_scan_blockers():
    game = FakeGame()
    unit = FakeObject("worker", 128, 128, 8)
    nearby_unit = FakeObject("other_worker", 144, 128, 8)
    far_unit = FakeObject("far_worker", 600, 600, 8)
    building = FakeObject("house", 170, 128, 32)
    site = FakeObject("farm_construction", 250, 128, 32)
    resource = FakeObject("wood", 128, 168, 16)
    far_resource = FakeObject("gold", 600, 128, 16)

    game.units.extend([unit, nearby_unit, far_unit])
    game.buildings.append(building)
    game.construction_sites.append(site)
    game.resources.extend([resource, far_resource])

    collisions = CollisionSystem(game)
    position = type("Point", (), {"x": 128, "y": 128})()
    buffer = 2

    full_scan = {
        obj.name
        for obj in game.units + game.buildings + game.construction_sites + game.resources
        if obj is not unit
        and math.hypot(position.x - obj.x, position.y - obj.y) < unit.radius + obj.radius + buffer
    }

    candidates = list(collisions._nearby_units(position.x, position.y, unit.radius, exclude=unit))
    candidates.extend(collisions._nearby_static(position.x, position.y, unit.radius))
    spatial_scan = {
        obj.name
        for obj in candidates
        if math.hypot(position.x - obj.x, position.y - obj.y) < unit.radius + obj.radius + buffer
    }

    assert spatial_scan == full_scan
    assert "far_worker" not in {obj.name for obj in candidates}
    assert "gold" not in {obj.name for obj in candidates}
