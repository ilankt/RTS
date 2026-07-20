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


def _named_value(table: dict, object_name: str, stat: str, value, multiply: bool):
    """Fold a tech's stat table into a running multiplier/bonus.

    The mode is explicit — the old sentinel dispatch (`default == 1.0` meant
    multiply) broke the moment a running BONUS totalled exactly 1: the next
    tiered armor level multiplied 1x1 instead of adding (+1 +1 read as +1).
    Latent until §8.17's 3-level techs made additive stacking real."""
    for key in ("all", object_name):
        stats = table.get(key, {})
        if stat in stats:
            if multiply:
                value *= stats[stat]
            else:
                value += stats[stat]
    return value


def _mod_cache(player):
    """Per-player memo of computed modifiers, invalidated by upgrades_version.

    Returns None (compute uncached) for players without version tracking so a
    mutated upgrades dict can never serve stale values."""
    version = getattr(player, "upgrades_version", None)
    if version is None:
        return None
    cache = getattr(player, "_stat_mod_cache", None)
    if cache is None or getattr(player, "_stat_mod_cache_version", None) != version:
        cache = {}
        player._stat_mod_cache = cache
        player._stat_mod_cache_version = version
    return cache


def _stat_mods(player, kind: str, name: str, stat: str):
    """(multiplier, bonus) for a unit/building stat, memoized per player."""
    upgrades = getattr(player, "upgrades", None)
    if not upgrades:
        return 1.0, 0
    cache = _mod_cache(player)
    key = (kind, name, stat)
    if cache is not None:
        mods = cache.get(key)
        if mods is not None:
            return mods
    multiplier = 1.0
    bonus = 0
    for effects in _completed_effects(player):
        multiplier = _named_value(effects.get(f"{kind}_stat_multipliers", {}), name, stat, multiplier, multiply=True)
        bonus = _named_value(effects.get(f"{kind}_stat_bonuses", {}), name, stat, bonus, multiply=False)
    if cache is not None:
        cache[key] = (multiplier, bonus)
    return multiplier, bonus


def effective_unit_stat(unit, stat: str, base_value):
    multiplier, bonus = _stat_mods(getattr(unit, "player", None), "unit", getattr(unit, "name", ""), stat)
    if multiplier == 1.0 and bonus == 0:
        return base_value
    return base_value * multiplier + bonus


def effective_building_stat(building, stat: str, base_value):
    multiplier, bonus = _stat_mods(getattr(building, "player", None), "building", getattr(building, "name", ""), stat)
    if multiplier == 1.0 and bonus == 0:
        return base_value
    return base_value * multiplier + bonus


def effective_gather_rate_multiplier(player, resource_type: str) -> float:
    upgrades = getattr(player, "upgrades", None)
    if not upgrades:
        return 1.0
    cache = _mod_cache(player)
    key = ("gather_rate", resource_type)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    multiplier = 1.0
    for effects in _completed_effects(player):
        resource_multipliers = effects.get("gather_rate_multipliers", {})
        multiplier *= resource_multipliers.get(resource_type, resource_multipliers.get("all", 1.0))
    if cache is not None:
        cache[key] = multiplier
    return multiplier


def effective_build_speed_multiplier(player) -> float:
    upgrades = getattr(player, "upgrades", None)
    if not upgrades:
        return 1.0
    cache = _mod_cache(player)
    key = ("build_speed",)
    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return cached
    multiplier = 1.0
    for effects in _completed_effects(player):
        multiplier *= effects.get("build_speed_multiplier", 1.0)
    if cache is not None:
        cache[key] = multiplier
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
