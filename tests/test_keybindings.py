"""Rebindable hotkeys + camera bookmarks (§8.6)."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

if not pygame.get_init():
    pygame.init()

from core.keybindings import KeyBindings, DEFAULT_BINDINGS


def test_defaults_resolve_and_match(tmp_path):
    kb = KeyBindings(path=str(tmp_path / "kb.json"))
    for action in DEFAULT_BINDINGS:
        assert kb.key_for(action) is not None, f"{action} has no keycode"
    assert kb.matches("idle_worker", pygame.K_F1)
    assert kb.matches("speed_up", pygame.K_RIGHTBRACKET)
    assert not kb.matches("idle_worker", pygame.K_F2)


def test_rebind_persists_across_restart(tmp_path):
    path = str(tmp_path / "kb.json")
    kb = KeyBindings(path=path)
    assert kb.rebind("toggle_fog", "f7")
    assert kb.save()

    fresh = KeyBindings(path=path)  # "restart"
    assert fresh.matches("toggle_fog", pygame.K_F7)
    assert not fresh.matches("toggle_fog", pygame.K_F6)


def test_rebind_rejects_bad_input(tmp_path):
    kb = KeyBindings(path=str(tmp_path / "kb.json"))
    assert not kb.rebind("no_such_action", "f7")
    assert not kb.rebind("toggle_fog", "not-a-key")
    # Refuses a key already bound to another action
    assert not kb.rebind("toggle_fog", "f1")
    assert kb.matches("toggle_fog", pygame.K_F6)  # unchanged


def test_corrupt_overrides_are_ignored(tmp_path):
    path = tmp_path / "kb.json"
    path.write_text('{"toggle_fog": "zzz-not-a-key", "junk_action": "f7", not json')
    kb = KeyBindings(path=str(path))
    assert kb.matches("toggle_fog", pygame.K_F6)  # falls back to defaults


def test_camera_bookmarks_cycle():
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    game.camera.x, game.camera.y = -100.0, -200.0
    game._set_camera_bookmark()
    game.camera.x, game.camera.y = -900.0, -800.0
    game._set_camera_bookmark()

    game.camera.x, game.camera.y = 0.0, 0.0
    game._jump_camera_bookmark()
    first_jump = (game.camera.x, game.camera.y)
    game._jump_camera_bookmark()
    second_jump = (game.camera.x, game.camera.y)
    assert {first_jump, second_jump} == {(-100.0, -200.0), (-900.0, -800.0)}

    # Slots rotate: a fifth bookmark evicts the oldest
    for i in range(4):
        game.camera.x = -1000.0 - i
        game._set_camera_bookmark()
    assert len(game.camera_bookmarks) == game.MAX_CAMERA_BOOKMARKS
    assert (-100.0, -200.0) not in [(x, y) for x, y, _z in game.camera_bookmarks]
