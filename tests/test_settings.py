"""Persistent settings (§8.2): defaults, persistence, live application."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from core.settings import Settings, DEFAULTS


def test_settings_persist_across_restart(tmp_path):
    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    settings.set("volume", 0.7)
    settings.set("default_game_speed", 3.0)
    settings.set("resolution", [1920, 1080])
    assert settings.save()

    fresh = Settings(path=path)  # "restart"
    assert fresh.get("volume") == pytest.approx(0.7)
    assert fresh.get("default_game_speed") == 3.0
    assert fresh.get("resolution") == [1920, 1080]


def test_all_defaults_saved_removes_file(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(path=str(path))
    settings.set("volume", 0.9)
    settings.save()
    assert path.exists()
    settings.set("volume", DEFAULTS["volume"])
    settings.save()
    assert not path.exists()  # nothing differs from defaults


def test_corrupt_and_invalid_values_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"volume": "loud", "resolution": [123, 45], "junk": 1}')
    settings = Settings(path=str(path))
    assert settings.get("volume") == DEFAULTS["volume"]
    assert settings.get("resolution") == DEFAULTS["resolution"]


def test_apply_to_game_sets_volume_and_speed(tmp_path):
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    settings = Settings(path=str(tmp_path / "settings.json"))
    settings.set("volume", 0.55)
    settings.set("default_game_speed", 2.0)
    settings.apply_to_game(game)

    assert game.game_speed == 2.0
    if game.sound_manager and game.sound_manager.enabled:
        assert game.sound_manager.volume == pytest.approx(0.55)

    settings.set("sound_enabled", False)
    settings.apply_to_game(game)
    assert game.sound_manager is None or not game.sound_manager.enabled


def test_colorblind_palette_toggle_persists(tmp_path):
    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    assert settings.get("colorblind_palette") is False  # default off
    settings.set("colorblind_palette", True)
    settings.save()
    assert Settings(path=path).get("colorblind_palette") is True


def test_colorblind_palette_swaps_in_place():
    """main.py patches PLAYER_COLORS with slice assignment so by-value
    imports elsewhere see the swap (§8.7)."""
    import core.config as config

    original = list(config.PLAYER_COLORS)
    alias = config.PLAYER_COLORS  # simulates `from core.config import PLAYER_COLORS`
    try:
        config.PLAYER_COLORS[:] = config.PLAYER_COLORS_COLORBLIND
        assert alias == config.PLAYER_COLORS_COLORBLIND
        assert alias is config.PLAYER_COLORS
    finally:
        config.PLAYER_COLORS[:] = original


def test_apply_resolution_derives_map_view():
    """apply_resolution (§8.2.1 Phase D) recomputes the derived layout
    constants so anchored HUD layouts scale with the startup resolution."""
    import core.config as config

    original = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
    try:
        config.apply_resolution(1920, 1080)
        assert (config.SCREEN_WIDTH, config.SCREEN_HEIGHT) == (1920, 1080)
        assert config.MAP_VIEW_HEIGHT == 1080 - config.TOP_BAR_HEIGHT
        assert config.MAP_VIEW_WIDTH == 1920 - (config.MINIMAP_WIDTH - 22)
    finally:
        config.apply_resolution(*original)
    # Restore is consistent whatever resolution the session started at
    assert (config.SCREEN_WIDTH, config.SCREEN_HEIGHT) == original
    assert config.MAP_VIEW_HEIGHT == original[1] - config.TOP_BAR_HEIGHT
    assert config.MAP_VIEW_WIDTH == original[0] - (config.MINIMAP_WIDTH - 22)


def test_batch_queue_size_clamped(tmp_path):
    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    assert settings.get("batch_queue_size") == 5  # default
    path_obj = tmp_path / "settings.json"
    path_obj.write_text('{"batch_queue_size": 99}')
    assert Settings(path=str(path_obj)).get("batch_queue_size") == 10  # clamped
    path_obj.write_text('{"batch_queue_size": "junk"}')
    assert Settings(path=str(path_obj)).get("batch_queue_size") == 5  # default
