import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT


class MainMenu:
    """Simple main menu with Start Game, Load Game, and Exit options"""
    
    def __init__(self, screen):
        if not pygame.font.get_init():
            pygame.font.init()

        self.screen = screen
        self.font_large = pygame.font.Font(None, 64)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)
        
        self.options = [
            ("Start Game", "start"),
            ("Load Game", "load"),
            ("Exit", "exit")
        ]
        self.selected_index = 0
        self.running = True
        self.result = None
        
        # Colors
        self.bg_color = (20, 20, 30)
        self.title_color = (200, 180, 100)
        self.option_color = (200, 200, 200)
        self.selected_color = (255, 255, 100)
        self.version_color = (100, 100, 100)
    
    def run(self):
        """Run the menu loop until an option is selected"""
        clock = pygame.time.Clock()
        
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.result = "exit"
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP or event.key == pygame.K_w:
                        self.selected_index = (self.selected_index - 1) % len(self.options)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_s:
                        self.selected_index = (self.selected_index + 1) % len(self.options)
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                        self.result = self.options[self.selected_index][1]
                        self.running = False
                    elif event.key == pygame.K_ESCAPE:
                        self.result = "exit"
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = pygame.mouse.get_pos()
                    for i, (_, action) in enumerate(self.options):
                        rect = self._get_option_rect(i)
                        if rect.collidepoint(mouse_pos):
                            self.result = action
                            self.running = False
            
            self.draw()
            pygame.display.flip()
            clock.tick(60)
        
        return self.result
    
    def _get_option_rect(self, index):
        """Get the rectangle for an option at the given index"""
        start_y = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        text_surface = self.font_medium.render(self.options[index][0], True, self.option_color)
        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, start_y + index * spacing))
        # Expand rect for easier clicking
        return text_rect.inflate(40, 20)
    
    def draw(self):
        """Draw the menu"""
        self.screen.fill(self.bg_color)
        
        # Title
        title = self.font_large.render("RTS Game", True, self.title_color)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))
        self.screen.blit(title, title_rect)
        
        # Options
        start_y = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        mouse_pos = pygame.mouse.get_pos()
        
        for i, (text, action) in enumerate(self.options):
            # Check hover
            rect = self._get_option_rect(i)
            is_hovered = rect.collidepoint(mouse_pos)
            is_selected = (i == self.selected_index)
            
            if is_selected or is_hovered:
                color = self.selected_color
                # Draw selection indicator
                pygame.draw.rect(self.screen, (60, 60, 80), rect, border_radius=5)
                pygame.draw.rect(self.screen, self.selected_color, rect, 2, border_radius=5)
            else:
                color = self.option_color
            
            text_surface = self.font_medium.render(text, True, color)
            text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, start_y + i * spacing))
            self.screen.blit(text_surface, text_rect)
        
        # Controls hint
        hint = self.font_small.render("Use Arrow Keys / Mouse to navigate, Enter / Click to select", True, self.version_color)
        hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60))
        self.screen.blit(hint, hint_rect)
        
        # Version
        version = self.font_small.render("v1.0 - Improvement Plan Build", True, self.version_color)
        version_rect = version.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30))
        self.screen.blit(version, version_rect)
