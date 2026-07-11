import argparse
import random

import pygame

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
from screens.main_menu import MainMenu
from managers.save_manager import SaveManager


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
    random.seed(setup["seed"])
    if setup["mode"] == "spectate":
        game = Game(mode="ai_spectator", player_count=max(2, setup["opponents"] + 1))
    else:
        game = Game(mode="human_1v1", player_count=setup["opponents"] + 1)
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
    settings.apply_to_game(game)  # volume/mute + default speed (§8.2)
    game.game_speed = max(MIN_GAME_SPEED, min(MAX_GAME_SPEED, setup.get("speed", 1)))
    return game


def main():
    args = parse_args()
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    resolution = (_config.SCREEN_WIDTH, _config.SCREEN_HEIGHT)
    screen = pygame.display.set_mode(resolution)

    if args.spectate:
        launch_spectator(player_count=args.players, speed=args.speed, seed=args.seed)
        pygame.quit()
        return

    while True:
        menu = MainMenu(screen)
        choice = menu.run()

        if choice == "exit":
            break
        elif choice == "start":
            from screens.match_setup import MatchSetupScreen

            setup = MatchSetupScreen(screen).run()
            if setup:
                game = create_game_from_setup(setup)
                game.run()
        elif choice == "spectate":
            launch_spectator(player_count=args.players, speed=args.speed, seed=args.seed)
        elif choice == "load":
            game = Game()
            settings.apply_to_game(game)  # before load: the save's speed wins
            success, msg = SaveManager.load_game(game, slot=0)
            if success:
                game.run()
        elif choice == "settings":
            from screens.settings_menu import SettingsMenu

            SettingsMenu(screen).run()
            settings.load()  # pick up what the screen saved

        # Reset display mode in case game modified it
        screen = pygame.display.set_mode(resolution)

    pygame.quit()


if __name__ == "__main__":
    main()
