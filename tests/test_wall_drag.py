"""Wall drag-placement UI (§8.10): a drag lays a line of wall sites."""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(30):
        game.update(delta_time_override=1 / 60)
    return game


def wall_data():
    with open(os.path.join(os.path.dirname(__file__), "..", "data", "buildings.json")) as f:
        return next(b for b in json.load(f) if b["name"] == "wooden_wall")


def enter_wall_mode(game):
    bs = game.building_system
    human = game.players[0]
    human.resources["wood"] = 10000
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    for u in game.units:
        u.selected = False
    worker.selected = True
    assert bs.enter_building_placement_mode(wall_data())
    return bs


def find_open_run(game, bs, length):
    """A start point with `length` consecutive valid wall slots going east."""
    for y in range(300, int(game.game_map.height * 56), 120):
        for x in range(300, int(game.game_map.width * 56), 120):
            slots = [(x + i * bs.WALL_SPACING, y) for i in range(length)]
            if all(bs._wall_slot_valid(s) for s in slots):
                return (float(x), float(y))
    raise AssertionError("no open ground found for the test wall")


def to_screen(game, world):
    cam = game.camera
    return (world[0] * cam.zoom + cam.x, world[1] * cam.zoom + cam.y)


def wall_sites(game):
    return [s for s in game.construction_sites
            if s.player is game.players[0] and s.building_name == "wooden_wall"]


def test_drag_places_a_spaced_line_of_sites(game):
    bs = enter_wall_mode(game)
    human = game.players[0]
    start = find_open_run(game, bs, 6)
    end = (start[0] + 5 * bs.WALL_SPACING, start[1])
    wood_before = human.resources["wood"]

    bs.wall_drag_anchor = start
    assert bs.finish_wall_drag(to_screen(game, end))

    sites = sorted(wall_sites(game), key=lambda s: s.x)
    assert len(sites) == 6
    for a, b in zip(sites, sites[1:]):
        gap = math.hypot(b.x - a.x, b.y - a.y)
        assert abs(gap - bs.WALL_SPACING) < 1.0  # sealed spacing along the line
    assert human.resources["wood"] == wood_before - 6 * 40
    assert not bs.building_placement_mode  # mode exits after the drag


def test_short_drag_places_single_piece(game):
    bs = enter_wall_mode(game)
    start = find_open_run(game, bs, 1)

    bs.wall_drag_anchor = start
    assert bs.finish_wall_drag(to_screen(game, (start[0] + 10, start[1])))
    assert len(wall_sites(game)) == 1


def test_drag_stops_when_wood_runs_out(game):
    bs = enter_wall_mode(game)
    human = game.players[0]
    human.resources["wood"] = 95  # exactly two 40-wood pieces, third fails
    start = find_open_run(game, bs, 6)

    bs.wall_drag_anchor = start
    bs.finish_wall_drag(to_screen(game, (start[0] + 5 * bs.WALL_SPACING, start[1])))

    assert len(wall_sites(game)) == 2
    assert human.resources["wood"] == 95 - 80
