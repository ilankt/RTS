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


def test_pause_menu_click_actions(screen):
    """The pause menu owns the mouse: Resume unpauses, Quit exits to the
    menu loop, and gameplay clicks are blocked while paused."""
    import random
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")

    game.game_paused = True

    # Gameplay clicks are blocked: clicking a worker while paused must not
    # select it
    worker.selected = False
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)
    game._handle_mouse_down(event)
    assert worker.selected is False

    # Resume row unpauses (click at the row's center)
    resume_rect = game._pause_option_rect(0)
    pygame.mouse.set_pos(resume_rect.center)
    game._handle_pause_menu_click(resume_rect.center)
    assert game.game_paused is False

    # Quit row leaves the match loop
    game.game_paused = True
    quit_rect = game._pause_option_rect(2)
    game._handle_pause_menu_click(quit_rect.center)
    assert game.running is False
    assert game.game_paused is False

    # Drawing the overlay must not raise
    game.game_paused = True
    game._draw_pause_overlay()


def test_settings_persist_immediately_on_change(screen, tmp_path):
    """Every adjustment writes to disk right away — closing the app without
    touching Back must not lose settings (user request)."""
    from core.settings import Settings
    from screens.settings_menu import SettingsMenu

    path = str(tmp_path / "settings.json")
    menu = SettingsMenu(screen)
    menu.settings = Settings(path=path)

    menu.selected_index = next(i for i, (_l, key) in enumerate(menu.rows)
                               if key == "fullscreen")
    menu._row_adjust(1)  # toggle fullscreen On — no Back, no explicit save

    assert Settings(path=path).get("fullscreen") is True

    menu.selected_index = next(i for i, (_l, key) in enumerate(menu.rows)
                               if key == "music_volume")
    menu._row_adjust(1)
    assert Settings(path=path).get("music_volume") == pytest.approx(0.5)


def test_fullscreen_setting_and_display_flags(tmp_path):
    from core.settings import Settings

    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    assert settings.get("fullscreen") is False  # default: windowed
    assert settings.display_flags() == 0

    settings.set("fullscreen", True)
    assert settings.display_flags() == (pygame.FULLSCREEN | pygame.SCALED)
    settings.save()
    assert Settings(path=path).get("fullscreen") is True
