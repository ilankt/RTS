"""Shared economy helpers for resource selection and drop-off planning."""

import math
from typing import Iterable, Optional, Tuple

from core.config import DROP_OFF_BUILDINGS


RESOURCE_TO_DROPOFF = {
    "wood": "lumbermill",
    "gold": "mine",
    "stone": "quarry",
}

DROPOFF_TO_RESOURCE = {building: resource for resource, building in RESOURCE_TO_DROPOFF.items()}

RESOURCE_DROPOFF_CAPS = {
    "lumbermill": 3,
    "mine": 2,
    "quarry": 2,
}

RESOURCE_SERVICE_RADIUS = 280.0
RESOURCE_CLUSTER_RADIUS = 220.0

CRITICAL_STOCKPILE = {
    "wood": 75,
    "gold": 75,
    "stone": 50,
}


def resource_type_for_dropoff(building_type: str) -> Optional[str]:
    return DROPOFF_TO_RESOURCE.get(building_type)


def dropoff_for_resource(resource_type: str) -> Optional[str]:
    return RESOURCE_TO_DROPOFF.get(resource_type)


def is_resource_known(game, player, resource) -> bool:
    """Return whether this player has explored the resource location."""
    if resource is None or getattr(resource, "amount_remaining", 0) <= 0:
        return False

    fog = getattr(game, "fog_of_war", None)
    if not fog or not getattr(fog, "enabled", True):
        return True

    try:
        return fog.is_explored(player, resource.x, resource.y)
    except Exception:
        return True


def known_resources(game, player, resource_type: Optional[str] = None) -> list:
    resources = []
    for resource in getattr(game, "resources", []):
        if resource_type and resource.name != resource_type:
            continue
        if is_resource_known(game, player, resource):
            resources.append(resource)
    return resources


def find_nearest_dropoff(
    game,
    player,
    resource_type: str,
    position: Tuple[float, float],
    include_pending: bool = False,
):
    valid_names = set(DROP_OFF_BUILDINGS.get(resource_type, []))
    best = None
    best_dist = float("inf")

    for building in getattr(game, "buildings", []):
        if building.player != player or building.name not in valid_names or getattr(building, "hp", 1) <= 0:
            continue
        dist = math.hypot(position[0] - building.x, position[1] - building.y)
        if dist < best_dist:
            best = building
            best_dist = dist

    if include_pending:
        pending_name = dropoff_for_resource(resource_type)
        for site in getattr(game, "construction_sites", []):
            if site.player != player or site.building_name != pending_name or getattr(site, "hp", 1) <= 0:
                continue
            dist = math.hypot(position[0] - site.x, position[1] - site.y)
            if dist < best_dist:
                best = site
                best_dist = dist

    return best, best_dist


def is_resource_serviced(game, player, resource, include_pending: bool = False) -> bool:
    dropoff, distance = find_nearest_dropoff(
        game,
        player,
        resource.name,
        (resource.x, resource.y),
        include_pending=include_pending,
    )
    return bool(dropoff and distance <= RESOURCE_SERVICE_RADIUS)


def count_dropoffs(game, player, building_type: str, include_pending: bool = True) -> int:
    count = sum(
        1
        for building in getattr(game, "buildings", [])
        if building.player == player and building.name == building_type and getattr(building, "hp", 1) > 0
    )
    if include_pending:
        count += sum(
            1
            for site in getattr(game, "construction_sites", [])
            if site.player == player and site.building_name == building_type and getattr(site, "hp", 1) > 0
        )
    return count


def _nearby_resource_count(resources: Iterable, resource) -> int:
    return sum(
        1
        for other in resources
        if other is not resource and math.hypot(other.x - resource.x, other.y - resource.y) <= RESOURCE_CLUSTER_RADIUS
    )


def best_resource_for_dropoff(game, player, building_type: str):
    resource_type = resource_type_for_dropoff(building_type)
    if not resource_type:
        return None

    resources = known_resources(game, player, resource_type)
    if not resources:
        return None

    best = None
    best_score = float("-inf")
    for resource in resources:
        if is_resource_serviced(game, player, resource, include_pending=True):
            continue
        _, nearest_dist = find_nearest_dropoff(
            game,
            player,
            resource_type,
            (resource.x, resource.y),
            include_pending=True,
        )
        if nearest_dist == float("inf"):
            nearest_dist = RESOURCE_SERVICE_RADIUS * 2

        cluster_count = _nearby_resource_count(resources, resource)
        remaining = getattr(resource, "amount_remaining", 0)
        score = (nearest_dist - RESOURCE_SERVICE_RADIUS) + cluster_count * 90 + remaining * 0.05
        if score > best_score:
            best_score = score
            best = resource

    return best


def score_dropoff_building_need(ctx, building_type: str) -> float:
    resource_type = resource_type_for_dropoff(building_type)
    if not resource_type:
        return 0

    cap = RESOURCE_DROPOFF_CAPS.get(building_type, 1)
    if count_dropoffs(ctx.game, ctx.player, building_type, include_pending=True) >= cap:
        return 0

    target_resource = best_resource_for_dropoff(ctx.game, ctx.player, building_type)
    if not target_resource:
        return 0

    _, nearest_dist = find_nearest_dropoff(
        ctx.game,
        ctx.player,
        resource_type,
        (target_resource.x, target_resource.y),
        include_pending=True,
    )
    if nearest_dist == float("inf"):
        nearest_dist = RESOURCE_SERVICE_RADIUS * 2

    resources = known_resources(ctx.game, ctx.player, resource_type)
    cluster_count = _nearby_resource_count(resources, target_resource)
    shortage = max(0, CRITICAL_STOCKPILE.get(resource_type, 0) * 2 - ctx.resources.get(resource_type, 0))
    travel_savings = max(0, nearest_dist - RESOURCE_SERVICE_RADIUS)

    return 40 + min(80, travel_savings * 0.2) + cluster_count * 12 + shortage * 0.1
