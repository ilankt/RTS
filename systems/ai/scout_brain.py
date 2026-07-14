"""AI scouting logic - exploration and map awareness."""
import math
import random
from utils.debug_logger import debug_log


class ScoutBrain:
    """Manages AI scouting: exploration, enemy base detection, resource awareness."""

    def __init__(self, game):
        self.game = game
        # Per-player explored tiles (set of (row, col) tuples)
        self.explored_tiles = {}
        # Per-player known enemy positions
        self.known_enemy_castles = {}
        # Per-player scout unit assignment
        self.scout_units = {}

    def update(self, player, delta_time):
        """Update scouting for one AI player."""
        if player not in self.explored_tiles:
            self.explored_tiles[player] = set()
        if player not in self.known_enemy_castles:
            self.known_enemy_castles[player] = None
        if player not in self.scout_units:
            self.scout_units[player] = None

        # Update explored area around all our units
        self._update_explored_area(player)

        # Check if we can see enemy castle
        self._detect_enemies(player)

        # Assign or update scout unit
        self._manage_scout(player)

    def _update_explored_area(self, player):
        """Mark tiles around all player units as explored."""
        sight_radius_tiles = 6  # How many tiles around a unit are visible
        explored = self.explored_tiles[player]
        
        for unit in self.game.units:
            if unit.player != player:
                continue
            hex_coord = self.game.game_map.world_to_grid(unit.x, unit.y)
            if not hex_coord:
                continue
            col, row = hex_coord
            
            # Mark tiles in radius
            for dr in range(-sight_radius_tiles, sight_radius_tiles + 1):
                for dc in range(-sight_radius_tiles, sight_radius_tiles + 1):
                    r = row + dr
                    c = col + dc
                    if 0 <= r < self.game.game_map.height and 0 <= c < self.game.game_map.width:
                        explored.add((r, c))

    def _detect_enemies(self, player):
        """Detect enemy buildings/units within sight range of our units."""
        for building in self.game.buildings:
            if building.player == player:
                continue
            # Check if any of our units can see this building
            for unit in self.game.units:
                if unit.player != player:
                    continue
                dist = math.hypot(unit.x - building.x, unit.y - building.y)
                if dist < 250:  # Sight range in pixels
                    if building.name == "castle":
                        self.known_enemy_castles[player] = (building.x, building.y)
                    break

    def _manage_scout(self, player):
        """Manage a dedicated scout unit for exploration."""
        # Find a suitable scout (prefer fast unit, or first idle worker)
        scout = self.scout_units.get(player)
        
        # Validate existing scout
        if scout and (scout.hp <= 0 or not getattr(scout, "in_world", True)):
            scout = None
            self.scout_units[player] = None
        
        # Assign new scout if needed
        if not scout:
            # Look for idle cavalry first (fastest)
            for unit in self.game.units:
                if unit.player == player and unit.name == "cavalry" and self._is_idle(unit):
                    scout = unit
                    break
            # Then any idle military
            if not scout:
                for unit in self.game.units:
                    if unit.player == player and unit.name in ("warrior", "archer", "spearman") and self._is_idle(unit):
                        scout = unit
                        break
            # Then an idle worker
            if not scout:
                for unit in self.game.units:
                    if unit.player == player and unit.name == "worker" and self._is_idle(unit):
                        scout = unit
                        break
            
            if scout:
                self.scout_units[player] = scout
                debug_log.log(f"AI {player.name}: Assigned {scout.name} as scout", "AI")
        
        # Send scout to unexplored areas
        if scout and self._is_idle(scout):
            target = self._find_unexplored_target(player, scout)
            if target:
                self.game.selection_manager._move_unit_to_position(
                    scout, target, self.game.pathfinder
                )

    def _is_idle(self, unit):
        """Check if a unit is idle and available for scouting."""
        return (unit.status == "idle" and 
                not unit.in_combat and 
                not unit.is_engaging and 
                not unit.destination and 
                not unit.path)

    # §8.11 directed scouting: spawn placement maximizes player spread, so
    # enemies live near far edges/corners — that's fair MAP knowledge (any
    # human knows it too). Anchors at 15% margins + center; probed
    # farthest-from-home first. Without this, random-walk scouting under
    # fair perception never found the enemy and matches timed out.
    def _spawn_anchors(self):
        w, h = self.game.game_map.width, self.game.game_map.height
        mc, mr = max(3, int(w * 0.15)), max(3, int(h * 0.15))
        cols = (mc, w // 2, w - 1 - mc)
        rows = (mr, h // 2, h - 1 - mr)
        return [(r, c) for r in rows for c in cols]

    def _tile_explored(self, player, r, c):
        """Explored per the FOG grid — the model that actually gates the
        AI's knowledge. The scout's own 6-tile stamp is WIDER than fog
        sight (~2.7 tiles), so trusting it left permanent blind spots: a
        castle could sit on a scout-'explored' tile the fog never saw,
        and 2/12 fair-perception matches stalled exactly that way."""
        fog = getattr(self.game, "fog_of_war", None)
        if fog is not None and player in fog.visibility_grid:
            return fog.visibility_grid[player][r][c] >= fog.EXPLORED
        return (r, c) in self.explored_tiles.get(player, set())

    def next_unexplored_anchor(self, player, from_pos=None):
        """World position of the best fog-unexplored search target: spawn
        anchors first (farthest from our castle — enemies are maximally
        spread; nearest to from_pos as tie-break), then a coarse sweep for
        the farthest unexplored ground once anchors are done. None only
        when the map is essentially fully explored. Also used by the
        military brain for armed scouting when no enemy is known."""
        own_castle = next(
            (b for b in self.game.buildings
             if b.player == player and b.name == "castle" and b.hp > 0),
            None,
        )

        def key_for(r, c):
            wx, wy = self.game.game_map.grid_to_world(c, r)
            home_dist = math.hypot(wx - own_castle.x, wy - own_castle.y) if own_castle else 0.0
            travel = math.hypot(wx - from_pos[0], wy - from_pos[1]) if from_pos else 0.0
            return (-home_dist, travel), (wx, wy)

        best = None
        best_key = None
        for r, c in self._spawn_anchors():
            if self._tile_explored(player, r, c):
                continue
            key, pos = key_for(r, c)
            if best_key is None or key < best_key:
                best, best_key = pos, key
        if best is not None:
            return best

        # Anchors done, enemy still unknown: sweep a coarse grid for the
        # farthest unexplored ground (fills the anchor gaps — the search
        # never goes back to blind random-walking).
        h, w = self.game.game_map.height, self.game.game_map.width
        for r in range(3, h - 3, 4):
            for c in range(3, w - 3, 4):
                if self._tile_explored(player, r, c):
                    continue
                key, pos = key_for(r, c)
                if best_key is None or key < best_key:
                    best, best_key = pos, key
        return best

    def _find_unexplored_target(self, player, scout):
        """Find an unexplored tile to send the scout to."""
        # If we know enemy castle, scout around it
        enemy_castle = self.known_enemy_castles.get(player)
        if enemy_castle and random.random() < 0.3:
            # Scout perimeter of enemy base
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(200, 400)
            return (enemy_castle[0] + math.cos(angle) * dist,
                   enemy_castle[1] + math.sin(angle) * dist)

        # Probe likely spawn areas before wandering (§8.11)
        anchor = self.next_unexplored_anchor(player, (scout.x, scout.y))
        if anchor is not None:
            return anchor

        # Otherwise, find an unexplored edge
        map_w = self.game.game_map.width
        map_h = self.game.game_map.height

        # Pick random unexplored tiles near the edge (fog model — §8.11)
        candidates = []
        for _ in range(20):
            r = random.randint(2, map_h - 3)
            c = random.randint(2, map_w - 3)
            if not self._tile_explored(player, r, c):
                world_pos = self.game.game_map.grid_to_world(c, r)
                candidates.append((world_pos, math.hypot(world_pos[0] - scout.x, world_pos[1] - scout.y)))
        
        if candidates:
            # Prefer closer targets
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]
        
        # If mostly explored, pick random spot
        r = random.randint(5, map_h - 6)
        c = random.randint(5, map_w - 6)
        return self.game.game_map.grid_to_world(c, r)

    def get_exploration_percent(self, player):
        """Return percentage of map explored (fog model when available —
        the scout's own 6-tile stamp overestimates coverage, §8.11)."""
        fog = getattr(self.game, "fog_of_war", None)
        if fog is not None and player in fog.visibility_grid:
            return fog.get_exploration_percent(player)
        explored = self.explored_tiles.get(player, set())
        total_tiles = self.game.game_map.width * self.game.game_map.height
        if total_tiles == 0:
            return 0
        return len(explored) / total_tiles * 100
