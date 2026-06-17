"""Fog of War system - per-player visibility grid."""
import math


class FogOfWar:
    """Manages fog of war visibility for all players.

    Grid states:
      0 = UNEXPLORED  - never seen, completely black
      1 = EXPLORED    - seen before but not currently, dimmed
      2 = VISIBLE     - currently in line of sight, fully rendered
    """
    UNEXPLORED = 0
    EXPLORED = 1
    VISIBLE = 2

    SIGHT_RADIUS_UNITS = 150  # Base sight radius for units in world pixels
    SIGHT_RADIUS_BUILDINGS = 250  # Larger sight for buildings
    SIGHT_RADIUS_CASTLE = 400  # Castle has largest sight range

    def __init__(self, game):
        self.game = game
        self.map_width = game.game_map.width
        self.map_height = game.game_map.height

        # visibility_grid[player] = 2D list of states
        self.visibility_grid = {}

        for player in game.players:
            self._init_player_grid(player)

    @property
    def enabled(self):
        """Whether fog should affect rendering and visibility checks."""
        return getattr(self.game, "fog_of_war_enabled", True)

    def _init_player_grid(self, player):
        """Initialize a player's visibility grid."""
        self.visibility_grid[player] = [
            [self.UNEXPLORED for _ in range(self.map_width)]
            for _ in range(self.map_height)
        ]

    def update(self):
        """Update visibility for all players each frame."""
        for player in self.game.players:
            grid = self.visibility_grid[player]

            # Fade all VISIBLE tiles to EXPLORED
            for r in range(self.map_height):
                for c in range(self.map_width):
                    if grid[r][c] == self.VISIBLE:
                        grid[r][c] = self.EXPLORED

            # Mark tiles around this player's units and buildings as VISIBLE
            for unit in self.game.units:
                if unit.player != player or unit.hp <= 0:
                    continue
                self._mark_visible_around(player, unit.x, unit.y, self.SIGHT_RADIUS_UNITS)

            for building in self.game.buildings:
                if building.player != player or building.hp <= 0:
                    continue
                radius = self.SIGHT_RADIUS_BUILDINGS
                if building.name == "castle":
                    radius = self.SIGHT_RADIUS_CASTLE
                self._mark_visible_around(player, building.x, building.y, radius)

    def _mark_visible_around(self, player, wx: float, wy: float, radius: float):
        """Mark all tiles within radius of (wx, wy) as VISIBLE."""
        grid = self.visibility_grid[player]

        # Convert world center to grid
        center = self.game.game_map.world_to_grid(wx, wy)
        if not center:
            return
        col_center, row_center = center

        # Mark tiles in a circular area
        radius_tiles = int(radius / 40) + 1
        for dr in range(-radius_tiles, radius_tiles + 1):
            for dc in range(-radius_tiles, radius_tiles + 1):
                r = row_center + dr
                c = col_center + dc
                if 0 <= r < self.map_height and 0 <= c < self.map_width:
                    # Check if within actual circular radius
                    # Convert tile to world to check distance
                    wx_tile, wy_tile = self.game.game_map.grid_to_world(c, r)
                    dist = math.sqrt((wx - wx_tile) ** 2 + (wy - wy_tile) ** 2)
                    if dist <= radius:
                        grid[r][c] = self.VISIBLE

    def is_visible(self, player, wx: float, wy: float) -> bool:
        """Check if a world position is currently visible to player."""
        if not self.enabled:
            return True
        if player not in self.visibility_grid:
            return True  # No fog for unregistered players
        hex_coord = self.game.game_map.world_to_grid(wx, wy)
        if not hex_coord:
            return False
        c, r = hex_coord
        if 0 <= r < self.map_height and 0 <= c < self.map_width:
            return self.visibility_grid[player][r][c] == self.VISIBLE
        return False

    def is_explored(self, player, wx: float, wy: float) -> bool:
        """Check if a world position has ever been explored by player."""
        if not self.enabled:
            return True
        if player not in self.visibility_grid:
            return True
        hex_coord = self.game.game_map.world_to_grid(wx, wy)
        if not hex_coord:
            return False
        c, r = hex_coord
        if 0 <= r < self.map_height and 0 <= c < self.map_width:
            return self.visibility_grid[player][r][c] >= self.EXPLORED
        return False

    def get_tile_state(self, player, r: int, c: int) -> int:
        """Get the fog state of a tile for a player."""
        if not self.enabled:
            return self.VISIBLE
        if player not in self.visibility_grid:
            return self.VISIBLE
        if 0 <= r < self.map_height and 0 <= c < self.map_width:
            return self.visibility_grid[player][r][c]
        return self.UNEXPLORED

    def is_object_visible(self, obj) -> bool:
        """Check if an object is visible to the human player."""
        if not self.enabled:
            return True

        human = self.game.players[0] if self.game.players else None
        if not human:
            return True
        
        # Own units and buildings are always visible
        if hasattr(obj, 'player') and obj.player == human:
            return True
        
        return self.is_visible(human, obj.x, obj.y)

    def get_exploration_percent(self, player):
        """Return percentage of map tiles explored."""
        if not self.enabled:
            return 100.0
        if player not in self.visibility_grid:
            return 100.0
        grid = self.visibility_grid[player]
        total = self.map_width * self.map_height
        explored = sum(
            1 for r in range(self.map_height) for c in range(self.map_width)
            if grid[r][c] >= self.EXPLORED
        )
        return explored / total * 100 if total > 0 else 0.0
