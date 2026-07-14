"""Shared combat math for units, buildings, AI scoring, and tests."""
from __future__ import annotations

import random

from core.config import (COMBAT_BONUS_VS_TAGS_ENABLED, COMBAT_BONUS_VS_TAG_MULTIPLIER,
                         COMBAT_TERRAIN_COVER_ENABLED, COMBAT_FOREST_COVER_MULTIPLIER)
from systems.upgrade_effects import effective_building_stat, effective_unit_stat

# §8.4 position matters: set by Game init so damage math can read terrain
# without threading the map through every entity call site.
_game_map = None


def set_terrain_provider(game_map):
    global _game_map
    _game_map = game_map


def terrain_cover_multiplier(target) -> float:
    """Damage multiplier from the target's ground: forest is cover.
    Buildings don't hide in trees — units only."""
    if not COMBAT_TERRAIN_COVER_ENABLED or _game_map is None:
        return 1.0
    if is_building_target(target):
        return 1.0
    grid_pos = _game_map.world_to_grid(target.x, target.y)
    if not grid_pos:
        return 1.0
    col, row = grid_pos
    if _game_map.grid[row][col] == "forest":
        return COMBAT_FOREST_COVER_MULTIPLIER
    return 1.0


EFFECTIVENESS_TABLE = {
    ("slash", "light"): 1.35,
    ("slash", "heavy"): 0.85,
    ("slash", "siege"): 1.25,
    ("slash", "fortified"): 0.55,
    ("pierce", "light"): 1.15,
    ("pierce", "heavy"): 1.35,
    ("pierce", "siege"): 0.45,
    ("pierce", "fortified"): 0.55,
    ("siege", "light"): 0.45,
    ("siege", "heavy"): 0.75,
    ("siege", "siege"): 0.8,
    ("siege", "fortified"): 2.25,
}


BUILDING_CLASS_NAMES = {"Building", "ConstructionSite"}


def is_building_target(target) -> bool:
    return target.__class__.__name__ in BUILDING_CLASS_NAMES


def is_valid_attack_target(attacker, target) -> bool:
    # Corpses and despawned objects are never valid — without this, units
    # kept "attacking" dead targets until cleanup, widening the frozen-
    # animation window (§8.11).
    if getattr(target, "hp", 0) <= 0 or not getattr(target, "in_world", True):
        return False
    if getattr(attacker, "building_only_attack", False) and not is_building_target(target):
        return False
    return True


def effective_stat(obj, stat: str):
    base = getattr(obj, stat)
    if obj.__class__.__name__ == "Building":
        return effective_building_stat(obj, stat, base)
    return effective_unit_stat(obj, stat, base)


def effective_attack_range(attacker) -> float:
    return float(effective_stat(attacker, "attack_range"))


def effective_armor_value(target) -> int:
    return int(effective_stat(target, "armor_value"))


def type_effectiveness(attack_type: str, armor_type: str) -> float:
    return EFFECTIVENESS_TABLE.get((attack_type, armor_type), 1.0)


def has_bonus_against(attacker, target) -> bool:
    """Does the attacker's strong_against tag list cover this target? (§8.4)

    Tags contain unit/building names plus the generic 'building' token."""
    tags = getattr(attacker, "strong_against", None)
    if not tags:
        return False
    if getattr(target, "name", None) in tags:
        return True
    return "building" in tags and is_building_target(target)


def is_resisted_by(attacker, target) -> bool:
    """Is this a type-disadvantaged hit (§8.4 "Resisted!" cue)? True when the
    target's armor class resists the attack type, or the attacker's
    weak_against tags cover the target."""
    attack_type = getattr(attacker, "attack_type", "slash")
    armor_type = getattr(target, "armor_type", "light")
    if type_effectiveness(attack_type, armor_type) < 1.0:
        return True
    weak = getattr(attacker, "weak_against", None)
    return bool(weak) and getattr(target, "name", None) in weak


def calculate_damage(attacker, target) -> int:
    min_damage = int(effective_stat(attacker, "min_damage"))
    max_damage = int(effective_stat(attacker, "max_damage"))
    if max_damage < min_damage:
        max_damage = min_damage
    base_damage = random.randint(min_damage, max_damage)
    attack_type = getattr(attacker, "attack_type", "slash")
    armor_type = getattr(target, "armor_type", "light")
    damage = base_damage * type_effectiveness(attack_type, armor_type)
    # §8.4 counter model: strong_against tags now change real damage instead
    # of being UI/AI-only lore, so e.g. spearman counters cavalry distinctly.
    if COMBAT_BONUS_VS_TAGS_ENABLED and has_bonus_against(attacker, target):
        damage *= COMBAT_BONUS_VS_TAG_MULTIPLIER
    damage *= terrain_cover_multiplier(target)  # §8.4 position matters (flagged)
    damage -= effective_armor_value(target)
    return max(1, int(damage))
