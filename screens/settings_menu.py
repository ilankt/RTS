"""Settings screen (§8.2), split into categories 2026-07-26.

One flat list stopped scaling: the panel is sized from the row count, so every
new setting ate the bottom margin until `Back` fell off a 720p screen. Settings
now live in categories — the screen opens on a hub (Video / Audio / Gameplay)
and each category shows only its own rows, so adding a setting costs one row in
one category instead of one row in everything.

Same row-cycling interaction as the match-setup screen; every change saves
immediately. Resolution takes effect on restart (layout constants are baked at
import time until the §8.2 resolution-independence rework).
"""
import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
from core.settings import Settings, RESOLUTION_CHOICES
from screens import theme


# A row is (label, key). `key` is a settings key, None for the Back action, or
# CATEGORY_PREFIX + name for a row that opens a category — the same
# string-action idiom the pause menu uses for its rows.
CATEGORY_PREFIX = "category:"

# Labels are kept SHORT on purpose: the screen shares one panel width with the
# pause menu (theme.PANEL_W), and the long forms ("Colorblind team colors")
# needed 514px of row against the 420px that width allows. `*` marks a setting
# that needs a restart; the hint spells it out.
CATEGORIES = [
    ("Video", [
        ("Resolution", "resolution"),
        ("Fullscreen", "fullscreen"),
        ("Object shadows", "shadows"),
        ("Ambient effects", "ambient"),
        ("Colorblind colors", "colorblind_palette"),
    ]),
    ("Audio", [
        ("SFX volume", "volume"),
        ("Music volume", "music_volume"),
        ("Sound", "sound_enabled"),
    ]),
    ("Gameplay", [
        ("Game speed", "default_game_speed"),
        ("Adaptive difficulty", "adaptive_difficulty"),
        ("Shift-queue size", "batch_queue_size"),
        ("Gameplay tips", "show_onboarding"),
        ("Replay tips", "onboarding_force"),
    ]),
]

CATEGORY_ROWS = dict(CATEGORIES)
CATEGORY_NAMES = [name for name, _rows in CATEGORIES]


def category_of(key):
    """The category a navigation row opens, or None for any other row."""
    if isinstance(key, str) and key.startswith(CATEGORY_PREFIX):
        return key[len(CATEGORY_PREFIX):]
    return None


class SettingsMenu:
    def __init__(self, screen, backdrop=None):
        """`backdrop` is a snapshot to sit over (the paused battlefield). With
        it the screen draws as an in-game modal; without it, as a main-menu
        page on the splash art."""
        if not pygame.font.get_init():
            pygame.font.init()
        self.screen = screen
        self.backdrop = backdrop
        self.font_large = pygame.font.Font(None, 56)
        self.font_medium = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 24)

        self.settings = Settings()
        self.category = None      # None = the hub; else a CATEGORY_NAMES entry
        self.selected_index = 0
        self._hub_index = 0       # where to land when a category closes

        self.bg_color = (20, 20, 30)
        self.title_color = (200, 180, 100)
        self.option_color = (200, 200, 200)
        self.selected_color = (255, 255, 100)
        self.hint_color = (100, 100, 100)

    # --- Navigation ---------------------------------------------------------
    @property
    def rows(self):
        """The rows currently on screen — the category list at the hub, or one
        category's settings. Always ends in Back."""
        if self.category is None:
            return ([(name, CATEGORY_PREFIX + name) for name in CATEGORY_NAMES]
                    + [("Back", None)])
        return CATEGORY_ROWS[self.category] + [("Back", None)]

    def open_category(self, name):
        """Enter a category. Also the seam tests drive instead of synthesising
        clicks on the hub."""
        if name not in CATEGORY_ROWS:
            raise KeyError(f"unknown settings category: {name}")
        self._hub_index = self.selected_index
        self.category = name
        self.selected_index = 0

    def close_category(self):
        """Back out to the hub, landing on the category just left."""
        self.category = None
        self.selected_index = self._hub_index

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
        elif key in ("sound_enabled", "colorblind_palette",
                     "adaptive_difficulty", "fullscreen",
                     "show_onboarding", "onboarding_force", "shadows",
                     "ambient"):
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
            return f"{w} x {h} *"
        if key in ("volume", "music_volume"):
            return f"{int(self.settings.get(key) * 100)}%"
        if key == "fullscreen":
            return "On" if self.settings.get("fullscreen") else "Off"
        if key == "sound_enabled":
            return "On" if self.settings.get("sound_enabled") else "Off"
        if key == "colorblind_palette":
            return ("On" if self.settings.get("colorblind_palette") else "Off") + " *"
        if key == "shadows":
            return "On" if self.settings.get("shadows") else "Off"
        if key == "ambient":
            return "On" if self.settings.get("ambient") else "Off"
        if key == "adaptive_difficulty":
            return "On" if self.settings.get("adaptive_difficulty") else "Off"
        if key == "show_onboarding":
            return "On" if self.settings.get("show_onboarding") else "Off"
        if key == "onboarding_force":
            return "Armed" if self.settings.get("onboarding_force") else "Off"
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
                        # Esc steps UP one level, so it can't drop the player
                        # out of settings entirely from inside a category.
                        self.settings.save()
                        if self.category is not None:
                            self.close_category()
                        else:
                            return self.settings
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self.selected_index = (self.selected_index - 1) % len(self.rows)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self.selected_index = (self.selected_index + 1) % len(self.rows)
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        self._row_adjust(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._row_adjust(1)
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self._activate(self.selected_index):
                            return self.settings
                if event.type == pygame.MOUSEMOTION:
                    # Hover moves the ONE selection (no keyboard/mouse
                    # double highlight)
                    for i in range(len(self.rows)):
                        if self._row_rect(i).collidepoint(event.pos):
                            self.selected_index = i
                            break
                if event.type == pygame.MOUSEBUTTONDOWN:
                    for i in range(len(self.rows)):
                        if self._row_rect(i).collidepoint(event.pos):
                            self.selected_index = i
                            if self._activate(i, click_x=event.pos[0]):
                                return self.settings
                            break
            self.draw()
            pygame.display.flip()
            clock.tick(60)

    def _activate(self, index, click_x=None):
        """Act on a row. Returns True when the menu should close.

        Shared by the keyboard and the mouse so the two can't drift apart;
        `click_x` picks the adjuster direction for a mouse press and is None
        for Enter (which always steps up).
        """
        _label, key = self.rows[index]
        category = category_of(key)
        if category is not None:
            self.open_category(category)
            return False
        if key is None:                       # Back
            self.settings.save()
            if self.category is not None:
                self.close_category()
                return False
            return True
        if click_x is None:
            step = 1
        else:
            # Click the left arrow/half to step down, the right to step up
            # (not always up)
            value_w = self.font_medium.size(self._value_text(key))[0]
            step = theme.setting_click_step(self._row_rect(index), value_w,
                                            click_x)
        self._row_adjust(step)
        return False

    def _row_adjust(self, direction):
        _label, key = self.rows[self.selected_index]
        if key is None or category_of(key) is not None:
            return
        self._adjust(key, direction)
        # Persist immediately — no "save on back" step to forget
        self.settings.save()
        if key == "music_volume":
            # Live preview: the menu theme is playing right now
            from managers.sound_manager import music_player
            music_player.set_volume(self.settings.get("music_volume"))

    # --- Drawing ------------------------------------------------------------
    ROWS_TOP_OFFSET = 88   # first row's offset inside the panel
    ROW_PITCH = 48
    LAST_ROW_GAP = 10      # breathing room above the Back action

    @property
    def ROW_W(self):
        return theme.ROW_W  # shared with the pause menu

    def _row_pitch(self):
        """Row spacing, compressed if a list ever outgrows a short screen.

        Categories make this a safety net rather than the everyday path: no
        category is near the limit today. It stays because the panel is still
        sized from the row COUNT, and 720p is still a supported resolution —
        the failure it guards is `Back` falling off the bottom, and Back is
        the only *visible* way out (Esc works, but nothing on screen says so).
        """
        rows = self.rows
        available = (SCREEN_HEIGHT - 24 - self.ROWS_TOP_OFFSET - 36
                     - self.LAST_ROW_GAP)
        if len(rows) * self.ROW_PITCH <= available:
            return self.ROW_PITCH
        return max(30, available // len(rows))

    def _panel_rect(self):
        height = (self.ROWS_TOP_OFFSET + len(self.rows) * self._row_pitch()
                  + 36)
        top = max(12, (SCREEN_HEIGHT - height) // 2)
        return pygame.Rect(SCREEN_WIDTH // 2 - theme.PANEL_W // 2, top,
                           theme.PANEL_W, height)

    def _row_rect(self, index):
        panel = self._panel_rect()
        pitch = self._row_pitch()
        y = panel.y + self.ROWS_TOP_OFFSET + index * pitch
        if index == len(self.rows) - 1:
            y += self.LAST_ROW_GAP  # breathe before the Back action
        return pygame.Rect(SCREEN_WIDTH // 2 - self.ROW_W // 2, y,
                           self.ROW_W, pitch - 6)

    def draw(self):
        title = "Settings" if self.category is None else f"Settings · {self.category}"
        panel = self._panel_rect()
        if self.backdrop is not None:
            theme.draw_modal_scene(self.screen, title, panel, self.backdrop)
        else:
            theme.draw_menu_scene(self.screen, title, panel)

        for i, (label, key) in enumerate(self.rows):
            rect = self._row_rect(i)
            selected = i == self.selected_index
            # Category and Back rows are ACTIONS: drawing them as setting rows
            # would put ◀ ▶ adjuster arrows on something that isn't a value.
            if key is None or category_of(key) is not None:
                theme.draw_action_row(self.screen, rect, label, selected,
                                      self.font_medium)
            else:
                theme.draw_setting_row(self.screen, rect, label,
                                       self._value_text(key), selected,
                                       self.font_medium)

        if self.category is None:
            hint = "Arrows navigate · Enter opens · Esc goes back"
        elif any(self._value_text(key).endswith(" *")
                 for _label, key in self.rows if key is not None):
            hint = "Arrows navigate/change · Esc goes back · * needs a restart"
        else:
            hint = "Arrows navigate/change · Esc goes back"
        # Inside a modal the hint sits on the panel, not at the screen bottom,
        # where it would float over the battlefield away from the dialog.
        y = self._panel_rect().bottom - 26 if self.backdrop is not None else None
        theme.draw_hint(self.screen, hint, y=y)
