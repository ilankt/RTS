"""Rebindable hotkeys (§8.6).

Defaults live here; user overrides persist in keybindings.json next to the
game (partial files are fine — unknown actions and unparsable key names are
ignored). Key names are pygame names: "f1", "home", "tab", "[", "s", ...
"""
import json
import os

import pygame

from utils.debug_logger import debug_log

BINDINGS_FILE = "keybindings.json"

DEFAULT_BINDINGS = {
    "idle_worker": "f1",          # select/cycle idle workers
    "jump_to_base": "home",       # center camera on own castle
    "cycle_army": "tab",          # select + center next military unit
    "path_overlay": "f3",         # pathfinding/coordinate debug overlay
    "ai_debug_panel": "f4",       # AI goal scores panel
    "quick_save": "f5",
    "toggle_fog": "f6",
    "quick_load": "f9",
    "speed_down": "[",
    "speed_up": "]",
    "cycle_stance": "s",
    "toggle_gates": "g",
    "cycle_formation": "f",
    "camera_bookmark_set": "b",   # save current camera view (4 rotating slots)
    "camera_bookmark_jump": "n",  # cycle through saved views
}


class KeyBindings:
    def __init__(self, path=BINDINGS_FILE):
        self.path = path
        self.bindings = dict(DEFAULT_BINDINGS)
        self._codes = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r") as f:
                overrides = json.load(f)
        except (OSError, ValueError):
            overrides = {}
        for action, key_name in overrides.items():
            if action in self.bindings and self._key_code(key_name) is not None:
                self.bindings[action] = key_name
        self._codes = {
            action: self._key_code(key_name)
            for action, key_name in self.bindings.items()
        }

    def save(self):
        """Persist only the entries that differ from the defaults."""
        overrides = {
            action: key_name
            for action, key_name in self.bindings.items()
            if DEFAULT_BINDINGS.get(action) != key_name
        }
        try:
            if overrides:
                with open(self.path, "w") as f:
                    json.dump(overrides, f, indent=2, sort_keys=True)
            elif os.path.exists(self.path):
                os.remove(self.path)
            return True
        except OSError as e:
            debug_log.log(f"Keybindings save failed: {e}", "GENERAL")
            return False

    def rebind(self, action, key_name):
        """Bind an action to a new key. Returns False for unknown actions,
        unparsable keys, or keys already bound to another action."""
        if action not in self.bindings:
            return False
        code = self._key_code(key_name)
        if code is None:
            return False
        for other, other_code in self._codes.items():
            if other != action and other_code == code:
                return False
        self.bindings[action] = key_name
        self._codes[action] = code
        return True

    def key_for(self, action):
        return self._codes.get(action)

    def matches(self, action, keycode):
        return self._codes.get(action) == keycode

    @staticmethod
    def _key_code(key_name):
        try:
            return pygame.key.key_code(str(key_name))
        except (ValueError, TypeError):
            return None
