"""Settings screen (§8.2): resolution, volume, sound, default game speed.

Same row-cycling interaction as the match-setup screen. Saves on Back.
Resolution takes effect on restart (layout constants are baked at import
time until the §8.2 resolution-independence rework).
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.settings import Settings, RESOLUTION_CHOICES
from screens import theme


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
            ("SFX volume", "volume"),
            ("Music volume", "music_volume"),
            ("Sound", "sound_enabled"),
            ("Default game speed", "default_game_speed"),
            ("Colorblind team colors", "colorblind_palette"),
            ("Adaptive difficulty", "adaptive_difficulty"),
            ("Shift-queue batch size", "batch_queue_size"),
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
        elif key in ("volume", "music_volume"):
            volume = round(self.settings.get(key) + direction * 0.1, 1)
            self.settings.set(key, min(1.0, max(0.0, volume)))
        elif key in ("sound_enabled", "colorblind_palette", "adaptive_difficulty"):
            self.settings.set(key, not self.settings.get(key))
        elif key == "default_game_speed":
            speed = self.settings.get("default_game_speed") + direction
            self.settings.set("default_game_speed", float(min(5, max(1, int(speed)))))
        elif key == "batch_queue_size":
            size = self.settings.get("batch_queue_size") + direction
            self.settings.set("batch_queue_size", min(10, max(1, int(size))))

    def _value_text(self, key):
        if key == "resolution":
            w, h = self.settings.get("resolution")
            return f"{w} x {h} (restart)"
        if key in ("volume", "music_volume"):
            return f"{int(self.settings.get(key) * 100)}%"
        if key == "sound_enabled":
            return "On" if self.settings.get("sound_enabled") else "Off"
        if key == "colorblind_palette":
            return ("On" if self.settings.get("colorblind_palette") else "Off") + " (restart)"
        if key == "adaptive_difficulty":
            return "On" if self.settings.get("adaptive_difficulty") else "Off"
        if key == "default_game_speed":
            return f"{self.settings.get('default_game_speed'):.0f}x"
        if key == "batch_queue_size":
            return f"{self.settings.get('batch_queue_size')} units"
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
                if event.type == pygame.MOUSEMOTION:
                    # Hover moves the ONE selection (no keyboard/mouse
                    # double highlight)
                    for i in range(len(self.rows)):
                        if self._row_rect(i).collidepoint(event.pos):
                            self.selected_index = i
                            break
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
    ROWS_TOP_OFFSET = 88   # first row's offset inside the panel
    ROW_PITCH = 48
    ROW_W = 530

    def _panel_rect(self):
        height = self.ROWS_TOP_OFFSET + len(self.rows) * self.ROW_PITCH + 36
        top = max(12, (SCREEN_HEIGHT - height) // 2)
        return pygame.Rect(SCREEN_WIDTH // 2 - 320, top, 640, height)

    def _row_rect(self, index):
        panel = self._panel_rect()
        y = panel.y + self.ROWS_TOP_OFFSET + index * self.ROW_PITCH
        if index == len(self.rows) - 1:
            y += 10  # breathe before the Back action
        return pygame.Rect(SCREEN_WIDTH // 2 - self.ROW_W // 2, y,
                           self.ROW_W, self.ROW_PITCH - 6)

    def draw(self):
        theme.draw_menu_scene(self.screen, "Settings", self._panel_rect())

        for i, (label, key) in enumerate(self.rows):
            rect = self._row_rect(i)
            selected = i == self.selected_index
            if key is None:
                theme.draw_action_row(self.screen, rect, label, selected,
                                      self.font_medium)
            else:
                theme.draw_setting_row(self.screen, rect, label,
                                       self._value_text(key), selected,
                                       self.font_medium)

        theme.draw_hint(self.screen,
                        "Arrows navigate/change · Enter/Esc saves and goes back")
