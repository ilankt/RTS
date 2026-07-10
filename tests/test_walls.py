"""Wall & gate mechanics (§8.10): walls block, open gates don't."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.building import Building
from systems.pathfinding import Pathfinding


class FakeMap:
    width = 10
    height = 10

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


class FakeGame:
    def __init__(self):
        self.game_map = FakeMap()
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.frame_counter = 1


def make_wall_piece(name, x, y):
    return Building(
        name=name, size=[1, 1], hp=1200, sprite=None, build_duration=6,
        x=x, y=y, radius=24, armor_type="fortified",
    )


def wall_line(game, pathfinder, name, x, y_from, y_to, step=48):
    pieces = []
    for y in range(y_from, y_to, step):
        piece = make_wall_piece(name, x, y)
        game.buildings.append(piece)
        pathfinder.notify_blocker_added(piece)
        pieces.append(piece)
    return pieces


def test_wall_line_forces_detour():
    game = FakeGame()
    pathfinder = Pathfinding(game.game_map, game)
    wall_line(game, pathfinder, "wall", x=320, y_from=0, y_to=640)

    result = pathfinder.find_result((100, 320), (540, 320), unit_radius=8)
    # Fully sealed vertical line across the map: no path at all
    assert not result.ok
    assert result.failure_reason == "no_path"


def test_closed_gate_blocks_open_gate_passes():
    game = FakeGame()
    pathfinder = Pathfinding(game.game_map, game)
    # Wall line with one gate in the middle
    wall_line(game, pathfinder, "wall", x=320, y_from=0, y_to=280)
    gate = make_wall_piece("gate", 320, 320)
    game.buildings.append(gate)
    pathfinder.notify_blocker_added(gate)
    wall_line(game, pathfinder, "wall", x=320, y_from=380, y_to=640)

    blocked = pathfinder.find_result((100, 320), (540, 320), unit_radius=8)
    assert not blocked.ok  # closed gate seals the line

    # Open the gate: passable + un-indexed from nav
    assert gate.toggle_gate() is True
    assert gate.passable
    pathfinder.notify_blocker_removed(gate)

    through = pathfinder.find_result((100, 320), (540, 320), unit_radius=8)
    assert through.ok  # path goes through the open gate

    # Close it again
    assert gate.toggle_gate() is False
    pathfinder.notify_blocker_added(gate)
    resealed = pathfinder.find_result((100, 320), (540, 320), unit_radius=8)
    assert not resealed.ok


def test_only_gates_toggle():
    wall = make_wall_piece("wall", 0, 0)
    assert wall.toggle_gate() is None
    gate = make_wall_piece("gate", 0, 0)
    assert gate.is_gate and not wall.is_gate
