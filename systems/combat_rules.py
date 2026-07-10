"""Shared combat math for units, buildings, AI scoring, and tests."""
from __future__ import annotations

import random

from core.config import COMBAT_BONUS_VS_TAGS_ENABLED, COMBAT_BONUS_VS_TAG_MULTIPLIER
from systems.upgrade_effects import effective_building_stat, effective_unit_stat


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
    damage -= effective_armor_value(target)
    return max(1, int(damage))
