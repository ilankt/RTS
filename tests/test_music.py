"""Background music (§8.5): playlist discovery, volume separation from SFX,
live audio re-apply from the pause-screen settings."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_playlist_contains_the_three_soundtracks(game):
    sound = game.sound_manager
    names = [os.path.basename(p) for p in sound.music_playlist]
    assert names == [
        "Crown_of_the_Morning.ogg",
        "Legacy_of_the_Gilded_Peak.ogg",
        "Where_Light_Fails.ogg",
    ]


def test_music_volume_is_independent_and_clamped(game):
    sound = game.sound_manager
    sound.set_volume(0.2)
    sound.set_music_volume(1.7)
    assert sound.music_volume == 1.0
    assert sound.volume == 0.2  # SFX untouched
    sound.set_music_volume(-3)
    assert sound.music_volume == 0.0
    sound.set_music_volume(0.4)


def test_start_and_stop_music(game):
    sound = game.sound_manager
    if not sound.enabled:
        pytest.skip("mixer unavailable in this environment")

    sound.start_music()
    assert sound.music_started is True
    sound.start_music()  # idempotent
    assert sound.music_started is True

    game.update(delta_time_override=1 / 60)  # update_music must not crash

    sound.stop_music()
    assert sound.music_started is False
    sound.update_music()  # no-op when stopped
    assert sound.music_started is False


def test_apply_audio_controls_music_and_reenables(game):
    from core.settings import Settings

    sound = game.sound_manager
    if not sound.enabled:
        pytest.skip("mixer unavailable in this environment")

    settings = Settings(path="nonexistent-settings.json")
    settings.set("music_volume", 0.8)
    settings.set("volume", 0.1)

    settings.apply_audio(game)
    assert sound.music_volume == pytest.approx(0.8)
    assert sound.volume == pytest.approx(0.1)
    assert sound.music_started is True  # started by apply

    # Mute everything: music stops, SFX disabled
    settings.set("sound_enabled", False)
    settings.apply_audio(game)
    assert sound.enabled is False
    assert sound.music_started is False

    # Re-enable from the same session (the pause-screen path)
    settings.set("sound_enabled", True)
    settings.apply_audio(game)
    assert sound.enabled is True
    assert sound.music_started is True
    sound.stop_music()


def test_music_volume_setting_persists(tmp_path):
    from core.settings import Settings

    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    assert settings.get("music_volume") == pytest.approx(0.4)  # default
    settings.set("music_volume", 0.7)
    settings.save()
    assert Settings(path=path).get("music_volume") == pytest.approx(0.7)
