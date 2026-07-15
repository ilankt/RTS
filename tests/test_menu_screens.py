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

    # Quit row leaves the match loop (found by action, not a fixed index)
    game.game_paused = True
    quit_index = next(i for i, (_l, a) in enumerate(game.PAUSE_OPTIONS)
                      if a == "quit_to_menu")
    quit_rect = game._pause_option_rect(quit_index)
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
    before = menu.settings.get("fullscreen")
    menu._row_adjust(1)  # toggle fullscreen — no Back, no explicit save

    assert Settings(path=path).get("fullscreen") is (not before)

    menu.selected_index = next(i for i, (_l, key) in enumerate(menu.rows)
                               if key == "music_volume")
    menu._row_adjust(1)
    assert Settings(path=path).get("music_volume") == pytest.approx(0.5)


def test_setting_click_step_splits_at_value_center():
    """The mouse-click adjuster splits a row at its value's center so the
    ◀ value ▶ arrows work: left steps down, right steps up."""
    from screens import theme

    rect = pygame.Rect(100, 0, 530, 42)
    value_w = 30
    center = rect.right - theme.SETTING_VALUE_INSET - value_w / 2
    assert theme.setting_click_step(rect, value_w, center - 5) == -1
    assert theme.setting_click_step(rect, value_w, center + 5) == 1


def test_settings_mouse_click_can_decrease_a_value(screen, tmp_path):
    """User-reported: game speed got stuck at max because every mouse click
    on a settings row stepped UP. A click on the left arrow/half must step
    the value DOWN; the right steps it back up."""
    from core.settings import Settings
    from screens.settings_menu import SettingsMenu

    path = str(tmp_path / "settings.json")
    menu = SettingsMenu(screen)
    menu.settings = Settings(path=path)
    menu.settings.set("default_game_speed", 4.0)

    row = next(i for i, (_l, key) in enumerate(menu.rows)
               if key == "default_game_speed")
    rect = menu._row_rect(row)

    # Click near the left arrow -> step down
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(rect.left + 30, rect.centery)))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    menu.run()
    assert menu.settings.get("default_game_speed") == 3.0

    # Click near the right arrow -> step back up
    menu.settings.set("default_game_speed", 3.0)
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=(rect.right - 20, rect.centery)))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    menu.run()
    assert menu.settings.get("default_game_speed") == 4.0


def test_fullscreen_setting_and_display_flags(tmp_path):
    from core.settings import Settings

    path = str(tmp_path / "settings.json")
    settings = Settings(path=path)
    assert settings.get("fullscreen") is True  # default: fullscreen 1920x1080
    # Scaled fullscreen: render at the logical resolution, GPU-scale to fill
    # the display (reliable across monitors) — not an exclusive mode switch
    assert settings.display_flags() == (pygame.FULLSCREEN | pygame.SCALED)

    settings.set("fullscreen", False)  # windowed is still an option
    assert settings.display_flags() == 0
    settings.save()
    assert Settings(path=path).get("fullscreen") is False


def test_map_size_row_caps_opponents(screen):
    """No 8-player brawls on Tiny: the opponent cap follows the map size,
    and shrinking the map clamps an already-high opponent count."""
    from screens.match_setup import MatchSetupScreen, MAP_SIZE_CHOICES

    setup = MatchSetupScreen(screen)
    assert "speed" not in setup.config          # Game-speed row removed
    assert not any(key == "speed" for _l, key in setup.rows)
    assert setup.config["map_size"] == "medium"

    # Large allows 8 total players -> 7 opponents
    setup.config["map_size"] = "large"
    setup.config["opponents"] = 1
    for _ in range(10):
        setup._adjust("opponents", 1)
    assert setup.config["opponents"] == 7

    # Cycling down to tiny clamps the head count to 2 players total
    while setup.config["map_size"] != "tiny":
        setup._adjust("map_size", 1)
    assert setup.config["opponents"] == 1
    setup._adjust("opponents", 1)
    assert setup.config["opponents"] == 1       # capped, can't grow

    # Word values, with the cap surfaced
    assert setup._value_text("map_size") == "Tiny (up to 2 players)"
    assert MAP_SIZE_CHOICES == ["tiny", "small", "medium", "large", "huge"]


def test_game_accepts_map_size_and_save_remembers_it(screen, tmp_path, monkeypatch):
    import random
    random.seed(97)
    from core.game import Game
    from managers.save_manager import SaveManager

    game = Game(mode="human_1v1", player_count=2, map_size=(45, 45))
    assert (game.game_map.width, game.game_map.height) == (45, 45)
    castles = [b for b in game.buildings if b.name == "castle"]
    assert len(castles) == 2                    # both spawns fit on Tiny

    monkeypatch.setattr(SaveManager, "SAVE_DIR", str(tmp_path))
    SaveManager.save_game(game, slot=3)
    assert SaveManager.peek_map_size(slot=3) == (45, 45)
    assert SaveManager.peek_map_size(slot=9) is None  # no such save
