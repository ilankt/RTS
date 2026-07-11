import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from managers.sound_manager import music_player

SPLASH_PATH = "assets/ui/splash_background.png"
_splash_cache = {}  # (w, h) -> cover-scaled surface


def splash_background(size=None):
    """The splash art cover-scaled + center-cropped to `size` (defaults to
    the screen). Returns None if the art is missing."""
    size = size or (SCREEN_WIDTH, SCREEN_HEIGHT)
    cached = _splash_cache.get(size)
    if cached is not None:
        return cached
    try:
        art = pygame.image.load(SPLASH_PATH).convert()
    except Exception:
        return None
    width, height = size
    scale = max(width / art.get_width(), height / art.get_height())
    scaled = pygame.transform.smoothscale(
        art, (int(art.get_width() * scale) + 1, int(art.get_height() * scale) + 1))
    surface = pygame.Surface(size)
    surface.blit(scaled, ((width - scaled.get_width()) // 2,
                          (height - scaled.get_height()) // 2))
    _splash_cache[size] = surface
    return surface


def draw_splash(screen, caption=None):
    """Full-screen splash with an optional caption — used as the loading
    screen while a match is being generated."""
    background = splash_background(screen.get_size())
    if background is not None:
        screen.blit(background, (0, 0))
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        overlay.fill((10, 10, 20, 90))
        screen.blit(overlay, (0, 0))
    else:
        screen.fill((20, 20, 30))
    if caption:
        font = pygame.font.Font(None, 40)
        text = font.render(caption, True, (240, 225, 170))
        rect = text.get_rect(center=(screen.get_width() // 2,
                                     screen.get_height() - 80))
        backdrop = rect.inflate(30, 14)
        panel = pygame.Surface(backdrop.size, pygame.SRCALPHA)
        panel.fill((0, 0, 0, 150))
        screen.blit(panel, backdrop.topleft)
        screen.blit(text, rect)
    pygame.display.flip()


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
        """Get the rectangle for an option at the given index"""
        start_y = SCREEN_HEIGHT // 2 - 40
        spacing = 60
        text_surface = self.font_medium.render(self.options[index][0], True, self.option_color)
        text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, start_y + index * spacing))
        # Expand rect for easier clicking
        return text_rect.inflate(40, 20)
    
    def draw(self):
        """Draw the menu over the splash art (falls back to the flat bg)."""
        background = splash_background()
        if background is not None:
            self.screen.blit(background, (0, 0))
            # Scrim column behind title + options so text stays readable
            # over the busy art
            scrim = pygame.Surface((560, SCREEN_HEIGHT), pygame.SRCALPHA)
            scrim_rect = scrim.get_rect(centerx=SCREEN_WIDTH // 2)
            pygame.draw.rect(
                scrim, (12, 12, 22, 165),
                pygame.Rect(0, SCREEN_HEIGHT // 3 - 70,
                            560, SCREEN_HEIGHT - (SCREEN_HEIGHT // 3 - 70) - 90),
                border_radius=16,
            )
            self.screen.blit(scrim, scrim_rect)
        else:
            self.screen.fill(self.bg_color)

        # Title (with a drop shadow so it pops off the art)
        shadow = self.font_large.render("RTS Game", True, (15, 15, 15))
        title = self.font_large.render("RTS Game", True, self.title_color)
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3))
        self.screen.blit(shadow, title_rect.move(3, 3))
        self.screen.blit(title, title_rect)
        
        # Options — exactly one highlighted: selected_index (hover moves it)
        start_y = SCREEN_HEIGHT // 2 - 40
        spacing = 60

        for i, (text, action) in enumerate(self.options):
            rect = self._get_option_rect(i)
            is_selected = (i == self.selected_index)

            if is_selected:
                color = self.selected_color
                # Draw selection indicator
                pygame.draw.rect(self.screen, (60, 60, 80), rect, border_radius=5)
                pygame.draw.rect(self.screen, self.selected_color, rect, 2, border_radius=5)
            else:
                color = self.option_color
            
            text_surface = self.font_medium.render(text, True, color)
            text_rect = text_surface.get_rect(center=(SCREEN_WIDTH // 2, start_y + i * spacing))
            self.screen.blit(text_surface, text_rect)
        
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
