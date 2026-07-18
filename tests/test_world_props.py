"""§11.2 round 2: world props (rocks / dead trees / ruins) — placement
rules, blocking behavior, and save/load survival."""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(90210)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def props_of(game, name):
    return [p for p in game.props if p.name == name]


def test_art_present_types_are_available():
    from entities.prop import available_prop_types

    assert available_prop_types() == {"rocks", "dead_tree", "ruins"}


def test_props_placed_on_allowed_terrain(game):
    from core.game_state import GameState

    assert game.props, "a 70x70 map should place world props"
    gm = game.game_map
    for prop in game.props:
        allowed = GameState.PROP_PLACEMENT[prop.name]["terrain"]
        c, r = gm.world_to_grid(prop.x, prop.y)
        # ±1-tile tolerance: the world<->grid round trip (§8.13.4) can
        # land one tile off the placement tile
        tiles = [(r, c)] + list(gm.hex_neighbors(r, c))
        assert any(0 <= tr < gm.height and 0 <= tc < gm.width
                   and gm.grid[tr][tc] in allowed for tr, tc in tiles), \
            f"{prop.name} at ({prop.x:.0f},{prop.y:.0f}) sits on {gm.grid[r][c]}"


def test_blocking_props_block_navigation(game):
    rocks = props_of(game, "rocks")
    assert rocks, "rocks should exist on this map"
    for rock in rocks[:3]:
        assert not game.pathfinder.is_position_walkable((rock.x, rock.y), 8), \
            "a rock outcrop must block the nav grid"


def test_decorative_props_do_not_block(game):
    dead_trees = props_of(game, "dead_tree")
    for tree in dead_trees[:3]:
        assert game.pathfinder.is_position_walkable((tree.x, tree.y), 8), \
            "dead trees are scenery — they must not block movement"


def test_ruins_are_rare_landmarks(game):
    ruins = props_of(game, "ruins")
    assert 1 <= len(ruins) <= 3
    castles = [b for b in game.buildings if b.name == "castle"]
    for ruin in ruins:
        for castle in castles:
            assert math.hypot(ruin.x - castle.x, ruin.y - castle.y) > 400


def test_props_survive_save_load(game, tmp_path):
    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)
    before = sorted((p.name, round(p.x), round(p.y)) for p in game.props)
    assert before
    SaveManager.save_game(game, slot=0)
    ok, msg = SaveManager.load_game(game, slot=0)
    assert ok, msg
    after = sorted((p.name, round(p.x), round(p.y)) for p in game.props)
    assert after == before
    # Blocking props still block after the load
    rock = next(p for p in game.props if p.name == "rocks")
    assert not game.pathfinder.is_position_walkable((rock.x, rock.y), 8)
