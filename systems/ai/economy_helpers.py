"""Shared economy helpers for resource selection and drop-off planning.

Ctx-suffixed helpers read the per-tick GoalContext blackboard (no world
rescans). The game-level `find_nearest_dropoff` remains for non-AI callers
(e.g. depleted-resource cleanup in core/game.py).
"""

import math
from typing import Optional, Tuple

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


def find_nearest_dropoff(
    game,
    player,
    resource_type: str,
    position: Tuple[float, float],
    include_pending: bool = False,
):
    """Game-level nearest drop-off (used outside the AI tick)."""
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


def find_nearest_dropoff_ctx(ctx, resource_type: str, position: Tuple[float, float], include_pending: bool = False):
    """Blackboard variant: reads ctx.buildings / ctx.construction_sites."""
    best = None
    best_dist = float("inf")
    for name in DROP_OFF_BUILDINGS.get(resource_type, ()):
        for building in ctx.buildings.get(name, ()):
            if getattr(building, "hp", 1) <= 0:
                continue
            dist = math.hypot(position[0] - building.x, position[1] - building.y)
            if dist < best_dist:
                best = building
                best_dist = dist

    if include_pending:
        pending_name = dropoff_for_resource(resource_type)
        for site in ctx.construction_sites:
            if site.building_name != pending_name or getattr(site, "hp", 1) <= 0:
                continue
            dist = math.hypot(position[0] - site.x, position[1] - site.y)
            if dist < best_dist:
                best = site
                best_dist = dist

    return best, best_dist


def is_resource_serviced_ctx(ctx, resource, include_pending: bool = False) -> bool:
    dropoff, distance = find_nearest_dropoff_ctx(
        ctx, resource.name, (resource.x, resource.y), include_pending=include_pending
    )
    return bool(dropoff and distance <= RESOURCE_SERVICE_RADIUS)


def count_dropoffs_ctx(ctx, building_type: str, include_pending: bool = True) -> int:
    count = sum(1 for b in ctx.buildings.get(building_type, ()) if getattr(b, "hp", 1) > 0)
    if include_pending:
        count += sum(
            1
            for site in ctx.construction_sites
            if site.building_name == building_type and getattr(site, "hp", 1) > 0
        )
    return count


def _cluster_counts(ctx, resource_type: str, resources) -> dict:
    """Approximate per-resource cluster sizes via one bucketing pass (O(n))
    instead of an O(n^2) pairwise sweep per candidate. Memoized per tick."""
    cache = getattr(ctx, "_cluster_count_cache", None)
    if cache is None:
        cache = ctx._cluster_count_cache = {}
    counts = cache.get(resource_type)
    if counts is not None:
        return counts

    cell = RESOURCE_CLUSTER_RADIUS
    buckets = {}
    for resource in resources:
        key = (int(resource.x // cell), int(resource.y // cell))
        buckets[key] = buckets.get(key, 0) + 1
    counts = {}
    for resource in resources:
        key_x = int(resource.x // cell)
        key_y = int(resource.y // cell)
        total = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                total += buckets.get((key_x + dx, key_y + dy), 0)
        counts[id(resource)] = total - 1  # exclude the resource itself
    cache[resource_type] = counts
    return counts


def best_resource_for_dropoff(ctx, building_type: str):
    resource_type = resource_type_for_dropoff(building_type)
    if not resource_type:
        return None

    resources = ctx.known_resources(resource_type)
    if not resources:
        return None

    cluster_counts = _cluster_counts(ctx, resource_type, resources)
    best = None
    best_score = float("-inf")
    for resource in resources:
        _, nearest_dist = find_nearest_dropoff_ctx(
            ctx, resource_type, (resource.x, resource.y), include_pending=True
        )
        if nearest_dist <= RESOURCE_SERVICE_RADIUS:
            continue  # already serviced
        if nearest_dist == float("inf"):
            nearest_dist = RESOURCE_SERVICE_RADIUS * 2

        cluster_count = cluster_counts.get(id(resource), 0)
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
    if count_dropoffs_ctx(ctx, building_type, include_pending=True) >= cap:
        return 0

    target_resource = best_resource_for_dropoff(ctx, building_type)
    if not target_resource:
        return 0

    _, nearest_dist = find_nearest_dropoff_ctx(
        ctx, resource_type, (target_resource.x, target_resource.y), include_pending=True
    )
    if nearest_dist == float("inf"):
        nearest_dist = RESOURCE_SERVICE_RADIUS * 2

    resources = ctx.known_resources(resource_type)
    cluster_count = _cluster_counts(ctx, resource_type, resources).get(id(target_resource), 0)
    shortage = max(0, CRITICAL_STOCKPILE.get(resource_type, 0) * 2 - ctx.resources.get(resource_type, 0))
    travel_savings = max(0, nearest_dist - RESOURCE_SERVICE_RADIUS)

    return 40 + min(80, travel_savings * 0.2) + cluster_count * 12 + shortage * 0.1
