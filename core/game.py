import pygame
import math
import traceback
from core.config import (SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT,
                        CAMERA_SPEED, TILE_WIDTH, TILE_HEIGHT,
                        MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, MINIMAP_WIDTH, 
                        MINIMAP_HEIGHT, NUM_PLAYERS, PLAYER_COLORS, TOP_BAR_HEIGHT,
                        SMART_CURSORS_ENABLED, DEFAULT_GAME_SPEED, MIN_GAME_SPEED,
                        MAX_GAME_SPEED, GAME_SPEED_INCREMENT, AI_ONLY_MODE,
                        AI_ONLY_PLAYER_COUNT, SPECTATOR_FOG_OF_WAR,
                        SPECTATOR_START_ZOOM)
from world.map import Map
from world.camera import Camera
from entities import load_game_data
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
from systems.worker_task_system import WorkerTaskSystem
from systems.ai import UtilityAISystem
from systems.projectile_system import ProjectileSystem
from systems.fog_of_war import FogOfWar
from systems.particle_system import ParticleSystem as Particles
from systems.research_manager import ResearchManager
from systems.ai.economy_helpers import find_nearest_dropoff
from managers.save_manager import SaveManager
from managers.sound_manager import SoundManager
from utils.debug_logger import debug_log
from utils.perf_stats import perf_stats


class Game:
    def __init__(self, mode="human_1v1", player_count=2):
        pygame.init()
        if not pygame.font.get_init():
            pygame.font.init()

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
        import random
        ai_personalities = ["rusher", "boomer", "turtle", "balanced"]
        self.mode = mode
        if mode == "ai_spectator":
            configured_players = player_count or AI_ONLY_PLAYER_COUNT
            ai_only = True
        elif mode == "human_1v1":
            configured_players = player_count or 2
            ai_only = False
        else:
            configured_players = AI_ONLY_PLAYER_COUNT if AI_ONLY_MODE else (player_count or NUM_PLAYERS)
            ai_only = AI_ONLY_MODE

        num_players = max(2, min(configured_players, len(PLAYER_COLORS)))
        self.players = []
        for i in range(num_players):
            if i == 0 and not ai_only:
                self.players.append(Player("Human", human=True, color=PLAYER_COLORS[i]))
            else:
                ai_number = i + 1 if ai_only else i
                player = Player(f"AI {ai_number}", human=False, color=PLAYER_COLORS[i])
                player.ai_personality = random.choice(ai_personalities)
                self.players.append(player)
        self.spectator_mode = not any(player.human for player in self.players)
        if self.spectator_mode:
            self.camera.zoom = SPECTATOR_START_ZOOM
        
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
        self.research_manager = ResearchManager(self)
        self.game_state = GameState(self)
        self.gathering_manager = GatheringManager(self)
        self.pathfinder = Pathfinding(self.game_map, self)
        
        # Initialize new systems
        self.movement_system = MovementSystem(self)
        self.collision_system = CollisionSystem(self)
        self.combat_system = CombatSystem(self)
        self.building_system = BuildingSystem(self)
        self.rendering_system = RenderingSystem(self)
        self.worker_task_system = WorkerTaskSystem(self)
        self.unit_watchdog = UnitWatchdog(self)
        self.ai_system = UtilityAISystem(self)
        self.projectile_system = ProjectileSystem(self)
        self.fog_of_war_enabled = SPECTATOR_FOG_OF_WAR if self.spectator_mode else True
        self.fog_of_war = FogOfWar(self)
        self.particles = Particles(self)
        self.sound_manager = SoundManager(self)
        
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
        self.tree_regrowth_enabled = mode != "human_1v1"
        
        # Game over state: None, "victory", or "defeat"
        self.game_over_state = None
        self.winning_player = None
        self.game_paused = False

        # Match statistics (§8.8 balance sim / §8.7 post-match summary):
        # {(player_name, unit_or_building_type): count}
        self.stats_units_trained = {}
        self.stats_buildings_built = {}
        
        # Set up initial game state
        self.game_state.setup_game_objects()
        self.game_map.scale_tiles(self.camera.zoom)
        self.pathfinder.mark_dirty()

        # Everything alive at this point (map, sprites, systems, initial world)
        # is effectively permanent; freezing it keeps it out of GC scans.
        import gc
        gc.collect()
        gc.freeze()
    
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
        # Game over keys take priority
        if self.game_over_state:
            if event.key == pygame.K_r:
                self._restart_game()
                return
            elif event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                self.running = False
                return
        
        if event.key == pygame.K_ESCAPE:
            # Game over takes priority
            if self.game_over_state:
                self.running = False
            # Check if command mode is active first
            elif self.ui_manager.active_command_mode:
                self.ui_manager.clear_command_mode()
            else:
                # Toggle pause
                self.game_paused = not self.game_paused
                if hasattr(self, 'sound_manager') and self.sound_manager:
                    self.sound_manager.play_ui_click()
        elif event.key == pygame.K_F1:
            # Select/cycle idle workers (§7.4)
            self.selection_manager.select_next_idle_worker()
        elif event.key == pygame.K_F3:
            self.debug_overlay = not self.debug_overlay
        elif event.key == pygame.K_F4:
            try:
                self.ai_debug_panel.toggle_visibility()
            except Exception as e:
                debug_log.log(f"ERROR: F4 debug panel crashed: {e}", "GENERAL")
                debug_log.log(traceback.format_exc(), "GENERAL")
        elif event.key == pygame.K_F6:
            self.fog_of_war_enabled = not self.fog_of_war_enabled
            state = "enabled" if self.fog_of_war_enabled else "disabled"
            debug_log.log(f"Fog of war {state}", "GENERAL")
        elif event.key == pygame.K_F5:
            # Save game
            try:
                path = SaveManager.save_game(self, slot=0)
                debug_log.log(f"Game saved to {path}", "GENERAL")
            except Exception as e:
                debug_log.log(f"Save failed: {e}", "GENERAL")
        elif event.key == pygame.K_F9:
            # Load game
            try:
                success, msg = SaveManager.load_game(self, slot=0)
                debug_log.log(f"Load: {msg}", "GENERAL")
            except Exception as e:
                debug_log.log(f"Load failed: {e}", "GENERAL")
                debug_log.log(traceback.format_exc(), "GENERAL")
        elif event.key == pygame.K_LEFTBRACKET:  # [ key - decrease speed
            self.game_speed = max(MIN_GAME_SPEED, self.game_speed - GAME_SPEED_INCREMENT)
            debug_log.log(f"Game speed: {self.game_speed:.1f}x", "GENERAL")
        elif event.key == pygame.K_RIGHTBRACKET:  # ] key - increase speed
            self.game_speed = min(MAX_GAME_SPEED, self.game_speed + GAME_SPEED_INCREMENT)
            debug_log.log(f"Game speed: {self.game_speed:.1f}x", "GENERAL")
        elif event.key == pygame.K_s:
            # Cycle stance for selected combat units
            self._cycle_selected_unit_stances()
        elif event.key == pygame.K_f:
            # Cycle formation type
            formation = self.selection_manager.cycle_formation()
            debug_log.log(f"Formation changed to: {formation}", "GENERAL")
        else:
            # Control groups: 1-9
            key_num = None
            if pygame.K_1 <= event.key <= pygame.K_9:
                key_num = event.key - pygame.K_1 + 1
            elif pygame.K_KP1 <= event.key <= pygame.K_KP9:
                key_num = event.key - pygame.K_KP1 + 1
            
            if key_num:
                keys = pygame.key.get_pressed()
                ctrl_held = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
                shift_held = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
                
                if ctrl_held:
                    # Set control group (Shift+Ctrl = add to group)
                    self.selection_manager.set_control_group(key_num, add=shift_held)
                    debug_log.log(f"Control group {key_num} set", "GENERAL")
                else:
                    # Recall control group; double-tap centers the camera (§7.4)
                    recalled = self.selection_manager.recall_control_group(key_num)
                    if recalled:
                        now = pygame.time.get_ticks()
                        if (
                            getattr(self, "_last_group_recall", None) == key_num
                            and now - getattr(self, "_last_group_recall_time", -10**9) < 450
                        ):
                            self.selection_manager.center_camera_on_selection()
                        self._last_group_recall = key_num
                        self._last_group_recall_time = now
                        debug_log.log(f"Control group {key_num} recalled", "GENERAL")
    
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
    
    def update(self, delta_time_override=None):
        """Update all game systems"""
        perf_stats.begin_frame()
        try:
            # Skip updates when paused or game over
            if self.game_paused or self.game_over_state:
                raw_delta_time = delta_time_override if delta_time_override is not None else self.clock.get_time() / 1000.0
                self.delta_time = raw_delta_time * self.game_speed
                # Still update animations and particles for visual appeal
                if hasattr(self, 'particles') and self.particles:
                    self.particles.update(self.delta_time)
                return
            
            # Apply game speed to delta time
            raw_delta_time = delta_time_override if delta_time_override is not None else self.clock.get_time() / 1000.0
            self.delta_time = raw_delta_time * self.game_speed
            self.frame_counter += 1
            
            # Update input
            self._update_camera_movement()

            # Drain queued path commands first so an AI tick's mass orders
            # spread across frames instead of spiking this one.
            self.pathfinder.process_pending()

            # Assign/update worker tasks before movement, then resolve arrivals after movement.
            self.ai_system.update(self.delta_time)
            self.ai_debug_panel.update(self.delta_time)
            self.worker_task_system.update_pre_movement(self.delta_time)
            
            # Update unit movement and combat
            self.collision_system.begin_frame()
            self._update_units(self.delta_time)
            # Resolve residual unit-unit overlaps (steering avoids most, but
            # spawns/pushes can still compress crowds into deep overlap).
            self.collision_system.separate_overlapping_units()
            self.worker_task_system.update_post_movement(self.delta_time)
            # Shift-queued commands fire as units go idle (§7.4)
            self.selection_manager.drain_command_queues()

            # Update core systems with speed-adjusted delta time
            self.gathering_manager.update(self.delta_time)
            self.building_system.update_construction(self.delta_time)
            self.production_manager.update(self.delta_time)
            self.research_manager.update(self.delta_time)
            self.unit_watchdog.update()
            
            # Update combat system (for both units and buildings)
            self.combat_system.update_combat_units(self.delta_time)
            
            # Update projectiles
            self.projectile_system.update(self.delta_time)
            
            # Update fog of war
            self.fog_of_war.update(self.delta_time)
            
            # Update particles
            self.particles.update(self.delta_time)
            
            # Remove destroyed objects
            self._cleanup_destroyed_objects()
            
            # Check victory/defeat conditions
            self._check_victory_defeat()
            
            # Update camera bounds
            self._update_camera_bounds()
        finally:
            perf_stats.end_frame()
    
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
    
    # Longest distance (world px) a unit may cover in one movement step before
    # substepping kicks in; keeps high game speeds from tunneling units
    # through obstacles (B6). Slow units stay single-step even at 5x.
    MAX_MOVEMENT_STEP_PX = 10.0

    def _update_units(self, delta_time):
        """Update all units using the movement system (substepped per unit)"""
        for unit in self.units:
            step_px = unit.movement_speed * delta_time
            steps = 1 if step_px <= self.MAX_MOVEMENT_STEP_PX else math.ceil(step_px / self.MAX_MOVEMENT_STEP_PX)
            if steps == 1:
                self.movement_system.update_unit_movement(unit, delta_time)
            else:
                sub_dt = delta_time / steps
                for _ in range(steps):
                    self.movement_system.update_unit_movement(unit, sub_dt)
    
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
            self.pathfinder.notify_blocker_removed(building)

        # Remove destroyed construction sites
        destroyed_sites = [site for site in self.construction_sites if site.hp <= 0]
        for site in destroyed_sites:
            site.in_world = False
            self.pathfinder.notify_blocker_removed(site)
        if destroyed_sites:
            self.construction_sites = [site for site in self.construction_sites if site.hp > 0]

        # Remove depleted resources
        depleted_resources = [resource for resource in self.resources if resource.amount_remaining <= 0]
        for resource in depleted_resources:
            debug_log.log(f"Removing depleted {resource.name} resource at ({resource.x:.0f}, {resource.y:.0f})", "GENERAL")
            
            # Clear any workers still targeting this resource
            for unit in self.units:
                targeting = (
                    getattr(unit, 'gathering_target', None) == resource or
                    getattr(unit, 'previous_gathering_target', None) == resource
                )
                if targeting:
                    debug_log.log(f"  Clearing depleted resource from worker at ({unit.x:.0f}, {unit.y:.0f})", "GENERAL")

                    # Push worker away before clearing state
                    dx = unit.x - resource.x
                    dy = unit.y - resource.y
                    distance = math.sqrt(dx * dx + dy * dy)
                    if distance < unit.radius + resource.radius + 10 and distance > 0:
                        push_force = 10
                        unit.x += (dx / distance) * push_force
                        unit.y += (dy / distance) * push_force

                    if getattr(unit, "resource_amount", 0) > 0 and getattr(unit, "resource_type", None):
                        worker_tasks = getattr(self, "worker_task_system", None)
                        if worker_tasks:
                            worker_tasks.cancel(unit)
                        else:
                            unit.path = None
                            unit.path_index = 0
                            unit.path_target = None
                            unit.destination = None

                        unit.is_gathering = False
                        unit.gathering_target = None
                        unit.previous_gathering_target = None
                        unit.is_engaging = False
                        unit.status = "idle"

                        dropoff, _ = find_nearest_dropoff(
                            self,
                            unit.player,
                            unit.resource_type,
                            (unit.x, unit.y),
                        )
                        if dropoff:
                            if worker_tasks:
                                worker_tasks.assign_dropoff(unit, dropoff)
                            else:
                                self.pathfinder.issue_interact(unit, dropoff, "dropoff")
                    else:
                        # Full state wipe so an empty worker becomes truly idle.
                        unit.clear_all_movement_state()
            
            # Track wood resource positions for regrowth
            if resource.name == "wood" and getattr(self, "tree_regrowth_enabled", True):
                if not hasattr(self, '_tree_regrowth'):
                    self._tree_regrowth = []
                self._tree_regrowth.append((resource.x, resource.y, 60.0))  # 60 seconds regrow
            
            # Remove from resources list
            resource.in_world = False
            self.resources.remove(resource)
            self.pathfinder.notify_blocker_removed(resource)

            # Invalidate AI memory cache since resources changed
            if hasattr(self, 'ai_system') and self.ai_system:
                self.ai_system.invalidate_memory_cache()

    def _check_victory_defeat(self):
        """Check if victory or defeat conditions are met"""
        if self.game_over_state:
            return
        
        # Count castles per player
        castles_by_player = {}
        for building in self.buildings:
            if building.name == "castle":
                castles_by_player[building.player] = castles_by_player.get(building.player, 0) + 1
        
        human_players = [p for p in self.players if p.human]
        ai_players = [p for p in self.players if not p.human]

        if not human_players:
            active_players = [p for p in ai_players if castles_by_player.get(p, 0) > 0]
            if len(active_players) <= 1 and len(ai_players) > 1:
                self.winning_player = active_players[0] if active_players else None
                self.game_over_state = "simulation_complete"
                winner_name = self.winning_player.name if self.winning_player else "No player"
                debug_log.log(f"AI simulation complete: {winner_name} remains", "GENERAL")
            return

        human_player = human_players[0]
        
        # Check human defeat (no castle)
        if human_player and castles_by_player.get(human_player, 0) == 0:
            self.game_over_state = "defeat"
            debug_log.log("Game Over: Human player defeated!", "GENERAL")
            return
        
        # Check human victory (all AI castles destroyed)
        if ai_players:
            all_ai_defeated = all(castles_by_player.get(p, 0) == 0 for p in ai_players)
            if all_ai_defeated:
                self.game_over_state = "victory"
                debug_log.log("Game Over: Human player victorious!", "GENERAL")
                return
    
    def _cycle_selected_unit_stances(self):
        """Cycle stance for selected human combat units"""
        from entities.unit import (STANCE_AGGRESSIVE, STANCE_DEFENSIVE, 
                                   STANCE_STAND_GROUND, STANCE_NO_ATTACK)
        
        stance_cycle = [STANCE_AGGRESSIVE, STANCE_DEFENSIVE, STANCE_STAND_GROUND, STANCE_NO_ATTACK]
        
        selected_units = [obj for obj in self.selection_manager.selected_objects
                         if obj in self.units and hasattr(obj, 'player') 
                         and obj.player and obj.player.human and hasattr(obj, 'can_attack_flag') 
                         and obj.can_attack_flag]
        
        for unit in selected_units:
            current_idx = stance_cycle.index(unit.stance) if unit.stance in stance_cycle else 0
            unit.stance = stance_cycle[(current_idx + 1) % len(stance_cycle)]
            unit.stance_home_position = (unit.x, unit.y)
            debug_log.log(f"{unit.name} stance changed to {unit.stance}", "GENERAL")
    
    def _draw_pause_overlay(self):
        """Draw pause overlay"""
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(120)
        self.screen.blit(overlay, (0, 0))
        
        font_large = pygame.font.Font(None, 72)
        font_small = pygame.font.Font(None, 36)
        
        title = font_large.render("PAUSED", True, (255, 255, 255))
        title_rect = title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 40))
        self.screen.blit(title, title_rect)
        
        sub = font_small.render("Press ESC to Resume", True, (200, 200, 200))
        sub_rect = sub.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))
        self.screen.blit(sub, sub_rect)
    
    def _restart_game(self):
        """Restart the game by reinitializing core state"""
        self.game_over_state = None
        self.winning_player = None
        self.worker_task_system = WorkerTaskSystem(self)
        for obj in self.buildings + self.units + self.resources + self.construction_sites:
            obj.in_world = False
        self.buildings.clear()
        self.units.clear()
        self.resources.clear()
        self.construction_sites.clear()
        self.frame_counter = 0
        
        # Reset players resources
        for player in self.players:
            if player.human:
                player.resources = self.game_data.get("starting_resources_human", {"food": 10000, "gold": 10000, "stone": 10000, "wood": 10000}).copy()
            else:
                player.resources = self.game_data.get("starting_resources_ai", {"food": 10000, "gold": 10000, "stone": 10000, "wood": 10000}).copy()
        
        # Reinitialize game state
        self.game_state.setup_game_objects()
        self.pathfinder.mark_dirty()
        self.selection_manager.selected_objects.clear()
        
        # Reset camera
        focus_castle = next((b for b in self.buildings if b.player.human and b.name == "castle"), None)
        if not focus_castle:
            focus_castle = next((b for b in self.buildings if b.name == "castle"), None)
        if focus_castle:
            self.camera.x = (MAP_VIEW_WIDTH / 2) - focus_castle.x * self.camera.zoom
            self.camera.y = (MAP_VIEW_HEIGHT / 2) - focus_castle.y * self.camera.zoom
        
        debug_log.log("Game restarted", "GENERAL")
    
    def _draw_game_over_overlay(self):
        """Draw victory or defeat overlay"""
        if not self.game_over_state:
            return
        
        # Darken screen
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        self.screen.blit(overlay, (0, 0))
        
        # Title
        font_large = pygame.font.Font(None, 72)
        font_small = pygame.font.Font(None, 36)
        
        if self.game_over_state == "victory":
            title_text = "VICTORY!"
            title_color = (0, 255, 0)
        elif self.game_over_state == "simulation_complete":
            winner_name = self.winning_player.name if self.winning_player else "No Player"
            title_text = f"{winner_name} WINS"
            title_color = getattr(self.winning_player, "color", (255, 255, 255)) if self.winning_player else (255, 255, 255)
        else:
            title_text = "DEFEAT"
            title_color = (255, 0, 0)
        
        title_surface = font_large.render(title_text, True, title_color)
        title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 50))
        self.screen.blit(title_surface, title_rect)
        
        # Subtitle
        sub_text = "Press R to Restart  |  Press ESC or Q to Quit"
        sub_surface = font_small.render(sub_text, True, (255, 255, 255))
        sub_rect = sub_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 30))
        self.screen.blit(sub_surface, sub_rect)
    
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
        
        # Draw game over overlay if applicable
        self._draw_game_over_overlay()
        
        # Draw pause overlay
        if self.game_paused and not self.game_over_state:
            self._draw_pause_overlay()
        
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
