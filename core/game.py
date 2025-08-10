import pygame
import math
from core.config import (SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, 
                        WHITE, CAMERA_SPEED, TILE_WIDTH, TILE_HEIGHT, 
                        MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, MINIMAP_WIDTH, 
                        MINIMAP_HEIGHT, NUM_PLAYERS, PLAYER_COLORS, TOP_BAR_HEIGHT,
                        SMART_CURSORS_ENABLED, DEFAULT_GAME_SPEED, MIN_GAME_SPEED,
                        MAX_GAME_SPEED, GAME_SPEED_INCREMENT)
from world.map import Map
from world.camera import Camera
from entities.objects import load_game_data
from ui.minimap import Minimap
from entities.player import Player
from managers.sprite_manager import SpriteManager
from managers.selection_manager import SelectionManager
from ui.ui_manager import UIManager
from ui.floating_ui import FloatingUI
from ui.ai_debug_panel import AIDebugPanel
from core.game_state import GameState
from systems.gathering_manager import GatheringManager
from systems.pathfinding import Pathfinding
from systems.production_manager import ProductionManager
from systems.movement_system import MovementSystem
from systems.collision_system import CollisionSystem
from systems.combat_system import CombatSystem
from systems.building_system import BuildingSystem
from systems.rendering_system import RenderingSystem
from systems.unit_watchdog import UnitWatchdog
from systems.ai import ModularAISystem
from systems.projectile_system import ProjectileSystem


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.map_surface = pygame.Surface((MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT))
        pygame.display.set_caption("RTS Game")
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Core game components
        self.game_map = Map(MAP_WIDTH, MAP_HEIGHT, self)
        self.camera = Camera(MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT)
        self.camera.x = TILE_WIDTH * 0.5
        self.camera.y = TILE_HEIGHT * 0.5
        self.game_data = load_game_data()
        
        # Create players dynamically based on config
        num_players = max(2, min(NUM_PLAYERS, len(PLAYER_COLORS)))
        self.players = []
        for i in range(num_players):
            if i == 0:
                self.players.append(Player("Human", human=True, color=PLAYER_COLORS[i]))
            else:
                self.players.append(Player(f"AI {i}", human=False, color=PLAYER_COLORS[i]))
        
        # Game objects
        self.buildings = []
        self.units = []
        self.resources = []
        self.construction_sites = []
        self.debug_overlay = False
        self.frame_counter = 0
        
        # Initialize managers
        self.sprite_manager = SpriteManager(self.game_data, self.players)
        self.selection_manager = SelectionManager(self)
        self.ui_manager = UIManager(self)
        self.floating_ui = FloatingUI(self)
        self.production_manager = ProductionManager(self)
        self.game_state = GameState(self)
        self.gathering_manager = GatheringManager(self)
        self.pathfinder = Pathfinding(self.game_map, self)
        
        # Initialize new systems
        self.movement_system = MovementSystem(self)
        self.collision_system = CollisionSystem(self)
        self.combat_system = CombatSystem(self)
        self.building_system = BuildingSystem(self)
        self.rendering_system = RenderingSystem(self)
        self.unit_watchdog = UnitWatchdog(self)
        self.ai_system = ModularAISystem(self)
        self.projectile_system = ProjectileSystem(self)
        
        # Link projectile system to combat system
        self.combat_system.projectile_system = self.projectile_system
        
        # Other components
        self.minimap = Minimap(self, MINIMAP_WIDTH, MINIMAP_HEIGHT)
        self.ai_debug_panel = AIDebugPanel(self)
        
        # Load resource icons
        self._load_resource_icons()
        
        # Game start time
        self.game_start_time = pygame.time.get_ticks()
        
        # Game speed factor
        self.game_speed = DEFAULT_GAME_SPEED
        
        # Set up initial game state
        self.game_state.setup_game_objects()
    
    def _load_resource_icons(self):
        """Load and scale resource icons"""
        self.resource_icons = {
            "food": pygame.image.load("assets/ui/food_icon.png").convert_alpha(),
            "gold": pygame.image.load("assets/ui/gold_icon.png").convert_alpha(),
            "stone": pygame.image.load("assets/ui/stone_icon.png").convert_alpha(),
            "wood": pygame.image.load("assets/ui/lumber_icon.png").convert_alpha(),
            "house": pygame.image.load("assets/ui/house_icon.png").convert_alpha()
        }
        
        # Scale icons
        icon_size = 48
        for resource in self.resource_icons:
            self.resource_icons[resource] = pygame.transform.scale(
                self.resource_icons[resource], (icon_size, icon_size)
            )
    
    def screen_to_world(self, screen_x, screen_y):
        """Convert screen coordinates to world coordinates"""
        map_screen_x = screen_x
        map_screen_y = screen_y - TOP_BAR_HEIGHT
        world_x = (map_screen_x - self.camera.x) / self.camera.zoom
        world_y = (map_screen_y - self.camera.y) / self.camera.zoom
        return (world_x, world_y)
    
    def run(self):
        """Main game loop"""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        pygame.quit()
    
    def handle_events(self):
        """Handle all input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event)
            elif event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event)
    
    def _handle_keydown(self, event):
        """Handle keyboard input"""
        if event.key == pygame.K_ESCAPE:
            # Check if command mode is active first
            if self.ui_manager.active_command_mode:
                self.ui_manager.clear_command_mode()
            else:
                self.running = False
        elif event.key == pygame.K_F3:
            self.debug_overlay = not self.debug_overlay
        elif event.key == pygame.K_F4:
            try:
                self.ai_debug_panel.toggle_visibility()
            except Exception as e:
                print(f"ERROR: F4 debug panel crashed: {e}")
                import traceback
                traceback.print_exc()
        elif event.key == pygame.K_LEFTBRACKET:  # [ key - decrease speed
            self.game_speed = max(MIN_GAME_SPEED, self.game_speed - GAME_SPEED_INCREMENT)
            print(f"Game speed: {self.game_speed:.1f}x")
        elif event.key == pygame.K_RIGHTBRACKET:  # ] key - increase speed
            self.game_speed = min(MAX_GAME_SPEED, self.game_speed + GAME_SPEED_INCREMENT)
            print(f"Game speed: {self.game_speed:.1f}x")
    
    def _handle_mouse_wheel(self, event):
        """Handle mouse wheel zoom"""
        mouse_pos = pygame.mouse.get_pos()
        
        # Calculate world position before zoom
        map_screen_x = mouse_pos[0]
        map_screen_y = mouse_pos[1] - (SCREEN_HEIGHT - MAP_VIEW_HEIGHT)
        world_x_before = (map_screen_x - self.camera.x) / self.camera.zoom
        world_y_before = (map_screen_y - self.camera.y) / self.camera.zoom
        
        # Perform zoom
        if event.y > 0:
            self.camera.zoom_in()
        elif event.y < 0:
            self.camera.zoom_out()
        
        # Adjust camera for zoom-to-cursor
        self.camera.x = map_screen_x - (world_x_before * self.camera.zoom)
        self.camera.y = map_screen_y - (world_y_before * self.camera.zoom)
        
        self.game_map.scale_tiles(self.camera.zoom)
    
    def _handle_mouse_down(self, event):
        """Handle mouse button down events"""
        if event.button == 1:  # Left click
            mouse_pos = pygame.mouse.get_pos()
            
            # Check AI debug panel click first
            if self.ai_debug_panel.handle_click(mouse_pos):
                pass  # Debug panel handled the click
            # Check minimap click
            elif (mouse_pos[0] > SCREEN_WIDTH - MINIMAP_WIDTH and 
                mouse_pos[1] < MINIMAP_HEIGHT):
                self.minimap.handle_click(mouse_pos)
            else:
                # Check UI click first
                if not self.ui_manager.handle_click(mouse_pos):
                    if self.building_system.building_placement_mode:
                        self.building_system.handle_building_placement_click(mouse_pos)
                    elif self.ui_manager.active_command_mode:
                        # Handle command mode click
                        if self.selection_manager.handle_command_mode_click(mouse_pos, self.ui_manager.active_command_mode):
                            # Command executed successfully, clear command mode
                            self.ui_manager.clear_command_mode()
                    else:
                        self.selection_manager.handle_left_click(mouse_pos)
                        
        elif event.button == 3:  # Right click
            if self.building_system.building_placement_mode:
                self.building_system.cancel_building_placement()
            else:
                mouse_pos = pygame.mouse.get_pos()
                self.selection_manager.handle_right_click(mouse_pos)
    
    def _handle_mouse_motion(self, event):
        """Handle mouse motion events"""
        mouse_pos = pygame.mouse.get_pos()
        
        if self.minimap.dragging:
            self.minimap.handle_drag(mouse_pos)
        elif self.building_system.building_placement_mode:
            self.building_system.update_building_preview(mouse_pos)
        elif self.ui_manager.active_command_mode or SMART_CURSORS_ENABLED:
            # Update cursor based on target validity or smart cursor logic
            self._update_cursor_for_context(mouse_pos)
        else:
            self.ui_manager.handle_production_hover(mouse_pos)
    
    def _handle_mouse_up(self, event):
        """Handle mouse button up events"""
        if event.button == 1:  # Left click
            if self.minimap.dragging:
                self.minimap.handle_release()
            else:
                self.selection_manager.handle_left_release(pygame.mouse.get_pos())
    
    def _update_cursor_for_context(self, mouse_pos):
        """Update cursor appearance based on target validity or smart cursor logic"""
        # Skip if mouse is over UI areas
        if (mouse_pos[0] > SCREEN_WIDTH - MINIMAP_WIDTH or  # Right panel/minimap
            mouse_pos[1] < TOP_BAR_HEIGHT):  # Top bar
            return
            
        # Get world position
        world_pos = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Check what object is at this position
        clicked_object = self.selection_manager._get_object_at_position(world_pos)
        
        if self.ui_manager.active_command_mode:
            # Command mode active - show tinted cursor for invalid targets
            valid_units = self.selection_manager._get_valid_units_for_command(self.ui_manager.active_command_mode)
            is_valid_target = self.selection_manager._is_valid_target_for_command(
                self.ui_manager.active_command_mode, clicked_object, valid_units
            )
            self.ui_manager.update_cursor_for_target(is_valid_target)
        else:
            # Smart cursor mode - automatically choose cursor based on context
            selected_units = [obj for obj in self.selection_manager.selected_objects 
                            if obj in self.units and hasattr(obj, 'player') and obj.player and obj.player.human]
            
            if selected_units:
                smart_cursor = self.ui_manager.get_smart_cursor_for_target(clicked_object, selected_units)
                if smart_cursor and smart_cursor in self.ui_manager.command_cursors:
                    # Check if target would be valid for this smart cursor action
                    is_valid = self.selection_manager._is_valid_target_for_command(smart_cursor, clicked_object, selected_units)
                    cursor_type = 'normal' if is_valid else 'tinted'
                    
                    try:
                        pygame.mouse.set_cursor(self.ui_manager.command_cursors[smart_cursor][cursor_type])
                    except:
                        pass
    
    def update(self):
        """Update all game systems"""
        # Apply game speed to delta time
        raw_delta_time = self.clock.get_time() / 1000.0
        self.delta_time = raw_delta_time * self.game_speed
        self.frame_counter += 1
        
        # Update input
        self._update_camera_movement()
        
        # Update core systems with speed-adjusted delta time
        self.gathering_manager.update(self.delta_time)
        self.building_system.update_construction(self.delta_time)
        self.production_manager.update(self.delta_time)
        self.unit_watchdog.update()
        self.ai_system.update(self.delta_time)
        self.ai_debug_panel.update(self.delta_time)
        
        # Update unit movement and combat
        self._update_units(self.delta_time)
        
        # Update combat system (for both units and buildings)
        self.combat_system.update_combat_units(self.delta_time)
        
        # Update projectiles
        self.projectile_system.update(self.delta_time)
        
        # Remove destroyed objects
        self._cleanup_destroyed_objects()
        
        # Update camera bounds
        self._update_camera_bounds()
    
    def _update_camera_movement(self):
        """Update camera movement from keyboard input"""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.camera.move(dx=CAMERA_SPEED)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.camera.move(dx=-CAMERA_SPEED)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.camera.move(dy=CAMERA_SPEED)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.camera.move(dy=-CAMERA_SPEED)
    
    def _update_units(self, delta_time):
        """Update all units using the movement system"""
        for unit in self.units:
            self.movement_system.update_unit_movement(unit, delta_time)
    
    def _cleanup_destroyed_objects(self):
        """Remove destroyed units and buildings"""
        # Remove destroyed units
        destroyed_units = [unit for unit in self.units if unit.hp <= 0]
        for unit in destroyed_units:
            self.combat_system.handle_unit_death(unit)
        
        # Remove destroyed buildings
        destroyed_buildings = [building for building in self.buildings if building.hp <= 0]
        for building in destroyed_buildings:
            self.combat_system.handle_building_destruction(building)
        
        # Remove destroyed construction sites
        self.construction_sites = [site for site in self.construction_sites if site.hp > 0]
        
        # Remove depleted resources
        depleted_resources = [resource for resource in self.resources if resource.amount_remaining <= 0]
        for resource in depleted_resources:
            print(f"Removing depleted {resource.name} resource at ({resource.x:.0f}, {resource.y:.0f})")
            
            # Clear any workers still targeting this resource
            for unit in self.units:
                if (hasattr(unit, 'gathering_target') and 
                    unit.gathering_target == resource):
                    print(f"  Clearing resource from worker at ({unit.x:.0f}, {unit.y:.0f})")
                    
                    # Clear gathering state
                    unit.gathering_target = None
                    unit.is_gathering = False
                    unit.status = "idle"
                    
                    # Clear movement state if worker was moving to this resource
                    unit.destination = None
                    unit.path = None
                    unit.path_index = 0
                    unit.path_target = None
                    unit.is_engaging = False
                    
                    # Apply small separation force to push worker away from depleted resource position
                    dx = unit.x - resource.x
                    dy = unit.y - resource.y
                    distance = math.sqrt(dx * dx + dy * dy)
                    if distance < unit.radius + resource.radius + 10 and distance > 0:
                        # Push worker away slightly
                        push_force = 10  # pixels
                        dx_norm = dx / distance
                        dy_norm = dy / distance
                        unit.x += dx_norm * push_force
                        unit.y += dy_norm * push_force
                        print(f"  Pushed worker away from depleted resource to ({unit.x:.0f}, {unit.y:.0f})")
                    
                    print(f"  Worker state cleared")
            
            # Remove from resources list
            self.resources.remove(resource)
            
            # Invalidate AI memory cache since resources changed
            if hasattr(self, 'ai_system') and self.ai_system:
                self.ai_system.invalidate_memory_cache()
    
    def _update_camera_bounds(self):
        """Update camera bounds to keep it within map limits"""
        map_width_pixels = MAP_WIDTH * TILE_WIDTH * 0.75 * self.camera.zoom
        map_height_pixels = MAP_HEIGHT * TILE_HEIGHT * self.camera.zoom
        
        self.camera.x = max(min(self.camera.x, 0), 
                           MAP_VIEW_WIDTH - map_width_pixels - (TILE_WIDTH * 0.25 * self.camera.zoom))
        self.camera.y = max(min(self.camera.y, 0), 
                           MAP_VIEW_HEIGHT - map_height_pixels - (TILE_HEIGHT * 0.5 * self.camera.zoom))
    
    def draw(self):
        """Draw everything using the rendering system"""
        delta_time = getattr(self, 'delta_time', 1/60.0)  # Use stored delta time or fallback
        self.rendering_system.draw_frame(self.screen, self.map_surface, self.camera, delta_time)
        
        # Draw debug information if enabled
        if self.debug_overlay:
            self.rendering_system.draw_debug_info(self.screen)
            self.rendering_system.draw_grid_overlay(self.map_surface, self.camera)
            self.rendering_system.draw_object_bounds(self.map_surface, self.camera)
        
        pygame.display.flip()
    
    # Delegation methods for systems that need access to game state
    def enter_building_placement_mode(self, building_data):
        """Enter building placement mode"""
        return self.building_system.enter_building_placement_mode(building_data)
    
    def cancel_building_placement(self):
        """Cancel building placement mode"""
        self.building_system.cancel_building_placement()
    
    def _check_unit_collision_and_adjust(self, unit, new_pos, direction):
        """Delegate collision checking to collision system"""
        return self.collision_system.check_unit_collision_and_adjust(unit, new_pos, direction)
    
    def _handle_blocked_unit(self, unit):
        """Delegate blocked unit handling to collision system"""
        self.collision_system.handle_blocked_unit(unit)
    
    def _find_optimal_attack_position(self, unit, target, other_attackers):
        """Delegate optimal attack positioning to combat system"""
        return self.combat_system.find_optimal_attack_position(unit, target, other_attackers)
    
    # Properties to maintain compatibility with existing code
    @property
    def building_placement_mode(self):
        return self.building_system.building_placement_mode
    
    @property
    def building_preview_pos(self):
        return self.building_system.building_preview_pos