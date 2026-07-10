"""Settings screen (§8.2): resolution, volume, sound, default game speed.

Same row-cycling interaction as the match-setup screen. Saves on Back.
Resolution takes effect on restart (layout constants are baked at import
time until the §8.2 resolution-independence rework).
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.settings import Settings, RESOLUTION_CHOICES


class SettingsMenu:
    def __init__(self, screen):
        if not pygame.font.get_init():
            pygame.font.init()
        self.screen = screen
        self.font_large = pygame.font.Font(None, 56)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)

        self.settings = Settings()
        self.rows = [
            ("Resolution", "resolution"),
            ("Volume", "volume"),
            ("Sound", "sound_enabled"),
            ("Default game speed", "default_game_speed"),
            ("Colorblind team colors", "colorblind_palette"),
            ("Back (saves)", None),
        ]
        self.selected_index = 0

        self.bg_color = (20, 20, 30)
        self.title_color = (200, 180, 100)
        self.option_color = (200, 200, 200)
        self.selected_color = (255, 255, 100)
        self.hint_color = (100, 100, 100)

    # --- Value cycling -----------------------------------------------------
    def _adjust(self, key, direction):
        if key == "resolution":
            index = RESOLUTION_CHOICES.index(self.settings.get("resolution"))
            self.settings.set("resolution", list(
                RESOLUTION_CHOICES[(index + direction) % len(RESOLUTION_CHOICES)]
            ))
        elif key == "volume":
            volume = round(self.settings.get("volume") + direction * 0.1, 1)
            self.settings.set("volume", min(1.0, max(0.0, volume)))
        elif key in ("sound_enabled", "colorblind_palette"):
            self.settings.set(key, not self.settings.get(key))
        elif key == "default_game_speed":
            speed = self.settings.get("default_game_speed") + direction
            self.settings.set("default_game_speed", float(min(5, max(1, int(speed)))))

    def _value_text(self, key):
        if key == "resolution":
            w, h = self.settings.get("resolution")
            return f"{w} x {h} (restart)"
        if key == "volume":
            return f"{int(self.settings.get('volume') * 100)}%"
        if key == "sound_enabled":
            return "On" if self.settings.get("sound_enabled") else "Off"
        if key == "colorblind_palette":
            return ("On" if self.settings.get("colorblind_palette") else "Off") + " (restart)"
        if key == "default_game_speed":
            return f"{self.settings.get('default_game_speed'):.0f}x"
        return ""

    # --- Loop ---------------------------------------------------------------
    def run(self):
        """Returns the saved Settings (or the unsaved ones on window close)."""
        clock = pygame.time.Clock()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return self.settings
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.settings.save()
                        return self.settings
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self.selected_index = (self.selected_index - 1) % len(self.rows)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected_index = (self.selected_index + 1) % len(self.rows)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        self._row_adjust(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._row_adjust(1)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        label, key = self.rows[self.selected_index]
                        if key is None:
                            self.settings.save()
                            return self.settings
                        self._row_adjust(1)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for i, (label, key) in enumerate(self.rows):
                        if self._row_rect(i).collidepoint(pygame.mouse.get_pos()):
                            self.selected_index = i
                            if key is None:
                                self.settings.save()
                                return self.settings
                            self._row_adjust(1)
            self.draw()
            pygame.display.flip()
            clock.tick(60)

    def _row_adjust(self, direction):
        _label, key = self.rows[self.selected_index]
        if key is not None:
            self._adjust(key, direction)

    # --- Drawing ------------------------------------------------------------
    def _row_rect(self, index):
        y = SCREEN_HEIGHT // 3 + index * 52
        return pygame.Rect(SCREEN_WIDTH // 2 - 260, y - 18, 520, 42)

    def draw(self):
        self.screen.fill(self.bg_color)
        title = self.font_large.render("Settings", True, self.title_color)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 5)))

        mouse_pos = pygame.mouse.get_pos()
        for i, (label, key) in enumerate(self.rows):
            rect = self._row_rect(i)
            selected = i == self.selected_index or rect.collidepoint(mouse_pos)
            color = self.selected_color if selected else self.option_color
            if selected:
                pygame.draw.rect(self.screen, (60, 60, 80), rect, border_radius=5)
                pygame.draw.rect(self.screen, self.selected_color, rect, 2, border_radius=5)

            if key is None:
                text = self.font_medium.render(label, True, color)
                self.screen.blit(text, text.get_rect(center=rect.center))
            else:
                label_surface = self.font_medium.render(label, True, color)
                self.screen.blit(label_surface, (rect.x + 14, rect.y + 6))
                value_surface = self.font_medium.render(f"< {self._value_text(key)} >", True, color)
                self.screen.blit(value_surface, (rect.right - value_surface.get_width() - 14, rect.y + 6))

        hint = self.font_small.render(
            "Arrows to navigate/change - Enter/Esc saves and goes back",
            True, self.hint_color,
        )
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 50)))
