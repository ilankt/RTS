"""Persistent player profile + achievements (§8.7).

Lifetime stats accumulate across matches in profile.json (same pattern as
core/settings.py). Achievements unlock once; newly unlocked ones are
returned so the game can toast them.
"""
import json
import os
from datetime import date

from core.app_paths import user_path
from utils.debug_logger import debug_log

# Relative when run from source; under %LOCALAPPDATA%\RTS when frozen.
PROFILE_FILE = user_path("profile.json")

STAT_DEFAULTS = {
    "matches_played": 0,
    "matches_won": 0,
    "matches_lost": 0,
    "units_trained": 0,
    "buildings_built": 0,
    "resources_gathered": 0,
}

# id -> (title, requirement description)
ACHIEVEMENTS = {
    "first_win": ("First Victory", "Win your first match"),
    "veteran": ("Veteran", "Play 10 matches"),
    "economist": ("Economist", "Gather 10,000 resources lifetime"),
    "warlord": ("Warlord", "Train 100 units lifetime"),
    "master_builder": ("Master Builder", "Construct 50 buildings lifetime"),
    "blitz": ("Blitz", "Win a match in under 10 game-minutes"),
}


class Profile:
    def __init__(self, path=None):
        self.path = path if path is not None else PROFILE_FILE
        self.stats = dict(STAT_DEFAULTS)
        self.achievements = {}  # id -> unlock date string
        self.load()

    def load(self):
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for key in STAT_DEFAULTS:
            value = data.get("stats", {}).get(key)
            if isinstance(value, (int, float)):
                self.stats[key] = int(value)
        for ach_id, unlocked in data.get("achievements", {}).items():
            if ach_id in ACHIEVEMENTS:
                self.achievements[ach_id] = str(unlocked)

    def save(self):
        try:
            with open(self.path, "w") as f:
                json.dump({"stats": self.stats, "achievements": self.achievements},
                          f, indent=2, sort_keys=True)
            return True
        except OSError as e:
            debug_log.log(f"Profile save failed: {e}", "GENERAL")
            return False

    def record_match(self, game, human_player, won):
        """Fold one finished match into the profile. Returns newly unlocked
        achievement (id, title) pairs, already saved to disk."""
        name = human_player.name
        self.stats["matches_played"] += 1
        self.stats["matches_won" if won else "matches_lost"] += 1
        self.stats["units_trained"] += sum(
            v for (p, _t), v in getattr(game, "stats_units_trained", {}).items() if p == name
        )
        self.stats["buildings_built"] += sum(
            v for (p, _t), v in getattr(game, "stats_buildings_built", {}).items() if p == name
        )
        self.stats["resources_gathered"] += int(
            getattr(game, "stats_resources_gathered", {}).get(name, 0)
        )

        unlocked = []
        def check(ach_id, condition):
            if condition and ach_id not in self.achievements:
                self.achievements[ach_id] = date.today().isoformat()
                unlocked.append((ach_id, ACHIEVEMENTS[ach_id][0]))

        check("first_win", won)
        check("veteran", self.stats["matches_played"] >= 10)
        check("economist", self.stats["resources_gathered"] >= 10000)
        check("warlord", self.stats["units_trained"] >= 100)
        check("master_builder", self.stats["buildings_built"] >= 50)
        check("blitz", won and getattr(game, "sim_time_elapsed", 1e9) < 600)

        self.save()
        return unlocked
