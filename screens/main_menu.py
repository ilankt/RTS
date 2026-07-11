import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from managers.sound_manager import music_player
# Re-exported for callers/tests that import them from here
from screens.theme import splash_background, draw_splash  # noqa: F401


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
            ("Spectate AI Battle", "spectate"),
            ("Load Game", "load"),
            ("Settings", "settings"),
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
                elif event.type == pygame.MOUSEMOTION:
                    # Hover moves the ONE selection (keyboard and mouse share
                    # it — no double highlight)
                    for i in range(len(self.options)):
                        if self._get_option_rect(i).collidepoint(event.pos):
                            self.selected_index = i
                            break
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mouse_pos = pygame.mouse.get_pos()
                    for i, (_, action) in enumerate(self.options):
                        rect = self._get_option_rect(i)
                        if rect.collidepoint(mouse_pos):
                            self.result = action
                            self.running = False
            
            music_player.update()  # advance the menu playlist between tracks
            self.draw()
            pygame.display.flip()
            clock.tick(60)

        return self.result
    
    def _get_option_rect(self, index):
        """Fixed-size framed button rect for an option."""
        start_y = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        return pygame.Rect(SCREEN_WIDTH // 2 - 180,
                           start_y + index * spacing - 23, 360, 46)
    
    def draw(self):
        """Draw the menu over the splash art (falls back to the flat bg)."""
        background = splash_background()
        if background is not None:
            self.screen.blit(background, (0, 0))
            # Panel behind title + options so text stays readable over
            # the busy art (textured via the theme when the art exists)
            from screens import theme
            panel_rect = pygame.Rect(
                SCREEN_WIDTH // 2 - 280, SCREEN_HEIGHT // 3 - 70,
                560, SCREEN_HEIGHT - (SCREEN_HEIGHT // 3 - 70) - 90)
            theme.draw_panel(self.screen, panel_rect)
        else:
            self.screen.fill(self.bg_color)

        # Title (with a drop shadow so it pops off the art)
        shadow = self.font_large.render("RTS Game", True, (15, 15, 15))
        title = self.font_large.render("RTS Game", True, self.title_color)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))
        self.screen.blit(shadow, title_rect.move(3, 3))
        self.screen.blit(title, title_rect)
        
        # Options — framed buttons; exactly one highlighted (hover moves it)
        from screens import theme

        for i, (text, action) in enumerate(self.options):
            theme.draw_action_row(self.screen, self._get_option_rect(i), text,
                                  i == self.selected_index, self.font_medium,
                                  primary=(action == "start"))
        
        # Controls hint (on a small backdrop — the art below is busy)
        hint = self.font_small.render("Use Arrow Keys / Mouse to navigate, Enter / Click to select", True, (170, 170, 170))
        hint_rect = hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60))
        backdrop = pygame.Surface(hint_rect.inflate(20, 8).size, pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 140))
        self.screen.blit(backdrop, hint_rect.inflate(20, 8).topleft)
        self.screen.blit(hint, hint_rect)
        
        # Version
        version = self.font_small.render("v1.0 - Improvement Plan Build", True, (170, 170, 170))
        version_rect = version.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 30))
        backdrop = pygame.Surface(version_rect.inflate(20, 8).size, pygame.SRCALPHA)
        backdrop.fill((0, 0, 0, 140))
        self.screen.blit(backdrop, version_rect.inflate(20, 8).topleft)
        self.screen.blit(version, version_rect)
