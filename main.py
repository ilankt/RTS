import argparse
import random

import pygame

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
    if speed is not None:
        game.game_speed = max(MIN_GAME_SPEED, min(MAX_GAME_SPEED, speed))
    game.run()


def main():
    args = parse_args()
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))

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
            game = Game()
            game.run()
        elif choice == "spectate":
            launch_spectator(player_count=args.players, speed=args.speed, seed=args.seed)
        elif choice == "load":
            game = Game()
            success, msg = SaveManager.load_game(game, slot=0)
            if success:
                game.run()

        # Reset display mode in case game modified it
        screen = pygame.display.set_mode((1280, 720))

    pygame.quit()


if __name__ == "__main__":
    main()
