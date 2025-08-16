import math
import random
import pygame
from entities import Building, ConstructionSite
from core.config import TILE_WIDTH, TILE_HEIGHT, SCREEN_HEIGHT, MAP_VIEW_HEIGHT, TOP_BAR_HEIGHT
from utils.debug_logger import debug_log


class BuildingSystem:
    """Handles building placement, construction, and building management"""
    
    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        
        # Building placement state
        self.building_placement_mode = False
        self.building_to_place = None
        self.building_preview_valid = False
        self.building_preview_pos = None
        self.selected_builder = None
        
    def enter_building_placement_mode(self, building_data):
        """Enter building placement mode with the selected building type"""
        # Find and store the selected worker
        self.selected_builder = None
        for unit in self.game.units:
            if unit.selected and unit.name == "worker" and unit.player == self.game.players[0]:
                # Check if unit has can_build attribute, default to True for workers
                can_build = getattr(unit, 'can_build', True) if unit.name == "worker" else False
                if can_build:
                    self.selected_builder = unit
                    break
                
        if not self.selected_builder:
            # No eligible builder selected
            return False
            
        self.building_placement_mode = True
        self.building_to_place = building_data
        self.building_preview_valid = False
        self.building_preview_pos = None
        # Entered building placement mode
        return True
    
    def cancel_building_placement(self):
        """Cancel building placement mode"""
        self.building_placement_mode = False
        self.building_to_place = None
        self.building_preview_valid = False
        self.building_preview_pos = None
        self.selected_builder = None
        # Cancelled building placement
    
    def update_building_preview(self, mouse_pos):
        """Update building preview position and validity"""
        if not self.building_placement_mode or not self.building_to_place:
            return
            
        # Convert mouse position to world coordinates
        world_pos = self.game.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Check if position is within the top bar area (exclude UI area)
        if mouse_pos[1] < TOP_BAR_HEIGHT:
            self.building_preview_pos = None
            return
            
        self.building_preview_pos = list(world_pos) if isinstance(world_pos, tuple) else world_pos
        
        # Check if position is valid for building
        self.building_preview_valid = self.is_valid_building_position(world_pos)
    
    def is_valid_building_position(self, world_pos):
        """Check if a position is valid for building placement"""
        if not self.building_to_place:
            return False
            
        building_size = self.building_to_place['size']
        building_radius = building_size[0] * TILE_WIDTH / 2
        
        # Check if position is within map bounds
        hex_coord = self.game_map.world_to_grid(world_pos[0], world_pos[1])
        if not hex_coord:
            return False
            
        # Check terrain type
        tile_type = self.game_map.grid[hex_coord[1]][hex_coord[0]]
        if tile_type in {"water", "lava"}:
            return False
        
        # Check collision with existing objects, including the builder itself
        all_objects = self.game.buildings + self.game.units + self.game.resources + self.game.construction_sites
        for obj in all_objects:
            # Don't check collision with the builder if it's the selected builder
            if self.selected_builder and obj == self.selected_builder:
                continue
            distance = math.sqrt((world_pos[0] - obj.x)**2 + (world_pos[1] - obj.y)**2)
            min_distance = building_radius + obj.radius
            if distance < min_distance:
                return False

        # Also check if the builder is inside the new building's radius
        if self.selected_builder:
            distance = math.sqrt((world_pos[0] - self.selected_builder.x)**2 + (world_pos[1] - self.selected_builder.y)**2)
            if distance < building_radius + self.selected_builder.radius:
                return False
                
        return True
    
    def draw_building_preview(self, map_surface, camera):
        """Draw the building preview with appropriate tint"""
        if not self.building_preview_pos or not self.building_placement_mode:
            return
            
        # Get building sprite
        sprite_path = self.building_to_place['sprite']
        building_size = self.building_to_place['size']
        
        # Load the sprite directly since we'll apply our own tinting
        sprite = pygame.image.load(sprite_path).convert_alpha()
        
        if sprite:
            # Apply green/red tint based on validity
            preview_sprite = sprite.copy()
            tint_color = (0, 255, 0, 128) if self.building_preview_valid else (255, 0, 0, 128)
            
            # Create a surface with per-pixel alpha
            tint_surface = pygame.Surface(preview_sprite.get_size(), pygame.SRCALPHA)
            tint_surface.fill(tint_color)
            
            # Apply tint to preview sprite
            preview_sprite.blit(tint_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            # Set transparency
            preview_sprite.set_alpha(128)
            
            # Calculate screen position
            screen_x = self.building_preview_pos[0] * camera.zoom + camera.x
            screen_y = self.building_preview_pos[1] * camera.zoom + camera.y
            
            # Scale the sprite using the same logic as normal building rendering
            sprite_w, sprite_h = preview_sprite.get_size()
            scale = (building_size[0] * TILE_WIDTH) / sprite_w
            scaled_width = int(sprite_w * scale * camera.zoom)
            scaled_height = int(sprite_h * scale * camera.zoom)
            
            scaled_sprite = pygame.transform.scale(preview_sprite, (scaled_width, scaled_height))
            
            # Draw centered on position
            blit_x = screen_x - (scaled_width / 2)
            blit_y = screen_y - (scaled_height / 2)
            
            map_surface.blit(scaled_sprite, (blit_x, blit_y))
    
    def handle_building_placement_click(self, mouse_pos):
        """Handle click during building placement mode"""
        if not self.building_preview_valid or not self.building_preview_pos:
            # Invalid placement
            return False
            
        # Use the stored builder
        if not self.selected_builder:
            # No builder stored
            self.cancel_building_placement()
            return False
            
        # Deduct resources
        human_player = self.game.players[0]
        costs = self.building_to_place.get('costs', {})
        for resource, amount in costs.items():
            human_player.resources[resource] -= amount
            
        # Create construction site
        building_size = self.building_to_place['size']
        building_radius = building_size[0] * TILE_WIDTH / 2
        
        construction_site = ConstructionSite(
            self.building_to_place['name'],
            self.building_to_place,
            self.building_preview_pos[0],
            self.building_preview_pos[1],
            building_radius,
            human_player
        )
        
        self.game.construction_sites.append(construction_site)
        
        # Assign builder to construction site
        construction_site.builder = self.selected_builder
        self.selected_builder.building_target = construction_site
        self.selected_builder.is_building = False  # Will be set to true when worker arrives
        
        # Debug logging
        debug_log.log(f"Building placement: Assigned worker {id(self.selected_builder)} to construction site", "BUILDING")
        
        # Move worker directly to the construction site
        from systems.pathfinding import Pathfinding
        pathfinder = Pathfinding(self.game_map, self.game)
        
        # Path directly to construction site center
        target_pos = (construction_site.x, construction_site.y)
        
        # Allow pathfinding to this specific construction site
        pathfinder.building_target = construction_site
        pathfinder.current_unit = self.selected_builder
        
        path = pathfinder.find_path((self.selected_builder.x, self.selected_builder.y), target_pos, self.selected_builder.radius, self.selected_builder)
        if path:
            self.selected_builder.path = path
            self.selected_builder.path_index = 0
            self.selected_builder.path_target = target_pos
            self.selected_builder.destination = path[0] if path else None
            self.selected_builder.status = "run"
            self.selected_builder.last_task = {"type": "build", "target": construction_site}
            debug_log.log(f"Building placement: Worker pathing directly to construction site at ({target_pos[0]:.0f}, {target_pos[1]:.0f})", "BUILDING")
        else:
            debug_log.log(f"Building placement: No path found to construction site!", "BUILDING")
            
        # Exit building placement mode  
        building_name = self.building_to_place['name']  # Store name before cancelling
        self.cancel_building_placement()
        # Placed construction site
        return True
    
    def update_construction(self, delta_time):
        """Update construction progress for all construction sites"""
        completed_sites = []
        
        for site in self.game.construction_sites:
            # Log construction site status
            builder_info = f"builder={site.builder}, is_building={site.builder.is_building if site.builder else 'N/A'}"
            debug_log.log(f"Checking construction site at ({site.x:.0f}, {site.y:.0f}) - {builder_info}", "BUILD_UPDATE")
            
            if site.builder and site.builder.is_building:
                # Update construction progress with player's build speed bonus
                build_speed = delta_time
                if hasattr(site, 'player') and site.player:
                    build_speed *= site.player.build_speed_bonus
                site.construction_progress += build_speed
                debug_log.log(f"  Construction progress: {site.construction_progress:.2f}/{site.construction_duration} (+{build_speed:.3f})", "BUILD_UPDATE")
                
                # Check if construction is complete
                if site.construction_progress >= site.construction_duration:
                    # Create the actual building
                    building_class = Building(
                        name=site.building_name,
                        size=site.building_data['size'],
                        hp=site.building_data['hp'],
                        sprite=site.building_data['sprite'],
                        build_duration=site.building_data['build_duration'],
                        x=site.x,
                        y=site.y,
                        radius=site.radius,
                        player=site.player,
                        costs=site.building_data.get('costs', {}),
                        armor_type=site.building_data.get('armor_type', 'fortified'),
                        armor_value=site.building_data.get('armor_value', 0),
                        can_attack=site.building_data.get('can_attack', False),
                        min_damage=site.building_data.get('min_damage', 0),
                        max_damage=site.building_data.get('max_damage', 0),
                        attack_type=site.building_data.get('attack_type', 'slash'),
                        attack_speed=site.building_data.get('attack_speed', 1.0),
                        attack_range=site.building_data.get('attack_range', 0)
                    )
                    
                    self.game.buildings.append(building_class)
                    completed_sites.append(site)
                    
                    # Free the builder with complete state cleanup before nudging
                    if site.builder:
                        site.builder.stop()
                        site.builder.building_target = None

                    # Nudge the worker to a safe position outside the new building's radius
                    if site.builder:
                        # First ensure the builder still exists in game units
                        if site.builder not in self.game.units:
                            debug_log.log(f"WARNING: Builder no longer exists in game units!", "BUILD_UPDATE")
                            site.builder = None
                        else:
                            # Log worker position before nudging
                            debug_log.log(f"AI: Worker position before nudge: ({site.builder.x:.0f}, {site.builder.y:.0f})", "BUILD_UPDATE")
                            
                            site.builder.collision = False
                            
                            # Calculate a nudge position directly away from the building center
                            direction_x = site.builder.x - site.x
                            direction_y = site.builder.y - site.y
                            distance = math.sqrt(direction_x**2 + direction_y**2)
                            
                            if distance == 0: # Avoid division by zero if worker is at the center
                                direction_x, direction_y = 1, 0
                            else:
                                direction_x /= distance
                                direction_y /= distance

                            nudge_distance = site.radius + site.builder.radius + 5  # Increased nudge distance for safety
                            nudge_pos_x = site.x + direction_x * nudge_distance
                            nudge_pos_y = site.y + direction_y * nudge_distance
                            
                            debug_log.log(f"AI: Calculated nudge position: ({nudge_pos_x:.0f}, {nudge_pos_y:.0f}), distance={nudge_distance:.0f}", "BUILD_UPDATE")
                            
                            # Validate the nudge position is on valid terrain
                            grid_pos = self.game.game_map.world_to_grid(nudge_pos_x, nudge_pos_y)
                            if grid_pos:
                                col, row = grid_pos
                                if 0 <= col < self.game.game_map.width and 0 <= row < self.game.game_map.height:
                                    terrain = self.game.game_map.grid[row][col]
                                    if terrain not in ["water", "lava"]:
                                        # Safe to nudge
                                        site.builder.x = nudge_pos_x
                                        site.builder.y = nudge_pos_y
                                        site.builder.destination = (nudge_pos_x, nudge_pos_y)
                                        site.builder.status = "idle"
                                        debug_log.log(f"AI: Worker nudged to position: ({site.builder.x:.0f}, {site.builder.y:.0f})", "BUILD_UPDATE")
                                    else:
                                        # Can't nudge to water/lava, just clear state
                                        debug_log.log(f"WARNING: Nudge position is invalid terrain!", "BUILD_UPDATE")
                                        site.builder.destination = None
                                        site.builder.status = "idle"
                            else:
                                # Invalid position, just clear state
                                debug_log.log(f"WARNING: Nudge position is off map!", "BUILD_UPDATE")
                                site.builder.destination = None
                                site.builder.status = "idle"
                            
                            # Re-enable collision after nudging
                            site.builder.collision = True
                    
                    # Construction complete
                    debug_log.log(f"AI: Construction of {site.building_name} completed at ({site.x:.0f}, {site.y:.0f})", "BUILD_UPDATE")
                    
                    # Force AI to immediately re-evaluate after construction completion
                    if hasattr(self.game, 'ai_system') and self.game.ai_system and site.player:
                        self.game.ai_system.invalidate_memory_cache(site.player)
                        # Force economy module update for newly idle worker
                        if site.player in self.game.ai_system.player_modules:
                            economy_module = self.game.ai_system.player_modules[site.player].get("economy")
                            if economy_module:
                                economy_module.force_next_update = True
                                debug_log.log(f"AI: Forced economy module update for {site.player.name} after construction", "BUILD_UPDATE")
        
        # Remove completed construction sites
        for site in completed_sites:
            if site in self.game.construction_sites:
                self.game.construction_sites.remove(site)
    
    def cancel_construction(self, construction_site):
        """Cancel a construction site and refund half the resources"""
        if construction_site in self.game.construction_sites:
            # Refund half the resources
            for resource, amount in construction_site.costs.items():
                construction_site.player.resources[resource] += amount // 2
            
            # Free the builder with complete state cleanup
            if construction_site.builder:
                if hasattr(construction_site.builder, 'clear_all_movement_state'):
                    construction_site.builder.clear_all_movement_state()
                else:
                    # Fallback to manual cleanup
                    construction_site.builder.is_building = False
                    construction_site.builder.building_target = None
                    construction_site.builder.status = "idle"
                
                debug_log.log(f"AI: Construction cancelled - worker at ({construction_site.builder.x:.0f},{construction_site.builder.y:.0f}) freed and cleaned", "BUILDING")
                
                # Invalidate AI memory cache for immediate detection of newly idle worker
                if hasattr(self.game, 'ai_system') and self.game.ai_system:
                    self.game.ai_system.invalidate_memory_cache(construction_site.player)
                    debug_log.log(f"AI: Invalidated memory cache for {construction_site.player.name} after construction cancellation", "BUILDING")
            
            # Remove the construction site
            self.game.construction_sites.remove(construction_site)
            
            # Cancelled construction, refunded half resources
    
    def get_buildings_by_type(self, building_type, player=None):
        """Get all buildings of a specific type, optionally filtered by player"""
        buildings = []
        for building in self.game.buildings:
            if building.name == building_type:
                if player is None or building.player == player:
                    buildings.append(building)
        return buildings
    
    def get_construction_sites_by_type(self, building_type, player=None):
        """Get all construction sites of a specific type, optionally filtered by player"""
        sites = []
        for site in self.game.construction_sites:
            if site.building_name == building_type:
                if player is None or site.player == player:
                    sites.append(site)
        return sites
    
    def get_building_count(self, building_type, player):
        """Get total count of buildings and construction sites of a type for a player"""
        buildings = self.get_buildings_by_type(building_type, player)
        sites = self.get_construction_sites_by_type(building_type, player)
        return len(buildings) + len(sites)
    
    def can_player_build(self, player, building_data):
        """Check if a player can afford to build a building"""
        costs = building_data.get('costs', {})
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False
        return True
    
    def get_nearest_building(self, position, building_types, player=None, max_distance=None):
        """Find the nearest building of specified types to a position"""
        nearest = None
        nearest_distance = float('inf')
        
        for building in self.game.buildings:
            if building.name in building_types:
                if player is not None and building.player != player:
                    continue
                    
                distance = math.sqrt((building.x - position[0])**2 + (building.y - position[1])**2)
                if max_distance is not None and distance > max_distance:
                    continue
                    
                if distance < nearest_distance:
                    nearest = building
                    nearest_distance = distance
        
        return nearest, nearest_distance if nearest else (None, None)