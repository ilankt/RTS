"""Save/load restores the TERRAIN, not just the objects (user-reported:
main-menu loads dropped you onto a freshly generated random map).

Note the map's seed alone can't do this: generation also draws from the
global RNG (world/map.py), so the grid itself is the only faithful record.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from managers.save_manager import SaveManager


@pytest.fixture
def saves(tmp_path, monkeypatch):
    monkeypatch.setattr(SaveManager, "SAVE_DIR", str(tmp_path))
    return tmp_path


def _grid_copy(game):
    return [list(row) for row in game.game_map.grid]


def test_terrain_round_trips_into_a_differently_generated_map(saves):
    """The real main-menu path: save one map, build a NEW game (which
    generates its own random terrain), load, and the saved ground is back."""
    from core.game import Game

    random.seed(11)
    saved_game = Game(mode="human_1v1", player_count=2)
    saved_grid = _grid_copy(saved_game)
    SaveManager.save_game(saved_game, slot=0)

    # A different seed => a genuinely different map to load over
    random.seed(999)
    fresh = Game(mode="human_1v1", player_count=2,
                 map_size=SaveManager.peek_map_size(slot=0))
    assert _grid_copy(fresh) != saved_grid, "sanity: fresh map differs"

    ok, _msg = SaveManager.load_game(fresh, slot=0)
    assert ok
    assert _grid_copy(fresh) == saved_grid, "loaded map must be the saved map"


def test_pathfinder_terrain_bitmap_follows_the_restored_ground(saves):
    """The nav bitmap is built once and mark_dirty() never wipes it, so a
    terrain swap must explicitly rebuild it — otherwise units path over the
    old map's water."""
    from core.game import Game

    random.seed(21)
    game = Game(mode="human_1v1", player_count=2)
    SaveManager.save_game(game, slot=1)

    # Corrupt the live terrain + its derived bitmap, then load it back
    game.game_map.grid = [["water" for _ in range(game.game_map.width)]
                          for _ in range(game.game_map.height)]
    game.pathfinder.rebuild_terrain()
    bitmap = lambda: sum(sum(row) for row in game.pathfinder.grid._terrain_bitmap)
    assert bitmap() == 0, "sanity: an all-water map is unwalkable"

    ok, _ = SaveManager.load_game(game, slot=1)
    assert ok
    assert bitmap() > 0, "nav bitmap must be rebuilt from the restored terrain"


def test_terrain_payload_is_compact_and_lossless(saves):
    from core.game import Game

    random.seed(31)
    game = Game(mode="human_1v1", player_count=2)
    payload = SaveManager._serialize_terrain(game)

    assert set(payload) == {"palette", "rows"}
    assert len(payload["rows"]) == game.game_map.height
    assert all(len(r) == game.game_map.width for r in payload["rows"])
    # one char per tile, not a fat name-per-tile dump
    assert sum(len(r) for r in payload["rows"]) == game.game_map.width * game.game_map.height

    # round-trips exactly through the restore path
    original = _grid_copy(game)
    game.game_map.grid = [["grass"] * game.game_map.width
                          for _ in range(game.game_map.height)]
    assert SaveManager._restore_terrain(game, payload) is True
    assert _grid_copy(game) == original


def test_v1_saves_without_terrain_still_load(saves):
    """Old saves keep the generated map instead of crashing."""
    from core.game import Game

    random.seed(41)
    game = Game(mode="human_1v1", player_count=2)
    before = _grid_copy(game)
    assert SaveManager._restore_terrain(game, None) is False
    assert _grid_copy(game) == before
