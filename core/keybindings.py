"""Rebindable hotkeys (§8.6).

Defaults live here; user overrides persist in keybindings.json next to the
game (partial files are fine — unknown actions and unparsable key names are
ignored). Key names are pygame names: "f1", "home", "tab", "[", "s", ...
"""
import json
import os

import pygame

from core.app_paths import user_path
from utils.debug_logger import debug_log

# Relative when run from source; under %LOCALAPPDATA%\RTS when frozen.
BINDINGS_FILE = user_path("keybindings.json")

DEFAULT_BINDINGS = {
    "idle_worker": "f1",          # select/cycle idle workers
    "select_all_production": "f2",  # select every own military-production building
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
    "toggle_event_log": "l",      # scrolling log of past alerts (§8.2)
    "open_settings": "o",         # settings screen while paused (§8.5 audio)
    # Command-card grid hotkeys (§8.2.1 Phase A): position-mapped onto the
    # sidebar's fixed 2x4 tile grid, row by row. 2026-07-18 (user decision):
    # NO key may ever collide with WASD camera pan — the old Q W / A S rows
    # stole W/A/S whenever a worker was selected. Number keys were
    # considered and rejected: 1-9 AND numpad 1-9 are control groups.
    # Layout is the top letter row + bottom letter row, read left to right.
    "card_slot_0": "q",
    "card_slot_1": "e",
    "card_slot_2": "r",
    "card_slot_3": "t",
    "card_slot_4": "z",
    "card_slot_5": "x",
    "card_slot_6": "c",
    "card_slot_7": "v",
    # Swap Economy/Military build tabs. Deliberately the same key as
    # cycle_army: the command card consumes Tab FIRST and only while the
    # build chips are on screen (worker selected), so Tab is contextual —
    # builder menu open: swap tabs; otherwise: cycle army (user request
    # 2026-07-18; was space, which nobody found).
    "card_tab_swap": "tab",
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
