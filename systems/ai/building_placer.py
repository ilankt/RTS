"""Simple building placement for AI - ring search around castle or resources."""
import math
from typing import Optional, Tuple
from core.config import TILE_WIDTH, TILE_HEIGHT
from systems.ai.economy_helpers import best_resource_for_dropoff
from utils.debug_logger import debug_log


class BuildingPlacer:
    """Find valid build positions using simple ring search."""

    # Buildings that must be placed near their matching resource
    RESOURCE_BUILDINGS = {
        "mine": "gold",
        "lumbermill": "wood",
        "quarry": "stone",
    }

    def __init__(self, game):
        self.game = game

    def find_position(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Find a valid position for the given building type."""
        if building_type in self.RESOURCE_BUILDINGS:
            return self._find_near_resource(building_type, ctx)
        else:
            return self._find_near_castle(building_type, ctx)

    def _find_near_resource(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Ring search around the closest matching resource."""
        resource_name = self.RESOURCE_BUILDINGS[building_type]
        if not ctx.castle:
            return None

        # Prefer the best known, unserved resource cluster over the closest
        # resource to the castle.
        best_resource = best_resource_for_dropoff(ctx, building_type)
        if not best_resource:
            debug_log.log(f"AI BuildingPlacer: No unserved known {resource_name} resource found for {building_type}", "AI")
            return None

        # Ring search around that resource
        for distance in range(80, 220, 40):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                x = best_resource.x + distance * math.cos(angle)
                y = best_resource.y + distance * math.sin(angle)
                if self._is_valid_position(x, y, building_type, ctx):
                    return (x, y)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near {resource_name}", "AI")
        return None

    def _find_near_castle(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Ring search around the castle (100-300px, 30-degree increments)."""
        if not ctx.castle:
            return None

        for distance in range(100, 320, 40):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                x = ctx.castle.x + distance * math.cos(angle)
                y = ctx.castle.y + distance * math.sin(angle)
                if self._is_valid_position(x, y, building_type, ctx):
                    return (x, y)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near castle", "AI")
        return None

    def _is_valid_position(self, x: float, y: float, building_type: str, ctx) -> bool:
        """Check terrain, collisions, and enemy proximity."""
        # Map bounds
        map_w = self.game.game_map.width * TILE_WIDTH
        map_h = self.game.game_map.height * TILE_HEIGHT
        if x < 50 or y < 50 or x > map_w - 50 or y > map_h - 50:
            return False

        # Terrain check
        grid_pos = self.game.game_map.world_to_grid(x, y)
        if not grid_pos:
            return False
        col, row = grid_pos
        if col < 0 or col >= self.game.game_map.width or row < 0 or row >= self.game.game_map.height:
            return False
        terrain = self.game.game_map.grid[row][col]
        if terrain not in ("grass", "plains", "dirt"):
            return False

        # Get building radius from template
        building_template = self.game.game_data["buildings"].get(building_type)
        if not building_template:
            return False
        building_radius = building_template.radius
        min_distance = building_radius + 30

        # Collision with existing statics via the shared spatial index
        collision = getattr(self.game, "collision_system", None)
        if collision is not None:
            for obj in collision.query_nearby_static(x, y, min_distance + 8):
                dist = math.hypot(x - obj.x, y - obj.y)
                if dist < min_distance + obj.radius:
                    return False
        # Don't build near enemy castles (blackboard list, not a world scan)
        for building in ctx.enemy_buildings:
            if building.name == "castle" and math.hypot(x - building.x, y - building.y) < 500:
                return False

        return True
