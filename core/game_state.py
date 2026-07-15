import random
import math
from entities import Building, Unit, Resource
from systems.animation import Animation
from core.config import MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT


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
            # Starting gold/stone: one RICH deposit each near the castle (5x the
            # old 500). Big enough to carry the early game, so hunting for fresh
            # deposits is a mid-game concern, not an opening chore. (2026-07-12)
            # Band tightened 3-5 → 3-4 tiles (2026-07-14): with haul time
            # dominating gold income, a 147 px vs 280 px starting deposit was
            # a ~2x income difference decided by spawn luck (instrumented
            # seed 1001). Wider band kept as fallback so placement never fails.
            if not self._place_resource_near_spawn("gold", spawn_r, spawn_c, 3, 4, 1, amount_override=2500):
                self._place_resource_near_spawn("gold", spawn_r, spawn_c, 3, 6, 1, amount_override=2500)

            if not self._place_resource_near_spawn("stone", spawn_r, spawn_c, 3, 4, 1, amount_override=2500):
                self._place_resource_near_spawn("stone", spawn_r, spawn_c, 3, 6, 1, amount_override=2500)

            # Wood is left as-is (per-bunch amount is fine) — 8 trees near spawn.
            self._place_resource_near_spawn("wood", spawn_r, spawn_c, 2, 6, 8, amount_override=250)
        
        # Calculate resource counts based on map size and player count
        map_area = self.game.game_map.width * self.game.game_map.height
        player_count = len(self.game.players)
        
        # Base resource counts scaled by map area (40x40 = 1600 tiles as reference)
        area_factor = map_area / 1600.0
        
        # Reduce resources for more players (more competition)
        player_factor = 1.0 - (player_count - 2) * 0.1  # -10% per player above 2
        player_factor = max(0.5, player_factor)  # Minimum 50%
        
        # Resource counts (rebalance 2026-07-12): FEWER but far RICHER gold/stone
        # deposits — you control a deposit longer and hunt less often — and MORE
        # wood clusters so timber is always easy to find nearby.
        extra_gold = int(random.randint(1, 2) * area_factor * player_factor)
        extra_stone = int(random.randint(1, 2) * area_factor * player_factor)
        extra_wood = int(random.randint(20, 30) * area_factor * player_factor)

        # Additional gold/stone across the map — 5x richer per node (was 1500).
        for _ in range(extra_gold):
            self._place_random_resource("gold", spawn_locations, min_distance=15, amount_override=7500)

        for _ in range(extra_stone):
            self._place_random_resource("stone", spawn_locations, min_distance=15, amount_override=7500)

        # Instead of individual trees, create forest clusters (many more now)
        self._place_forest_clusters(extra_wood, spawn_locations)

        # §8.9 neutral healing fountain at the map center — contested ground
        self._place_fountain(spawn_locations)

    def _place_fountain(self, spawn_locations):
        """One healing fountain as near the map center as possible: open
        walkable terrain, clear of objects, and at least 12 tiles from every
        spawn so it's genuinely neutral ground."""
        from entities.fountain import Fountain

        game_map = self.game.game_map
        center_r, center_c = game_map.height // 2, game_map.width // 2

        def viable(r, c):
            if not (3 <= r < game_map.height - 3 and 3 <= c < game_map.width - 3):
                return False
            if game_map.grid[r][c] not in ("grass", "plains", "dirt"):
                return False
            for spawn_r, spawn_c in spawn_locations:
                if math.hypot(r - spawn_r, c - spawn_c) < 12:
                    return False
            x, y = game_map.grid_to_world(c, r)
            if self._check_collision_with_objects(x, y, 48):
                return False
            return self._has_open_approach(x, y, ring=70.0, needed=5)

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
                
                if resource_type in ["gold", "stone"]:
                    suitable = terrain in {"grass", "plains", "rocky", "dirt"}
                elif resource_type == "wood":
                    suitable = terrain in {"grass", "forest", "plains"}
                
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
            if self.game.game_map.grid[row][col] in {"water", "lava", "mountain"}:
                continue
            if self._check_collision_with_objects(px, py, 12):
                continue
            open_points += 1
            if open_points >= needed:
                return True
        return False

    def _place_forest_clusters(self, total_trees, spawn_locations):
        """Place trees in natural forest clusters instead of scattered individual trees"""
        # Calculate number of forests based on total trees
        avg_trees_per_forest = 15  # Average 15 trees per forest
        num_forests = max(2, int(total_trees / avg_trees_per_forest))
        
        forests_placed = 0
        attempts = 0
        max_attempts = num_forests * 50
        
        while forests_placed < num_forests and attempts < max_attempts:
            attempts += 1
            
            # Find a suitable center for the forest
            center_r = random.randint(5, self.game.game_map.height - 6)
            center_c = random.randint(5, self.game.game_map.width - 6)
            
            # Check if too close to spawn locations
            too_close_to_spawn = False
            for spawn_r, spawn_c in spawn_locations:
                dist = math.sqrt((center_r - spawn_r)**2 + (center_c - spawn_c)**2)
                if dist < 8:  # Keep forests at least 8 tiles from spawns
                    too_close_to_spawn = True
                    break
            
            if too_close_to_spawn:
                continue
            
            # Check terrain suitability for forest center
            terrain = self.game.game_map.grid[center_r][center_c]
            if terrain not in {"grass", "forest", "plains"}:
                continue
            
            # Place a cluster of trees around this center
            trees_in_this_forest = random.randint(10, 20)
            trees_placed = 0
            
            # Use a more organic placement pattern
            for i in range(trees_in_this_forest * 3):  # More attempts for denser forests
                if trees_placed >= trees_in_this_forest:
                    break
                
                # Use gaussian distribution for more natural clustering
                angle = random.uniform(0, 2 * math.pi)
                # Distance with normal distribution - most trees near center
                distance = abs(random.gauss(0, 2))  # Mean 0, std dev 2
                distance = min(distance, 5)  # Cap at 5 tiles from center
                
                dr = int(distance * math.sin(angle))
                dc = int(distance * math.cos(angle))
                r = center_r + dr
                c = center_c + dc
                
                # Check bounds
                if not (2 <= r < self.game.game_map.height - 2 and 
                       2 <= c < self.game.game_map.width - 2):
                    continue
                
                # Check terrain
                terrain = self.game.game_map.grid[r][c]
                if terrain not in {"grass", "forest", "plains"}:
                    continue
                
                world_pos = self.game.game_map.grid_to_world(c, r)
                
                # Use smaller collision radius for trees within forests (allow denser placement)
                tree_collision_radius = 8  # Reduced from 16 for denser forests
                if not self._check_collision_with_objects(world_pos[0], world_pos[1], tree_collision_radius):
                    resource = self._create_instance_from_template(self.game.game_data["resources"]["wood"])
                    resource.x, resource.y = world_pos
                    self.game.resources.append(resource)
                    trees_placed += 1
            
            if trees_placed > 5:  # Only count as successful if we placed at least 5 trees
                forests_placed += 1
    
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
            
            if resource_type in ["gold", "stone"]:
                suitable = terrain in {"grass", "plains", "rocky", "dirt", "cracked_dirt"}
            elif resource_type == "wood":
                suitable = terrain in {"grass", "forest", "plains"}
            
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
                        self.game.resources.append(resource)
                        break
            
            attempts += 1
    
    def _check_collision_with_objects(self, x, y, radius):
        """Check if a position would collide with any existing game object"""
        # Check collision with buildings
        for building in self.game.buildings:
            dist = ((building.x - x)**2 + (building.y - y)**2)**0.5
            if dist < (building.radius + radius + 20):  # Add some extra spacing
                return True
        
        # Check collision with units
        for unit in self.game.units:
            dist = ((unit.x - x)**2 + (unit.y - y)**2)**0.5
            if dist < (unit.radius + radius + 20):  # Add some extra spacing
                return True
        
        # Check collision with existing resources
        for resource in self.game.resources:
            dist = ((resource.x - x)**2 + (resource.y - y)**2)**0.5
            if dist < (resource.radius + radius + 20):  # Add some extra spacing
                return True
        
        return False
