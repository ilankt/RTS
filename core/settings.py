"""Persistent user settings (§8.2).

Same pattern as core/keybindings.py: defaults here, user diffs in
settings.json. Resolution is applied at app startup (main.py patches
core.config before the UI modules import the screen constants), so a
resolution change takes effect on restart; volume and default speed apply
live to each new Game.
"""
import json
import os

from utils.debug_logger import debug_log

SETTINGS_FILE = "settings.json"

RESOLUTION_CHOICES = [[1280, 720], [1600, 900], [1920, 1080]]

DEFAULTS = {
    "resolution": [1280, 720],
    "volume": 0.3,               # 0.0 - 1.0
    "sound_enabled": True,
    "default_game_speed": 1.0,   # used when a match doesn't set one
    "colorblind_palette": False,  # Okabe-Ito team colors (§8.7), on restart
    "adaptive_difficulty": False,  # covert DDA (§7.2): AI reaction-time nudges
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
            elif key == "volume":
                try:
                    self.values[key] = min(1.0, max(0.0, float(value)))
                except (TypeError, ValueError):
                    pass
            elif key in ("sound_enabled", "colorblind_palette", "adaptive_difficulty"):
                self.values[key] = bool(value)
            elif key == "default_game_speed":
                try:
                    self.values[key] = min(5.0, max(1.0, float(value)))
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

    def set(self, key, value):
        if key in DEFAULTS:
            self.values[key] = value

    def apply_to_game(self, game):
        """Live-applicable settings: volume/mute and the default game speed."""
        sound = getattr(game, "sound_manager", None)
        if sound is not None:
            sound.enabled = sound.enabled and self.values["sound_enabled"]
            if hasattr(sound, "set_volume"):
                sound.set_volume(self.values["volume"])
        game.game_speed = self.values["default_game_speed"]
        game.adaptive_difficulty = self.values["adaptive_difficulty"]
