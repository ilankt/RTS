"""Shared action helpers for utility-AI goals.

Most goals end up doing one of three things: train a unit, queue research, or
start a construction. The first two are one-liners; construction is a multi-
step dance (pick position, create site, deduct resources, path the worker)
factored out here.
"""
from entities import ConstructionSite
from utils.debug_logger import debug_log
from core.config import TILE_WIDTH
from systems.upgrade_effects import has_required_buildings


def start_construction(ctx, building_name: str, building_placer, position=None) -> bool:
    """Place a construction site, deduct resources, send a worker.

    Pass `position` to build at an exact spot (wall segments, §8.10) instead
    of letting the placer's ring search choose. Returns True if construction
    actually started.
    """
    if ctx.has_construction_in_progress(building_name):
        return False
    if not ctx.can_afford(building_name):
        return False

    worker = ctx.find_idle_worker()
    if not worker:
        return False

    if position is None:
        position = building_placer.find_position(building_name, ctx)
    if not position:
        return False

    template = ctx.game.game_data["buildings"].get(building_name)
    if not template:
        debug_log.log(f"AI {ctx.player.name}: No template for {building_name}", "AI")
        return False
    if not getattr(template, "buildable", True):
        return False
    if not has_required_buildings(ctx.game, ctx.player, getattr(template, "requires", [])):
        return False

    costs = ctx.cost_data.get(building_name, {})

    # Deduct resources from the live player dict (ctx.resources is a snapshot)
    for r, a in costs.items():
        ctx.player.resources[r] -= a

    building_data = {
        "name": building_name,
        "size": template.size,
        "hp": template.hp,
        "sprite": template.sprite,
        "build_duration": template.build_duration,
        "costs": costs,
        "armor_type": getattr(template, "armor_type", "fortified"),
        "armor_value": getattr(template, "armor_value", 0),
        "can_attack": getattr(template, "can_attack", False),
        "min_damage": getattr(template, "min_damage", 0),
        "max_damage": getattr(template, "max_damage", 0),
        "attack_type": getattr(template, "attack_type", "slash"),
        "attack_speed": getattr(template, "attack_speed", 1.0),
        "attack_range": getattr(template, "attack_range", 0),
        "display_name": getattr(template, "display_name", None),
        "role": getattr(template, "role", ""),
        "requires": list(getattr(template, "requires", [])),
        "buildable": getattr(template, "buildable", True),
        "strong_against": list(getattr(template, "strong_against", [])),
        "weak_against": list(getattr(template, "weak_against", [])),
    }
    radius = template.size[0] * TILE_WIDTH / 2

    try:
        site = ConstructionSite(
            building_name=building_name,
            building_data=building_data,
            x=position[0],
            y=position[1],
            radius=radius,
            player=ctx.player,
        )
    except Exception as e:
        # Refund and surface the error
        for r, a in costs.items():
            ctx.player.resources[r] += a
        debug_log.log(f"AI {ctx.player.name}: ConstructionSite() failed for {building_name}: {e}", "AI")
        return False

    ctx.game.construction_sites.append(site)
    ctx.game.pathfinder.notify_blocker_added(site)
    worker_tasks = getattr(ctx.game, "worker_task_system", None)
    if worker_tasks:
        success = worker_tasks.assign_build(worker, site)
    else:
        success = ctx.game.pathfinder.issue_interact(worker, site, "build")
    if not success:
        debug_log.log(
            f"AI {ctx.player.name}: no path to {building_name} site at ({position[0]:.0f}, {position[1]:.0f})",
            "AI",
        )

    debug_log.log(
        f"AI {ctx.player.name}: started {building_name} at ({position[0]:.0f}, {position[1]:.0f})",
        "AI",
    )
    return True


def queue_unit(ctx, building, unit_type: str) -> bool:
    """Try to start production of `unit_type` at `building`. Returns True on success."""
    if building is None:
        return False
    if not ctx.has_pop_space():
        return False
    success, _ = ctx.game.production_manager.start_production(building, unit_type)
    if success:
        debug_log.log(f"AI {ctx.player.name}: queued {unit_type} at {building.name}", "AI")
    return success


def queue_research(ctx, building, tech_id: str) -> bool:
    """Try to start or queue research at `building`. Returns True on success."""
    if building is None:
        return False
    manager = getattr(ctx.game, "research_manager", None)
    if not manager:
        return False
    success, reason = manager.start_research(building, tech_id)
    if success:
        debug_log.log(f"AI {ctx.player.name}: queued research {tech_id} at {building.name}", "AI")
    else:
        debug_log.log(f"AI {ctx.player.name}: research {tech_id} failed: {reason}", "AI")
    return success
