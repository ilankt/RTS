"""Menu screens: keyboard and mouse share ONE selection (user-reported bug:
hovering with the mouse while a different row was keyboard-selected drew two
highlights)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

if not pygame.get_init():
    pygame.init()


@pytest.fixture()
def screen():
    return pygame.display.get_surface() or pygame.display.set_mode((1280, 720))


def test_hover_moves_the_keyboard_selection(screen):
    from screens.main_menu import MainMenu

    menu = MainMenu(screen)
    assert menu.selected_index == 0  # keyboard default: Start Game

    settings_index = next(i for i, (label, _a) in enumerate(menu.options)
                          if label == "Settings")
    hover_pos = menu._get_option_rect(settings_index).center

    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=hover_pos))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

    # Enter must activate the row the mouse moved the selection to —
    # a single shared selection, not two competing highlights
    assert menu.run() == "settings"
    assert menu.selected_index == settings_index


def test_settings_rows_follow_hover(screen):
    from screens.settings_menu import SettingsMenu

    menu = SettingsMenu(screen)
    hover_pos = menu._row_rect(2).center

    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=hover_pos))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    menu.run()
    assert menu.selected_index == 2


def test_match_setup_rows_follow_hover(screen):
    from screens.match_setup import MatchSetupScreen

    setup = MatchSetupScreen(screen)
    hover_pos = setup._row_rect(1).center

    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=hover_pos))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    setup.run()
    assert setup.selected_index == 1
