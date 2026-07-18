import pygame
import math
import traceback
from core.config import (SCREEN_WIDTH, SCREEN_HEIGHT, MAP_WIDTH, MAP_HEIGHT,
                        CAMERA_SPEED, TILE_WIDTH, TILE_HEIGHT,
                        MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, MINIMAP_WIDTH, 
                        MINIMAP_HEIGHT, NUM_PLAYERS, PLAYER_COLORS, TOP_BAR_HEIGHT,
                        SMART_CURSORS_ENABLED, DEFAULT_GAME_SPEED, MIN_GAME_SPEED,
                        MAX_GAME_SPEED, GAME_SPEED_INCREMENT, AI_ONLY_MODE,
                        AI_ONLY_PLAYER_COUNT, SPECTATOR_REVEALED_DISPLAY,
                        SPECTATOR_START_ZOOM, HUMAN_STARTING_RESOURCES,
                        AI_STARTING_RESOURCES)
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
    def __init__(self, mode="human_1v1", player_count=2, map_size=None):
        pygame.init()
        if not pygame.font.get_init():
            pygame.font.init()

        # Reuse the existing display (it may be exclusive fullscreen — a
        # plain set_mode here would clobber it back to windowed)
        self.screen = pygame.display.get_surface() or \
            pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.map_surface = pygame.Surface((MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT))
        pygame.display.set_caption("RTS Game")
        self.clock = pygame.time.Clock()
        self.running = True

        # Core game components (§7.5: match setup can pick the map size)
        map_w, map_h = map_size if map_size else (MAP_WIDTH, MAP_HEIGHT)
        self.game_map = Map(map_w, map_h, self)
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
        self.fountains = []  # §8.9 neutral healing fountains
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
        from systems.dynamic_events import DynamicEventSystem
        self.dynamic_events = DynamicEventSystem(self)  # §7.5 random_events mutator
        from systems.combat_rules import set_terrain_provider
        set_terrain_provider(self.game_map)  # §8.4 flagged forest cover
        
        # Initialize new systems
        self.movement_system = MovementSystem(self)
        self.collision_system = CollisionSystem(self)
        from systems.fountain_system import FountainSystem
        self.fountain_system = FountainSystem(self)  # §8.9 healing fountain
        self.combat_system = CombatSystem(self)
        self.building_system = BuildingSystem(self)
        self.rendering_system = RenderingSystem(self)
        self.worker_task_system = WorkerTaskSystem(self)
        self.unit_watchdog = UnitWatchdog(self)
        self.ai_system = UtilityAISystem(self)
        self.projectile_system = ProjectileSystem(self)
        # §8.11 fair spectating: fog RULES are always on (AIs must scout —
        # they used to be omniscient in spectator mode and built across the
        # map); spectators get a revealed DISPLAY instead of disabled fog.
        self.fog_of_war_enabled = True
        self.spectator_reveal_display = self.spectator_mode and SPECTATOR_REVEALED_DISPLAY
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
        # Forests regrow (60 s per felled tree, never under a building) — wood
        # is the renewable resource by design (§8.3). Enabled in ALL modes
        # 2026-07-14 (user-reported): human matches used to be the odd one
        # out with regrowth OFF, contradicting the design AND the balance
        # sims (which all run with it on).
        self.tree_regrowth_enabled = True
        
        # Game over state: None, "victory", or "defeat"
        self.game_over_state = None
        self.winning_player = None
        self.game_paused = False

        # Match statistics (§8.8 balance sim / §8.7 post-match summary):
        # {(player_name, unit_or_building_type): count}
        self.stats_units_trained = {}
        self.stats_buildings_built = {}
        self.stats_tower_damage = {}  # {player_name: damage dealt by watchtowers}
        self.stats_resources_gathered = {}  # {player_name: cumulative gathered}
        self.sim_time_elapsed = 0.0   # game-time seconds since match start
        # Income-rate HUD (§8.3): human player's recent income events,
        # {resource: [(sim_time, amount), ...]} pruned as it's read
        self.income_events = {}

        # Match mutators (§7.5): optional togglable rules picked at setup.
        # "double_resources" | "no_towers" | "revealed_map"
        self.mutators = set()

        # Rebindable hotkeys (§8.6): defaults + keybindings.json overrides
        from core.keybindings import KeyBindings
        self.keybindings = KeyBindings()

        # Victory condition (§7.5): "annihilation" (default), "economic"
        # (first to gather ECONOMIC_VICTORY_TARGET total), or "timed"
        # (highest score when TIMED_VICTORY_MINUTES elapse). Castle loss
        # always eliminates regardless of mode.
        self.victory_condition = "annihilation"
        
        # Set up initial game state
        self.game_state.setup_game_objects()
        self.game_map.scale_tiles(self.camera.zoom)
        self.pathfinder.mark_dirty()

        # Onboarding tips for new players (§8.7) — needs players to exist
        self._init_onboarding()

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
            # Back out of building/wall placement before anything else — this
            # also aborts an in-progress wall drag. Nothing is charged until
            # release, so it's a zero-cost bail-out (Esc used to pause here).
            elif self.building_system.building_placement_mode:
                self.building_system.cancel_building_placement()
            # Check if command mode is active first
            elif self.ui_manager.active_command_mode:
                self.ui_manager.clear_command_mode()
            else:
                # Toggle pause
                self.game_paused = not self.game_paused
                if hasattr(self, 'sound_manager') and self.sound_manager:
                    self.sound_manager.play_ui_click()
        elif self.game_paused and self.keybindings.matches("open_settings", event.key):
            # In-game settings from the pause screen (§8.5): volumes apply
            # live; resolution still needs a restart
            self._open_settings_from_pause()
        elif self.ui_manager.command_card.handle_hotkey(event.key):
            # Command-card grid hotkey (§8.2.1): build/produce/research/army
            # action on the current selection; unoccupied slots fall through
            pass
        elif self.keybindings.matches("idle_worker", event.key):
            # Select/cycle idle workers (§7.4)
            self.selection_manager.select_next_idle_worker()
        elif self.keybindings.matches("select_all_production", event.key):
            # Select all own military-production buildings (§8.2.1 Phase C)
            self.selection_manager.select_all_military_production()
        elif self.keybindings.matches("jump_to_base", event.key):
            # Jump camera to own base (§8.6)
            self._jump_to_base()
        elif self.keybindings.matches("cycle_army", event.key):
            # Cycle through own military units (§8.6)
            self._cycle_army_unit()
        elif self.keybindings.matches("path_overlay", event.key):
            self.debug_overlay = not self.debug_overlay
        elif self.keybindings.matches("ai_debug_panel", event.key):
            try:
                self.ai_debug_panel.toggle_visibility()
            except Exception as e:
                debug_log.log(f"ERROR: F4 debug panel crashed: {e}", "GENERAL")
                debug_log.log(traceback.format_exc(), "GENERAL")
        elif self.keybindings.matches("toggle_fog", event.key):
            self.fog_of_war_enabled = not self.fog_of_war_enabled
            state = "enabled" if self.fog_of_war_enabled else "disabled"
            debug_log.log(f"Fog of war {state}", "GENERAL")
            # Visible toast so this debug toggle is never a silent/mysterious
            # change (e.g. an accidental F6 while reaching for F1).
            try:
                self.ui_manager.add_alert(f"Fog of war {state} (F6)")
            except Exception:
                pass
        elif self.keybindings.matches("quick_save", event.key):
            try:
                path = SaveManager.save_game(self, slot=0)
                debug_log.log(f"Game saved to {path}", "GENERAL")
                if self.ui_manager:
                    self.ui_manager.add_alert("Game saved (Slot 1)")
            except Exception as e:
                debug_log.log(f"Save failed: {e}", "GENERAL")
                if self.ui_manager:
                    self.ui_manager.add_alert("Save failed")
        elif self.keybindings.matches("quick_load", event.key):
            try:
                success, msg = SaveManager.load_game(self, slot=0)
                debug_log.log(f"Load: {msg}", "GENERAL")
                if self.ui_manager:
                    self.ui_manager.add_alert("Game loaded" if success else "No save in Slot 1")
            except Exception as e:
                debug_log.log(f"Load failed: {e}", "GENERAL")
                debug_log.log(traceback.format_exc(), "GENERAL")
                if self.ui_manager:
                    self.ui_manager.add_alert("Load failed")
        elif self.keybindings.matches("speed_down", event.key):
            self.game_speed = max(MIN_GAME_SPEED, self.game_speed - GAME_SPEED_INCREMENT)
            debug_log.log(f"Game speed: {self.game_speed:.1f}x", "GENERAL")
        elif self.keybindings.matches("speed_up", event.key):
            self.game_speed = min(MAX_GAME_SPEED, self.game_speed + GAME_SPEED_INCREMENT)
            debug_log.log(f"Game speed: {self.game_speed:.1f}x", "GENERAL")
        elif self.keybindings.matches("cycle_stance", event.key):
            # Cycle stance for selected combat units
            self._cycle_selected_unit_stances()
        elif self.keybindings.matches("toggle_gates", event.key):
            # Toggle selected own gates open/closed (§8.10)
            self._toggle_selected_gates()
        elif self.keybindings.matches("cycle_formation", event.key):
            # Cycle formation type
            formation = self.selection_manager.cycle_formation()
            debug_log.log(f"Formation changed to: {formation}", "GENERAL")
        elif self.keybindings.matches("camera_bookmark_set", event.key):
            self._set_camera_bookmark()
        elif self.keybindings.matches("camera_bookmark_jump", event.key):
            self._jump_camera_bookmark()
        elif self.keybindings.matches("toggle_event_log", event.key):
            self.ui_manager.toggle_event_log()
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
        # While paused the pause menu owns the mouse — no gameplay clicks
        if self.game_paused and not self.game_over_state:
            if event.button == 1:
                self._handle_pause_menu_click(pygame.mouse.get_pos())
            return

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
                        # Wall pieces start a drag; everything else places now
                        self.building_system.handle_placement_mouse_down(mouse_pos)
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
                # Right-click on the command card (cancel queued units etc.)
                if self.ui_manager.handle_right_click(mouse_pos):
                    return
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
    
    def _handle_mouse_up(self, event):
        """Handle mouse button up events"""
        if event.button == 1:  # Left click
            if self.minimap.dragging:
                self.minimap.handle_release()
            elif self.building_system.wall_drag_active:
                self.building_system.finish_wall_drag(pygame.mouse.get_pos())
            else:
                self.selection_manager.handle_left_release(pygame.mouse.get_pos())
    
    def _update_cursor_for_context(self, mouse_pos):
        """Update cursor appearance based on target validity or smart cursor logic"""
        # Skip if mouse is over UI areas
        if (mouse_pos[0] > SCREEN_WIDTH - MINIMAP_WIDTH or  # Right panel/minimap
            mouse_pos[1] < TOP_BAR_HEIGHT):  # Top bar
            self.selection_manager.hovered_object = None
            return

        # Get world position
        world_pos = self.screen_to_world(mouse_pos[0], mouse_pos[1])

        # Check what object is at this position
        clicked_object = self.selection_manager._get_object_at_position(world_pos)
        # §7.4 readability: remember what's under the cursor for the hover marker
        self.selection_manager.hovered_object = clicked_object
        
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
            self._update_mouse_confinement()

            # Music playlist advance runs even while paused/game-over (§8.5).
            # Mood follows recent human-involved combat; game over plays the
            # victory/defeat stinger once (when the files exist).
            if self.sound_manager:
                if self.game_over_state and not getattr(self, "_stinger_played", False):
                    self._stinger_played = True
                    self.sound_manager.play_game_over(
                        self.game_over_state in ("victory", "simulation_complete"))
                in_combat = getattr(self, "_human_combat_until", 0.0) > self.sim_time_elapsed
                self.sound_manager.update_music(in_combat)

            # Skip updates when paused or game over
            if self.game_paused or self.game_over_state:
                raw_delta_time = delta_time_override if delta_time_override is not None else self.clock.get_time() / 1000.0
                self.delta_time = raw_delta_time * self.game_speed
                # Still update animations and particles for visual appeal
                if hasattr(self, 'particles') and self.particles:
                    self.particles.update(self.delta_time)
                if getattr(self, 'floating_ui', None):
                    self.floating_ui.update_notifications(self.delta_time)
                return
            
            # Apply game speed to delta time
            raw_delta_time = delta_time_override if delta_time_override is not None else self.clock.get_time() / 1000.0
            self.delta_time = raw_delta_time * self.game_speed
            self.frame_counter += 1
            self.sim_time_elapsed += self.delta_time
            
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
            self.dynamic_events.update(self.delta_time)
            self.building_system.update_construction(self.delta_time)
            self.production_manager.update(self.delta_time)
            self.research_manager.update(self.delta_time)
            self.unit_watchdog.update()
            
            # Update combat system (for both units and buildings)
            self.combat_system.update_combat_units(self.delta_time)

            # §8.9 healing fountain regeneration
            self.fountain_system.update(self.delta_time)
            
            # Update projectiles
            self.projectile_system.update(self.delta_time)
            
            # Update fog of war
            self.fog_of_war.update(self.delta_time)
            
            # Update particles
            self.particles.update(self.delta_time)

            # Expire floating notifications sim-side: draw used to own this,
            # so headless runs (benchmark, balance sim) never drained the list
            self.floating_ui.update_notifications(self.delta_time)

            # Remove destroyed objects
            self._cleanup_destroyed_objects()
            
            # Check victory/defeat conditions
            self._check_victory_defeat()

            # Low-resource alerts for the human player (§7.4)
            self._check_low_resources(self.delta_time)

            # Onboarding tips for new players (§8.7)
            self._update_onboarding()

            # Scouting intel: first sighting of enemy types (§7.2)
            self._check_scouting_intel(self.delta_time)

            # Update camera bounds
            self._update_camera_bounds()
        finally:
            perf_stats.end_frame()
    
    # Buildings a mutator forbids for everyone this match (§7.5)
    MUTATOR_DISABLED_BUILDINGS = {"no_towers": {"watchtower"}}

    def is_building_disabled(self, building_name):
        """Is this building forbidden by an active mutator?"""
        for mutator in self.mutators:
            if building_name in self.MUTATOR_DISABLED_BUILDINGS.get(mutator, ()):
                return True
        return False

    COMBAT_MOOD_LINGER_S = 10.0  # combat music holds this long past the last hit

    def notify_human_combat(self, attacker, target):
        """§8.5 music mood: remember that the human is fighting (either
        side of a damage event) so the combat playlist takes over."""
        for obj in (attacker, target):
            player = getattr(obj, "player", None)
            if player is not None and getattr(player, "human", False):
                self._human_combat_until = self.sim_time_elapsed + self.COMBAT_MOOD_LINGER_S
                return

    INCOME_WINDOW_SECS = 15.0  # rolling window for the +X/s HUD readout

    def record_income(self, player, resource_type, amount):
        """Log an income event for the +X/s HUD (§8.3). Human player only."""
        if not getattr(player, "human", False) or amount <= 0:
            return
        self.income_events.setdefault(resource_type, []).append(
            (self.sim_time_elapsed, float(amount))
        )

    def income_rate(self, resource_type):
        """Average income per second over the rolling window."""
        events = self.income_events.get(resource_type)
        if not events:
            return 0.0
        cutoff = self.sim_time_elapsed - self.INCOME_WINDOW_SECS
        fresh = [e for e in events if e[0] >= cutoff]
        self.income_events[resource_type] = fresh
        return sum(amount for _t, amount in fresh) / self.INCOME_WINDOW_SECS

    # §8.7 onboarding: timed tips during a new player's first matches
    ONBOARDING_MAX_MATCHES = 3  # stop tipping once the profile shows experience
    ONBOARDING_HINTS = (
        (15, "Right-click a resource to send workers gathering"),
        (45, "Use the right panel's build menu to place buildings"),
        (80, "F1 selects idle workers; Ctrl+1 saves a control group"),
        (120, "Select a production building and right-click to set its rally"),
        (160, "Press L for the event log, B/N for camera bookmarks"),
        (200, "S cycles unit stances; [ and ] change game speed"),
    )

    def _init_onboarding(self):
        """Queue timed tips if the profile says this player is still new."""
        self._onboarding_queue = []
        if not any(getattr(p, "human", False) for p in self.players):
            return
        try:
            from core.profile import Profile

            if Profile().stats["matches_played"] < self.ONBOARDING_MAX_MATCHES:
                self._onboarding_queue = list(self.ONBOARDING_HINTS)
        except Exception as e:
            debug_log.log(f"Onboarding init failed: {e}", "GENERAL")

    def _update_onboarding(self):
        queue = getattr(self, "_onboarding_queue", None)
        if queue and self.sim_time_elapsed >= queue[0][0]:
            _due, hint = queue.pop(0)
            self.ui_manager.add_alert(f"Tip: {hint}")

    # §7.2 scouting payoff: buildings whose first sighting is real intel
    INTEL_BUILDINGS = ("castle", "barracks", "stable", "siege_workshop",
                       "blacksmith", "watchtower")

    def _check_scouting_intel(self, delta_time):
        """First time the human SEES each enemy unit type / key building,
        toast it (§7.2). Fog-gated: intel is earned by scouting, and with
        fog disabled everything is visible so there's nothing to reveal."""
        self._intel_timer = getattr(self, "_intel_timer", 0.0) + delta_time
        if self._intel_timer < 1.0:
            return
        self._intel_timer = 0.0
        human = self.players[0] if self.players else None
        if human is None or not getattr(human, "human", False):
            return
        fog = getattr(self, "fog_of_war", None)
        if fog is None or not fog.enabled:
            return
        spotted = getattr(self, "_spotted_enemy_types", None)
        if spotted is None:
            spotted = self._spotted_enemy_types = set()

        from systems.ai.utility.context import MILITARY_NAMES

        for unit in self.units:
            if unit.player is human or unit.hp <= 0 or unit.name not in MILITARY_NAMES:
                continue
            if unit.name in spotted or not fog.is_visible(human, unit.x, unit.y):
                continue
            spotted.add(unit.name)
            self.ui_manager.add_alert(f"Enemy {unit.name} spotted!", (unit.x, unit.y))

        for building in self.buildings:
            if building.player is human or building.player is None or building.hp <= 0:
                continue
            if building.name not in self.INTEL_BUILDINGS:
                continue
            key = (building.player.name, building.name)
            if key in spotted or not fog.is_visible(human, building.x, building.y):
                continue
            spotted.add(key)
            label = building.name.replace("_", " ")
            self.ui_manager.add_alert(f"Enemy {label} located!", (building.x, building.y))

    LOW_RESOURCE_THRESHOLD = 25   # below the cheapest common purchase
    LOW_RESOURCE_ALERT_SECS = 30  # per-resource re-alert throttle

    def _check_low_resources(self, delta_time):
        """Toast when a human resource stockpile dips low (§7.4). Checked
        once per sim second; alerts only on a real dip (not while staying
        low), throttled per resource."""
        self._low_resource_timer = getattr(self, "_low_resource_timer", 0.0) + delta_time
        if self._low_resource_timer < 1.0:
            return
        self._low_resource_timer = 0.0
        player = self.players[0] if self.players else None
        if player is None or not getattr(player, "human", False):
            return
        previous = getattr(self, "_last_resource_snapshot", {})
        for resource, amount in player.resources.items():
            was = previous.get(resource, amount)
            if amount < self.LOW_RESOURCE_THRESHOLD <= was:
                self.ui_manager.add_alert(
                    f"Low on {resource}!",
                    throttle_key=f"low_{resource}",
                    throttle_ms=self.LOW_RESOURCE_ALERT_SECS * 1000,
                )
        self._last_resource_snapshot = dict(player.resources)

    # §8.2 edge scroll: 14 px was a sliver — the cursor had to sit in a
    # near-invisible band for anything to happen (user-reported). 32 px is a
    # comfortable target, and speed ramps with penetration so the effect
    # fades in instead of snapping on at an exact pixel line.
    EDGE_SCROLL_MARGIN = 32
    EDGE_SCROLL_MIN_FACTOR = 0.45  # speed at the inner rim of the band

    def _update_mouse_confinement(self):
        """Confine the OS cursor to the window while a match is live (§8.2,
        user-reported: on an ultrawide the cursor sails past the window edge
        and edge scroll never fires). Standard RTS behavior — grab during
        play, release on pause/game-over so menus and other monitors work.
        SDL drops the grab automatically on alt-tab and re-asserts it when
        the window regains focus. Human matches only; headless/spectator
        sims never grab."""
        # Keyboard focus, not mouse focus: mouse focus flickers off when the
        # cursor presses the bottom screen edge (see edge-scroll note), and a
        # dropped grab there would invite the taskbar in mid-battle.
        want_grab = (self.mode == "human_1v1"
                     and not self.game_paused
                     and not self.game_over_state
                     and pygame.key.get_focused())
        try:
            if pygame.event.get_grab() != want_grab:
                pygame.event.set_grab(want_grab)
        except pygame.error:
            pass  # dummy video driver

    def _update_camera_movement(self):
        """Update camera movement from keyboard input + edge scrolling (§8.6).

        A WASD key stops panning while it maps to an occupied command-card
        slot (§8.2.1 grid hotkeys); arrows and edge-scroll always pan.
        """
        keys = pygame.key.get_pressed()
        card = self.ui_manager.command_card
        if keys[pygame.K_LEFT] or (keys[pygame.K_a] and not card.consumes_key(pygame.K_a)):
            self.camera.move(dx=CAMERA_SPEED)
        if keys[pygame.K_RIGHT] or (keys[pygame.K_d] and not card.consumes_key(pygame.K_d)):
            self.camera.move(dx=-CAMERA_SPEED)
        if keys[pygame.K_UP] or (keys[pygame.K_w] and not card.consumes_key(pygame.K_w)):
            self.camera.move(dy=CAMERA_SPEED)
        if keys[pygame.K_DOWN] or (keys[pygame.K_s] and not card.consumes_key(pygame.K_s)):
            self.camera.move(dy=-CAMERA_SPEED)

        # Edge scroll when the mouse hugs the window border. Speed ramps from
        # EDGE_SCROLL_MIN_FACTOR at the band's inner rim to full CAMERA_SPEED
        # at the window edge. Measured against the real window size, not the
        # config constants, so other resolutions keep working.
        #
        # KEYBOARD focus gate on purpose: pressing the cursor against the
        # bottom screen edge can flick SDL's MOUSE focus off for a frame
        # (Windows probes the auto-hide taskbar there), which killed edge
        # scroll exactly on the bottom-most pixel (user-reported). Keyboard
        # focus stays put while the window is active.
        if pygame.key.get_focused():
            mouse_x, mouse_y = pygame.mouse.get_pos()
            margin = self.EDGE_SCROLL_MARGIN
            win_w, win_h = self.screen.get_width(), self.screen.get_height()
            # Clamp into the surface and anchor the far bands on the LAST
            # reachable pixel (size-1): scaled displays can report the border
            # row at or past the surface size, and the boundary row must
            # always scroll.
            mouse_x = max(0, min(mouse_x, win_w - 1))
            mouse_y = max(0, min(mouse_y, win_h - 1))

            def edge_speed(depth):
                fraction = max(0.0, min(1.0, depth / margin))
                factor = self.EDGE_SCROLL_MIN_FACTOR + (1 - self.EDGE_SCROLL_MIN_FACTOR) * fraction
                return CAMERA_SPEED * factor

            if mouse_x <= margin:
                self.camera.move(dx=edge_speed(margin - mouse_x))
            elif mouse_x >= win_w - 1 - margin:
                self.camera.move(dx=-edge_speed(mouse_x - (win_w - 1 - margin)))
            if mouse_y <= margin:
                self.camera.move(dy=edge_speed(margin - mouse_y))
            elif mouse_y >= win_h - 1 - margin:
                self.camera.move(dy=-edge_speed(mouse_y - (win_h - 1 - margin)))

    def _center_camera_on(self, x, y):
        self.camera.x = -x * self.camera.zoom + MAP_VIEW_WIDTH / 2
        self.camera.y = -y * self.camera.zoom + MAP_VIEW_HEIGHT / 2

    MAX_CAMERA_BOOKMARKS = 4

    def _set_camera_bookmark(self):
        """Save the current camera view into a rotating slot (§8.6)."""
        bookmarks = getattr(self, "camera_bookmarks", None)
        if bookmarks is None:
            bookmarks = self.camera_bookmarks = []
        view = (self.camera.x, self.camera.y, self.camera.zoom)
        bookmarks.append(view)
        if len(bookmarks) > self.MAX_CAMERA_BOOKMARKS:
            bookmarks.pop(0)
        self._camera_bookmark_cursor = len(bookmarks) - 1
        if getattr(self, "ui_manager", None):
            self.ui_manager.add_alert(f"Camera bookmark {len(bookmarks)} set")

    def _jump_camera_bookmark(self):
        """Cycle the camera through saved bookmarks (§8.6)."""
        bookmarks = getattr(self, "camera_bookmarks", None)
        if not bookmarks:
            return
        cursor = (getattr(self, "_camera_bookmark_cursor", -1) + 1) % len(bookmarks)
        self._camera_bookmark_cursor = cursor
        x, y, zoom = bookmarks[cursor]
        self.camera.zoom = zoom
        self.camera.x, self.camera.y = x, y

    def _jump_to_base(self):
        """Center the camera on the (human) player's castle (§8.6)."""
        human = next((p for p in self.players if p.human), None)
        castle = next(
            (b for b in self.buildings if b.name == "castle" and (human is None or b.player is human)),
            None,
        )
        if castle:
            self._center_camera_on(castle.x, castle.y)

    def _cycle_army_unit(self):
        """Select and center the next military unit (§8.6)."""
        human = next((p for p in self.players if p.human), None)
        if human is None:
            return
        military = [
            u for u in self.units
            if u.player is human and u.name != "worker" and u.hp > 0
        ]
        if not military:
            return
        self._army_cycle_index = (getattr(self, "_army_cycle_index", -1) + 1) % len(military)
        unit = military[self._army_cycle_index]
        self.selection_manager._clear_all_selections()
        unit.selected = True
        self.selection_manager.selected_objects.append(unit)
        self._center_camera_on(unit.x, unit.y)
    
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
            # Drop the razed foundation from anyone attacking it — unit and
            # building deaths already do this; sites didn't, so attackers
            # "engaged" a removed object forever (§8.11 frozen-target family).
            for unit in self.units:
                if getattr(unit, 'current_target', None) is site:
                    unit.current_target = None
                    unit.is_engaging = False
                    unit.in_combat = False
                    if unit.status in ("attack", "run") and not getattr(unit, 'destination', None):
                        unit.status = "idle"
        if destroyed_sites:
            self.construction_sites = [site for site in self.construction_sites if site.hp > 0]

        # Remove depleted resources
        depleted_resources = [resource for resource in self.resources if resource.amount_remaining <= 0]
        for resource in depleted_resources:
            debug_log.log(f"Removing depleted {resource.name} resource at ({resource.x:.0f}, {resource.y:.0f})", "GENERAL")
            
            # Clear any workers still targeting this resource
            worker_tasks = getattr(self, "worker_task_system", None)
            for unit in self.units:
                targeting = (
                    getattr(unit, 'gathering_target', None) == resource or
                    getattr(unit, 'previous_gathering_target', None) == resource
                )
                if targeting:
                    # §8.13.1: a worker the task system OWNS needs no rescue —
                    # its task still holds kind="gather" + the depleted node,
                    # and the drop-off completion path continues it onto a
                    # nearby node. The cancel+reassign below laundered that
                    # task into kind="dropoff"/resource=None, which is why
                    # human workers idled after every depletion (the AI's
                    # idle-scan re-tasked its own, hiding the bug).
                    if worker_tasks and worker_tasks.owns(unit):
                        continue
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

    def _score(self, player):
        """Timed-victory score: economy + production achievements (§7.5)."""
        gathered = self.stats_resources_gathered.get(player.name, 0)
        trained = sum(v for (name, _t), v in self.stats_units_trained.items() if name == player.name)
        built = sum(v for (name, _t), v in self.stats_buildings_built.items() if name == player.name)
        army = sum(1 for u in self.units if u.player is player and u.name != "worker")
        return gathered + trained * 20 + built * 50 + army * 30

    def _declare_winner(self, winner):
        """End the match with a winner under a non-annihilation condition."""
        self.winning_player = winner
        humans = [p for p in self.players if p.human]
        if not humans:
            self.game_over_state = "simulation_complete"
        elif winner is humans[0]:
            self.game_over_state = "victory"
        else:
            self.game_over_state = "defeat"
        debug_log.log(f"Victory ({self.victory_condition}): {winner.name}", "GENERAL")
        self._record_match_result()

    def _record_match_result(self):
        """Fold a finished human match into the persistent profile (§8.7).
        Idempotent: the first game-over records, replays/re-checks don't."""
        if getattr(self, "_profile_recorded", False):
            return
        if self.game_over_state not in ("victory", "defeat"):
            return
        humans = [p for p in self.players if p.human]
        if not humans:
            return
        self._profile_recorded = True
        try:
            from core.profile import Profile

            profile = Profile()
            unlocked = profile.record_match(self, humans[0], self.game_over_state == "victory")
            for _ach_id, title in unlocked:
                if getattr(self, "ui_manager", None):
                    self.ui_manager.add_alert(f"Achievement unlocked: {title}")
                debug_log.log(f"Achievement unlocked: {title}", "GENERAL")
        except Exception as e:
            debug_log.log(f"Profile recording failed: {e}", "GENERAL")

    def _check_special_victory(self):
        """Economic / timed victory checks (§7.5); annihilation always applies."""
        from core.config import ECONOMIC_VICTORY_TARGET, TIMED_VICTORY_MINUTES

        if self.victory_condition == "economic":
            for player in self.players:
                if self.stats_resources_gathered.get(player.name, 0) >= ECONOMIC_VICTORY_TARGET:
                    self._declare_winner(player)
                    return
        elif self.victory_condition == "timed":
            if self.sim_time_elapsed >= TIMED_VICTORY_MINUTES * 60:
                self._declare_winner(max(self.players, key=self._score))

    def _player_can_continue(self, player, castle_count):
        """§8.12: losing the castle is no longer instant elimination — the
        castle is rebuildable, so a player stays in the game while they hold
        a castle, a castle construction site, or any surviving worker
        (the comeback path). Out = none of the three."""
        if castle_count > 0:
            return True
        for site in self.construction_sites:
            if site.player is player and site.building_name == "castle":
                return True
        for unit in self.units:
            if unit.player is player and unit.name == "worker" and unit.hp > 0:
                return True
        # §8.9: garrisoned workers are out of game.units but still alive
        for building in self.buildings:
            if building.player is player:
                for unit in getattr(building, "garrison", ()):
                    if unit.name == "worker" and unit.hp > 0:
                        return True
        return False

    def _check_victory_defeat(self):
        """Check if victory or defeat conditions are met"""
        if self.game_over_state:
            return
        if self.victory_condition != "annihilation":
            self._check_special_victory()
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
            active_players = [
                p for p in ai_players
                if self._player_can_continue(p, castles_by_player.get(p, 0))
            ]
            if len(active_players) <= 1 and len(ai_players) > 1:
                self.winning_player = active_players[0] if active_players else None
                self.game_over_state = "simulation_complete"
                winner_name = self.winning_player.name if self.winning_player else "No player"
                debug_log.log(f"AI simulation complete: {winner_name} remains", "GENERAL")
            return

        human_player = human_players[0]

        # Check human defeat (no castle, no castle site, no workers left)
        if human_player and not self._player_can_continue(
                human_player, castles_by_player.get(human_player, 0)):
            self.game_over_state = "defeat"
            debug_log.log("Game Over: Human player defeated!", "GENERAL")
            self._record_match_result()
            return

        # Check human victory (every AI knocked out for good)
        if ai_players:
            all_ai_defeated = all(
                not self._player_can_continue(p, castles_by_player.get(p, 0))
                for p in ai_players
            )
            if all_ai_defeated:
                self.game_over_state = "victory"
                debug_log.log("Game Over: Human player victorious!", "GENERAL")
                self._record_match_result()
                return
    
    def _toggle_selected_gates(self):
        """Open/close selected own gates; open gates stop blocking nav+collision."""
        for obj in self.selection_manager.selected_objects:
            if not getattr(obj, "is_gate", False):
                continue
            if not (obj.player and obj.player.human):
                continue
            now_open = obj.toggle_gate()
            if now_open:
                self.pathfinder.notify_blocker_removed(obj)
            else:
                self.pathfinder.notify_blocker_added(obj)
            debug_log.log(f"Gate {'opened' if now_open else 'closed'}", "GENERAL")

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
    
    PAUSE_OPTIONS = [
        ("Resume", "resume"),
        ("Save / Load", "save_load"),
        ("Settings", "settings"),
        ("Help", "help"),
        ("Quit to Menu", "quit_to_menu"),
    ]

    def _pause_option_rect(self, index):
        panel = self._pause_panel_rect()
        return pygame.Rect(panel.centerx - 150, panel.y + 84 + index * 54, 300, 44)

    def _pause_panel_rect(self):
        height = 84 + len(self.PAUSE_OPTIONS) * 54 + 52
        return pygame.Rect(SCREEN_WIDTH // 2 - 190, (SCREEN_HEIGHT - height) // 2,
                           380, height)

    def _draw_pause_overlay(self):
        """The in-game pause menu (§8.2 menu polish): dim the battlefield,
        then a themed panel with clickable options."""
        from screens import theme

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(140)
        self.screen.blit(overlay, (0, 0))

        panel = self._pause_panel_rect()
        theme.draw_panel(self.screen, panel)

        font_title = pygame.font.Font(None, 56)
        shadow = font_title.render("Paused", True, theme.TITLE_SHADOW)
        title = font_title.render("Paused", True, theme.TITLE_COLOR)
        title_rect = title.get_rect(center=(panel.centerx, panel.y + 44))
        self.screen.blit(shadow, title_rect.move(2, 2))
        self.screen.blit(title, title_rect)

        font_option = pygame.font.Font(None, 36)
        mouse_pos = pygame.mouse.get_pos()
        for i, (label, _action) in enumerate(self.PAUSE_OPTIONS):
            rect = self._pause_option_rect(i)
            theme.draw_action_row(self.screen, rect, label,
                                  rect.collidepoint(mouse_pos), font_option,
                                  primary=(label == "Resume"))

        theme.draw_hint(self.screen, "Esc resumes · O opens Settings",
                        y=panel.bottom - 26)

    def _handle_pause_menu_click(self, mouse_pos):
        """Left click on the pause menu. Gameplay clicks are blocked while
        paused — the menu owns the screen."""
        for i, (_label, action) in enumerate(self.PAUSE_OPTIONS):
            if not self._pause_option_rect(i).collidepoint(mouse_pos):
                continue
            if self.sound_manager:
                self.sound_manager.play_ui_click()
            if action == "resume":
                self.game_paused = False
            elif action == "save_load":
                self._open_save_load_from_pause()
            elif action == "settings":
                self._open_settings_from_pause()
            elif action == "help":
                from core.help_launcher import open_help

                open_help()  # field manual in the browser; game stays paused
            elif action == "quit_to_menu":
                self.game_paused = False
                self.running = False  # back to main.py's menu loop
            return

    def _open_settings_from_pause(self):
        """Run the settings screen over the paused game and live-apply the
        audio settings (music/SFX volume, mute) and a fullscreen toggle on
        return (§8.5); resolution still needs a restart."""
        from screens.settings_menu import SettingsMenu

        settings = SettingsMenu(self.screen).run()
        settings.apply_audio(self)
        self.screen = settings.create_display((SCREEN_WIDTH, SCREEN_HEIGHT))

    def _open_save_load_from_pause(self):
        """Multi-slot Save / Load over the paused game. Saving writes the
        chosen slot in place; loading restores it into the running match and
        unpauses. (Loading a save from a different map size reuses the current
        terrain — the known save/load gap.)"""
        from screens.save_load_menu import SaveLoadScreen

        slot = SaveLoadScreen(self.screen, game=self).run()
        if slot is not None:
            try:
                success, msg = SaveManager.load_game(self, slot=slot)
                if self.ui_manager:
                    self.ui_manager.add_alert("Game loaded" if success else "Load failed")
            except Exception as e:
                debug_log.log(f"Load failed: {e}", "GENERAL")
            self.game_paused = False
    
    def _restart_game(self):
        """Restart the game by reinitializing core state"""
        self.game_over_state = None
        self.winning_player = None
        self._stinger_played = False
        self._human_combat_until = 0.0
        self.worker_task_system = WorkerTaskSystem(self)
        for obj in self.buildings + self.units + self.resources + self.construction_sites + self.fountains:
            obj.in_world = False
        self.buildings.clear()
        self.units.clear()
        self.resources.clear()
        self.construction_sites.clear()
        self.fountains.clear()
        self.frame_counter = 0
        self.sim_time_elapsed = 0.0
        self.stats_units_trained = {}
        self.stats_buildings_built = {}
        self.stats_tower_damage = {}
        
        # Reset players resources
        for player in self.players:
            if player.human:
                player.resources = self.game_data.get("starting_resources_human", HUMAN_STARTING_RESOURCES).copy()
            else:
                player.resources = self.game_data.get("starting_resources_ai", AI_STARTING_RESOURCES).copy()
        
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
        title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 160))
        self.screen.blit(title_surface, title_rect)

        # Post-match summary (§8.7): per-player stats from the match counters
        font_stats = pygame.font.Font(None, 28)
        minutes = int(self.sim_time_elapsed // 60)
        seconds = int(self.sim_time_elapsed % 60)
        header = f"Match length: {minutes}:{seconds:02d} (game time)"
        header_surface = font_small.render(header, True, (200, 200, 200))
        self.screen.blit(header_surface, header_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 105)))

        columns = ["Player", "Units trained", "Buildings", "Army left", "Tower dmg"]
        col_x = [SCREEN_WIDTH // 2 - 330, SCREEN_WIDTH // 2 - 110, SCREEN_WIDTH // 2 + 30, SCREEN_WIDTH // 2 + 150, SCREEN_WIDTH // 2 + 260]
        y = SCREEN_HEIGHT // 2 - 70
        for i, column in enumerate(columns):
            col_surface = font_small.render(column, True, (150, 150, 150))
            self.screen.blit(col_surface, (col_x[i], y))
        y += 28
        for player in self.players:
            trained = sum(v for (name, _t), v in self.stats_units_trained.items() if name == player.name)
            built = sum(v for (name, _t), v in self.stats_buildings_built.items() if name == player.name)
            army = sum(1 for u in self.units if u.player is player and u.name != "worker")
            tower_damage = int(self.stats_tower_damage.get(player.name, 0))
            label = player.name + (" (you)" if player.human else "")
            values = [label, str(trained), str(built), str(army), str(tower_damage)]
            for i, value in enumerate(values):
                color = player.color if i == 0 else (230, 230, 230)
                cell_surface = font_stats.render(value, True, color)
                self.screen.blit(cell_surface, (col_x[i], y))
            y += 30

        # Subtitle
        sub_text = "Press R to Restart  |  Press ESC or Q to Quit"
        sub_surface = font_small.render(sub_text, True, (255, 255, 255))
        sub_rect = sub_surface.get_rect(center=(SCREEN_WIDTH // 2, y + 30))
        self.screen.blit(sub_surface, sub_rect)
    
    def _update_camera_bounds(self):
        """Update camera bounds to keep it within map limits"""
        map_width_pixels = self.game_map.width * TILE_WIDTH * 0.75 * self.camera.zoom
        map_height_pixels = self.game_map.height * TILE_HEIGHT * self.camera.zoom
        
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
