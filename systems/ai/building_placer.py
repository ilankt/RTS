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
        """Ring search around the castle (100-300px, 30-degree increments).

        Watchtowers bias the search toward the threat (§8.10): angles closest
        to the bearing of the nearest enemy castle are tried first, so towers
        stand between the base and the enemy instead of at the first free slot
        due-east."""
        if not ctx.castle:
            return None

        angles = list(range(0, 360, 30))
        distances = list(range(100, 320, 40))
        angle_major = False
        if building_type == "watchtower":
            bearing = self._threat_bearing(ctx)
            if bearing is not None:
                angles.sort(key=lambda a: abs(((a - bearing + 180) % 360) - 180))
                # Bearing outranks distance for towers: take the best-facing
                # slot even if it sits on an outer ring - and search farther
                # out, since the ground toward the enemy is usually cluttered
                # with the base's own resource clusters.
                angle_major = True
                distances = list(range(100, 460, 40))

        if angle_major:
            candidates = ((a, d) for a in angles for d in distances)
        else:
            candidates = ((a, d) for d in distances for a in angles)

        for angle_deg, distance in candidates:
            angle = math.radians(angle_deg)
            x = ctx.castle.x + distance * math.cos(angle)
            y = ctx.castle.y + distance * math.sin(angle)
            if self._is_valid_position(x, y, building_type, ctx):
                return (x, y)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near castle", "AI")
        return None

    # --- §8.10 AI walling -------------------------------------------------
    # Outside the base-building ring search (up to 320 from the castle) plus
    # the largest building radius, so own structures don't straddle the line.
    WALL_DISTANCE = 420
    WALL_SPACING = 56       # center-to-center segment spacing (radius 32 → sealed)
    WALL_PIECE = "wooden_wall"
    _WALL_NAMES = ("wall", "wooden_wall", "gate")

    def plan_wall_line(self, ctx, segments: int):
        """Planned wall line across the threat bearing: [(piece_name, x, y), ...].

        A straight picket of `segments` slots centered where the bearing from
        the castle to the nearest enemy castle crosses WALL_DISTANCE, laid
        perpendicular to that bearing, with a gate in the middle slot so the
        owner's own workers keep a way through. Deterministic given the castle
        and enemy positions, so re-planning each tick converges on one line.
        """
        if not ctx.castle or segments <= 0:
            return []
        bearing = self._threat_bearing(ctx)
        if bearing is None:
            return []
        theta = math.radians(bearing)
        center_x = ctx.castle.x + self.WALL_DISTANCE * math.cos(theta)
        center_y = ctx.castle.y + self.WALL_DISTANCE * math.sin(theta)
        # Perpendicular to the bearing
        perp_x, perp_y = -math.sin(theta), math.cos(theta)
        gate_index = segments // 2
        plan = []
        for i in range(segments):
            offset = (i - (segments - 1) / 2) * self.WALL_SPACING
            piece = "gate" if i == gate_index else self.WALL_PIECE
            plan.append((piece, center_x + offset * perp_x, center_y + offset * perp_y))
        return plan

    def next_wall_piece(self, ctx, segments: int) -> Optional[Tuple[str, Tuple[float, float]]]:
        """First plannable wall slot not yet occupied: (piece_name, (x, y)).

        Slots already holding one of the player's wall pieces (built or under
        construction) are skipped; slots blocked by terrain or other statics
        are skipped too (the line gets a hole there — obstacles usually block
        that spot anyway). If the planned gate slot itself is blocked — e.g.
        by the player's own watchtower, which targets the same bearing — the
        gate role moves to the nearest open slot so the line always keeps a
        way through for the owner's workers. Returns None when the line is
        done or unplannable.
        """
        plan = self.plan_wall_line(ctx, segments)
        if not plan:
            return None
        occupied = [
            (b.x, b.y)
            for name in self._WALL_NAMES
            for b in ctx.buildings.get(name, [])
        ] + [
            (s.x, s.y)
            for s in ctx.construction_sites
            if s.building_name in self._WALL_NAMES
        ]
        half_gap = self.WALL_SPACING / 2
        slots = []
        for i, (piece, x, y) in enumerate(plan):
            taken = any(math.hypot(x - ox, y - oy) < half_gap for ox, oy in occupied)
            valid = self._is_valid_wall_position(x, y, piece, ctx)
            slots.append({"i": i, "piece": piece, "x": x, "y": y,
                          "taken": taken, "valid": valid})

        # Keep the gate reachable: if no gate exists in the line yet and the
        # planned gate slot can't be built, reassign it to the closest open slot.
        gate_positions = [(g.x, g.y) for g in ctx.buildings.get("gate", [])] + [
            (s.x, s.y) for s in ctx.construction_sites if s.building_name == "gate"
        ]
        line_has_gate = any(
            math.hypot(s["x"] - gx, s["y"] - gy) < half_gap
            for s in slots for gx, gy in gate_positions
        )
        if not line_has_gate:
            gate_slot = next(s for s in slots if s["piece"] == "gate")
            if gate_slot["taken"] or not gate_slot["valid"]:
                replacement = min(
                    (s for s in slots if not s["taken"] and s["valid"]),
                    key=lambda s: abs(s["i"] - gate_slot["i"]),
                    default=None,
                )
                if replacement is not None:
                    gate_slot["piece"] = self.WALL_PIECE
                    replacement["piece"] = "gate"

        for s in slots:
            if not s["taken"] and s["valid"]:
                return (s["piece"], (s["x"], s["y"]))
        return None

    def _is_valid_wall_position(self, x: float, y: float, piece: str, ctx) -> bool:
        """Like _is_valid_position but without the +30 spacing padding —
        wall segments must pack shoulder to shoulder to seal."""
        map_w = self.game.game_map.width * TILE_WIDTH
        map_h = self.game.game_map.height * TILE_HEIGHT
        if x < 50 or y < 50 or x > map_w - 50 or y > map_h - 50:
            return False
        grid_pos = self.game.game_map.world_to_grid(x, y)
        if not grid_pos:
            return False
        col, row = grid_pos
        if col < 0 or col >= self.game.game_map.width or row < 0 or row >= self.game.game_map.height:
            return False
        if self.game.game_map.grid[row][col] not in ("grass", "plains", "dirt"):
            return False
        template = self.game.game_data["buildings"].get(piece)
        if not template:
            return False
        radius = template.size[0] * TILE_WIDTH / 2
        collision = getattr(self.game, "collision_system", None)
        if collision is not None:
            for obj in collision.query_nearby_static(x, y, radius + 96):
                # Sibling wall pieces/sites may touch; anything else may not overlap
                sibling = (getattr(obj, "name", "") in self._WALL_NAMES
                           or getattr(obj, "building_name", "") in self._WALL_NAMES)
                allowed = radius * 0.5 if sibling else radius + obj.radius
                if math.hypot(x - obj.x, y - obj.y) < allowed:
                    return False
        for building in ctx.enemy_buildings:
            if building.name == "castle" and math.hypot(x - building.x, y - building.y) < 500:
                return False
        return True

    def _threat_bearing(self, ctx) -> Optional[float]:
        """Bearing (degrees) from own castle toward the most relevant threat."""
        if not ctx.castle:
            return None
        targets = [b for b in ctx.enemy_buildings if b.name == "castle"] or ctx.enemy_buildings
        if not targets:
            return None
        nearest = min(targets, key=lambda b: (b.x - ctx.castle.x) ** 2 + (b.y - ctx.castle.y) ** 2)
        return math.degrees(math.atan2(nearest.y - ctx.castle.y, nearest.x - ctx.castle.x)) % 360

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
