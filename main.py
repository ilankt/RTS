import pygame
from core.game import Game
from screens.main_menu import MainMenu
from managers.save_manager import SaveManager

def main():
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    
    while True:
        menu = MainMenu(screen)
        choice = menu.run()
        
        if choice == "exit":
            break
        elif choice == "start":
            game = Game()
            game.run()
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

