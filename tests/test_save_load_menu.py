"""Multi-slot Save / Load screen (§8.2)."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from managers.save_manager import SaveManager


@pytest.fixture
def saves(tmp_path, monkeypatch):
    monkeypatch.setattr(SaveManager, "SAVE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="module")
def game():
    random.seed(9)
    from core.game import Game

    g = Game(mode="human_1v1", player_count=2)
    for _ in range(120):
        g.update(delta_time_override=1 / 60)
    return g


def test_slot_meta_empty_and_occupied(saves, game):
    assert SaveManager.slot_meta(0) is None
    SaveManager.save_game(game, slot=0)
    meta = SaveManager.slot_meta(0)
    assert meta is not None
    assert "played" in meta["summary"] and meta["when"]
    assert SaveManager.slot_meta(1) is None


def test_load_only_screen_buttons_and_empty_slot(saves):
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    assert screen.can_save is False
    assert list(screen._button_rects().keys()) == ["Load", "Back"]

    # Loading an empty slot doesn't return — it just warns
    screen.selected = 0
    screen._do_load()
    assert screen.result is None and screen.running is True
    assert screen._toast is not None


def test_load_returns_selected_occupied_slot(saves, game):
    SaveManager.save_game(game, slot=3)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    screen.selected = 3
    screen._do_load()
    assert screen.result == 3 and screen.running is False


def test_in_game_save_writes_slot(saves, game):
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=game)
    assert screen.can_save is True
    assert list(screen._button_rects().keys()) == ["Save", "Load", "Back"]

    assert SaveManager.slot_meta(4) is None
    screen.selected = 4
    screen._do_save()
    assert SaveManager.slot_meta(4) is not None       # written
    assert screen._meta[4] is not None                # UI refreshed
    assert "Saved to Slot 5" in screen._toast[0]
    assert screen.result is None                       # save doesn't exit
