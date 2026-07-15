"""Garrison (§8.9 depth round 3): units shelter inside the castle or a
watchtower. Garrisoned units leave the world (safe, untargetable, invisible)
and are ejected unharmed when they leave or the building falls. Each
garrisoned unit speeds a watchtower's fire by +15% (entities/building.py).

Design notes:
- Units are REMOVED from game.units while garrisoned (every system skips
  them naturally). The exceptions that must still see them are handled at
  their sites: population counting (context.py), elimination rules
  (game._player_can_continue), and save/load (save_manager).
- Ejection places units on a ring around the building; on building death
  survivors are ejected unharmed (generous and simple).
"""
import math

GARRISON_CAPACITY = {"castle": 10, "watchtower": 4}


def capacity(building) -> int:
    return GARRISON_CAPACITY.get(getattr(building, "name", ""), 0)


def garrison_list(building) -> list:
    existing = getattr(building, "garrison", None)
    if existing is None:
        existing = building.garrison = []
    return existing


def can_accept(building, unit) -> bool:
    if getattr(building, "hp", 0) <= 0 or not getattr(building, "in_world", True):
        return False
    if getattr(building, "player", None) is not getattr(unit, "player", object()):
        return False
    return len(garrison_list(building)) < capacity(building)


def try_enter(game, unit, building) -> bool:
    """Garrison the unit if it's close enough and there's room."""
    if not can_accept(building, unit):
        unit.garrison_target = None
        return False
    reach = building.radius + unit.radius + 40
    if (unit.x - building.x) ** 2 + (unit.y - building.y) ** 2 > reach * reach:
        return False  # keep walking; the arrival hook will retry

    worker_tasks = getattr(game, "worker_task_system", None)
    if worker_tasks is not None:
        worker_tasks.cancel(unit)
    if hasattr(unit, "clear_all_movement_state"):
        unit.clear_all_movement_state()
    unit.current_target = None
    unit.in_combat = False
    unit.is_engaging = False
    unit.garrison_target = None
    unit.selected = False
    selection = getattr(game, "selection_manager", None)
    if selection is not None and unit in selection.selected_objects:
        selection.selected_objects.remove(unit)

    if unit in game.units:
        game.units.remove(unit)
    unit.garrisoned_in = building
    unit.status = "idle"
    garrison_list(building).append(unit)
    return True


def eject_all(game, building) -> list:
    """Empty the building; units reappear on a ring around it."""
    units = list(garrison_list(building))
    garrison_list(building).clear()
    for index, unit in enumerate(units):
        _place_outside(game, building, unit, index)
        unit.garrisoned_in = None
        unit.status = "idle"
        unit.in_world = True
        if unit not in game.units:
            game.units.append(unit)
    return units


def _place_outside(game, building, unit, index):
    ring = building.radius + unit.radius + 12
    collision = getattr(game, "collision_system", None)
    for attempt in range(12):
        angle = (index * 0.7 + attempt * (math.pi / 6)) % (2 * math.pi)
        x = building.x + math.cos(angle) * ring
        y = building.y + math.sin(angle) * ring
        if collision is not None and collision._is_on_unwalkable_terrain(x, y, unit.radius):
            continue
        unit.x, unit.y = x, y
        return
    unit.x, unit.y = building.x + ring, building.y  # last resort


def total_garrisoned(game, player, unit_name=None) -> int:
    count = 0
    for building in game.buildings:
        if building.player is not player:
            continue
        for unit in getattr(building, "garrison", ()):
            if unit_name is None or unit.name == unit_name:
                count += 1
    return count
