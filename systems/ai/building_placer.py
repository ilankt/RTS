"""Simple building placement for AI - ring search around castle or resources."""
import math
from typing import Optional, Tuple
from core.config import GRID_SIZE, TILE_WIDTH, TILE_HEIGHT
from systems.ai.economy_helpers import ranked_resources_for_dropoff
from utils.debug_logger import debug_log


class BuildingPlacer:
    """Find valid build positions using simple ring search."""

    # Buildings that must be placed near their matching resource
    RESOURCE_BUILDINGS = {
        "mine": "gold",
        "lumbermill": "wood",
    }

    # §9 placement-starvation fix: the 72-candidate castle ring saturates
    # after ~6 buildings plus terrain (measured: stable 580/596 placement
    # attempts failed across 600 sim-s; houses/markets/blacksmiths starved
    # too). When it exhausts, fall back to an exhaustive nearest-first
    # lattice scan (_fallback_grid_search), capped PER BUILDING so base
    # structures never straddle the §8.10 wall line: candidate distance
    # <= WALL_DISTANCE − wall-piece radius − the building's own radius
    # (a single hand-derived cap drifted immediately — 340 was right for
    # the radius-48 stable but violated the invariant for the radius-64
    # watchtower).
    # A base with no room stays that way for a while — don't burn the full
    # lattice scan every 0.5 s tick forever once it has come up empty.
    FALLBACK_RETRY_SECONDS = 10.0

    def __init__(self, game):
        self.game = game
        # player name -> (retry sim time, smallest radius that found no slot)
        self._fallback_backoff = {}
        # (player name, building type) -> retry sim time (§7 P1 resource path)
        self._resource_backoff = {}

    def _fallback_cap(self, building_radius: float, ctx) -> float:
        """Max distance from the castle for fallback placements.

        The §8.10 wall-line invariant (structures must not straddle the
        planned wall) only binds when a wall line can actually exist: walls
        enabled as content AND this personality maintains segments. Otherwise
        the cap starved placement outright (§7 P1: temple 162/162 failures on
        one seed — a congested base exhausts the 356 px disc permanently), so
        the search may use the full lattice radius."""
        wall = self.game.game_data.get("buildings", {}).get("wooden_wall")
        walls_live = wall is not None and getattr(wall, "buildable", True)
        if walls_live:
            from systems.ai.utility.personality import wall_segments

            if wall_segments(getattr(ctx.player, "ai_personality", "balanced")) > 0:
                wall_radius = wall.radius if wall is not None else 32
                return self.WALL_DISTANCE - wall_radius - building_radius
        return self._FALLBACK_LATTICE_RADIUS - building_radius

    def find_position(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Find a valid position for the given building type."""
        if building_type in self.RESOURCE_BUILDINGS:
            return self._find_near_resource(building_type, ctx)
        else:
            return self._find_near_castle(building_type, ctx)

    # §7 P1: a dropoff must stay within RESOURCE_SERVICE_RADIUS (280) of the
    # cluster it serves — cap the lattice fallback below that so a rescued
    # placement still counts as servicing the node.
    RESOURCE_FALLBACK_CAP = 260

    def _find_near_resource(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Ring search around the best unserved resource clusters (§7 P1:
        several candidates, not one — a cluster whose surroundings can't fit
        the building no longer blocks placement forever), with a lattice
        fallback around each before moving to the next cluster."""
        resource_name = self.RESOURCE_BUILDINGS[building_type]
        if not ctx.castle:
            return None

        # Failure backoff: when every candidate cluster came up empty, the
        # ground won't change within a tick — skip the scan for a while.
        key = (getattr(ctx.player, "name", ""), building_type)
        now = getattr(self.game, "sim_time_elapsed", 0.0)
        if now < self._resource_backoff.get(key, 0.0):
            return None

        # limit 5: dense forest interiors are unbuildable terrain — more
        # distinct clusters means some candidate sits near open ground.
        candidates = ranked_resources_for_dropoff(ctx, building_type, limit=5)
        if not candidates:
            debug_log.log(f"AI BuildingPlacer: No unserved known {resource_name} resource found for {building_type}", "AI")
            return None

        for resource in candidates:
            for distance in range(80, 220, 40):
                for angle_deg in range(0, 360, 30):
                    angle = math.radians(angle_deg)
                    x = resource.x + distance * math.cos(angle)
                    y = resource.y + distance * math.sin(angle)
                    if self._is_valid_position(x, y, building_type, ctx):
                        return (x, y)
            # Ring saturated (pocket-sized holes, terrain) — 20 px lattice
            # around the cluster before giving up on it.
            cap_sq = self.RESOURCE_FALLBACK_CAP ** 2
            for dx, dy in self._fallback_lattice():
                if dx * dx + dy * dy > cap_sq:
                    break  # offsets are sorted nearest-first
                x, y = resource.x + dx, resource.y + dy
                if self._is_valid_position(x, y, building_type, ctx):
                    return (x, y)

        self._resource_backoff[key] = now + self.FALLBACK_RETRY_SECONDS
        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near {resource_name}", "AI")
        return None

    def _rebuild_anchor(self, ctx) -> Optional[Tuple[float, float]]:
        """§8.12 castle rebuild: with no castle to ring around, anchor at
        the surviving base — the own building nearest the worker cluster,
        else the worker cluster itself."""
        if not ctx.workers:
            return None
        wx = sum(w.x for w in ctx.workers) / len(ctx.workers)
        wy = sum(w.y for w in ctx.workers) / len(ctx.workers)
        own = [b for group in ctx.buildings.values() for b in group if b.hp > 0]
        if own:
            nearest = min(own, key=lambda b: (b.x - wx) ** 2 + (b.y - wy) ** 2)
            return (nearest.x, nearest.y)
        return (wx, wy)

    def _forward_tower_anchor(self, ctx) -> Optional[Tuple[float, float]]:
        """§8.12 batch 3 map awareness: after the first castle-ring tower,
        towers guard the FORWARD ECONOMY — the dropoffs raids target. Pick
        the forward dropoff (>=300px from the castle) farthest from every
        existing tower (the least-protected one)."""
        if not ctx.castle:
            return None
        towers = ctx.buildings.get("watchtower", [])
        best, best_score = None, -1.0
        for name in ("mine", "lumbermill", "market"):
            for building in ctx.buildings.get(name, []):
                castle_dist = math.hypot(building.x - ctx.castle.x, building.y - ctx.castle.y)
                if castle_dist < 300:
                    continue  # castle-ring towers already cover home turf
                tower_dist = min(
                    (math.hypot(building.x - t.x, building.y - t.y) for t in towers),
                    default=1e9,
                )
                if tower_dist < 260:
                    continue  # this one is already guarded
                if tower_dist > best_score:
                    best, best_score = building, tower_dist
        if best is None:
            return None
        return (best.x, best.y)

    def _find_near_castle(self, building_type: str, ctx) -> Optional[Tuple[float, float]]:
        """Ring search around the castle (100-300px, 30-degree increments).

        Watchtowers bias the search toward the threat (§8.10): angles closest
        to the bearing of the nearest enemy castle are tried first, so towers
        stand between the base and the enemy instead of at the first free slot
        due-east."""
        if ctx.castle:
            anchor_x, anchor_y = ctx.castle.x, ctx.castle.y
        elif building_type == "castle":
            anchor = self._rebuild_anchor(ctx)
            if anchor is None:
                return None
            anchor_x, anchor_y = anchor
        else:
            return None

        # Towers after the first guard the forward economy when one needs it
        if building_type == "watchtower" and ctx.buildings.get("watchtower"):
            forward = self._forward_tower_anchor(ctx)
            if forward is not None:
                for distance in range(90, 220, 40):
                    for angle_deg in range(0, 360, 30):
                        angle = math.radians(angle_deg)
                        x = forward[0] + distance * math.cos(angle)
                        y = forward[1] + distance * math.sin(angle)
                        if self._is_valid_position(x, y, "watchtower", ctx):
                            return (x, y)
                # fall through to the castle ring if nothing fits out there

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
            x = anchor_x + distance * math.cos(angle)
            y = anchor_y + distance * math.sin(angle)
            if self._is_valid_position(x, y, building_type, ctx):
                return (x, y)

        # §9 placement-starvation fix: the classic ring is full — try the
        # exhaustive lattice. Failure backoff is per player and radius-aware:
        # a scan that found nothing for radius r proves failure for any
        # radius >= r, while a SMALLER building may still fit and scans
        # anyway.
        template = self.game.game_data["buildings"].get(building_type)
        radius = template.radius if template is not None else 0
        key = getattr(ctx.player, "name", "")
        now = getattr(self.game, "sim_time_elapsed", 0.0)
        retry_at, failed_radius = self._fallback_backoff.get(key, (0.0, float("inf")))
        if now >= retry_at or radius < failed_radius:
            position = self._fallback_grid_search(building_type, ctx, anchor_x, anchor_y)
            if position is not None:
                return position
            if now < retry_at:
                failed_radius = min(failed_radius, radius)
            else:
                failed_radius = radius
            self._fallback_backoff[key] = (now + self.FALLBACK_RETRY_SECONDS, failed_radius)

        debug_log.log(f"AI BuildingPlacer: No valid position found for {building_type} near castle", "AI")
        return None

    # Lattice offsets, nearest-first, built once at the widest cap any search
    # may use (§7 P1: 600 px — the wall-line cap of ~356 only applies while a
    # wall line can exist, see _fallback_cap); each search breaks at its own
    # per-building cap. Step matches the nav grid: ~2800 candidate points,
    # scan cost bounded by the FALLBACK_RETRY_SECONDS backoff.
    _FALLBACK_LATTICE = None
    _FALLBACK_LATTICE_RADIUS = 600

    @classmethod
    def _fallback_lattice(cls):
        if cls._FALLBACK_LATTICE is None:
            cap, step = cls._FALLBACK_LATTICE_RADIUS, GRID_SIZE
            offsets = [
                (dx, dy)
                for dx in range(-cap, cap + 1, step)
                for dy in range(-cap, cap + 1, step)
                if dx * dx + dy * dy <= cap * cap
            ]
            offsets.sort(key=lambda o: o[0] * o[0] + o[1] * o[1])
            cls._FALLBACK_LATTICE = offsets
        return cls._FALLBACK_LATTICE

    def _fallback_grid_search(self, building_type: str, ctx,
                              castle_x: float, castle_y: float) -> Optional[Tuple[float, float]]:
        """§9: exhaustive nearest-first lattice scan around the castle,
        capped per building by the §8.10 wall-line invariant (_fallback_cap).

        A denser RING search is not enough: adjacent 15° ring points sit up
        to ~89 px apart at the outer radii, and late-game bases keep exactly
        pocket-sized holes — measured on seed 12345: 465/465 ring-fallback
        failures had a valid slot that a 20 px lattice found. Cost on the
        failure path is bounded by the radius-aware FALLBACK_RETRY_SECONDS
        backoff."""
        template = self.game.game_data["buildings"].get(building_type)
        if template is None:
            return None
        cap_sq = self._fallback_cap(template.radius, ctx) ** 2
        for dx, dy in self._fallback_lattice():
            if dx * dx + dy * dy > cap_sq:
                break  # offsets are sorted nearest-first
            x, y = castle_x + dx, castle_y + dy
            if self._is_valid_position(x, y, building_type, ctx):
                return (x, y)
        return None

    # --- §7 P5 expansion --------------------------------------------------

    EXPANSION_MIN_DISTANCE = 700   # a real second base, not a castle-ring annex
    EXPANSION_MAX_DISTANCE = 2200  # not a suicide island across the map either
    EXPANSION_MAX_THREAT = 300     # don't plant a base in the enemy's lap

    def find_expansion_anchor(self, ctx):
        """Best far, unserved, quiet resource to expand toward, or None.

        The castle is a universal dropoff (DROP_OFF_BUILDINGS), so planting
        one on a rich distant cluster instantly serves it. Cheap: reuses the
        per-tick cluster counts, one pass over known resources."""
        castle = ctx.castle
        if castle is None:
            return None
        from systems.ai.economy_helpers import (
            _cluster_counts, find_nearest_dropoff_ctx, RESOURCE_SERVICE_RADIUS)

        best, best_score = None, 0.0
        for resource_type in ("gold", "wood"):
            resources = ctx.known_resources(resource_type)
            if not resources:
                continue
            counts = _cluster_counts(ctx, resource_type, resources)
            for resource in resources:
                dist = math.hypot(resource.x - castle.x, resource.y - castle.y)
                if not (self.EXPANSION_MIN_DISTANCE <= dist <= self.EXPANSION_MAX_DISTANCE):
                    continue
                if ctx.threat_at(resource.x, resource.y) > self.EXPANSION_MAX_THREAT:
                    continue
                _, nearest = find_nearest_dropoff_ctx(
                    ctx, resource_type, (resource.x, resource.y), include_pending=True)
                if nearest <= RESOURCE_SERVICE_RADIUS:
                    continue  # already served — nothing to gain by moving in
                # Rich clusters win; gold (the chronic bottleneck) counts double
                score = counts.get(id(resource), 0) * (2.0 if resource_type == "gold" else 1.0)
                if score > best_score:
                    best, best_score = resource, score
        return best

    def find_expansion_position(self, ctx) -> Optional[Tuple[float, float]]:
        """A castle slot near the expansion anchor (ring, then lattice)."""
        anchor = self.find_expansion_anchor(ctx)
        if anchor is None:
            return None
        key = (getattr(ctx.player, "name", ""), "castle_expansion")
        now = getattr(self.game, "sim_time_elapsed", 0.0)
        if now < self._resource_backoff.get(key, 0.0):
            return None
        for distance in range(140, 320, 40):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                x = anchor.x + distance * math.cos(angle)
                y = anchor.y + distance * math.sin(angle)
                if self._is_valid_position(x, y, "castle", ctx):
                    return (x, y)
        cap_sq = 340 ** 2
        for dx, dy in self._fallback_lattice():
            if dx * dx + dy * dy > cap_sq:
                break
            x, y = anchor.x + dx, anchor.y + dy
            if self._is_valid_position(x, y, "castle", ctx):
                return (x, y)
        self._resource_backoff[key] = now + self.FALLBACK_RETRY_SECONDS
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
        if not self._is_explored_by(ctx.player, x, y):
            return False  # §8.11: walls need revealed ground too
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

    def _is_explored_by(self, player, x: float, y: float) -> bool:
        """§8.11: building requires REVEALED ground — the AI may only place
        where its own fog grid says explored (is_explored short-circuits to
        True when fog is off as a game rule, e.g. the revealed_map mutator)."""
        fog = getattr(self.game, "fog_of_war", None)
        if fog is None:
            return True
        return fog.is_explored(player, x, y)

    def _is_valid_position(self, x: float, y: float, building_type: str, ctx) -> bool:
        """Check terrain, collisions, and enemy proximity."""
        # Get building radius from template (needed for radius-aware bounds)
        building_template = self.game.game_data["buildings"].get(building_type)
        if not building_template:
            return False
        building_radius = building_template.radius

        # Map bounds — radius-aware (§8.12 batch 3): a flat 50px margin let
        # large buildings sit half outside the world at the map border
        map_w = self.game.game_map.width * TILE_WIDTH
        map_h = self.game.game_map.height * TILE_HEIGHT
        margin = building_radius + 20
        if x < margin or y < margin or x > map_w - margin or y > map_h - margin:
            return False

        # §8.11: never build on unexplored ground
        if not self._is_explored_by(ctx.player, x, y):
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
