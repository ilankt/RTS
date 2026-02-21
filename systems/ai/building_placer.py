"""Simple building placement for AI - ring search around castle or resources."""
import math
from typing import Optional, Tuple
from core.config import TILE_WIDTH, TILE_HEIGHT
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

    def find_position(self, building_type: str, player) -> Optional[Tuple[float, float]]:
        """Find a valid position for the given building type."""
        if building_type in self.RESOURCE_BUILDINGS:
            return self._find_near_resource(building_type, player)
        else:
            return self._find_near_castle(building_type, player)

    def _find_near_resource(self, building_type: str, player) -> Optional[Tuple[float, float]]:
        """Ring search around the closest matching resource."""
        resource_name = self.RESOURCE_BUILDINGS[building_type]
        castle = self._get_castle(player)
        if not castle:
            return None

        # Find closest matching resource to castle
        best_resource = None
        best_dist = float("inf")
        for res in self.game.resources:
            if res.name == resource_name and res.amount_remaining > 0:
                dist = math.hypot(res.x - castle.x, res.y - castle.y)
                if dist < best_dist:
                    best_dist = dist
                    best_resource = res

        if not best_resource:
            debug_log.log(f"AI BuildingPlacer: No {resource_name} resource found for {building_type}", "AI")
            return None

        # Ring search around that resource
        for distance in range(80, 220, 40):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                x = best_resource.x + distance * math.cos(angle)
                y = best_resource.y + distance * math.sin(angle)
                if self._is_valid_position(x, y, building_type, player):
                    return (x, y)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near {resource_name}", "AI")
        return None

    def _find_near_castle(self, building_type: str, player) -> Optional[Tuple[float, float]]:
        """Ring search around the castle (100-300px, 30-degree increments)."""
        castle = self._get_castle(player)
        if not castle:
            return None

        for distance in range(100, 320, 40):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                x = castle.x + distance * math.cos(angle)
                y = castle.y + distance * math.sin(angle)
                if self._is_valid_position(x, y, building_type, player):
                    return (x, y)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near castle", "AI")
        return None

    def _is_valid_position(self, x: float, y: float, building_type: str, player) -> bool:
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
        building_radius = building_template.size[0] * 32
        min_distance = building_radius + 30

        # Collision with existing buildings
        for building in self.game.buildings:
            dist = math.hypot(x - building.x, y - building.y)
            if dist < min_distance + building.radius:
                return False
            # Don't build near enemy castles
            if building.player != player and building.name == "castle" and dist < 500:
                return False

        # Collision with construction sites
        for site in self.game.construction_sites:
            dist = math.hypot(x - site.x, y - site.y)
            if dist < min_distance + site.radius:
                return False

        # Collision with resources
        for resource in self.game.resources:
            dist = math.hypot(x - resource.x, y - resource.y)
            if dist < min_distance + resource.radius:
                return False

        return True

    def _get_castle(self, player):
        """Find the player's castle."""
        for building in self.game.buildings:
            if building.player == player and building.name == "castle":
                return building
        return None
