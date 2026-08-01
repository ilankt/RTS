"""Persistent user settings (§8.2).

Same pattern as core/keybindings.py: defaults here, user diffs in
settings.json. Resolution is applied at app startup (main.py patches
core.config before the UI modules import the screen constants), so a
resolution change takes effect on restart; volume and default speed apply
live to each new Game.
"""
import json
import os

from core.app_paths import user_path
from utils.debug_logger import debug_log

# Relative when run from source; under %LOCALAPPDATA%\RTS when frozen.
SETTINGS_FILE = user_path("settings.json")

RESOLUTION_CHOICES = [[1280, 720], [1600, 900], [1920, 1080]]

# HUD scale (§8.2.2). "auto" matches the 720p design point by screen HEIGHT;
# the explicit steps exist because that is the wrong answer on a wide display —
# at 21:9 the height-matched scale is a third smaller than the width-matched
# one, and which reads "right" is the player's call, not a formula's.
UI_SCALE_CHOICES = ["auto", 1.0, 1.25, 1.5, 1.75, 2.0]

DEFAULTS = {
    "resolution": [1920, 1080],
    "ui_scale": "auto",          # HUD scale; applies on restart like resolution
    "fullscreen": True,          # fullscreen at the DESKTOP resolution (main.py
    # queries it at startup); the resolution setting governs windowed mode
    "volume": 0.3,               # SFX volume, 0.0 - 1.0
    "music_volume": 0.4,         # background music volume (§8.5)
    "sound_enabled": True,
    "default_game_speed": 1.0,   # used when a match doesn't set one
    "colorblind_palette": False,  # Okabe-Ito team colors (§8.7), on restart
    "adaptive_difficulty": False,  # covert DDA (§7.2): AI reaction-time nudges
    "batch_queue_size": 5,        # Shift+production-tile queues N (§8.2.1 B)
    "show_onboarding": True,      # new-player tips + reactive hints master switch
    "onboarding_force": False,    # one-shot: replay tips next match, then self-clears
    "shadows": True,              # blob shadows under objects (off = cheaper)
    "ambient": True,              # §11.3 tree sway, cloud shadows, smoke
}


class Settings:
    def __init__(self, path=SETTINGS_FILE):
        self.path = path
        self.values = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
        self.load()

    def load(self):
        try:
            with open(self.path, "r") as f:
                overrides = json.load(f)
        except (OSError, ValueError):
            return
        for key, value in overrides.items():
            if key not in DEFAULTS:
                continue
            if key == "resolution":
                if list(value) in RESOLUTION_CHOICES:
                    self.values[key] = list(value)
            elif key in ("volume", "music_volume"):
                try:
                    self.values[key] = min(1.0, max(0.0, float(value)))
                except (TypeError, ValueError):
                    pass
            elif key in ("sound_enabled", "colorblind_palette",
                         "adaptive_difficulty", "fullscreen",
                         "show_onboarding", "onboarding_force", "shadows",
                         "ambient"):
                self.values[key] = bool(value)
            elif key == "default_game_speed":
                try:
                    self.values[key] = min(5.0, max(1.0, float(value)))
                except (TypeError, ValueError):
                    pass
            elif key == "batch_queue_size":
                try:
                    self.values[key] = min(10, max(1, int(value)))
                except (TypeError, ValueError):
                    pass
            elif key == "ui_scale":
                if value in UI_SCALE_CHOICES:
                    self.values[key] = value
                else:
                    try:
                        self.values[key] = min(2.0, max(1.0, float(value)))
                    except (TypeError, ValueError):
                        pass

    def save(self):
        """Persist only entries that differ from the defaults."""
        overrides = {k: v for k, v in self.values.items() if DEFAULTS.get(k) != v}
        try:
            if overrides:
                with open(self.path, "w") as f:
                    json.dump(overrides, f, indent=2, sort_keys=True)
            elif os.path.exists(self.path):
                os.remove(self.path)
            return True
        except OSError as e:
            debug_log.log(f"Settings save failed: {e}", "GENERAL")
            return False

    def get(self, key):
        return self.values[key]

    def display_flags(self):
        """pygame.display.set_mode flags for the current settings.
        Fullscreen renders at the logical resolution and lets SDL GPU-scale
        it to fill the display (FULLSCREEN | SCALED) — reliable across
        monitors and driver quirks, unlike an exclusive display-mode switch
        which black-screened / drew off-position on some setups."""
        import pygame

        if self.values["fullscreen"]:
            return pygame.FULLSCREEN | pygame.SCALED
        return 0

    def create_display(self, resolution):
        """set_mode honoring the fullscreen setting.

        Fullscreen uses FULLSCREEN | SCALED: the game renders at the logical
        `resolution` and SDL scales it to fill the physical display. This
        avoids the exclusive display-mode switch that stopped producing a
        working fullscreen on some drivers, and it keeps screen.get_size()
        (and therefore the baked HUD layout + mouse coordinates) equal to
        the logical resolution. Falls back to a window if the driver refuses
        a fullscreen mode."""
        import pygame

        resolution = tuple(resolution)
        if self.values["fullscreen"]:
            try:
                return pygame.display.set_mode(
                    resolution, pygame.FULLSCREEN | pygame.SCALED)
            except pygame.error:
                pass
        return pygame.display.set_mode(resolution)

    def set(self, key, value):
        if key in DEFAULTS:
            self.values[key] = value

    def apply_to_game(self, game):
        """Live-applicable settings: audio, default game speed, gameplay flags."""
        self.apply_audio(game)
        game.game_speed = self.values["default_game_speed"]
        game.adaptive_difficulty = self.values["adaptive_difficulty"]
        game.batch_queue_size = self.values["batch_queue_size"]
        game.shadows_enabled = self.values["shadows"]
        game.ambient_enabled = self.values["ambient"]

    def apply_audio(self, game):
        """Audio-only subset — safe to re-apply mid-match from the pause
        screen without touching game speed or gameplay flags (§8.5)."""
        sound = getattr(game, "sound_manager", None)
        if sound is None:
            return
        # hasattr(sounds) == mixer init succeeded; the setting can then
        # freely re-enable audio that was toggled off earlier in the session
        sound.enabled = self.values["sound_enabled"] and hasattr(sound, "sounds")
        if hasattr(sound, "set_volume"):
            sound.set_volume(self.values["volume"])
        if hasattr(sound, "set_music_volume"):
            sound.set_music_volume(self.values["music_volume"])
        if not self.values["sound_enabled"]:
            if hasattr(sound, "stop_music"):
                sound.stop_music()
        elif hasattr(sound, "start_music"):
            sound.start_music()
