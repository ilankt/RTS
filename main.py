import argparse
import os
import random
import sys

import pygame

# When frozen by PyInstaller, the bundled assets/data are unpacked to a temp
# dir (sys._MEIPASS). Chdir there so every relative "assets/..." / "data/..."
# read across the codebase resolves. Writable files (saves, settings, debug)
# use absolute paths under %LOCALAPPDATA% via core.app_paths, so they are
# unaffected by this. No-op when running from source.
if getattr(sys, "frozen", False):
    os.chdir(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))

# Apply persisted settings BEFORE the game/UI modules import the screen
# constants by value (§8.2.1 Phase D: apply_resolution also recomputes the
# derived map-view size, so every anchored layout scales with the window;
# a resolution change takes effect at startup).
import core.config as _config
from core.settings import Settings

settings = Settings()
_config.apply_resolution(*settings.get("resolution"))
if settings.get("colorblind_palette"):
    # In-place so modules that imported the list by value see the swap too
    _config.PLAYER_COLORS[:] = _config.PLAYER_COLORS_COLORBLIND

from core.config import MIN_GAME_SPEED, MAX_GAME_SPEED
from core.game import Game
from screens.main_menu import MainMenu, draw_splash
from managers.save_manager import SaveManager
from managers.sound_manager import music_player


def sync_menu_music():
    """Menu vibe (§8.5): loop the menu theme, matching the settings."""
    settings.load()  # the pause-screen settings may have changed on disk
    if settings.get("sound_enabled"):
        music_player.set_volume(settings.get("music_volume"))
        music_player.play_menu()
    else:
        music_player.stop()


def parse_args():
    parser = argparse.ArgumentParser(description="RTS game")
    parser.add_argument(
        "--spectate",
        action="store_true",
        help="Skip the menu and watch AI players fight each other.",
    )
    parser.add_argument(
        "--players",
        type=int,
        default=4,
        help="AI player count for --spectate (2-8, default 4).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help=f"Starting game speed ({MIN_GAME_SPEED:.0f}-{MAX_GAME_SPEED:.0f}); adjust in-game with [ and ].",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Map/personality RNG seed for reproducible matches.",
    )
    return parser.parse_args()


def launch_spectator(player_count=4, speed=None, seed=None):
    if seed is not None:
        random.seed(seed)
    game = Game(mode="ai_spectator", player_count=player_count)
    settings.apply_to_game(game)
    if speed is not None:
        game.game_speed = max(MIN_GAME_SPEED, min(MAX_GAME_SPEED, speed))
    game.run()


def create_game_from_setup(setup):
    """Build a configured Game from a match-setup dict (§7.5)."""
    from core.config import MAP_SIZES

    random.seed(setup["seed"])
    tiles, max_players = MAP_SIZES.get(setup.get("map_size", "medium"),
                                       MAP_SIZES["medium"])
    player_count = max(2, min(setup["opponents"] + 1, max_players))
    if setup["mode"] == "spectate":
        game = Game(mode="ai_spectator", player_count=player_count,
                    map_size=(tiles, tiles))
    else:
        game = Game(mode="human_1v1", player_count=player_count,
                    map_size=(tiles, tiles))
    if setup.get("personality", "random") != "random":
        for player in game.players:
            if not player.human:
                player.ai_personality = setup["personality"]
    for player in game.players:
        if not player.human:
            player.ai_difficulty = setup.get("difficulty", "normal")
    game.victory_condition = setup.get("victory", "annihilation")
    mutator = setup.get("mutator", "none")
    if mutator != "none":
        game.mutators = {mutator}
        if mutator == "revealed_map":
            game.fog_of_war_enabled = False
    # Speed comes from the settings' default + in-game [ ] keys — the
    # match-setup row was removed (user request)
    settings.apply_to_game(game)
    return game


def apply_display_mode():
    """(Re)create the display honoring the fullscreen setting — called at
    startup and whenever the settings screen may have changed it. Uses the
    layout-baked startup resolution, never a pending settings change."""
    return settings.create_display((_config.SCREEN_WIDTH, _config.SCREEN_HEIGHT))


def main():
    args = parse_args()
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    screen = apply_display_mode()

    if args.spectate:
        launch_spectator(player_count=args.players, speed=args.speed, seed=args.seed)
        pygame.quit()
        return

    while True:
        sync_menu_music()
        menu = MainMenu(screen)
        choice = menu.run()

        if choice == "exit":
            break
        elif choice == "start":
            from screens.match_setup import MatchSetupScreen

            setup = MatchSetupScreen(screen).run()
            if setup:
                draw_splash(screen, "Preparing the battlefield...")
                game = create_game_from_setup(setup)
                game.run()
        elif choice == "spectate":
            draw_splash(screen, "Preparing the battlefield...")
            launch_spectator(player_count=args.players, speed=args.speed, seed=args.seed)
        elif choice == "load":
            draw_splash(screen, "Loading...")
            # Build the Game with the save's map size so restored objects
            # stay in bounds (terrain itself still regenerates — known gap)
            game = Game(map_size=SaveManager.peek_map_size(slot=0))
            settings.apply_to_game(game)  # before load: the save's speed wins
            success, msg = SaveManager.load_game(game, slot=0)
            if success:
                game.run()
        elif choice == "settings":
            from screens.settings_menu import SettingsMenu

            SettingsMenu(screen).run()
            settings.load()  # pick up what the screen saved

        # Reset the display in case the game or settings changed it
        # (also applies a fullscreen toggle made in the settings screen)
        settings.load()
        screen = apply_display_mode()

    pygame.quit()


if __name__ == "__main__":
    main()
