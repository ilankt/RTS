"""Shared action helpers for utility-AI goals.

Most goals end up doing one of three things: train a unit, queue research, or
start a construction. The first two are one-liners; construction is a multi-
step dance (pick position, create site, deduct resources, path the worker)
factored out here.
"""
from entities import ConstructionSite
from utils.debug_logger import debug_log
from core.config import TILE_WIDTH


def start_construction(ctx, building_name: str, building_placer) -> bool:
    """Place a construction site, deduct resources, send a worker.

    Returns True if construction actually started.
    """
    if ctx.has_construction_in_progress(building_name):
        return False
    if not ctx.can_afford(building_name):
        return False

    worker = ctx.find_idle_worker()
    if not worker:
        return False

    position = building_placer.find_position(building_name, ctx.player)
    if not position:
        return False

    template = ctx.game.game_data["buildings"].get(building_name)
    if not template:
        debug_log.log(f"AI {ctx.player.name}: No template for {building_name}", "AI")
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
    }
    radius = template.size[0] * TILE_WIDTH

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
    ctx.game.pathfinder.mark_dirty()
    site.builder = worker

    worker.clear_all_movement_state()
    worker.building_target = site
    worker.status = "run"

    path = ctx.game.pathfinder.find_path(
        (worker.x, worker.y),
        (site.x, site.y),
        worker.radius,
        worker,
        building_target=site,
    )
    if path:
        worker.path = path
        worker.path_index = 0
        worker.path_target = (site.x, site.y)
        worker.destination = path[0]
    # If no path, the construction site still exists; worker watchdog or the
    # worker_brain will pick another worker on a future tick.

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
