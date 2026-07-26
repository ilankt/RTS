import random
import math
from entities import Building, Unit, Resource
from entities.resource import assign_biome_sprite
from systems.animation import Animation
from utils.debug_logger import debug_log
from core.config import (MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, BLOCKED_TERRAIN,
                         RESOURCE_TERRAIN, SPAWN_SAFE_TERRAIN)

# §8.9 healing fountain: minimum WORLD-unit gap from any castle. The design
# invariant (tests/test_depth3.py) is "> 600px, neutral ground not a base
# buff"; this sits above it so placement never lands on the boundary.
FOUNTAIN_MIN_CASTLE_DIST = 640


class GameState:
    """Manages game object creation and initial game state setup"""
    
    def __init__(self, game):
        self.game = game
    
    def setup_game_objects(self):
        """Set up initial game objects for all players"""
        spawn_locations = []
        spread_spawns = []
        try:
            spread_spawns = self.game.game_map.find_spawn_locations(len(self.game.players))
        except ValueError:
            spread_spawns = []

        for i, player in enumerate(self.game.players):
            # Find a safe spawn location for the castle
            castle_template = self.game.game_data["buildings"]["castle"]
            if i < len(spread_spawns):
                spawn_r, spawn_c = spread_spawns[i]
                castle_world_pos = self.game.game_map.grid_to_world(spawn_c, spawn_r)
            else:
                castle_world_pos = self.game.game_map.find_safe_spawn_position(castle_template.radius)
            if castle_world_pos is None:
                raise Exception("Could not find a safe spawn position for the castle.")
            grid_x, grid_y = self.game.game_map.world_to_grid(castle_world_pos[0], castle_world_pos[1])
            spawn_locations.append((grid_y, grid_x))

            # Create castle
            castle = self._create_instance_from_template(castle_template)
            castle.x, castle.y = castle_world_pos
            castle.player = player
            self.game.buildings.append(castle)

            # Match-start home survey: you know your own surroundings —
            # critically the spawn forest, which sits past the castle's
            # sight line since the 2026-07-25 keep-out round (AI gathers
            # only from EXPLORED nodes and was starving for wood).
            fog = getattr(self.game, "fog_of_war", None)
            if fog is not None:
                fog.reveal_home_area(player, castle.x, castle.y)

            # Find a safe spawn location for the worker near the castle
            worker_template = self.game.game_data["units"]["worker"]
            search_range = (castle.radius + worker_template.radius + 10, castle.radius + worker_template.radius + 50)
            worker_world_pos = self.game.game_map.find_safe_spawn_position(worker_template.radius, center_pos=castle_world_pos, search_range=search_range)
            if worker_world_pos is None:
                # Fallback: place the worker next to the castle if the specific search fails
                worker_world_pos = (castle_world_pos[0] + castle.radius + worker_template.radius + 10, castle_world_pos[1])

            # Create worker
            worker = self._create_instance_from_template(worker_template)
            worker.x, worker.y = worker_world_pos
            worker.player = player
            
            # Set up animations with player-specific colors
            animations = {}
            for anim_name, anim_path in worker.animations.items():
                sheet = self.game.sprite_manager.get_unit_animation_sheet("worker", anim_name, i)
                animations[anim_name] = Animation(sheet, 192, 192, 100)
            worker.set_animations(animations)
            
            self.game.units.append(worker)

        # Center camera on the human castle, or on the first AI castle in spectator mode.
        focus_castle = next((b for b in self.game.buildings if b.player.human), None)
        if not focus_castle:
            focus_castle = next((b for b in self.game.buildings if b.name == "castle"), None)
        if focus_castle:
            self.game.camera.x = (MAP_VIEW_WIDTH / 2) - focus_castle.x * self.game.camera.zoom
            self.game.camera.y = (MAP_VIEW_HEIGHT / 2) - focus_castle.y * self.game.camera.zoom

        # §11.2 mountains + props BEFORE resources: everything placed after
        # them collision-checks against them, so nothing spawns inside
        self._place_mountains(spawn_locations)
        self._place_props(spawn_locations)

        # Place some resources around the map
        self._place_resources(spawn_locations)
    
    def _create_instance_from_template(self, template):
        """Create a new instance from a template object"""
        if isinstance(template, Building):
            return Building(
                name=template.name,
                size=template.size,
                hp=template.hp,
                sprite=template.sprite,
                build_duration=template.build_duration,
                radius=template.radius,
                costs=getattr(template, "costs", {}),
                armor_type=getattr(template, "armor_type", "fortified"),
                armor_value=getattr(template, "armor_value", 0),
                can_attack=getattr(template, "can_attack", False),
                min_damage=getattr(template, "min_damage", 0),
                max_damage=getattr(template, "max_damage", 0),
                attack_type=getattr(template, "attack_type", "slash"),
                attack_speed=getattr(template, "attack_speed", 1.0),
                attack_range=getattr(template, "attack_range", 0),
                display_name=getattr(template, "display_name", None),
                role=getattr(template, "role", ""),
                requires=list(getattr(template, "requires", [])),
                buildable=getattr(template, "buildable", True),
                strong_against=list(getattr(template, "strong_against", [])),
                weak_against=list(getattr(template, "weak_against", [])),
            )
        elif isinstance(template, Unit):
            return Unit(
                name=template.name,
                size=template.size,
                hp=template.hp,
                movement_speed=template.movement_speed,
                attack=template.attack,
                animations=template.animations.copy(),
                radius=template.radius,
                can_build=template.can_build,
                can_attack=template.can_attack_flag,
                min_damage=template.min_damage,
                max_damage=template.max_damage,
                attack_type=template.attack_type,
                armor_type=template.armor_type,
                armor_value=template.armor_value,
                attack_speed=template.attack_speed,
                attack_range=template.attack_range,
                display_name=getattr(template, "display_name", None),
                role=getattr(template, "role", ""),
                requires=list(getattr(template, "requires", [])),
                buildable=getattr(template, "buildable", True),
                strong_against=list(getattr(template, "strong_against", [])),
                weak_against=list(getattr(template, "weak_against", [])),
                building_only_attack=getattr(template, "building_only_attack", False),
            )
        elif isinstance(template, Resource):
            return Resource(
                name=template.name,
                sprite=template.sprite,
                radius=template.radius
            )
        else:
            # Fallback for other GameObject types
            return template.__class__(
                name=template.name,
                size=template.size,
                hp=template.hp,
                sprite=template.sprite,
                radius=template.radius
            )
    
    def _place_resources(self, spawn_locations):
        """Place resources around the map"""
        # First, place guaranteed resources near each castle
        for spawn_r, spawn_c in spawn_locations:
            # Starting gold: ONE rich deposit near the castle. Big enough to
            # carry the early game, so hunting for fresh deposits is a mid-game
            # concern, not an opening chore. (2026-07-12)
            # Band tightened 3-5 → 3-4 tiles (2026-07-14): with haul time
            # dominating gold income, a 147 px vs 280 px starting deposit was
            # a ~2x income difference decided by spawn luck (instrumented
            # seed 1001). Wider band kept as fallback so placement never fails.
            #
            # 2500 → 3000 (2026-07-19, stone removal): this is now the only
            # mineral at home and has to last longer. Deliberately still ONE
            # node — the saturation cap (3 workers) is what keeps gold the
            # early bottleneck, and a second home node would double base gold
            # income overnight. Freed stone labour is meant to go OUT to the
            # contested map deposits below, not stack up in the base.
            if not self._place_resource_near_spawn("gold", spawn_r, spawn_c, 3, 4, 1, amount_override=3000):
                self._place_resource_near_spawn("gold", spawn_r, spawn_c, 3, 6, 1, amount_override=3000)

            # Starting wood (2026-07-25, user feedback): one connected FOREST
            # of 8-10 trees instead of 8 scattered singles. Same per-tree
            # amount, so early wood income is unchanged; only the shape moved.
            self._place_spawn_forest(spawn_r, spawn_c, amount_override=250)
        
        # Calculate resource counts based on map size and player count
        map_area = self.game.game_map.width * self.game.game_map.height
        player_count = len(self.game.players)
        
        # Base resource counts scaled by map area (40x40 = 1600 tiles as reference)
        area_factor = map_area / 1600.0
        
        # Reduce resources for more players (more competition)
        player_factor = 1.0 - (player_count - 2) * 0.1  # -10% per player above 2
        player_factor = max(0.5, player_factor)  # Minimum 50%
        
        # Resource counts (rebalance 2026-07-12): FEWER but far RICHER gold
        # deposits — you control a deposit longer and hunt less often — and MORE
        # wood clusters so timber is always easy to find nearby.
        #
        # 1-2 → 2-3 map gold nodes (2026-07-19, stone removal): the stone
        # deposits that used to occupy this ground are gone, and the workers
        # who mined them need somewhere to go. Contested map gold is where
        # they go — that is the point of the swap, so do not fold this back
        # into the base without also re-tuning gold costs.
        extra_gold = int(random.randint(2, 3) * area_factor * player_factor)
        # 20-30 → 30-42 per 1600 tiles (2026-07-25, user: "plenty of wood").
        # Deliberately generous — the wood economy gets a balance pass later
        # (gather rate 2/s is suspected too fast), and forests-only placement
        # below means some of this budget is spent on cluster attempts that
        # roll back.
        extra_wood = int(random.randint(30, 42) * area_factor * player_factor)

        # Additional gold across the map — 5x richer per node (was 1500).
        for _ in range(extra_gold):
            self._place_random_resource("gold", spawn_locations, min_distance=15, amount_override=7500)

        # Instead of individual trees, create forest clusters (many more now)
        self._place_forest_clusters(extra_wood, spawn_locations)

        # §8.9 neutral healing fountain at the map center — contested ground
        self._place_fountain(spawn_locations)

    def _place_fountain(self, spawn_locations):
        """One healing fountain as near the map center as possible: open
        walkable terrain, clear of objects, and at least
        FOUNTAIN_MIN_CASTLE_DIST **world units** from every castle so it's
        genuinely neutral ground rather than somebody's private buff."""
        from entities.fountain import Fountain

        game_map = self.game.game_map
        center_r, center_c = game_map.height // 2, game_map.width // 2
        castles = [b for b in self.game.buildings if b.name == "castle"]

        def viable(r, c):
            if not (3 <= r < game_map.height - 3 and 3 <= c < game_map.width - 3):
                return False
            if game_map.grid[r][c] not in SPAWN_SAFE_TERRAIN:
                return False
            x, y = game_map.grid_to_world(c, r)
            # Measured in WORLD units against the real castles. The old rule
            # was "12 grid tiles from the spawn TILE", which broke the
            # invariant two ways: a hex column is 48px but a row is 56px, so
            # 12 tiles is 672px vertically and only 576px horizontally (under
            # the 600 the design wants); and the castle is placed at an offset
            # from its spawn tile, eating the rest of the margin. Seed 31007
            # landed a fountain 528px from a castle while passing the old
            # check. Castles already exist here — setup_game_objects places
            # them long before resources.
            for castle in castles:
                if math.hypot(x - castle.x, y - castle.y) < FOUNTAIN_MIN_CASTLE_DIST:
                    return False
            if self._check_collision_with_objects(x, y, 80):  # radius 70 + pad
                return False
            return self._has_open_approach(x, y, ring=100.0, needed=5)

        # Spiral out from the center until a viable tile is found
        for radius in range(0, 18):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if max(abs(dr), abs(dc)) != radius:
                        continue  # ring cells only
                    r, c = center_r + dr, center_c + dc
                    if viable(r, c):
                        x, y = game_map.grid_to_world(c, r)
                        fountain = Fountain(x, y)
                        self.game.fountains.append(fountain)
                        self.game.pathfinder.notify_blocker_added(fountain)
                        if getattr(self.game, "collision_system", None):
                            self.game.collision_system.invalidate_static_index()
                        return
        # No viable center spot (extreme maps): the match plays without one
    
    def _place_resource_near_spawn(self, resource_type, spawn_r, spawn_c, min_dist, max_dist, count, amount_override=None):
        """Place a specific number of resources near a spawn location.
        Returns True when everything requested was placed."""
        placed = 0
        attempts = 0
        max_attempts = count * 50
        
        while placed < count and attempts < max_attempts:
            # Random angle and distance for better distribution
            angle = random.uniform(0, 2 * 3.14159)
            distance = random.uniform(min_dist, max_dist)

            # Calculate position using proper circular distribution.
            # round(), not int(): truncation used to shrink the ring below
            # min_dist (a "3-4 tile" band produced 2.6-tile placements),
            # reintroducing the spawn-luck income spread (2026-07-14).
            dr = round(distance * math.sin(angle))
            dc = round(distance * math.cos(angle))
            if math.hypot(dr, dc) < min_dist:
                attempts += 1
                continue
            r = spawn_r + dr
            c = spawn_c + dc

            # Check bounds (keep away from edges)
            edge_buffer = 3  # Keep resources at least 3 tiles from edge
            if (edge_buffer <= r < self.game.game_map.height - edge_buffer and
                edge_buffer <= c < self.game.game_map.width - edge_buffer):
                # Check terrain suitability
                terrain = self.game.game_map.grid[r][c]
                suitable = False
                
                suitable = terrain in RESOURCE_TERRAIN.get(resource_type, ())
                
                if suitable:
                    world_pos = self.game.game_map.grid_to_world(c, r)

                    # Check collision with all game objects, and require an
                    # open approach: a node wedged into clutter with no
                    # walkable gathering ring starves that spawn's economy
                    # for the whole match (2026-07-14, instrumented run).
                    if (not self._check_collision_with_objects(world_pos[0], world_pos[1], 16)
                            and self._has_open_approach(world_pos[0], world_pos[1])):
                        resource_name = resource_type
                        
                        resource = self._create_instance_from_template(self.game.game_data["resources"][resource_name])
                        resource.x, resource.y = world_pos
                        if amount_override is not None:
                            resource.amount_remaining = amount_override
                        assign_biome_sprite(resource, self.game.game_map)
                        self.game.resources.append(resource)
                        placed += 1

            attempts += 1
        return placed >= count

    def _has_open_approach(self, x, y, ring=44.0, needed=4):
        """At least `needed` of 8 points on the gathering ring around (x, y)
        are on walkable terrain and clear of placed objects — workers can
        actually stand next to the node and mine it."""
        open_points = 0
        for i in range(8):
            angle = i * math.pi / 4
            px = x + ring * math.cos(angle)
            py = y + ring * math.sin(angle)
            grid = self.game.game_map.world_to_grid(px, py)
            if not grid:
                continue
            col, row = grid
            if not (0 <= row < self.game.game_map.height and 0 <= col < self.game.game_map.width):
                continue
            # (pre-hoist this also listed "mountain" — a tile that never
            # existed; mountains are §11.2 props, not terrain)
            if self.game.game_map.grid[row][col] in BLOCKED_TERRAIN:
                continue
            if self._check_collision_with_objects(px, py, 12):
                continue
            open_points += 1
            if open_points >= needed:
                return True
        return False

    # Forests (2026-07-25, user feedback): wood generates ONLY as forests.
    # A forest is a CONNECTED blob of tiles — one tree per hex tile, grown by
    # randomized BFS — never a gaussian sprinkle: the old sprinkle left most
    # trees with no adjacent neighbour, and clusters that failed part-way
    # kept their 1-4 orphan trees, which is exactly the "single trees
    # everywhere" the user reported.
    FOREST_MIN_TREES = 6
    FOREST_TREE_SPACING = 6  # gap (px) between a tree and non-tree obstacles
    # Round 2 ("everything is too together"): forest TILES keep ~5 tiles
    # clear of every castle and every non-wood resource — the same clearance
    # spawns keep from water (SPAWN_WATER_CLEARANCE). Also strictly covers
    # the older worry of a forest blocking a gold node's 44 px gathering
    # ring (ring + tree radius + probe clearance ≈ 98).
    FOREST_KEEPOUT_PX = 240.0

    def _grow_forest(self, center_r, center_c, target_trees,
                     amount_override=None, min_trees=None):
        """Grow one connected forest blob outward from a center tile and
        place its trees. Returns the list of placed trees — or [] after
        rolling everything back when fewer than `min_trees` (default
        FOREST_MIN_TREES) tiles fit (bad terrain/clutter/keep-outs):
        partial forests never leave orphan singles."""
        if min_trees is None:
            min_trees = self.FOREST_MIN_TREES
        game_map = self.game.game_map
        wood_terrain = RESOURCE_TERRAIN["wood"]
        keepout = [(b.x, b.y) for b in self.game.buildings
                   if b.name == "castle"]
        keepout += [(res.x, res.y) for res in self.game.resources
                    if res.name != "wood"]
        keepout_sq = self.FOREST_KEEPOUT_PX ** 2
        blob = []
        frontier = [(center_r, center_c)]
        seen = {(center_r, center_c)}
        while frontier and len(blob) < target_trees:
            # Random frontier pick → organic blob shapes, not hex discs
            r, c = frontier.pop(random.randrange(len(frontier)))
            if not (2 <= r < game_map.height - 2 and 2 <= c < game_map.width - 2):
                continue
            if game_map.grid[r][c] not in wood_terrain:
                continue
            x, y = game_map.grid_to_world(c, r)
            if any((kx - x) ** 2 + (ky - y) ** 2 < keepout_sq
                   for kx, ky in keepout):
                continue
            if self._check_collision_with_objects(x, y, 8,
                                                  spacing=self.FOREST_TREE_SPACING):
                continue
            blob.append((x, y))
            for neighbor in game_map.hex_neighbors(r, c):
                if neighbor not in seen:
                    seen.add(neighbor)
                    frontier.append(neighbor)
        if len(blob) < min_trees:
            return []

        placed = []
        for x, y in blob:
            tree = self._create_instance_from_template(
                self.game.game_data["resources"]["wood"])
            tree.x, tree.y = x, y
            if amount_override is not None:
                tree.amount_remaining = amount_override
            assign_biome_sprite(tree, game_map)
            self.game.resources.append(tree)
            placed.append(tree)
        return placed

    def _place_spawn_forest(self, spawn_r, spawn_c, amount_override=None):
        """One starting forest of 10-13 trees per spawn, centered 7-10 tiles
        out — past the castle/gold keep-out (FOREST_KEEPOUT_PX ≈ 5 tiles),
        so the base opening stays uncluttered but timber is still a short
        walk (round 2 feedback: "everything is too together")."""
        game_map = self.game.game_map
        wood_terrain = RESOURCE_TERRAIN["wood"]
        for band_min, band_max in ((7, 10), (6, 13)):  # widen before giving up
            for _ in range(60):
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(band_min, band_max)
                r = spawn_r + round(distance * math.sin(angle))
                c = spawn_c + round(distance * math.cos(angle))
                if not (3 <= r < game_map.height - 3 and 3 <= c < game_map.width - 3):
                    continue
                if game_map.grid[r][c] not in wood_terrain:
                    continue
                if self._grow_forest(r, c, random.randint(10, 13), amount_override):
                    return True
        return False

    def _place_forest_clusters(self, total_trees, spawn_locations):
        """Spend the map's tree budget on big forests of 14-28 trees each
        (round 2: "even bigger forests" — fewer, larger woods; a map forest
        that can't reach 10 trees rolls back), at least 8 tiles from every
        spawn (spawns get their own forest)."""
        game_map = self.game.game_map
        wood_terrain = RESOURCE_TERRAIN["wood"]
        trees_placed = 0
        attempts = 0
        max_attempts = 40 + total_trees * 3
        while trees_placed < total_trees and attempts < max_attempts:
            attempts += 1
            center_r = random.randint(4, game_map.height - 5)
            center_c = random.randint(4, game_map.width - 5)
            if any(math.hypot(center_r - sr, center_c - sc) < 8
                   for sr, sc in spawn_locations):
                continue
            if game_map.grid[center_r][center_c] not in wood_terrain:
                continue
            target = random.randint(14, 28)
            trees_placed += len(self._grow_forest(center_r, center_c, target,
                                                  min_trees=10))
    
    def _place_random_resource(self, resource_type, spawn_locations, min_distance, amount_override=None):
        """Place a resource randomly on the map, away from spawn locations"""
        attempts = 0
        edge_buffer = 5  # Keep resources well away from edges
        while attempts < 100:
            r = random.randint(edge_buffer, self.game.game_map.height - edge_buffer - 1)
            c = random.randint(edge_buffer, self.game.game_map.width - edge_buffer - 1)
            
            # Check terrain suitability
            terrain = self.game.game_map.grid[r][c]
            suitable = False
            
            suitable = terrain in RESOURCE_TERRAIN.get(resource_type, ())
            
            if suitable:
                # Check distance from spawn points
                too_close = False
                for spawn_r, spawn_c in spawn_locations:
                    dist = ((r - spawn_r)**2 + (c - spawn_c)**2)**0.5
                    if dist < min_distance:
                        too_close = True
                        break
                
                if not too_close:
                    world_pos = self.game.game_map.grid_to_world(c, r)
                    
                    # Check collision with all game objects
                    if not self._check_collision_with_objects(world_pos[0], world_pos[1], 16):  # 16 is resource radius (TILE_WIDTH/4)
                        resource_name = resource_type
                        
                        resource = self._create_instance_from_template(self.game.game_data["resources"][resource_name])
                        resource.x, resource.y = world_pos
                        if amount_override is not None:
                            resource.amount_remaining = amount_override
                        assign_biome_sprite(resource, self.game.game_map)
                        self.game.resources.append(resource)
                        break

            attempts += 1
    
    def _check_collision_with_objects(self, x, y, radius, spacing=20):
        """Check if a position would collide with any existing game object.
        `spacing` is the extra breathing room beyond the radii — forests
        shrink it so trees can pack tiles adjacent to other clutter."""
        for group in (self.game.buildings, self.game.units, self.game.resources,
                      getattr(self.game, "fountains", ()),
                      getattr(self.game, "mountains", ()),
                      getattr(self.game, "props", ())):
            for obj in group:
                dist = ((obj.x - x) ** 2 + (obj.y - y) ** 2) ** 0.5
                if dist < (obj.radius + radius + spacing):
                    return True
        return False

    # §11.2 mountain ridges: exclusion radii (tiles), chaining separation
    # (world px), and density cap per 1600 tiles. The elevation threshold
    # is ADAPTIVE — the top slice of the eligible ground — because the
    # island-shaped generator peaks at the (excluded) map center, so any
    # absolute threshold either starves flat maps or floods spiky ones.
    MOUNTAIN_ELEVATION_FLOOR = 0.28   # never ridge genuinely low ground
    MOUNTAIN_ELIGIBLE_FRACTION = 0.06  # top 6% of eligible cells qualify
    MOUNTAIN_SPAWN_CLEAR_TILES = 10
    MOUNTAIN_CENTER_CLEAR_TILES = 9
    MOUNTAIN_MIN_SEPARATION = 95.0
    MOUNTAINS_PER_1600_TILES = 7

    def _place_mountains(self, spawn_locations):
        """§11.2 mountains-as-props: ridge the high ground the old stone
        TILES used to mark. Candidates are the highest-elevation land
        cells; the ~2-tile separation lets perlin's natural elevation
        blobs chain into contiguous ridges instead of confetti. Spawn
        areas and the map center (fountain ground) stay clear, and a
        post-pass deletes any mountain that severs spawn-to-spawn
        reachability — an open map beats a broken one."""
        from entities.mountain import Mountain

        game_map = self.game.game_map
        elevation = getattr(game_map, "elevation", None)
        if not elevation:
            return
        cap = max(4, int(game_map.width * game_map.height / 1600.0
                         * self.MOUNTAINS_PER_1600_TILES))
        center = (game_map.height // 2, game_map.width // 2)

        eligible = []
        for r in range(2, game_map.height - 2):
            for c in range(2, game_map.width - 2):
                if game_map.grid[r][c] in BLOCKED_TERRAIN:
                    continue
                height = elevation[r][c]
                if height < self.MOUNTAIN_ELEVATION_FLOOR:
                    continue
                if math.hypot(r - center[0], c - center[1]) < self.MOUNTAIN_CENTER_CLEAR_TILES:
                    continue
                if any(math.hypot(r - sr, c - sc) < self.MOUNTAIN_SPAWN_CLEAR_TILES
                       for sr, sc in spawn_locations):
                    continue
                eligible.append((height, r, c))
        if not eligible:
            return
        eligible.sort(reverse=True)
        candidates = eligible[:max(cap * 3,
                                   int(len(eligible) * self.MOUNTAIN_ELIGIBLE_FRACTION))]
        threshold = candidates[-1][0]
        peak = candidates[0][0]
        spread = max(1e-6, peak - threshold)

        placed = []
        for height, r, c in candidates:
            if len(placed) >= cap:
                break
            x, y = game_map.grid_to_world(c, r)
            if any(math.hypot(x - m.x, y - m.y) < self.MOUNTAIN_MIN_SEPARATION
                   for m in placed):
                continue
            # Relatively higher ground grows bigger mountains (radius 60..110)
            radius = 60 + int(50 * (height - threshold) / spread)
            placed.append(Mountain(x, y, radius=radius))

        for mountain in placed:
            self.game.mountains.append(mountain)
            self.game.pathfinder.notify_blocker_added(mountain)
        if getattr(self.game, "collision_system", None):
            self.game.collision_system.invalidate_static_index()
        self._ensure_spawns_connected(spawn_locations)

    # §11.2 round 2: world props. Counts scale with map area; per-type
    # terrain, spawn clearance (tiles) and same-type separation (world px).
    PROP_PLACEMENT = {
        "rocks": {"terrain": {"grass", "desert", "dirt"}, "per_1600": 5,
                  "spawn_clear": 7, "separation": 150.0},
        "dead_tree": {"terrain": {"swamp"}, "per_1600": 5,
                      "spawn_clear": 5, "separation": 110.0},
        "ruins": {"terrain": {"grass", "desert", "dirt"}, "per_1600": 0.5,
                  "spawn_clear": 14, "separation": 900.0},
    }

    def _place_props(self, spawn_locations):
        """Scatter world props (rocks/dead trees/ruins) on their terrain,
        clear of spawns, the map center, and each other. Only types whose
        SPRITE exists are placed — props ship art-first. Blocking props
        register with nav and join the reachability guarantee."""
        from entities.prop import Prop, available_prop_types

        game_map = self.game.game_map
        center = (game_map.height // 2, game_map.width // 2)
        area_factor = game_map.width * game_map.height / 1600.0
        placed_any = False

        for name in sorted(available_prop_types()):
            rules = self.PROP_PLACEMENT.get(name)
            if rules is None:
                continue
            target = max(1, int(rules["per_1600"] * area_factor))
            placed = []
            attempts = 0
            while len(placed) < target and attempts < target * 60:
                attempts += 1
                r = random.randint(3, game_map.height - 4)
                c = random.randint(3, game_map.width - 4)
                if game_map.grid[r][c] not in rules["terrain"]:
                    continue
                if math.hypot(r - center[0], c - center[1]) < 6:
                    continue  # keep the fountain's neutral ground open
                if any(math.hypot(r - sr, c - sc) < rules["spawn_clear"]
                       for sr, sc in spawn_locations):
                    continue
                x, y = game_map.grid_to_world(c, r)
                if any(math.hypot(x - p.x, y - p.y) < rules["separation"]
                       for p in placed):
                    continue
                if self._check_collision_with_objects(x, y, 40):
                    continue
                prop = Prop(name, x, y)
                placed.append(prop)
                self.game.props.append(prop)
                if prop.blocks:
                    self.game.pathfinder.notify_blocker_added(prop)
                placed_any = True

        if placed_any:
            if getattr(self.game, "collision_system", None):
                self.game.collision_system.invalidate_static_index()
            self._ensure_spawns_connected(spawn_locations)

    def _blocking_world_props(self):
        """Everything huge-and-neutral that seals ground: mountains plus
        blocking props (rocks, ruins) — the reachability BFS's blocker set."""
        return (list(self.game.mountains)
                + [p for p in getattr(self.game, "props", ())
                   if getattr(p, "blocks", False)])

    def _ensure_spawns_connected(self, spawn_locations):
        """§11.2 reachability guarantee: every spawn can reach every other
        spawn on foot. Tile-level BFS over TRUE hex adjacency, with tiles
        under (or hugging) a mountain counting as blocked; while any spawn
        is cut off, the mountain nearest the failing corridor is deleted
        and the check reruns. Errs toward fewer mountains."""
        game_map = self.game.game_map
        if len(spawn_locations) < 2 or not self._blocking_world_props():
            return

        for _attempt in range(len(self._blocking_world_props()) + 1):
            unreachable = self._first_unreachable_spawn(spawn_locations)
            if unreachable is None:
                return
            blockers = self._blocking_world_props()
            if not blockers:
                # Still cut off with zero blockers: the WATER separates
                # these spawns (island map) — that predates props and
                # isn't ours to fix here.
                return
            # Delete the blocker closest to the line between spawn 0 and
            # the cut-off spawn — the likeliest wall in the corridor
            ax, ay = game_map.grid_to_world(spawn_locations[0][1], spawn_locations[0][0])
            bx, by = game_map.grid_to_world(unreachable[1], unreachable[0])
            blocker = min(
                blockers,
                key=lambda m: self._point_to_segment_sq(m.x, m.y, ax, ay, bx, by))
            blocker.in_world = False
            if blocker in self.game.mountains:
                self.game.mountains.remove(blocker)
            else:
                self.game.props.remove(blocker)
            self.game.pathfinder.notify_blocker_removed(blocker)
            debug_log.log(
                f"{blocker.name} at ({blocker.x:.0f}, {blocker.y:.0f}) removed: "
                "it cut off a spawn", "GENERAL")
        if getattr(self.game, "collision_system", None):
            self.game.collision_system.invalidate_static_index()

    def _first_unreachable_spawn(self, spawn_locations):
        """BFS from spawn 0 over walkable hex tiles; the first spawn not
        reached, or None when all are connected.

        ±1-tile tolerance on BOTH ends on purpose: spawn_locations come
        through the §8.13.4 world<->grid round trip, which can land one
        tile off (deliberately unfixed — see MASTER_PLAN). A spawn counts
        as connected if the component touches it OR any hex neighbour."""
        game_map = self.game.game_map
        blockers = self._blocking_world_props()

        def tile_open(r, c):
            if game_map.grid[r][c] in BLOCKED_TERRAIN:
                return False
            x, y = game_map.grid_to_world(c, r)
            # A tile whose center a blocker overlaps (plus a unit's width
            # of margin) doesn't count as a corridor
            return all((m.x - x) ** 2 + (m.y - y) ** 2 > (m.radius + 24) ** 2
                       for m in blockers)

        def in_bounds(r, c):
            return 0 <= r < game_map.height and 0 <= c < game_map.width

        def ring(tile):
            yield tile
            for nr, nc in game_map.hex_neighbors(*tile):
                if in_bounds(nr, nc):
                    yield (nr, nc)

        start = next((t for t in ring(spawn_locations[0]) if tile_open(*t)), None)
        if start is None:
            return None  # spawn 0 itself is walled in — nothing to compare against
        frontier = [start]
        seen = {start}
        while frontier:
            r, c = frontier.pop()
            for nr, nc in game_map.hex_neighbors(r, c):
                if not in_bounds(nr, nc):
                    continue
                if (nr, nc) in seen or not tile_open(nr, nc):
                    continue
                seen.add((nr, nc))
                frontier.append((nr, nc))
        for spawn in spawn_locations[1:]:
            if not any(tile in seen for tile in ring(spawn)):
                return spawn
        return None

    @staticmethod
    def _point_to_segment_sq(px, py, ax, ay, bx, by):
        """Squared distance from point P to segment AB."""
        abx, aby = bx - ax, by - ay
        ab_sq = abx * abx + aby * aby
        if ab_sq <= 0:
            return (px - ax) ** 2 + (py - ay) ** 2
        t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / ab_sq))
        cx, cy = ax + abx * t, ay + aby * t
        return (px - cx) ** 2 + (py - cy) ** 2
