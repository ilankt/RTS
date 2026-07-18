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


def test_load_only_screen_has_no_tabs_and_warns_on_empty(saves):
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    assert screen.can_save is False
    assert screen.mode == "load"
    assert screen._tab_rects() == {}

    # Activating an empty slot doesn't return — it just warns
    screen._activate_slot(0)
    assert screen.result is None and screen.running is True
    assert screen._toast is not None


def test_load_returns_activated_occupied_slot(saves, game):
    SaveManager.save_game(game, slot=3)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    screen._activate_slot(3)  # one click loads directly
    assert screen.result == 3 and screen.running is False


def test_in_game_defaults_to_save_tab_and_click_saves(saves, game):
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=game)
    assert screen.can_save is True
    assert screen.mode == "save"                      # loading needs a tab switch
    assert set(screen._tab_rects().keys()) == {"save", "load"}

    assert SaveManager.slot_meta(4) is None
    screen._activate_slot(4)                          # one click writes the slot
    assert SaveManager.slot_meta(4) is not None       # written
    assert screen._meta[4] is not None                # UI refreshed
    assert "Saved to Slot 5" in screen._toast[0]
    assert screen.result is None                      # save doesn't exit

    # Switch to the Load tab: the same click now loads the slot
    screen._set_mode("load")
    screen._activate_slot(4)
    assert screen.result == 4 and screen.running is False


def test_slot_meta_has_date_and_time(saves, game):
    SaveManager.save_game(game, slot=2)
    meta = SaveManager.slot_meta(2)
    assert meta["date"] and meta["time"]
    assert meta["time"] in meta["when"]
