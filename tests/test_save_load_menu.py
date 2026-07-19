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


# --- Delete (2026-07-19) --------------------------------------------------- #

def test_delete_save_removes_the_slot(saves, game):
    SaveManager.save_game(game, slot=1)
    assert SaveManager.slot_meta(1) is not None

    ok, message = SaveManager.delete_save(1)
    assert ok and "Slot 2" in message
    assert SaveManager.slot_meta(1) is None

    # Deleting an already-empty slot reports rather than raising
    ok, message = SaveManager.delete_save(1)
    assert ok is False and "empty" in message.lower()


def test_delete_needs_two_clicks_and_esc_cancels(saves, game):
    SaveManager.save_game(game, slot=2)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=game)

    # First press only ARMS — the save must survive a single stray click
    screen._request_delete(2)
    assert screen._confirm_delete == 2
    assert SaveManager.slot_meta(2) is not None, "one click must not delete"

    # Esc cancels the pending delete and does NOT close the screen
    esc = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    screen._handle(esc)
    assert screen._confirm_delete is None
    assert screen.running is True
    assert SaveManager.slot_meta(2) is not None

    # Arm again, then confirm
    screen._request_delete(2)
    screen._request_delete(2)
    assert SaveManager.slot_meta(2) is None
    assert screen._meta[2] is None          # UI refreshed
    assert screen._confirm_delete is None
    assert "Deleted Slot 3" in screen._toast[0]

    # A second Esc now leaves the screen as usual
    screen._handle(esc)
    assert screen.running is False


def test_changing_slot_disarms_a_pending_delete(saves, game):
    SaveManager.save_game(game, slot=0)
    SaveManager.save_game(game, slot=1)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=game)
    screen._request_delete(0)
    assert screen._confirm_delete == 0

    screen._handle(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    assert screen._confirm_delete is None, "moving off the slot must disarm it"

    # ...so the next delete press arms rather than deleting
    screen._request_delete(0)
    assert SaveManager.slot_meta(0) is not None


def test_delete_button_only_exists_on_occupied_slots(saves, game):
    SaveManager.save_game(game, slot=4)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    occupied = screen.slots.index(4)
    empty = screen.slots.index(5)

    assert screen._delete_rect(occupied) is not None
    assert screen._delete_rect(empty) is None, "nothing to delete on an empty slot"

    # Available load-only too (the main menu hides the tab strip entirely)
    assert screen.can_save is False and screen._tab_rects() == {}

    # The ✕ sits inside the row, and text is pulled in so it can't run under it
    assert screen._slot_rect(occupied).contains(screen._delete_rect(occupied))
    assert screen._text_right(occupied) <= screen._delete_rect(occupied).left
    assert screen._text_right(empty) > screen._text_right(occupied)


def test_clicking_the_x_deletes_instead_of_loading(saves, game):
    SaveManager.save_game(game, slot=3)
    pygame.display.set_mode((320, 240))
    from screens.save_load_menu import SaveLoadScreen

    screen = SaveLoadScreen(screen=pygame.display.get_surface(), game=None)
    index = screen.slots.index(3)
    click_x = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1,
                                 pos=screen._delete_rect(index).center)

    screen._handle(click_x)                 # arms
    assert screen._confirm_delete == 3
    assert screen.result is None, "the ✕ must not trigger the row's load"
    assert screen.running is True

    screen._handle(click_x)                 # confirms
    assert SaveManager.slot_meta(3) is None
    assert screen.result is None
