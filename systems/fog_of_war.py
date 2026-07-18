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

    UPDATE_INTERVAL = 0.2  # Game-time seconds between visibility rebuilds (~5 Hz)

    def __init__(self, game):
        self.game = game
        self.map_width = game.game_map.width
        self.map_height = game.game_map.height

        # visibility_grid[player] = 2D list of states
        self.visibility_grid = {}
        # Tiles currently marked VISIBLE per player (so fading is O(visible))
        self._visible_tiles = {}
        # Count of ever-explored tiles per player (incremental, for percent)
        self._explored_count = {}
        # Circular tile-offset masks keyed by (radius, center-column parity)
        self._mask_cache = {}
        self._time_accum = 0.0
        self._has_updated = False

        # Ghosts of resources that were depleted OUT of the human viewer's
        # sight: still drawn (dimmed) where last seen, until the player
        # actually reveals the spot and sees they're gone.
        # {(r, c, name): {"name", "x", "y"}}
        self.resource_ghosts = {}

        for player in game.players:
            self._init_player_grid(player)

    @property
    def enabled(self):
        """Whether fog RULES apply (perception gating + grid updates).
        False only when fog is off as a game rule (revealed_map mutator,
        F6 debug toggle) — then everyone is legitimately omniscient."""
        return getattr(self.game, "fog_of_war_enabled", True)

    @property
    def reveal_display(self):
        """Whether the DISPLAY shows everything regardless of fog rules.
        §8.11 fair spectating: in spectator mode the AIs still play under
        fog (their grids update, their perception is gated), but the human
        viewer watches the whole map."""
        return bool(getattr(self.game, "spectator_reveal_display", False))

    def _init_player_grid(self, player):
        """Initialize a player's visibility grid."""
        self.visibility_grid[player] = [
            [self.UNEXPLORED for _ in range(self.map_width)]
            for _ in range(self.map_height)
        ]
        self._visible_tiles[player] = set()
        self._explored_count[player] = 0

    def update(self, delta_time=None):
        """Rebuild visibility for all players (throttled to ~UPDATE_INTERVAL)."""
        if not self.enabled:
            return
        if delta_time is not None:
            self._time_accum += delta_time
            if self._has_updated and self._time_accum < self.UPDATE_INTERVAL:
                return
            self._time_accum = 0.0
        self._has_updated = True

        for player in self.game.players:
            grid = self.visibility_grid[player]
            previous_visible = self._visible_tiles.get(player, set())
            new_visible = set()

            # Mark tiles around this player's units and buildings as VISIBLE
            for unit in self.game.units:
                if unit.player != player or unit.hp <= 0:
                    continue
                self._mark_visible_around(player, grid, new_visible, unit.x, unit.y, self.SIGHT_RADIUS_UNITS)

            for building in self.game.buildings:
                if building.player != player or building.hp <= 0:
                    continue
                radius = self.SIGHT_RADIUS_BUILDINGS
                if building.name == "castle":
                    radius = self.SIGHT_RADIUS_CASTLE
                self._mark_visible_around(player, grid, new_visible, building.x, building.y, radius)

            # Fade only the tiles that dropped out of sight
            for r, c in previous_visible - new_visible:
                if grid[r][c] == self.VISIBLE:
                    grid[r][c] = self.EXPLORED
            self._visible_tiles[player] = new_visible

            # Revealing a ghost's tile shows the resource is gone — drop it
            if player is self._display_player() and self.resource_ghosts:
                self.resource_ghosts = {
                    key: ghost for key, ghost in self.resource_ghosts.items()
                    if (key[0], key[1]) not in new_visible
                }

    def _mark_visible_around(self, player, grid, new_visible, wx: float, wy: float, radius: float):
        """Mark all tiles within radius of (wx, wy) as VISIBLE via offset mask."""
        game_map = self.game.game_map
        world_to_grid = getattr(game_map, "world_to_grid_fast", game_map.world_to_grid)
        center = world_to_grid(wx, wy)
        if not center:
            return
        col_center, row_center = center

        map_height = self.map_height
        map_width = self.map_width
        unexplored = self.UNEXPLORED
        visible = self.VISIBLE
        explored_bump = 0
        for dr, dc in self._offset_mask(radius, col_center & 1):
            r = row_center + dr
            c = col_center + dc
            if 0 <= r < map_height and 0 <= c < map_width:
                tile = (r, c)
                if tile in new_visible:
                    continue
                new_visible.add(tile)
                if grid[r][c] != visible:
                    if grid[r][c] == unexplored:
                        explored_bump += 1
                    grid[r][c] = visible
        if explored_bump:
            self._explored_count[player] = self._explored_count.get(player, 0) + explored_bump

    def _offset_mask(self, radius: float, parity: int):
        """Tile offsets (dr, dc) within radius of a tile whose column parity is
        `parity`. Uses the map's own grid geometry; computed once per key."""
        key = (radius, parity)
        mask = self._mask_cache.get(key)
        if mask is not None:
            return mask

        grid_to_world = self.game.game_map.grid_to_world
        center_x, center_y = grid_to_world(parity, 0)
        radius_tiles = int(radius / 40) + 1
        radius_sq = radius * radius
        mask = []
        for dr in range(-radius_tiles, radius_tiles + 1):
            for dc in range(-radius_tiles, radius_tiles + 1):
                tile_x, tile_y = grid_to_world(parity + dc, dr)
                dx = tile_x - center_x
                dy = tile_y - center_y
                if dx * dx + dy * dy <= radius_sq:
                    mask.append((dr, dc))
        self._mask_cache[key] = mask
        return mask

    def _world_to_tile(self, wx: float, wy: float):
        game_map = self.game.game_map
        world_to_grid = getattr(game_map, "world_to_grid_fast", game_map.world_to_grid)
        return world_to_grid(wx, wy)

    def is_visible(self, player, wx: float, wy: float) -> bool:
        """Check if a world position is currently visible to player."""
        if not self.enabled:
            return True
        if player not in self.visibility_grid:
            return True  # No fog for unregistered players
        hex_coord = self._world_to_tile(wx, wy)
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
        hex_coord = self._world_to_tile(wx, wy)
        if not hex_coord:
            return False
        c, r = hex_coord
        if 0 <= r < self.map_height and 0 <= c < self.map_width:
            return self.visibility_grid[player][r][c] >= self.EXPLORED
        return False

    def get_tile_state(self, player, r: int, c: int) -> int:
        """Get the fog state of a tile for a player (display consumer)."""
        if not self.enabled or self.reveal_display:
            return self.VISIBLE
        if player not in self.visibility_grid:
            return self.VISIBLE
        if 0 <= r < self.map_height and 0 <= c < self.map_width:
            return self.visibility_grid[player][r][c]
        return self.UNEXPLORED

    def _display_player(self):
        """The player whose fog the human viewer watches through."""
        return self.game.players[0] if self.game.players else None

    def is_display_explored(self, wx: float, wy: float) -> bool:
        """Should a static neutral (resource/fountain) DRAW at this spot?
        Unlike units/buildings they can't move, so once seen they stay
        drawn — under the explored dim — exactly like the minimap dots."""
        if not self.enabled or self.reveal_display:
            return True
        human = self._display_player()
        if human is None:
            return True
        return self.is_explored(human, wx, wy)

    def record_resource_removed(self, resource) -> None:
        """A resource left the world. If the human viewer has seen the spot
        but can't see it right now, leave a ghost behind (the player still
        believes it's there); watching it deplete leaves nothing."""
        if not self.enabled or self.reveal_display:
            return
        human = self._display_player()
        if human is None:
            return
        tile = self._world_to_tile(resource.x, resource.y)
        if not tile:
            return
        c, r = tile
        if not (0 <= r < self.map_height and 0 <= c < self.map_width):
            return
        grid = self.visibility_grid.get(human)
        if grid is None:
            return
        if grid[r][c] != self.EXPLORED:  # visible: saw it vanish; unexplored: never knew
            return
        self.resource_ghosts[(r, c, resource.name)] = {
            "name": resource.name, "x": resource.x, "y": resource.y,
            # §11.1 biome trees: the ghost keeps the biome look too
            "variant": getattr(resource, "sprite_variant", None),
        }

    def clear_ghost_at(self, wx: float, wy: float, name: str) -> None:
        """A same-type resource (re)appeared here — the memory is true
        again, so the ghost is redundant (tree regrowth)."""
        tile = self._world_to_tile(wx, wy)
        if tile:
            self.resource_ghosts.pop((tile[1], tile[0], name), None)

    def is_object_visible(self, obj) -> bool:
        """Check if an object is visible to the human VIEWER (display)."""
        if not self.enabled or self.reveal_display:
            return True

        human = self.game.players[0] if self.game.players else None
        if not human:
            return True
        
        # Own units and buildings are always visible
        if hasattr(obj, 'player') and obj.player == human:
            return True
        
        return self.is_visible(human, obj.x, obj.y)

    def get_exploration_percent(self, player):
        """Return percentage of map tiles explored (incrementally tracked)."""
        if not self.enabled:
            return 100.0
        if player not in self.visibility_grid:
            return 100.0
        total = self.map_width * self.map_height
        return self._explored_count.get(player, 0) / total * 100 if total > 0 else 0.0
