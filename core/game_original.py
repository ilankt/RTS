import pygame
import math
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT, WHITE, CAMERA_SPEED, TILE_WIDTH, TILE_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT, NUM_PLAYERS, PLAYER_COLORS, TOP_BAR_HEIGHT
from world.map import Map
from world.camera import Camera
from entities.objects import load_game_data, Building, Unit, Resource, ConstructionSite
from systems.animation import Animation
from ui.minimap import Minimap
from entities.player import Player
from managers.sprite_manager import SpriteManager
from managers.selection_manager import SelectionManager
from ui.ui_manager import UIManager
from ui.floating_ui import FloatingUI
from core.game_state import GameState
from systems.gathering_manager import GatheringManager, get_gathering_distance, get_drop_off_distance
from systems.production_manager import ProductionManager

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.map_surface = pygame.Surface((MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT))
        pygame.display.set_caption("RTS Game")
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Core game components
        self.game_map = Map(MAP_WIDTH, MAP_HEIGHT)
        self.camera = Camera(MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT)
        self.camera.x = TILE_WIDTH * 0.5
        self.camera.y = TILE_HEIGHT * 0.5
        self.game_data = load_game_data()
        
        # Create players dynamically based on config (ensure minimum 2 players)
        num_players = max(2, min(NUM_PLAYERS, len(PLAYER_COLORS)))
        self.players = []
        for i in range(num_players):
            if i == 0:
                # First player is always human
                self.players.append(Player("Human", human=True, color=PLAYER_COLORS[i]))
            else:
                # All other players are AI
                self.players.append(Player(f"AI {i}", human=False, color=PLAYER_COLORS[i]))
        
        # Game objects
        self.buildings = []
        self.units = []
        self.resources = []
        self.construction_sites = []  # Active construction sites
        self.active_formation = None  # Formation staging data
        self.debug_overlay = False  # Toggle for debug features
        self.frame_counter = 0  # Frame counter for debug
        
        # Building placement state
        self.building_placement_mode = False
        self.building_to_place = None
        self.building_preview_valid = False
        self.building_preview_pos = None
        self.selected_builder = None
        
        # Initialize managers
        self.sprite_manager = SpriteManager(self.game_data, self.players)
        self.selection_manager = SelectionManager(self)
        self.ui_manager = UIManager(self)
        self.floating_ui = FloatingUI(self)
        self.production_manager = ProductionManager(self)
        self.game_state = GameState(self)
        self.gathering_manager = GatheringManager(self)
        
        # Other components
        self.minimap = Minimap(self, MINIMAP_WIDTH, MINIMAP_HEIGHT)
        
        # Load resource icons
        self.resource_icons = {
            "food": pygame.image.load("assets/ui/food_icon.png").convert_alpha(),
            "gold": pygame.image.load("assets/ui/gold_icon.png").convert_alpha(),
            "stone": pygame.image.load("assets/ui/stone_icon.png").convert_alpha(),
            "wood": pygame.image.load("assets/ui/lumber_icon.png").convert_alpha(),
            "house": pygame.image.load("assets/ui/house_icon.png").convert_alpha()
        }
        
        # Scale icons to larger size
        icon_size = 48  # Double the previous size
        for resource in self.resource_icons:
            self.resource_icons[resource] = pygame.transform.scale(
                self.resource_icons[resource], (icon_size, icon_size)
            )
        
        # Game start time for tracking elapsed time
        self.game_start_time = pygame.time.get_ticks()
        
        # Set up initial game state
        self.game_state.setup_game_objects()


    def screen_to_world(self, screen_x, screen_y):
        map_screen_x = screen_x
        map_screen_y = screen_y - TOP_BAR_HEIGHT  # Account for top bar offset
        world_x = (map_screen_x - self.camera.x) / self.camera.zoom
        world_y = (map_screen_y - self.camera.y) / self.camera.zoom
        return (world_x, world_y)
    

    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(60)
        pygame.quit()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_F3:
                    self.debug_overlay = not self.debug_overlay
            if event.type == pygame.MOUSEWHEEL:
                # Get mouse position for zoom-to-cursor
                mouse_pos = pygame.mouse.get_pos()
                
                # Calculate the world position under the cursor before zoom
                map_screen_x = mouse_pos[0]
                map_screen_y = mouse_pos[1] - (SCREEN_HEIGHT - MAP_VIEW_HEIGHT)
                world_x_before = (map_screen_x - self.camera.x) / self.camera.zoom
                world_y_before = (map_screen_y - self.camera.y) / self.camera.zoom
                
                # Perform zoom
                if event.y > 0:
                    self.camera.zoom_in()
                elif event.y < 0:
                    self.camera.zoom_out()
                
                # Adjust camera so the same world point stays under the cursor
                self.camera.x = map_screen_x - (world_x_before * self.camera.zoom)
                self.camera.y = map_screen_y - (world_y_before * self.camera.zoom)
                
                self.game_map.scale_tiles(self.camera.zoom)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click
                    mouse_pos = pygame.mouse.get_pos()
                    if mouse_pos[0] > SCREEN_WIDTH - MINIMAP_WIDTH and mouse_pos[1] < MINIMAP_HEIGHT:
                        self.minimap.handle_click(mouse_pos)
                    else:
                        # Check if UI handled the click first
                        if not self.ui_manager.handle_click(mouse_pos):
                            if self.building_placement_mode:
                                self.handle_building_placement_click(mouse_pos)
                            else:
                                self.selection_manager.handle_left_click(mouse_pos)
                elif event.button == 3: # Right click
                    if self.building_placement_mode:
                        self.cancel_building_placement()
                    else:
                        mouse_pos = pygame.mouse.get_pos()
                        self.selection_manager.handle_right_click(mouse_pos)

            if event.type == pygame.MOUSEMOTION:
                mouse_pos = pygame.mouse.get_pos()
                if self.minimap.dragging:
                    self.minimap.handle_drag(mouse_pos)
                elif self.building_placement_mode:
                    self.update_building_preview(mouse_pos)
                else:
                    # Handle UI hover effects
                    self.ui_manager.handle_production_hover(mouse_pos)

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1: # Left click
                    if self.minimap.dragging:
                        self.minimap.handle_release()
                    else:
                        self.selection_manager.handle_left_release(pygame.mouse.get_pos())

    def update(self):
        # Get delta time for frame-independent updates
        delta_time = self.clock.get_time() / 1000.0  # Convert to seconds
        self.frame_counter += 1
        
        # Update gathering
        self.gathering_manager.update(delta_time)
        
        # Update construction
        self.update_construction(delta_time)
        
        # Update unit production
        self.production_manager.update(delta_time)
        
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.camera.move(dx=CAMERA_SPEED)
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.camera.move(dx=-CAMERA_SPEED)
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.camera.move(dy=CAMERA_SPEED)
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.camera.move(dy=-CAMERA_SPEED)

        # Remove destroyed units and buildings
        self.units = [unit for unit in self.units if unit.hp > 0]
        self.buildings = [building for building in self.buildings if building.hp > 0]
        self.construction_sites = [site for site in self.construction_sites if site.hp > 0]
        
        for unit in self.units:
            unit.update_animation()
            
            # Update combat for units
            if hasattr(unit, 'update_combat'):
                unit.update_combat(delta_time)
                
                # Auto-attack when reaching target during movement
                if unit.current_target and not unit.in_combat and unit.status == "run":
                    if unit.can_attack(unit.current_target):
                        print(f"\n⚔️ {unit.name} ATTACKING {unit.current_target.name}!")
                        unit.start_attack(unit.current_target)
                
                # Handle engaging state - continuously track and pursue target
                if unit.is_engaging and unit.current_target:
                    # Check if target still exists and is valid
                    if unit.current_target.hp <= 0:
                        unit.current_target = None
                        unit.is_engaging = False
                        unit.status = "idle"
                        continue
                    
                    # Check if we can attack now
                    distance = unit.get_distance_to(unit.current_target)
                    
                    # Debug engaging state only when stuck
                    if (unit.status == "idle" and self.frame_counter % 120 == 0):
                        print(f"\n🚨 {unit.name} STUCK while engaging {unit.current_target.name}")
                        print(f"   Distance: {distance:.1f}, Can attack: {unit.can_attack(unit.current_target)}")
                    
                    if unit.can_attack(unit.current_target):
                        print(f"\n⚔️ {unit.name} ATTACKING {unit.current_target.name}!")
                        unit.start_attack(unit.current_target)
                        continue
                    
                    # Check current situation
                    dx = unit.current_target.x - unit.x
                    dy = unit.current_target.y - unit.y
                    distance = (dx * dx + dy * dy) ** 0.5
                    
                    # Track position for movement progress detection first
                    if not hasattr(unit, '_last_position'):
                        unit._last_position = (unit.x, unit.y)
                        unit._position_stuck_timer = 0
                        unit._strategy_timer = 0
                        unit._last_stuck_check_position = (unit.x, unit.y)
                        unit._stuck_check_timer = 0
                        unit._path_adjustment_count = 0
                    
                    # Check if unit has made progress (moved significantly)
                    position_delta = ((unit.x - unit._last_position[0])**2 + (unit.y - unit._last_position[1])**2)**0.5
                    has_moved = position_delta > unit.movement_speed * 0.5  # Half a frame of movement
                    
                    # Enhanced stuck detection - check progress over longer period
                    unit._stuck_check_timer += 1
                    if unit._stuck_check_timer >= 30:  # Check every 0.5 seconds
                        stuck_check_delta = ((unit.x - unit._last_stuck_check_position[0])**2 + 
                                           (unit.y - unit._last_stuck_check_position[1])**2)**0.5
                        if stuck_check_delta < unit.movement_speed * 10:  # Less than 10 frames of movement in 30 frames
                            # Unit is genuinely stuck
                            unit._position_stuck_timer += 30
                        else:
                            # Unit is making progress, reset stuck timer
                            unit._position_stuck_timer = max(0, unit._position_stuck_timer - 15)  # Gradual reduction
                        unit._last_stuck_check_position = (unit.x, unit.y)
                        unit._stuck_check_timer = 0
                    
                    # Update immediate movement tracking
                    if not has_moved:
                        unit._position_stuck_timer += 1
                    else:
                        unit._position_stuck_timer = max(0, unit._position_stuck_timer - 2)  # Reward movement
                        unit._last_position = (unit.x, unit.y)
                    
                    # Increment strategy timer (time spent in current strategy)
                    unit._strategy_timer += 1
                    
                    # Detect stuck conditions with more nuance
                    is_position_stuck = unit._position_stuck_timer >= 120  # 2 seconds without significant movement
                    is_strategy_timeout = unit._strategy_timer >= 300  # 5 seconds in same strategy
                    needs_path_adjustment = unit._position_stuck_timer >= 60 and unit.path  # 1 second stuck with path
                    force_strategy_change = is_position_stuck or is_strategy_timeout

                    # Path adjustment when stuck with existing path
                    if needs_path_adjustment and not force_strategy_change:
                        # Try to adjust the current path before completely re-evaluating
                        adjusted = self._adjust_stuck_unit_path(unit)
                        if adjusted:
                            print(f"🔧 {unit.name} path adjusted due to being stuck")
                            unit._position_stuck_timer = max(0, unit._position_stuck_timer - 30)  # Give it time
                            unit._path_adjustment_count += 1
                            # Don't re-evaluate strategy if we successfully adjusted the path
                            needs_path_adjustment = False
                    
                    # Re-evaluate strategy more conservatively - don't interrupt working paths
                    should_reevaluate = False
                    
                    # Only re-evaluate if target moved significantly
                    if unit.path_target and (abs(unit.path_target[0] - unit.current_target.x) > 60 or 
                                              abs(unit.path_target[1] - unit.current_target.y) > 60):
                        should_reevaluate = True
                    # If we have no path or destination at all
                    elif not unit.destination and not unit.path:
                        should_reevaluate = True
                    # Only re-evaluate idle status if we have no path (don't interrupt pathfinding)
                    elif unit.status == "idle" and unit.is_engaging and not unit.path:
                        should_reevaluate = True
                    # Force re-path when explicitly stuck
                    elif hasattr(unit, '_needs_repath') and unit._needs_repath:
                        should_reevaluate = True
                    # Periodic check only if unit is truly stuck for a long time
                    elif (hasattr(self, 'frame_counter') and self.frame_counter % 300 == 0 and  # Every 5 seconds instead of 1
                          is_position_stuck and unit.path):  # Only if stuck AND has path
                        should_reevaluate = True
                        unit._needs_repath = False
                        print(f"\n🔄 {unit.name} requesting repath due to collision")
                    
                    if should_reevaluate:
                        # Clear any pending repath flags at start of evaluation
                        if hasattr(unit, '_needs_repath'):
                            unit._needs_repath = False
                        # Check line of sight - include ALL obstacles (buildings, units, and resources)
                        obstacles = (self.buildings + 
                                   [u for u in self.units if u != unit and u != unit.current_target] +
                                   self.resources)
                        has_los = unit.has_line_of_sight(unit.current_target, self.game_map, obstacles)
                        
                        # Debug output only on actual strategy changes or persistent issues
                        debug_this_eval = False
                        if not hasattr(unit, '_last_strategy_state'):
                            unit._last_strategy_state = None
                            unit._stuck_counter = 0
                            debug_this_eval = True
                        
                        current_strategy = "LOS" if has_los else ("FALLBACK" if getattr(unit, 'is_fallback_movement', False) else "PATH")
                        current_state = f"{current_strategy}_{unit.status}_{unit.path is not None}_{unit.destination is not None}"
                        
                        # Only debug on actual state changes, position stuck, or strategy timeout
                        if unit._last_strategy_state != current_state:
                            debug_this_eval = True
                            unit._last_strategy_state = current_state
                            unit._stuck_counter = 0
                            unit._strategy_timer = 0  # Reset strategy timer on state change
                        elif force_strategy_change:
                            unit._stuck_counter += 1
                            if unit._stuck_counter >= 60:  # After 1 second of being stuck
                                debug_this_eval = True
                                print(f"\n🚨 {unit.name} STUCK ANALYSIS:")
                                print(f"   Strategy: {current_strategy}, Status: {unit.status}")
                                print(f"   Position stuck: {is_position_stuck}, Strategy timeout: {is_strategy_timeout}")
                                print(f"   Has path: {unit.path is not None}, Has dest: {unit.destination is not None}")
                                if unit.path:
                                    print(f"   Path progress: {unit.path_index}/{len(unit.path)}")
                                
                                # Force strategy re-evaluation
                                should_reevaluate = True
                                print(f"   🔄 Forcing strategy re-evaluation due to stuck condition")
                                if unit.path and unit.path_index < len(unit.path):
                                    waypoint = unit.path[unit.path_index]
                                    dist_to_waypoint = ((unit.x - waypoint[0]) ** 2 + (unit.y - waypoint[1]) ** 2) ** 0.5
                                    print(f"   Distance to next waypoint: {dist_to_waypoint:.1f}")
                        else:
                            unit._stuck_counter = 0
                        
                        if debug_this_eval and unit._stuck_counter == 0:  # Only show strategy changes, not stuck analysis
                            print(f"\n🎯 {unit.name} STRATEGY: {current_strategy}")
                            print(f"   Distance: {distance:.1f}, LOS: {has_los}, Status: {unit.status}")
                            print(f"   Path: {unit.path is not None}, Dest: {unit.destination is not None}")
                        
                        # Strategy 1: Clear LOS - use direct movement with multi-unit targeting considerations
                        if has_los and not is_strategy_timeout:  # Avoid LOS if strategy has timed out
                            # Check for multiple units attacking the same target
                            attacking_same_target = [u for u in self.units if u != unit and u.current_target == unit.current_target and u.is_engaging]
                            
                            # If multiple units are attacking the same target, use smarter positioning
                            if len(attacking_same_target) >= 2:
                                target_pos = (unit.current_target.x, unit.current_target.y)
                                optimal_position = self._find_optimal_attack_position(unit, unit.current_target, attacking_same_target)
                                
                                if optimal_position:
                                    if debug_this_eval:
                                        print(f"   🎯 Multi-unit attack - using optimal position")
                                    unit.destination = optimal_position
                                    unit.path = None
                                    unit.path_index = 0
                                    unit.path_target = None
                                    unit.has_los = True
                                    unit.is_fallback_movement = False
                                else:
                                    # Fall back to pathfinding if no good position found
                                    if debug_this_eval:
                                        print(f"   ⚠️ Multi-unit attack - no optimal position, using pathfinding")
                                    has_los = False  # Force pathfinding
                            # Single unit attack - use normal LOS logic
                            elif unit.status != "idle" or not hasattr(unit, '_blocked_by_collision'):
                                if not unit.has_los:  # Switching from pathfinding to direct
                                    if debug_this_eval:
                                        print(f"   ✅ Switching to direct LOS movement")
                                    unit.path = None
                                    unit.path_index = 0
                                    unit.path_target = None
                                unit.destination = (unit.current_target.x, unit.current_target.y)
                                unit.has_los = True
                                unit.is_fallback_movement = False  # Clear fallback flag when LOS is available
                            elif debug_this_eval:
                                print(f"   ⚠️ LOS available but unit blocked by collision")
                        
                        # Handle strategy timeout - force different approach
                        elif has_los and is_strategy_timeout:
                            if debug_this_eval:
                                print(f"   ⏰ LOS strategy timed out - forcing pathfinding")
                            # Force pathfinding even with LOS to break deadlock
                            has_los = False  # Temporarily override LOS to force pathfinding
                        
                        # Strategy 2: No LOS - use pathfinding with fallback (but don't interrupt existing paths)
                        elif not has_los:
                            # If unit already has a working path, don't interrupt it unless truly stuck
                            if unit.path and not force_strategy_change:
                                if debug_this_eval and unit._stuck_counter == 0:
                                    print(f"   ⏸️ Path exists - continuing current path")
                                # Don't re-pathfind, let the existing path continue
                                pass
                            else:
                                if debug_this_eval and unit._stuck_counter == 0:
                                    print(f"   🔍 No LOS - attempting pathfinding")
                                # Pathfinding attempt (debug info shown above)
                                from systems.pathfinding import Pathfinding
                                pathfinder = Pathfinding(self.game_map, self)
                                
                                # Try different approach strategies
                                path_found = False
                                
                                # Option 1: Direct to target
                                path = pathfinder.find_path((unit.x, unit.y), (unit.current_target.x, unit.current_target.y), unit.radius, unit)
                                if path:
                                    unit.path = path
                                    unit.path_index = 0
                                    unit.path_target = (unit.current_target.x, unit.current_target.y)
                                    unit.destination = path[0] if path else None
                                    unit.has_los = False
                                    unit.is_fallback_movement = False  # Clear fallback flag when pathfinding succeeds
                                    path_found = True
                                    if debug_this_eval and unit._stuck_counter == 0:
                                        print(f"   ✅ Pathfinding successful: {len(path)} waypoints")
                                
                                # Option 2: Approach to attack range if direct path failed
                                if not path_found and distance > unit.get_effective_attack_range("exact"):
                                    approach_distance = unit.get_effective_attack_range("approach")
                                    target_x = unit.current_target.x - (dx / distance) * approach_distance
                                    target_y = unit.current_target.y - (dy / distance) * approach_distance
                                    
                                    path = pathfinder.find_path((unit.x, unit.y), (target_x, target_y), unit.radius, unit)
                                    if path:
                                        unit.path = path
                                        unit.path_index = 0
                                        unit.path_target = (target_x, target_y)
                                        unit.destination = path[0] if path else None
                                        unit.has_los = False
                                        unit.is_fallback_movement = False  # Clear fallback flag when pathfinding succeeds
                                        path_found = True
                                        if debug_this_eval and unit._stuck_counter == 0:
                                            print(f"   ✅ Pathfinding to range: {len(path)} waypoints")
                                
                                # Option 3: Direct movement fallback with collision detection
                                if not path_found:
                                    # Check if fallback has been tried too long - if so, clear and retry
                                    if is_strategy_timeout and unit.is_fallback_movement:
                                        if debug_this_eval:
                                            print(f"   ⏰ Fallback strategy timed out - clearing and retrying")
                                        # Clear stuck state and retry from the beginning
                                        unit.destination = None
                                        unit.path = None
                                        unit.path_index = 0
                                        unit.path_target = None
                                        unit.is_fallback_movement = False
                                        unit.status = "idle"
                                        # Reset collision blocks
                                        if hasattr(unit, '_blocked_by_collision'):
                                            delattr(unit, '_blocked_by_collision')
                                        # Reset timers to restart strategy evaluation
                                        unit._strategy_timer = 0
                                        unit._position_stuck_timer = 0
                                    else:
                                        if debug_this_eval and unit._stuck_counter == 0:
                                            print(f"   ⚠️ Pathfinding failed - using direct fallback")
                                        unit.destination = (unit.current_target.x, unit.current_target.y)
                                        unit.path = None
                                        unit.path_index = 0
                                        unit.path_target = None
                                        unit.status = "run"  # Make sure unit starts moving
                                        unit.has_los = False  # Keep LOS accurate - no actual line of sight
                                        unit.is_fallback_movement = True  # Flag to indicate this is fallback
                                        if debug_this_eval and unit._stuck_counter == 0:
                                            print(f"   🎯 Fallback active: moving directly to target")
                    
                    # Update destination for moving targets (if using direct movement or fallback)
                    elif (unit.has_los or unit.is_fallback_movement) and unit.destination:
                        unit.destination = (unit.current_target.x, unit.current_target.y)
                        # Destination updates happen silently
            
            # Check if unit is close enough to targets during movement
            if unit.path or unit.destination or unit.is_dropping_off:
                # Check building target
                if (hasattr(unit, 'building_target') and unit.building_target and not unit.is_building):
                    build_distance = math.sqrt((unit.x - unit.building_target.x)**2 + (unit.y - unit.building_target.y)**2)
                    required_distance = unit.radius + unit.building_target.radius - 10  # Changed from -30 to -10 for better visibility
                    
                    # Add tolerance for stuck units trying to build
                    if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                        tolerance = unit.get_target_tolerance("movement")
                        required_distance += tolerance
                    
                    if build_distance <= required_distance:
                        # Stop movement and start building
                        unit.path = None
                        unit.path_index = 0
                        unit.path_target = None
                        unit.destination = None
                        unit.is_building = True
                        unit.status = "build"
                        print(f"Worker started building {unit.building_target.building_name} at distance {build_distance}")
                        continue  # Skip movement processing
                
                # Check drop-off target
                elif (hasattr(unit, 'drop_off_target') and unit.drop_off_target and 
                      (unit.resource_amount > 0 or unit.is_dropping_off)):
                    
                    drop_distance = math.sqrt((unit.x - unit.drop_off_target.x)**2 + (unit.y - unit.drop_off_target.y)**2)
                    required_distance = get_drop_off_distance(unit, unit.drop_off_target)
                    
                    # Add tolerance for stuck units trying to drop off
                    if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                        tolerance = unit.get_target_tolerance("movement")
                        required_distance += tolerance
                    
                    # Check if worker reached intended destination (reachable position)
                    reached_destination = False
                    if unit.path_target:
                        dest_distance = math.sqrt((unit.x - unit.path_target[0])**2 + (unit.y - unit.path_target[1])**2)
                        dest_tolerance = 15  # Generous tolerance for reachable positions
                        if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                            dest_tolerance = unit.get_target_tolerance("movement")
                        reached_destination = dest_distance <= dest_tolerance
                    
                    # Allow drop-off if close to building OR reached intended destination
                    if drop_distance <= required_distance or unit.is_dropping_off or reached_destination:
                        # Stop movement and drop off resources
                        unit.path = None
                        unit.path_index = 0
                        unit.path_target = None
                        unit.destination = None
                        
                        building_name = unit.drop_off_target.name  # Store before clearing
                        resource_type = unit.resource_type  # Store before clearing
                        if self.gathering_manager.drop_off_resources(unit, unit.drop_off_target, delta_time):
                            print(f"Worker dropped off {resource_type} at {building_name}")
                            # Move worker away from building to avoid being stuck
                            if hasattr(unit, 'gathering_target') and unit.gathering_target:
                                # Move toward gathering target
                                unit.destination = (unit.gathering_target.x, unit.gathering_target.y)
                                unit.status = "run"
                                print(f"Worker moving away from {building_name} toward gathering target")
                            else:
                                # No gathering target - just move away from building
                                away_x = unit.x + (unit.x - unit.drop_off_target.x) * 0.5
                                away_y = unit.y + (unit.y - unit.drop_off_target.y) * 0.5
                                unit.destination = (away_x, away_y)
                                unit.status = "run"
                                print(f"Worker moving away from {building_name}")
                        continue  # Skip movement processing
                
                # Check gathering target
                elif (unit.name == "worker" and hasattr(unit, 'gathering_target') and 
                      unit.gathering_target and not unit.is_gathering):
                    
                    target_distance = math.sqrt((unit.x - unit.gathering_target.x)**2 + (unit.y - unit.gathering_target.y)**2)
                    gathering_distance = get_gathering_distance(unit, unit.gathering_target)
                    
                    # Add tolerance for stuck units trying to gather
                    if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                        tolerance = unit.get_target_tolerance("movement")
                        gathering_distance += tolerance
                    
                    if target_distance <= gathering_distance:
                        # Stop movement and start gathering
                        unit.path = None
                        unit.path_index = 0
                        unit.path_target = None
                        unit.destination = None
                        unit.status = "idle"
                        
                        if self.gathering_manager.start_gathering(unit, unit.gathering_target):
                            print(f"Worker started gathering {unit.gathering_target.name} at distance {target_distance}")
                        continue  # Skip movement processing
            
            # Debug path processing and force re-pathfinding when stuck
            if (unit.is_engaging and unit.current_target and unit.path and 
                hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 120):
                print(f"\n🚨 {unit.name} STUCK in path processing - forcing re-pathfinding")
                print(f"   Path: {unit.path_index}/{len(unit.path)}, Status: {unit.status}")
                # Force re-pathfinding by clearing current path
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                unit.status = "idle"
                # Reset timers
                if hasattr(unit, '_position_stuck_timer'):
                    unit._position_stuck_timer = 0
                if hasattr(unit, '_strategy_timer'):
                    unit._strategy_timer = 0
                # Mark for immediate re-evaluation
                unit._needs_repath = True
            
            # Handle path following with dynamic target updates
            if unit.path and unit.path_index < len(unit.path):
                # Check if target has moved significantly (for any type of targeting)
                target_object = None
                if unit.is_engaging and unit.current_target:
                    target_object = unit.current_target
                elif hasattr(unit, 'gathering_target') and unit.gathering_target:
                    target_object = unit.gathering_target
                elif hasattr(unit, 'building_target') and unit.building_target:
                    target_object = unit.building_target
                elif hasattr(unit, 'drop_off_target') and unit.drop_off_target:
                    target_object = unit.drop_off_target
                
                if target_object and unit.path_target:
                    target_displacement = math.sqrt(
                        (target_object.x - unit.path_target[0])**2 + 
                        (target_object.y - unit.path_target[1])**2
                    )
                    
                    # Skip displacement check for drop-off targets (buildings don't move, so "displacement" is just reachable position offset)
                    is_drop_off = (hasattr(unit, 'drop_off_target') and unit.drop_off_target and target_object == unit.drop_off_target)
                    
                    # If target moved more than 2x unit radius, consider re-pathfinding (but not for drop-off)
                    if target_displacement > unit.radius * 2 and not is_drop_off:
                        # Check if we now have line of sight to the moved target (only for combat)
                        if unit.is_engaging and unit.current_target:
                            # Include other attacking units as obstacles for better spacing
                            attacking_units = [u for u in self.units if u != unit and u.current_target == target_object]
                            obstacles = (self.buildings + 
                                       [u for u in self.units if u != unit and u != target_object] +
                                       self.resources)
                            has_los = unit.has_line_of_sight(target_object, self.game_map, obstacles)
                            
                            if has_los:
                                # Switch to direct movement since target moved and we have LOS
                                print(f"🎯 {unit.name} target moved {target_displacement:.1f} units - switching to direct LOS")
                                unit.path = None
                                unit.path_index = 0
                                unit.path_target = None
                                unit.destination = (target_object.x, target_object.y)
                                unit.has_los = True
                                unit.is_fallback_movement = False
                                continue
                        
                        # Re-pathfind to new target location
                        target_type = "combat" if unit.is_engaging else "movement"
                        print(f"🔄 {unit.name} {target_type} target moved {target_displacement:.1f} units - re-pathfinding")
                        from systems.pathfinding import Pathfinding
                        pathfinder = Pathfinding(self.game_map, self)
                        
                        # Set appropriate pathfinder targets based on unit type
                        if hasattr(unit, 'gathering_target') and unit.gathering_target == target_object:
                            pathfinder.gathering_target = unit.gathering_target
                        elif hasattr(unit, 'drop_off_target') and unit.drop_off_target == target_object:
                            pathfinder.drop_off_target = unit.drop_off_target
                        
                        new_path = pathfinder.find_path(
                            (unit.x, unit.y),
                            (target_object.x, target_object.y),
                            unit.radius,
                            unit
                        )
                        if new_path:
                            unit.path = new_path
                            unit.path_index = 0
                            unit.path_target = (target_object.x, target_object.y)
                            unit.destination = new_path[0]
                            print(f"   ✅ New path found with {len(new_path)} waypoints")
                        else:
                            # For combat, use fallback movement; for other tasks, just clear path
                            if unit.is_engaging:
                                print(f"   ⚠️ Re-pathfinding failed - using direct fallback")
                                unit.path = None
                                unit.path_index = 0
                                unit.path_target = None
                                unit.destination = (target_object.x, target_object.y)
                                unit.has_los = False
                                unit.is_fallback_movement = True
                            else:
                                print(f"   ⚠️ Re-pathfinding failed - clearing path")
                                unit.path = None
                                unit.path_index = 0
                                unit.path_target = None
                                unit.destination = None
                                unit.status = "idle"
                
                # Get current waypoint
                if unit.path and unit.path_index < len(unit.path):
                    waypoint = unit.path[unit.path_index]
                    unit.destination = waypoint
                else:
                    # Path was cleared during target update
                    continue
                
                # Debug path processing only when stuck at waypoint
                if (unit.status == "idle" and hasattr(self, 'frame_counter') and 
                    self.frame_counter % 120 == 0 and unit.is_engaging):
                    distance_to_waypoint = ((unit.x - waypoint[0]) ** 2 + (unit.y - waypoint[1]) ** 2) ** 0.5
                    print(f"\n🚨 {unit.name} STUCK at waypoint {unit.path_index}/{len(unit.path)}")
                    print(f"   Distance to waypoint: {distance_to_waypoint:.1f}")
                
                pos = pygame.math.Vector2(unit.x, unit.y)
                dest_vec = pygame.math.Vector2(unit.destination)
                direction = (dest_vec - pos)
                distance = direction.length()

                # More precise waypoint tolerance - reduced from 10 to 4
                waypoint_tolerance = 4  # Base waypoint tolerance (half of grid_size)
                if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                    # Only increase tolerance if truly stuck
                    tolerance = unit.get_target_tolerance("movement")
                    waypoint_tolerance = max(4, min(tolerance, 8))  # Between 4-8 units

                if distance < waypoint_tolerance:  # Reached waypoint with tolerance
                    # Waypoint advancement happens silently
                    unit.path_index += 1
                    # Reset stuck timer when successfully reaching a waypoint
                    if hasattr(unit, '_position_stuck_timer'):
                        unit._position_stuck_timer = max(0, unit._position_stuck_timer - 20)
                    if hasattr(unit, '_path_adjustment_count'):
                        unit._path_adjustment_count = max(0, unit._path_adjustment_count - 1)
                    if unit.path_index >= len(unit.path):
                        # Path complete - continue moving to exact target without teleporting
                        if unit.path_target:
                            final_dist = math.sqrt((unit.x - unit.path_target[0])**2 + (unit.y - unit.path_target[1])**2)
                            
                            # Use precise tolerance for final destination
                            final_tolerance = 2  # Base final destination tolerance
                            if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                                tolerance = unit.get_target_tolerance("movement")
                                final_tolerance = max(2, min(tolerance * 0.5, 4))  # Between 2-4 units for final destination
                            
                            if final_dist > final_tolerance:
                                # Keep moving smoothly to final position
                                unit.destination = unit.path_target
                                unit.path = None
                                unit.path_index = 0
                            else:
                                # Actually reached the destination (within tolerance)
                                if final_tolerance > 1:
                                    print(f"   🎯 {unit.name} reached target within tolerance ({final_tolerance:.1f})")
                                # Don't teleport to exact position if using tolerance
                                unit.destination = None
                                unit.path = None
                                unit.path_index = 0
                                unit.path_target = None
                                unit.status = "idle"
                                # Reset stuck timer since unit reached its destination
                                if hasattr(unit, '_position_stuck_timer'):
                                    unit._position_stuck_timer = 0
                                
                                # Check if we arrived at a farm to garrison
                                if hasattr(unit, 'garrison_target') and unit.garrison_target:
                                    if self.gathering_manager.garrison_worker_to_farm(unit, unit.garrison_target):
                                        continue  # Skip rest of processing for this unit
                        else:
                            unit.destination = None
                            unit.path = None
                            unit.path_index = 0
                            unit.status = "idle"
                else:
                    # Move towards current waypoint
                    direction.normalize_ip()
                    new_pos = pos + direction * unit.movement_speed * (1/60)
                    
                    # Check unit collisions and adjust position if needed
                    adjusted_pos = self._check_unit_collision_and_adjust(unit, new_pos, direction)
                    
                    # Check if new position is on walkable terrain
                    hex_coord = self.game_map.world_to_grid(adjusted_pos.x, adjusted_pos.y)
                    if hex_coord:
                        tile_type = self.game_map.grid[hex_coord[1]][hex_coord[0]]
                        if tile_type not in {"water", "lava"}:
                            # Check if unit actually moved
                            actually_moved = abs(adjusted_pos.x - unit.x) > 0.1 or abs(adjusted_pos.y - unit.y) > 0.1
                            
                            if actually_moved:
                                unit.x, unit.y = adjusted_pos.x, adjusted_pos.y
                                unit.status = "run"
                                # Reset blocked counter
                                if hasattr(unit, '_movement_blocked_timer'):
                                    unit._movement_blocked_timer = 0
                            else:
                                # Movement was blocked
                                unit.status = "idle"  # Don't show running animation when stuck
                                if not hasattr(unit, '_movement_blocked_timer'):
                                    unit._movement_blocked_timer = 0
                                unit._movement_blocked_timer += 1
                                
                                # After being blocked for a while, try alternate solutions
                                if unit._movement_blocked_timer > 30:  # 0.5 seconds
                                    self._handle_blocked_unit(unit)
                        else:
                            # Stop if we hit unwalkable terrain and recalculate path
                            unit.path = None
                            unit.path_index = 0
                            unit.destination = None
                            unit.status = "idle"
                    else:
                        # Check if unit actually moved
                        actually_moved = abs(adjusted_pos.x - unit.x) > 0.1 or abs(adjusted_pos.y - unit.y) > 0.1
                        if actually_moved:
                            unit.x, unit.y = adjusted_pos.x, adjusted_pos.y
                            unit.status = "run"
                        else:
                            unit.status = "idle"
            elif unit.destination and not unit.path:
                # Direct movement (no pathfinding) - keep for backwards compatibility
                pos = pygame.math.Vector2(unit.x, unit.y)
                
                # Update destination if engaging a moving target with LOS or fallback movement
                if unit.is_engaging and unit.current_target and (unit.has_los or unit.is_fallback_movement):
                    unit.destination = (unit.current_target.x, unit.current_target.y)
                
                dest_vec = pygame.math.Vector2(unit.destination)
                direction = (dest_vec - pos)
                distance = direction.length()

                # Use precise tolerance for direct movement
                arrival_tolerance = 2  # Base arrival tolerance  
                if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
                    tolerance = unit.get_target_tolerance("movement")
                    arrival_tolerance = max(2, min(tolerance * 0.7, 5))  # Between 2-5 units for direct movement

                if distance < arrival_tolerance: 
                    if arrival_tolerance > 1:
                        print(f"   🎯 {unit.name} reached direct destination within tolerance ({arrival_tolerance:.1f})")
                    # Don't teleport to exact position if using tolerance
                    unit.destination = None
                    unit.status = "idle"
                    # Reset stuck timer since unit reached its destination
                    if hasattr(unit, '_position_stuck_timer'):
                        unit._position_stuck_timer = 0
                else:
                    direction.normalize_ip()
                    new_pos = pos + direction * unit.movement_speed * (1/60)
                    
                    # Check unit collisions and adjust position if needed
                    adjusted_pos = self._check_unit_collision_and_adjust(unit, new_pos, direction)
                    
                    # Check if new position is on walkable terrain
                    hex_coord = self.game_map.world_to_grid(adjusted_pos.x, adjusted_pos.y)
                    if hex_coord:
                        tile_type = self.game_map.grid[hex_coord[1]][hex_coord[0]]
                        if tile_type not in {"water", "lava"}:
                            # Check if unit actually moved
                            actually_moved = abs(adjusted_pos.x - unit.x) > 0.1 or abs(adjusted_pos.y - unit.y) > 0.1
                            
                            if actually_moved:
                                unit.x, unit.y = adjusted_pos.x, adjusted_pos.y
                                unit.status = "run"
                                # Reset blocked counter
                                if hasattr(unit, '_movement_blocked_timer'):
                                    unit._movement_blocked_timer = 0
                            else:
                                # Movement was blocked
                                unit.status = "idle"  # Don't show running animation when stuck
                                if not hasattr(unit, '_movement_blocked_timer'):
                                    unit._movement_blocked_timer = 0
                                unit._movement_blocked_timer += 1
                                
                                # For direct movement, being blocked might mean we need pathfinding
                                if unit._movement_blocked_timer > 30:  # 0.5 seconds
                                    self._handle_blocked_unit(unit)
                        else:
                            # Stop if we hit unwalkable terrain
                            unit.destination = None
                            unit.status = "idle"
                    else:
                        # Check if unit actually moved
                        actually_moved = abs(adjusted_pos.x - unit.x) > 0.1 or abs(adjusted_pos.y - unit.y) > 0.1
                        if actually_moved:
                            unit.x, unit.y = adjusted_pos.x, adjusted_pos.y
                            unit.status = "run"
                        else:
                            unit.status = "idle"

        map_width_pixels = MAP_WIDTH * TILE_WIDTH * 0.75 * self.camera.zoom
        map_height_pixels = MAP_HEIGHT * TILE_HEIGHT * self.camera.zoom

        self.camera.x = max(min(self.camera.x, 0), MAP_VIEW_WIDTH - map_width_pixels - (TILE_WIDTH * 0.25 * self.camera.zoom))
        self.camera.y = max(min(self.camera.y, 0), MAP_VIEW_HEIGHT - map_height_pixels - (TILE_HEIGHT * 0.5 * self.camera.zoom))

    def draw(self):
        # Dark gray background
        DARK_GRAY = (40, 40, 40)
        self.screen.fill(DARK_GRAY)
        
        # Lighter gray for map surface
        MAP_GRAY = (60, 60, 60)
        self.map_surface.fill(MAP_GRAY)
        self.game_map.draw(self.map_surface, self.camera)

        all_objects = self.resources + self.buildings + self.units + self.construction_sites
        all_objects.sort(key=lambda obj: obj.y)
        

        for obj in all_objects:
            draw_x = (obj.x * self.camera.zoom) + self.camera.x
            draw_y = (obj.y * self.camera.zoom) + self.camera.y

            sprite_to_draw = None
            if isinstance(obj, Building):
                player_index = self.players.index(obj.player)
                sprite_to_draw = self.sprite_manager.get_building_sprite(obj.name, player_index)
            elif isinstance(obj, Resource):
                sprite_to_draw = self.sprite_manager.get_resource_sprite(obj.name)
            elif isinstance(obj, Unit):
                sprite_to_draw = obj.get_current_sprite()
            elif isinstance(obj, ConstructionSite):
                # Use construction sprite with player tinting
                player_index = self.players.index(obj.player)
                sprite_to_draw = self.sprite_manager.get_building_sprite("construction", player_index)

            if sprite_to_draw:
                sprite_w, sprite_h = sprite_to_draw.get_size()
                scale = (obj.size[0] * TILE_WIDTH) / sprite_w
                scaled_width = int(sprite_w * scale * self.camera.zoom)
                scaled_height = int(sprite_h * scale * self.camera.zoom)
                
                scaled_sprite = pygame.transform.scale(sprite_to_draw, (scaled_width, scaled_height))

                blit_x = draw_x - (scaled_width / 2)
                blit_y = draw_y - (scaled_height / 2)
                
                self.map_surface.blit(scaled_sprite, (blit_x, blit_y))

        # Draw selection circles
        self.selection_manager.draw_selection_circles(self.map_surface, self.camera)
        
        # Draw attack target indicators
        self.selection_manager.draw_attack_targets(self.map_surface, self.camera)
        
        # Draw LOS debug visualization
        self.selection_manager.draw_los_debug(self.map_surface, self.camera)
        
        # Draw unit paths (debug mode only)
        self.selection_manager.draw_unit_paths(self.map_surface, self.camera)
        
        # Draw selection box if active
        self.selection_manager.draw_selection_box(self.map_surface)
        
        # Draw building preview if in placement mode
        if self.building_placement_mode and self.building_preview_pos:
            self.draw_building_preview()

        # Draw floating UI elements (health bars, etc.)
        self.floating_ui.draw_all_floating_ui(self.map_surface, self.camera)

        self.screen.blit(self.map_surface, (0, TOP_BAR_HEIGHT))  # Position below top bar
        self.minimap.draw(self.screen)
        self.ui_manager.draw_ui_panel(self.screen)
        
        # Draw top bar using UIManager
        self.ui_manager.draw_top_bar(self.screen)
        
        pygame.display.flip()
    
    
    def enter_building_placement_mode(self, building_data):
        """Enter building placement mode with the selected building type"""
        # Find and store the selected worker
        self.selected_builder = None
        for unit in self.units:
            if unit.selected and unit.name == "worker" and unit.player == self.players[0]:
                # Check if unit has can_build attribute, default to True for workers
                can_build = getattr(unit, 'can_build', True) if unit.name == "worker" else False
                if can_build:
                    self.selected_builder = unit
                    break
                
        if not self.selected_builder:
            print("No valid worker selected for building!")
            return
            
        self.building_placement_mode = True
        self.building_to_place = building_data
        self.building_preview_valid = False
        self.building_preview_pos = None
        print(f"Entered building placement mode for: {building_data['name']} with worker at ({self.selected_builder.x}, {self.selected_builder.y})")
    
    def cancel_building_placement(self):
        """Cancel building placement mode"""
        self.building_placement_mode = False
        self.building_to_place = None
        self.building_preview_valid = False
        self.building_preview_pos = None
        self.selected_builder = None
        print("Cancelled building placement")
    
    def update_building_preview(self, mouse_pos):
        """Update building preview position and validity"""
        if not self.building_placement_mode:
            return
            
        # Convert mouse position to world coordinates
        world_pos = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        
        # Check if position is within the map view area
        if mouse_pos[1] < SCREEN_HEIGHT - MAP_VIEW_HEIGHT:
            self.building_preview_pos = None
            return
            
        self.building_preview_pos = world_pos
        
        # Check if position is valid for building
        self.building_preview_valid = self.is_valid_building_position(world_pos)
    
    def is_valid_building_position(self, world_pos):
        """Check if a position is valid for building placement"""
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
        
        # Check collision with existing objects
        all_objects = self.buildings + self.units + self.resources + self.construction_sites
        for obj in all_objects:
            distance = math.sqrt((world_pos[0] - obj.x)**2 + (world_pos[1] - obj.y)**2)
            min_distance = building_radius + obj.radius
            if distance < min_distance:
                return False
                
        return True
    
    def draw_building_preview(self):
        """Draw the building preview with appropriate tint"""
        if not self.building_preview_pos:
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
            screen_x = self.building_preview_pos[0] * self.camera.zoom + self.camera.x
            screen_y = self.building_preview_pos[1] * self.camera.zoom + self.camera.y
            
            # Scale the sprite using the same logic as normal building rendering
            sprite_w, sprite_h = preview_sprite.get_size()
            scale = (building_size[0] * TILE_WIDTH) / sprite_w
            scaled_width = int(sprite_w * scale * self.camera.zoom)
            scaled_height = int(sprite_h * scale * self.camera.zoom)
            
            scaled_sprite = pygame.transform.scale(preview_sprite, (scaled_width, scaled_height))
            
            # Draw centered on position
            blit_x = screen_x - (scaled_width / 2)
            blit_y = screen_y - (scaled_height / 2)
            
            self.map_surface.blit(scaled_sprite, (blit_x, blit_y))
    
    def handle_building_placement_click(self, mouse_pos):
        """Handle click during building placement mode"""
        if not self.building_preview_valid or not self.building_preview_pos:
            print(f"Invalid placement: valid={self.building_preview_valid}, pos={self.building_preview_pos}")
            return
            
        # Use the stored builder
        if not self.selected_builder:
            print("No builder stored!")
            self.cancel_building_placement()
            return
            
        # Deduct resources
        human_player = self.players[0]
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
        
        self.construction_sites.append(construction_site)
        
        # Assign builder to construction site
        construction_site.builder = self.selected_builder
        self.selected_builder.building_target = construction_site
        self.selected_builder.is_building = False  # Will be set to true when worker arrives
        
        # Move worker to construction site - pathfind directly to it
        from systems.pathfinding import Pathfinding
        pathfinder = Pathfinding(self.game_map, self)
        
        # Simple pathfinding directly to construction site center
        path = pathfinder.find_path(
            (self.selected_builder.x, self.selected_builder.y),
            (construction_site.x, construction_site.y),
            self.selected_builder.radius,
            self.selected_builder
        )
        
        if path:
            self.selected_builder.path = path
            self.selected_builder.path_index = 0
            self.selected_builder.path_target = (construction_site.x, construction_site.y)
            self.selected_builder.destination = path[0] if path else None
            self.selected_builder.status = "run"
            
        # Exit building placement mode  
        building_name = self.building_to_place['name']  # Store name before cancelling
        self.cancel_building_placement()
        print(f"Placed construction site for {building_name} at ({construction_site.x}, {construction_site.y})")
    
    def update_construction(self, delta_time):
        """Update construction progress for all construction sites"""
        completed_sites = []
        
        for site in self.construction_sites:
            if site.builder and site.builder.is_building:
                # Update construction progress with player's build speed bonus
                build_speed = delta_time
                if hasattr(site, 'player') and site.player:
                    build_speed *= site.player.build_speed_bonus
                site.construction_progress += build_speed
                
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
                        costs=site.building_data.get('costs', {})
                    )
                    
                    self.buildings.append(building_class)
                    completed_sites.append(site)
                    
                    # Free the builder
                    site.builder.is_building = False
                    site.builder.building_target = None
                    site.builder.status = "idle"
                    
                    print(f"Construction complete: {site.building_name} at ({site.x}, {site.y})")
        
        # Remove completed construction sites
        for site in completed_sites:
            self.construction_sites.remove(site)
    
    def cancel_construction(self, construction_site):
        """Cancel a construction site and refund half the resources"""
        if construction_site in self.construction_sites:
            # Refund half the resources
            for resource, amount in construction_site.costs.items():
                construction_site.player.resources[resource] += amount // 2
            
            # Free the builder
            if construction_site.builder:
                construction_site.builder.is_building = False
                construction_site.builder.building_target = None
                construction_site.builder.status = "idle"
            
            # Remove the construction site
            self.construction_sites.remove(construction_site)
            
            print(f"Cancelled construction of {construction_site.building_name}, refunded half resources")
    
    def _find_optimal_attack_position(self, unit, target, other_attackers):
        """Find optimal attack position for unit when multiple units are attacking the same target"""
        target_x, target_y = target.x, target.y
        attack_range = unit.get_effective_attack_range("positioning")  # Use standardized positioning range
        
        # Generate potential attack positions in a circle around the target
        import math
        num_positions = 8  # Check 8 positions around the target
        best_position = None
        best_score = float('-inf')
        
        for i in range(num_positions):
            angle = (i / num_positions) * 2 * math.pi
            pos_x = target_x + math.cos(angle) * attack_range
            pos_y = target_y + math.sin(angle) * attack_range
            
            # Check if position is valid (not in water/lava, not blocked by buildings)
            hex_coord = self.game_map.world_to_grid(pos_x, pos_y)
            if not hex_coord:
                continue
            col, row = hex_coord
            if row < 0 or row >= self.game_map.height or col < 0 or col >= self.game_map.width:
                continue
            tile_type = self.game_map.grid[row][col]
            if tile_type in {"water", "lava"}:
                continue
            
            # Check for collision with buildings
            blocked_by_building = False
            for building in self.buildings:
                dist_to_building = math.sqrt((building.x - pos_x)**2 + (building.y - pos_y)**2)
                if dist_to_building < (building.radius + unit.radius):
                    blocked_by_building = True
                    break
            if blocked_by_building:
                continue
            
            # Score this position based on:
            # 1. Distance to other attacking units (farther is better)
            # 2. Distance to current unit position (closer is better)
            # 3. Line of sight to target
            
            score = 0
            
            # Distance to other attackers (farther is better)
            min_dist_to_attacker = float('inf')
            for other in other_attackers:
                dist = math.sqrt((other.x - pos_x)**2 + (other.y - pos_y)**2)
                min_dist_to_attacker = min(min_dist_to_attacker, dist)
            
            if min_dist_to_attacker < unit.radius * 3:  # Too close to other units
                score -= 100
            else:
                score += min(min_dist_to_attacker, unit.radius * 6)  # Cap the benefit
            
            # Distance to current position (closer is better)
            dist_to_current = math.sqrt((unit.x - pos_x)**2 + (unit.y - pos_y)**2)
            score += max(0, 200 - dist_to_current)  # Prefer closer positions
            
            # Check line of sight to target
            obstacles = (self.buildings + 
                        [u for u in self.units if u != unit and u != target] + 
                        self.resources)
            
            # Create temporary unit at this position to check LOS
            temp_unit = type('TempUnit', (), {
                'x': pos_x, 'y': pos_y, 'radius': unit.radius,
                'has_line_of_sight': unit.has_line_of_sight
            })()
            
            if temp_unit.has_line_of_sight(target, self.game_map, obstacles):
                score += 50  # Bonus for clear LOS
            
            if score > best_score:
                best_score = score
                best_position = (pos_x, pos_y)
        
        return best_position
    
    def _check_unit_collision_and_adjust(self, unit, new_pos, direction):
        """Smart collision detection with sliding behavior"""
        original_pos = pygame.math.Vector2(unit.x, unit.y)
        final_pos = new_pos
        
        # First, check for collisions with static objects (buildings, resources)
        for building in self.buildings:
            # Skip drop-off targets when unit is dropping off
            if (hasattr(unit, 'drop_off_target') and unit.drop_off_target == building and
                hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
                continue
                
            dx = final_pos.x - building.x
            dy = final_pos.y - building.y
            distance = math.sqrt(dx * dx + dy * dy)
            min_distance = unit.radius + building.radius + 2
            
            if distance < min_distance:
                # Calculate overlap amount
                overlap = min_distance - distance
                # Try sliding along the obstacle
                final_pos = self._calculate_slide_position(original_pos, final_pos, 
                                                         pygame.math.Vector2(building.x, building.y), 
                                                         building.radius + unit.radius + 2,
                                                         unit, overlap)
        
        # Check resources
        for resource in self.resources:
            # Skip gathering targets when unit is gathering
            if (hasattr(unit, 'gathering_target') and unit.gathering_target == resource):
                continue
                
            dx = final_pos.x - resource.x
            dy = final_pos.y - resource.y
            distance = math.sqrt(dx * dx + dy * dy)
            min_distance = unit.radius + resource.radius + 2
            
            if distance < min_distance:
                # Calculate overlap amount
                overlap = min_distance - distance
                # Try sliding along the obstacle
                final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                         pygame.math.Vector2(resource.x, resource.y),
                                                         resource.radius + unit.radius + 2,
                                                         unit, overlap)
        
        # Then check other units with special handling
        for other_unit in self.units:
            if other_unit == unit:
                continue
            
            # Calculate distances
            current_distance = math.sqrt((unit.x - other_unit.x)**2 + (unit.y - other_unit.y)**2)
            new_distance = math.sqrt((final_pos.x - other_unit.x)**2 + (final_pos.y - other_unit.y)**2)
            min_distance = unit.radius + other_unit.radius + 2
            
            # If already overlapping, prioritize separation
            if current_distance < min_distance:
                if new_distance > current_distance:
                    continue  # Allow movement that separates
                else:
                    # Try to find a perpendicular escape direction
                    escape_dir = self._find_escape_direction(original_pos, 
                                                           pygame.math.Vector2(other_unit.x, other_unit.y),
                                                           direction)
                    if escape_dir:
                        escape_move = escape_dir * (unit.movement_speed * (1/60))
                        test_pos = original_pos + escape_move
                        # Check if escape position is valid
                        if not self._would_collide_with_static(unit, test_pos):
                            final_pos = test_pos
                    else:
                        final_pos = original_pos  # Can't move
            
            # Normal collision avoidance
            elif new_distance < min_distance:
                # Calculate overlap amount
                overlap = min_distance - new_distance
                # Try sliding along the unit
                final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                         pygame.math.Vector2(other_unit.x, other_unit.y),
                                                         other_unit.radius + unit.radius + 2,
                                                         unit, overlap)
        
        return final_pos
    
    def _calculate_slide_position(self, start_pos, desired_pos, obstacle_pos, min_distance, unit=None, overlap_amount=0):
        """Calculate a sliding position along an obstacle"""
        # Vector from start to desired position
        move_vector = desired_pos - start_pos
        move_distance = move_vector.length()
        
        if move_distance < 0.1:
            return start_pos
        
        # Fix #1: Reduce sliding when combat unit is near attack target
        if unit and hasattr(unit, 'current_target') and hasattr(unit, 'is_engaging') and unit.is_engaging:
            if hasattr(unit, 'get_effective_attack_range'):
                attack_range = unit.get_effective_attack_range("exact")
                dist_to_target = math.sqrt((unit.current_target.x - start_pos.x)**2 + 
                                         (unit.current_target.y - start_pos.y)**2)
                # If within 2x attack range, reduce sliding to allow more direct approach
                if dist_to_target < attack_range * 2:
                    return start_pos  # Don't slide when close to target
        
        # Vector from obstacle to start position
        to_start = start_pos - obstacle_pos
        
        if to_start.length() < 0.1:
            return start_pos  # Too close to obstacle center
        
        # Project movement onto the tangent of the obstacle
        # This gives us the sliding direction
        to_start_normalized = to_start.normalize()
        dot = move_vector.dot(to_start_normalized)
        slide_vector = move_vector - to_start_normalized * dot
        
        if slide_vector.length() > 0.1:
            # Fix #3: Smooth sliding transitions based on overlap severity
            # Scale slide speed based on how much we're overlapping
            if overlap_amount > 0:
                # More overlap = slower movement (0.3 to 0.8 based on overlap)
                slide_factor = max(0.3, min(0.8, 1.0 - overlap_amount / 50))
            else:
                slide_factor = 0.7  # Default for non-overlap collisions
            
            # Apply sliding movement with smooth factor
            slide_pos = start_pos + slide_vector.normalize() * move_distance * slide_factor
            
            # Ensure we're not getting closer to the obstacle
            if (slide_pos - obstacle_pos).length() >= min_distance - 1:
                return slide_pos
        
        return start_pos  # Can't slide, stay in place
    
    def _find_escape_direction(self, unit_pos, obstacle_pos, preferred_dir):
        """Find a perpendicular direction to escape from an overlapping obstacle"""
        to_obstacle = obstacle_pos - unit_pos
        
        if to_obstacle.length() < 0.1:
            # Units are on top of each other, use preferred direction
            return preferred_dir
        
        # Get perpendicular directions
        perpendicular1 = pygame.math.Vector2(-to_obstacle.y, to_obstacle.x).normalize()
        perpendicular2 = pygame.math.Vector2(to_obstacle.y, -to_obstacle.x).normalize()
        
        # Choose the perpendicular that aligns better with preferred direction
        if preferred_dir.dot(perpendicular1) > preferred_dir.dot(perpendicular2):
            return perpendicular1
        else:
            return perpendicular2
    
    def _would_collide_with_static(self, unit, test_pos):
        """Check if a position would collide with static obstacles"""
        # Check buildings
        for building in self.buildings:
            dist = math.sqrt((test_pos.x - building.x)**2 + (test_pos.y - building.y)**2)
            if dist < building.radius + unit.radius + 2:
                return True
        
        # Check resources
        for resource in self.resources:
            dist = math.sqrt((test_pos.x - resource.x)**2 + (test_pos.y - resource.y)**2)
            if dist < resource.radius + unit.radius + 2:
                return True
        
        # Check terrain
        hex_coord = self.game_map.world_to_grid(test_pos.x, test_pos.y)
        if hex_coord:
            col, row = hex_coord
            if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                if self.game_map.grid[row][col] in {"water", "lava"}:
                    return True
        
        return False
    
    def _separate_overlapping_units(self):
        """Push apart units that are overlapping with priority for drop-off workers"""
        base_separation_force = 0.8  # Increased base separation force
        
        for i, unit1 in enumerate(self.units):
            for unit2 in self.units[i + 1:]:
                # Calculate distance between units
                dx = unit2.x - unit1.x
                dy = unit2.y - unit1.y
                distance = math.sqrt(dx * dx + dy * dy)
                
                # Check if they're overlapping
                min_distance = unit1.radius + unit2.radius + 2
                if distance < min_distance and distance > 0:
                    # Calculate overlap amount
                    overlap = min_distance - distance
                    
                    # Increase separation force if either unit is dropping off
                    separation_force = base_separation_force
                    if ((hasattr(unit1, 'is_dropping_off') and unit1.is_dropping_off) or 
                        (hasattr(unit1, 'drop_off_target') and unit1.drop_off_target and 
                         hasattr(unit1, 'resource_amount') and unit1.resource_amount > 0) or
                        (hasattr(unit2, 'is_dropping_off') and unit2.is_dropping_off) or 
                        (hasattr(unit2, 'drop_off_target') and unit2.drop_off_target and 
                         hasattr(unit2, 'resource_amount') and unit2.resource_amount > 0)):
                        separation_force = 1.5  # Stronger separation for drop-off workers
                    
                    # Normalize direction vector
                    dx_norm = dx / distance
                    dy_norm = dy / distance
                    
                    # Calculate separation distance for each unit
                    separation_per_unit = overlap * separation_force / 2
                    
                    # Push units apart (each moves half the distance)
                    unit1.x -= dx_norm * separation_per_unit
                    unit1.y -= dy_norm * separation_per_unit
                    unit2.x += dx_norm * separation_per_unit
                    unit2.y += dy_norm * separation_per_unit
                    
                    # Ensure units don't go into unwalkable terrain
                    self._ensure_unit_on_walkable_terrain(unit1)
                    self._ensure_unit_on_walkable_terrain(unit2)
    
    def _ensure_unit_on_walkable_terrain(self, unit):
        """Make sure unit stays on walkable terrain after separation"""
        hex_coord = self.game_map.world_to_grid(unit.x, unit.y)
        if hex_coord:
            col, row = hex_coord
            if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                tile_type = self.game_map.grid[row][col]
                if tile_type in {"water", "lava"}:
                    # Find nearest walkable position
                    for radius in range(5, 30, 5):
                        for angle in range(0, 360, 45):
                            test_x = unit.x + radius * math.cos(math.radians(angle))
                            test_y = unit.y + radius * math.sin(math.radians(angle))
                            test_hex = self.game_map.world_to_grid(test_x, test_y)
                            if test_hex:
                                test_col, test_row = test_hex
                                if 0 <= test_row < self.game_map.height and 0 <= test_col < self.game_map.width:
                                    test_tile = self.game_map.grid[test_row][test_col]
                                    if test_tile not in {"water", "lava"}:
                                        unit.x = test_x
                                        unit.y = test_y
                                        return
    
    def _apply_separation_to_unit(self, unit):
        """Apply separation force to a specific unit if it's overlapping with others"""
        separation_applied = False
        max_separation_force = 2.0  # Stronger force for individual separation
        
        for other_unit in self.units:
            if other_unit == unit:
                continue
                
            # Calculate distance between units
            dx = unit.x - other_unit.x
            dy = unit.y - other_unit.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            # Check if they're overlapping
            min_distance = unit.radius + other_unit.radius + 2
            if distance < min_distance and distance > 0:
                # Calculate overlap amount
                overlap = min_distance - distance
                
                # Normalize direction vector (direction to push this unit)
                dx_norm = dx / distance
                dy_norm = dy / distance
                
                # Calculate separation force based on overlap severity
                # More overlap = stronger force, up to max_separation_force
                separation_force = min(max_separation_force, overlap * 0.8)
                
                # Apply separation to this unit only
                unit.x += dx_norm * separation_force
                unit.y += dy_norm * separation_force
                separation_applied = True
                
                # Ensure unit doesn't go into unwalkable terrain
                self._ensure_unit_on_walkable_terrain(unit)
                
                # For workers dropping off, prioritize separation over pathfinding
                if (hasattr(unit, 'is_dropping_off') and unit.is_dropping_off) or \
                   (hasattr(unit, 'drop_off_target') and unit.drop_off_target and unit.resource_amount > 0):
                    # Clear destination temporarily to allow separation to take effect
                    if overlap > 5:  # Only for significant overlaps
                        unit.destination = None
                        # Don't clear path completely, just pause movement
                        if hasattr(unit, '_separation_pause_timer'):
                            unit._separation_pause_timer += 1
                        else:
                            unit._separation_pause_timer = 1
                        
                        # Resume movement after separation
                        if unit._separation_pause_timer > 10:  # About 1/6 second
                            unit._separation_pause_timer = 0
                            # Restore destination if we have drop-off target
                            if hasattr(unit, 'drop_off_target') and unit.drop_off_target:
                                unit.destination = (unit.drop_off_target.x, unit.drop_off_target.y)
        
        return separation_applied
    
    def _handle_blocked_unit(self, unit):
        """Handle a unit that has been blocked for too long"""
        # Reset the blocked timer
        unit._movement_blocked_timer = 0
        
        # Different strategies based on what the unit is doing
        if (hasattr(unit, 'drop_off_target') and unit.drop_off_target and 
            hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
            # Worker trying to drop off resources
            print(f"Worker {unit.name} blocked while trying to drop off resources")
            
            # Try to use pathfinding if not already using it
            if not unit.path:
                from systems.pathfinding import Pathfinding
                pathfinder = Pathfinding(self.game_map, self)
                pathfinder.drop_off_target = unit.drop_off_target
                pathfinder.current_unit = unit
                
                path = pathfinder.find_path((unit.x, unit.y), 
                                          (unit.drop_off_target.x, unit.drop_off_target.y), 
                                          unit.radius, unit)
                if path:
                    unit.path = path
                    unit.path_index = 0
                    unit.destination = path[0] if path else None
                    print(f"  Found alternate path with {len(path)} waypoints")
            else:
                # Already has path but still stuck - skip current waypoint
                if unit.path_index < len(unit.path) - 1:
                    unit.path_index += 1
                    unit.destination = unit.path[unit.path_index]
                    print(f"  Skipping to next waypoint")
                else:
                    # At last waypoint but stuck - clear path and try direct movement
                    unit.path = None
                    unit.path_index = 0
                    unit.destination = (unit.drop_off_target.x, unit.drop_off_target.y)
                    print(f"  Clearing path, trying direct movement")
        
        elif hasattr(unit, 'gathering_target') and unit.gathering_target:
            # Worker trying to gather resources
            print(f"Worker {unit.name} blocked while trying to gather")
            
            # Similar logic for gathering
            if not unit.path:
                from systems.pathfinding import Pathfinding
                pathfinder = Pathfinding(self.game_map, self)
                pathfinder.gathering_target = unit.gathering_target
                pathfinder.current_unit = unit
                
                path = pathfinder.find_path((unit.x, unit.y), 
                                          (unit.gathering_target.x, unit.gathering_target.y), 
                                          unit.radius, unit)
                if path:
                    unit.path = path
                    unit.path_index = 0
                    unit.destination = path[0] if path else None
                    print(f"  Found alternate path with {len(path)} waypoints")
        
        elif hasattr(unit, 'current_target') and unit.current_target and hasattr(unit, 'is_engaging') and unit.is_engaging:
            # Combat unit trying to reach target
            print(f"{unit.name} blocked while engaging {unit.current_target.name}")
            
            # Force re-pathfinding
            unit._needs_repath = True
            unit._position_stuck_timer = 100  # Trigger immediate re-evaluation
        
        else:
            # Generic movement - try to find alternate route
            if unit.destination:
                print(f"{unit.name} blocked during generic movement")
                
                # If using direct movement, try pathfinding
                if not unit.path:
                    from systems.pathfinding import Pathfinding
                    pathfinder = Pathfinding(self.game_map, self)
                    pathfinder.current_unit = unit
                    
                    path = pathfinder.find_path((unit.x, unit.y), unit.destination, unit.radius, unit)
                    if path:
                        unit.path = path
                        unit.path_index = 0
                        unit.destination = path[0] if path else None
                        print(f"  Switching to pathfinding with {len(path)} waypoints")
                else:
                    # Has path but stuck - try skipping waypoint
                    if unit.path_index < len(unit.path) - 1:
                        unit.path_index += 1
                        unit.destination = unit.path[unit.path_index]
                        print(f"  Skipping to next waypoint")
    
    def _adjust_stuck_unit_path(self, unit):
        """Force complete re-pathfinding when stuck"""
        if not unit.path or not unit.current_target:
            return False
        
        # Always force complete re-pathfinding when stuck
        print(f"   🔄 Unit stuck - forcing complete re-pathfinding")
        unit.path = None
        unit.path_index = 0
        unit.path_target = None
        unit.destination = None
        unit._path_adjustment_count = 0
        
        # Clear stuck timers to give the new path a chance
        if hasattr(unit, '_position_stuck_timer'):
            unit._position_stuck_timer = 0
        if hasattr(unit, '_strategy_timer'):
            unit._strategy_timer = 0
        
        return True
    
    def _find_blocking_object(self, start, end, radius, unit=None):
        """Find the first object blocking a path between two points"""
        # Sample points along the line
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance == 0:
            return None
        
        steps = int(distance / 10) + 1  # Check every 10 units
        
        for i in range(1, steps + 1):
            t = i / steps
            check_x = start[0] + dx * t
            check_y = start[1] + dy * t
            
            # Check collision with buildings
            for building in self.buildings:
                dist = math.sqrt((building.x - check_x)**2 + (building.y - check_y)**2)
                if dist < building.radius + radius + 2:
                    return building
            
            # Check collision with other units
            for other_unit in self.units:
                if unit and other_unit == unit:
                    continue  # Skip self
                dist = math.sqrt((other_unit.x - check_x)**2 + (other_unit.y - check_y)**2)
                if dist < other_unit.radius + radius + 2:
                    return other_unit
            
            # Check collision with resources
            for resource in self.resources:
                dist = math.sqrt((resource.x - check_x)**2 + (resource.y - check_y)**2)
                if dist < resource.radius + radius + 2:
                    return resource
        
        return None
    
    def _calculate_detour_point(self, start, end, obstacle, unit_radius):
        """Calculate a detour point to go around an obstacle"""
        # Calculate direction from start to obstacle
        dx = obstacle.x - start[0]
        dy = obstacle.y - start[1]
        dist_to_obstacle = math.sqrt(dx * dx + dy * dy)
        
        if dist_to_obstacle == 0:
            return None
        
        # Normalize direction
        dx /= dist_to_obstacle
        dy /= dist_to_obstacle
        
        # Calculate perpendicular directions (left and right)
        left_x, left_y = -dy, dx
        right_x, right_y = dy, -dx
        
        # Calculate detour distance (obstacle radius + unit radius + buffer)
        detour_distance = obstacle.radius + unit_radius + 20
        
        # Try both left and right detours
        for perpendicular in [(left_x, left_y), (right_x, right_y)]:
            detour_x = obstacle.x + perpendicular[0] * detour_distance
            detour_y = obstacle.y + perpendicular[1] * detour_distance
            
            # Check if detour point is walkable
            hex_coord = self.game_map.world_to_grid(detour_x, detour_y)
            if hex_coord:
                tile_type = self.game_map.grid[hex_coord[1]][hex_coord[0]]
                if tile_type not in {"water", "lava"}:
                    # Check if detour point is clear of obstacles
                    is_clear = True
                    for obj in self.buildings + self.units + self.resources:
                        dist = math.sqrt((obj.x - detour_x)**2 + (obj.y - detour_y)**2)
                        if dist < obj.radius + unit_radius + 5:
                            is_clear = False
                            break
                    
                    if is_clear:
                        return (detour_x, detour_y)
        
        return None
    

    def _position_is_free(self, unit, position, buffer):
        """Check if a position is free of collisions for the given unit"""
        # Get all potential obstacles (units, buildings, resources)
        obstacles = []
        
        # Add other units
        for other_unit in self.units:
            if other_unit == unit:
                continue
            obstacles.append(other_unit)
        
        # Add buildings (unless it's the unit's drop-off target)
        for building in self.buildings:
            if hasattr(unit, 'drop_off_target') and building == unit.drop_off_target:
                continue
            obstacles.append(building)
        
        # Add resources (unless it's the unit's gathering target)
        for resource in self.resources:
            if hasattr(unit, 'gathering_target') and resource == unit.gathering_target:
                continue
            obstacles.append(resource)
        
        # Check collision with all obstacles
        for obstacle in obstacles:
            distance = math.sqrt((position.x - obstacle.x)**2 + (position.y - obstacle.y)**2)
            min_distance = unit.radius + obstacle.radius + buffer
            
            if distance < min_distance:
                return False
        
        return True
''

