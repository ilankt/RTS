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
    "volume": 0.3,               # SFX volume, 0.0 - 1.0
    "music_volume": 0.4,         # background music volume (§8.5)
    "sound_enabled": True,
    "default_game_speed": 1.0,   # used when a match doesn't set one
    "colorblind_palette": False,  # Okabe-Ito team colors (§8.7), on restart
    "adaptive_difficulty": False,  # covert DDA (§7.2): AI reaction-time nudges
    "batch_queue_size": 5,        # Shift+production-tile queues N (§8.2.1 B)
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
            elif key in ("sound_enabled", "colorblind_palette", "adaptive_difficulty"):
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
        """Live-applicable settings: audio, default game speed, gameplay flags."""
        self.apply_audio(game)
        game.game_speed = self.values["default_game_speed"]
        game.adaptive_difficulty = self.values["adaptive_difficulty"]
        game.batch_queue_size = self.values["batch_queue_size"]

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
