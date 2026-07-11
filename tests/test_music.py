"""Background music (§8.5): playlist discovery, volume separation from SFX,
live audio re-apply from the pause-screen settings."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_track_roles_menu_theme_and_game_playlist(game):
    """menu.ogg is the dedicated menu theme; every game_N.ogg joins the
    in-match pool automatically, in numeric order (drop-in convention —
    don't hardcode a count here)."""
    import re
    from managers.sound_manager import music_player

    names = [os.path.basename(p) for p in game.sound_manager.music_playlist]
    assert len(names) >= 2
    assert all(re.fullmatch(r"game_\d+\.ogg", n) for n in names)
    numbers = [int(n[5:-4]) for n in names]
    assert numbers == sorted(numbers)
    assert music_player.menu_track is not None
    assert os.path.basename(music_player.menu_track) == "menu.ogg"


def test_game_playlist_sorts_numerically():
    from managers.sound_manager import MusicPlayer

    key = MusicPlayer._game_sort_key
    files = ["game_10.ogg", "game_2.ogg", "game_0.ogg", "game_1.ogg"]
    assert sorted(files, key=key) == [
        "game_0.ogg", "game_1.ogg", "game_2.ogg", "game_10.ogg"]


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


def test_menu_theme_switches_to_game_playlist_and_back(game):
    """Menu loops menu.ogg; launching a match switches to the game_N
    playlist; returning to the menu brings the theme back."""
    from managers.sound_manager import music_player

    sound = game.sound_manager
    if not sound.enabled:
        pytest.skip("mixer unavailable in this environment")

    music_player.stop()
    music_player.play_menu()      # the main-menu path
    assert music_player.mode == 'menu'
    music_player.update()         # menu theme loops itself: update no-ops
    assert music_player.mode == 'menu'

    sound.start_music()           # the match-launch path
    assert music_player.mode == 'game'
    sound.start_music()           # idempotent mid-match
    assert music_player.mode == 'game'

    music_player.play_menu()      # back to the menu after the match
    assert music_player.mode == 'menu'
    music_player.stop()


def test_splash_background_scales_to_screen():
    from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
    from screens.main_menu import splash_background, draw_splash
    import pygame

    surface = splash_background()
    assert surface is not None
    assert surface.get_size() == (SCREEN_WIDTH, SCREEN_HEIGHT)

    screen = pygame.display.get_surface() or pygame.display.set_mode((640, 360))
    draw_splash(screen, "Loading...")  # must not raise


def test_shuffle_never_repeats_the_previous_track():
    """Random order with a hard rule: the same track never plays twice in a
    row (once more than one track exists)."""
    import random as random_module
    from managers.sound_manager import MusicPlayer

    player = MusicPlayer()
    player._rng = random_module.Random(42)  # deterministic test

    # 3-track pool: 200 picks never return the previous pick, and every
    # other track shows up (it is genuinely random, not round-robin)
    player._last_game_index = 1
    seen = set()
    for _ in range(200):
        pick = player._pick_game_index(3)
        assert pick != player._last_game_index
        seen.add(pick)
        player._last_game_index = pick
    assert seen == {0, 1, 2}

    # Single track: repeating is the only option
    player._last_game_index = 0
    assert player._pick_game_index(1) == 0


def test_track_advance_shuffles_through_real_update(game, monkeypatch):
    from managers.sound_manager import music_player

    sound = game.sound_manager
    if not sound.enabled:
        pytest.skip("mixer unavailable in this environment")

    music_player.stop()
    sound.start_music()
    assert music_player.mode == 'game'
    first = music_player.index

    # Simulate the current track ending: update must pick a DIFFERENT track
    monkeypatch.setattr(pygame.mixer.music, "get_busy", lambda: False)
    music_player.update()
    assert music_player.mode == 'game'
    assert music_player.index != first  # never the same track twice in a row
    music_player.stop()
