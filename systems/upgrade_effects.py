"""Helpers for applying completed player upgrades without mutating templates."""
from __future__ import annotations


def is_tech_completed(player, tech_id: str) -> bool:
    upgrades = getattr(player, "upgrades", {})
    return tech_id in upgrades


def _completed_effects(player):
    upgrades = getattr(player, "upgrades", {})
    if not isinstance(upgrades, dict):
        return
    for value in upgrades.values():
        if isinstance(value, dict):
            yield value.get("effects", {})


def _named_value(table: dict, object_name: str, stat: str, default):
    value = default
    for key in ("all", object_name):
        stats = table.get(key, {})
        if stat in stats:
            if default == 1.0:
                value *= stats[stat]
            else:
                value += stats[stat]
    return value


def effective_unit_stat(unit, stat: str, base_value):
    multiplier = 1.0
    bonus = 0
    name = getattr(unit, "name", "")
    player = getattr(unit, "player", None)
    for effects in _completed_effects(player):
        multiplier = _named_value(effects.get("unit_stat_multipliers", {}), name, stat, multiplier)
        bonus = _named_value(effects.get("unit_stat_bonuses", {}), name, stat, bonus)
    return base_value * multiplier + bonus


def effective_building_stat(building, stat: str, base_value):
    multiplier = 1.0
    bonus = 0
    name = getattr(building, "name", "")
    player = getattr(building, "player", None)
    for effects in _completed_effects(player):
        multiplier = _named_value(effects.get("building_stat_multipliers", {}), name, stat, multiplier)
        bonus = _named_value(effects.get("building_stat_bonuses", {}), name, stat, bonus)
    return base_value * multiplier + bonus


def effective_gather_rate_multiplier(player, resource_type: str) -> float:
    multiplier = 1.0
    for effects in _completed_effects(player):
        resource_multipliers = effects.get("gather_rate_multipliers", {})
        multiplier *= resource_multipliers.get(resource_type, resource_multipliers.get("all", 1.0))
    return multiplier


def effective_build_speed_multiplier(player) -> float:
    multiplier = 1.0
    for effects in _completed_effects(player):
        multiplier *= effects.get("build_speed_multiplier", 1.0)
    return multiplier


def has_required_buildings(game, player, requirements) -> bool:
    if not requirements:
        return True
    owned = {
        building.name
        for building in getattr(game, "buildings", [])
        if getattr(building, "player", None) is player and getattr(building, "hp", 0) > 0
    }
    owned.update(
        site.building_name
        for site in getattr(game, "construction_sites", [])
        if getattr(site, "player", None) is player and getattr(site, "hp", 0) > 0
    )
    return all(requirement in owned for requirement in requirements)
