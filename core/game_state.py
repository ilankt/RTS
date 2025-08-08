import random
import math
from entities.objects import Building, Unit, Resource
from systems.animation import Animation
from core.config import MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, TILE_WIDTH, TILE_HEIGHT


class GameState:
    """Manages game object creation and initial game state setup"""
    
    def __init__(self, game):
        self.game = game
    
    def setup_game_objects(self):
        """Set up initial game objects for all players"""
        spawn_locations = []
        for i, player in enumerate(self.game.players):
            # Find a safe spawn location for the castle
            castle_template = self.game.game_data["buildings"]["castle"]
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
            worker.movement_speed *= 5
            worker.player = player
            
            # Set up animations with player-specific colors
            animations = {}
            for anim_name, anim_path in worker.animations.items():
                sheet = self.game.sprite_manager.get_unit_animation_sheet("worker", anim_name, i)
                animations[anim_name] = Animation(sheet, 192, 192, 100)
            worker.set_animations(animations)
            
            self.game.units.append(worker)

        # Center camera on human player's starting position
        human_castle = next((b for b in self.game.buildings if b.player.human), None)
        if human_castle:
            self.game.camera.x = (MAP_VIEW_WIDTH / 2) - human_castle.x
            self.game.camera.y = (MAP_VIEW_HEIGHT / 2) - human_castle.y

        # Place some resources around the map
        self._place_resources(spawn_locations)
    
    def _spawn_test_units(self, player, castle_pos):
        """Spawn test units around the castle for formation testing"""
        import random
        
        # Define test units to spawn
        test_units = [
            ("warrior", 3),  # 3 warriors
            ("archer", 3)    # 3 archers
        ]
        
        for unit_type, count in test_units:
            for _ in range(count):
                # Find a safe spawn position around the castle
                pass
                spawn_pos = self._find_safe_spawn_position(castle_pos, 80, 150)
                if spawn_pos:
                    # Create unit from template
                    pass
                    unit = self._create_instance_from_template(self.game.game_data["units"][unit_type])
                    unit.x, unit.y = spawn_pos
                    unit.player = player
                    
                    # Set up animations with player-specific colors
                    animations = {}
                    for anim_name, anim_path in unit.animations.items():
                        sheet = self.game.sprite_manager.get_unit_animation_sheet(unit_type, anim_name, 0)
                        animations[anim_name] = Animation(sheet, 192, 192, 100)
                    unit.set_animations(animations)
                    
                    self.game.units.append(unit)
                    # Debug: Spawned test unit
    
    def _spawn_enemy_test_units(self, castle_pos):
        """Spawn enemy units for combat testing"""
        import random
        
        # Use the second player as enemy (red player)
        enemy_player = self.game.players[1] if len(self.game.players) > 1 else None
        if not enemy_player:
            return
        
        # Define enemy test units to spawn
        enemy_units = [
            ("warrior", 2),  # 2 enemy warriors
            ("archer", 2)    # 2 enemy archers
        ]
        
        for unit_type, count in enemy_units:
            for _ in range(count):
                # Find a spawn position slightly further from castle (200-300 pixels away)
                pass
                spawn_pos = self._find_safe_spawn_position(castle_pos, 200, 300)
                if spawn_pos:
                    # Create unit from template
                    pass
                    unit = self._create_instance_from_template(self.game.game_data["units"][unit_type])
                    unit.x, unit.y = spawn_pos
                    unit.player = enemy_player
                    
                    # Set up animations with enemy player colors (red)
                    animations = {}
                    for anim_name, anim_path in unit.animations.items():
                        sheet = self.game.sprite_manager.get_unit_animation_sheet(unit_type, anim_name, 1)  # Player 1 = red
                        animations[anim_name] = Animation(sheet, 192, 192, 100)
                    unit.set_animations(animations)
                    
                    self.game.units.append(unit)
                    # Debug: Spawned enemy unit
    
    def _find_safe_spawn_position(self, center_pos, min_distance, max_distance):
        """Find a safe position to spawn a unit around a center point"""
        import random
        import math
        
        max_attempts = 20
        for _ in range(max_attempts):
            # Generate random position in ring around center
            pass
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(min_distance, max_distance)
            
            spawn_x = center_pos[0] + math.cos(angle) * distance
            spawn_y = center_pos[1] + math.sin(angle) * distance
            
            # Check if position is valid (walkable terrain)
            hex_coord = self.game.game_map.world_to_grid(spawn_x, spawn_y)
            if hex_coord:
                col, row = hex_coord
                if (0 <= row < self.game.game_map.height and 
                    0 <= col < self.game.game_map.width):
                    tile_type = self.game.game_map.grid[row][col]
                    if tile_type not in {"water", "lava"}:
                        # Check for collision with existing objects
                        pass
                        collision = False
                        for obj in self.game.buildings + self.game.units:
                            dist = math.sqrt((spawn_x - obj.x)**2 + (spawn_y - obj.y)**2)
                            if dist < (obj.radius + 20):  # 20 = unit radius + buffer
                                collision = True
                                break
                        
                        if not collision:
                            return (spawn_x, spawn_y)
        
        return None  # Couldn't find safe position
    
    def _create_instance_from_template(self, template):
        """Create a new instance from a template object"""
        if isinstance(template, Building):
            return Building(
                name=template.name,
                size=template.size,
                hp=template.hp,
                sprite=template.sprite,
                build_duration=template.build_duration,
                radius=template.radius
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
                attack_range=template.attack_range
            )
        elif isinstance(template, Resource):
            return Resource(
                name=template.name,
                sprite=template.sprite,
                radius=template.radius
            )
        else:
            # Fallback for other GameObject types
            pass
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
            # Place 1 gold deposit near castle (3-5 tiles away)
            pass
            self._place_resource_near_spawn("gold", spawn_r, spawn_c, 3, 5, 1)
            
            # Place 1 stone deposit near castle (3-5 tiles away)
            self._place_resource_near_spawn("stone", spawn_r, spawn_c, 3, 5, 1)
            
            # Place 5 wood resources near castle (2-6 tiles away)
            self._place_resource_near_spawn("wood", spawn_r, spawn_c, 2, 6, 5)
        
        # Calculate resource counts based on map size and player count
        map_area = self.game.game_map.width * self.game.game_map.height
        player_count = len(self.game.players)
        
        # Base resource counts scaled by map area (40x40 = 1600 tiles as reference)
        area_factor = map_area / 1600.0
        
        # Reduce resources for more players (more competition)
        player_factor = 1.0 - (player_count - 2) * 0.1  # -10% per player above 2
        player_factor = max(0.5, player_factor)  # Minimum 50%
        
        # Calculate final resource counts
        extra_gold = int(random.randint(2, 3) * area_factor * player_factor)
        extra_stone = int(random.randint(2, 3) * area_factor * player_factor)
        extra_wood = int(random.randint(8, 12) * area_factor * player_factor)
        
        # Place scarce additional resources across the map
        for _ in range(extra_gold):
            self._place_random_resource("gold", spawn_locations, min_distance=15)
        
        for _ in range(extra_stone):
            self._place_random_resource("stone", spawn_locations, min_distance=15)
        
        # Instead of individual trees, create forest clusters
        self._place_forest_clusters(extra_wood, spawn_locations)
    
    def _place_resource_near_spawn(self, resource_type, spawn_r, spawn_c, min_dist, max_dist, count):
        """Place a specific number of resources near a spawn location"""
        placed = 0
        attempts = 0
        max_attempts = count * 50
        
        while placed < count and attempts < max_attempts:
            # Random angle and distance for better distribution
            pass
            angle = random.uniform(0, 2 * 3.14159)
            distance = random.uniform(min_dist, max_dist)
            
            # Calculate position using proper circular distribution
            dr = int(distance * math.sin(angle))
            dc = int(distance * math.cos(angle))
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
                    
                    # Check collision with all game objects
                    if not self._check_collision_with_objects(world_pos[0], world_pos[1], 16):  # 16 is resource radius (TILE_WIDTH/4)
                        resource_name = resource_type
                        
                        resource = self._create_instance_from_template(self.game.game_data["resources"][resource_name])
                        resource.x, resource.y = world_pos
                        self.game.resources.append(resource)
                        placed += 1
            
            attempts += 1
    
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
    
    def _place_random_resource(self, resource_type, spawn_locations, min_distance):
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
                pass
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
                        # Determine which wood sprite to use
                        pass
                        resource_name = resource_type
                        
                        resource = self._create_instance_from_template(self.game.game_data["resources"][resource_name])
                        resource.x, resource.y = world_pos
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