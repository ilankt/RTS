"""§8.5 audio: file-based SFX overrides, unit barks, music moods, ducking."""
import os
import sys
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

import managers.sound_manager as sm


def _write_wav(path, seconds=0.5):
    """A silent 16-bit stereo wav long enough to distinguish from synth blips."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(44100)
        handle.writeframes(b"\x00\x00\x00\x00" * int(44100 * seconds))


@pytest.fixture
def sfx_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SFX_DIR", str(tmp_path))
    return tmp_path


def test_sfx_file_overrides_synth(sfx_dir):
    _write_wav(sfx_dir / "select.wav", seconds=0.5)
    manager = sm.SoundManager(game=None)
    assert manager.enabled
    # Synth select is 0.03s; the file is 0.5s -> the override took.
    assert manager.sounds["select"].get_length() > 0.3
    # Un-overridden keys keep their synth placeholder.
    assert manager.sounds["move_order"].get_length() < 0.2


def test_bark_files_register_and_play(sfx_dir):
    _write_wav(sfx_dir / "bark_warrior_select_01.wav")
    _write_wav(sfx_dir / "bark_warrior_select_02.wav")
    _write_wav(sfx_dir / "bark_warrior_move_01.wav")
    manager = sm.SoundManager(game=None)
    assert len(manager.barks[("warrior", "select")]) == 2
    assert len(manager.barks[("warrior", "move")]) == 1
    manager.play_select("warrior")   # bark path - must not raise
    manager.play_move_order("warrior")
    manager.play_attack("warrior")   # no attack bark -> generic fallback


def test_per_type_pitch_variants_without_barks(sfx_dir):
    manager = sm.SoundManager(game=None)
    manager.play_select("warrior")
    manager.play_select("worker")
    assert "select::warrior" in manager.sounds
    assert "select::worker" in manager.sounds
    # Deterministic and distinct per type
    assert sm.SoundManager._type_pitch_factor("warrior") != \
        sm.SoundManager._type_pitch_factor("worker")


def _bare_music_player(monkeypatch):
    player = sm.MusicPlayer()
    player._scanned = True  # skip the disk scan
    played = []
    monkeypatch.setattr(player, "_play", lambda path, loops=0, fade_ms=1500: played.append(path) or True)
    monkeypatch.setattr(player, "_ensure_ready", lambda: True)
    return player, played


def test_mood_switch_uses_combat_pool(monkeypatch):
    player, played = _bare_music_player(monkeypatch)
    player.peace_playlist = ["peace_01.ogg"]
    player.combat_playlist = ["combat_01.ogg"]
    player.play_game()
    assert played[-1] == "peace_01.ogg"

    player.set_mood("combat")
    assert played[-1] == "combat_01.ogg"
    player.set_mood("peace")
    assert played[-1] == "peace_01.ogg"


def test_mood_switch_without_combat_tracks_keeps_playing(monkeypatch):
    player, played = _bare_music_player(monkeypatch)
    player.peace_playlist = ["peace_01.ogg"]
    player.play_game()
    count = len(played)
    player.set_mood("combat")  # no combat pool -> no track hop
    assert len(played) == count
    assert player.mood == "combat"  # mood still recorded


def test_stinger_plays_when_file_exists(monkeypatch):
    player, played = _bare_music_player(monkeypatch)
    player.stingers = {"victory": "victory.ogg"}
    assert player.play_stinger("victory") is True
    assert player.mode == "stinger"
    assert played[-1] == "victory.ogg"
    assert player.play_stinger("defeat") is False  # no file


def test_duck_dips_and_recovers():
    player = sm.MusicPlayer()
    player.duck(2.0)
    assert player._duck_multiplier() == pytest.approx(player.DUCK_FACTOR)
    # Simulate the duck window having ended over a second ago -> recovered.
    player._duck_until = time.monotonic() - (player.DUCK_RECOVER_S + 0.5)
    assert player._duck_multiplier() == pytest.approx(1.0)


def test_notify_human_combat_sets_mood_window():
    import random as _random
    _random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    human_unit = next(u for u in game.units if u.player.human)
    enemy_unit = next(u for u in game.units if not u.player.human)

    game.notify_human_combat(human_unit, enemy_unit)
    assert getattr(game, "_human_combat_until", 0) > game.sim_time_elapsed

    # AI-vs-AI damage never flips the human's music
    game._human_combat_until = 0.0
    game.notify_human_combat(enemy_unit, enemy_unit)
    assert game._human_combat_until == 0.0
