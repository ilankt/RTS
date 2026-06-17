import pygame
from core.config import CURSOR_SIZE, SMART_CURSORS_ENABLED
from utils.debug_logger import debug_log


class CursorManager:
    """Manages cursor loading, command modes, and smart cursor switching"""
    
    def __init__(self, game):
        self.game = game
        
        # Command mode system
        self.active_command_mode = None  # 'move', 'gather', 'deposit', 'attack', or None
        self.command_cursors = {}  # Store loaded cursor data
        self.default_cursor = None  # Store default system cursor
        self.current_cursor_tinted = False  # Track if cursor is currently red-tinted
        
        # Load command mode cursors
        self._load_command_cursors()
    
    def _load_command_cursors(self):
        """Load and prepare command mode cursors"""
        try:
            # Store the default system cursor
            self.default_cursor = pygame.mouse.get_cursor()
            
            # Cursor file mapping
            cursor_files = {
                'move': 'assets/ui/Cursors/move_cursor.png',
                'attack': 'assets/ui/Cursors/attack_cursor.png', 
                'gather': 'assets/ui/Cursors/gather_cursor.png',
                'deposit': 'assets/ui/Cursors/deposit_cursor.png'
            }
            
            for command_mode, file_path in cursor_files.items():
                try:
                    # Load and scale cursor image to configured size
                    cursor_image = pygame.image.load(file_path).convert_alpha()
                    cursor_image = pygame.transform.smoothscale(cursor_image, (CURSOR_SIZE, CURSOR_SIZE))
                    
                    # Create normal cursor
                    normal_cursor = self._create_cursor_from_surface(cursor_image)
                    
                    # Create red-tinted version for invalid targets
                    tinted_image = cursor_image.copy()
                    red_overlay = pygame.Surface((CURSOR_SIZE, CURSOR_SIZE), pygame.SRCALPHA)
                    red_overlay.fill((255, 100, 100, 128))  # Semi-transparent red
                    tinted_image.blit(red_overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
                    tinted_cursor = self._create_cursor_from_surface(tinted_image)
                    
                    # Store both versions
                    self.command_cursors[command_mode] = {
                        'normal': normal_cursor,
                        'tinted': tinted_cursor
                    }
                    
                except Exception as e:
                    debug_log.log(f"Failed to load cursor for {command_mode}: {e}", "UI")
                    # Create fallback cursor data
                    self.command_cursors[command_mode] = {
                        'normal': self.default_cursor,
                        'tinted': self.default_cursor
                    }
                    
        except Exception as e:
            debug_log.log(f"Failed to initialize cursor system: {e}", "UI")
            self.command_cursors = {}
    
    def _create_cursor_from_surface(self, surface):
        """Convert a pygame surface to cursor data with center hotspot"""
        try:
            # Create hotspot for cursor
            hotspot = (CURSOR_SIZE // 2, CURSOR_SIZE // 2)  # Center of configurable cursor
            
            # Convert to cursor format
            cursor_data = pygame.cursors.Cursor(hotspot, surface)
            return cursor_data
        except:
            # Fallback to default cursor if conversion fails
            return self.default_cursor
    
    def set_command_mode(self, command_mode):
        """Set active command mode and update cursor"""
        if command_mode not in ['move', 'gather', 'deposit', 'attack']:
            self.clear_command_mode()
            return
            
        self.active_command_mode = command_mode
        self.current_cursor_tinted = False
        
        # Set cursor for this command mode
        if command_mode in self.command_cursors:
            try:
                pygame.mouse.set_cursor(self.command_cursors[command_mode]['normal'])
            except:
                # Fallback to default cursor if setting fails
                pass
        
        debug_log.log(f"Entered {command_mode} command mode", "UI")
    
    def clear_command_mode(self):
        """Clear command mode and return to default cursor"""
        self.active_command_mode = None
        self.current_cursor_tinted = False
        
        # Restore default cursor
        try:
            if self.default_cursor:
                pygame.mouse.set_cursor(self.default_cursor)
        except:
            pass
            
        debug_log.log("Exited command mode", "UI")
    
    def update_cursor_for_target(self, is_valid_target):
        """Update cursor based on target validity (red tint for invalid)"""
        if not self.active_command_mode or self.active_command_mode not in self.command_cursors:
            return
            
        should_tint = not is_valid_target
        
        # Only change cursor if tint state has changed
        if should_tint != self.current_cursor_tinted:
            self.current_cursor_tinted = should_tint
            
            try:
                cursor_type = 'tinted' if should_tint else 'normal'
                pygame.mouse.set_cursor(self.command_cursors[self.active_command_mode][cursor_type])
            except:
                pass
    
    def get_smart_cursor_for_target(self, clicked_object, selected_units):
        """Determine the best cursor based on selected units and target"""
        if not SMART_CURSORS_ENABLED or not selected_units:
            return None
            
        # Analyze selected units to determine capabilities
        has_workers = any(unit.name == 'worker' for unit in selected_units)
        has_combat_units = any(hasattr(unit, 'can_attack') and unit.can_attack for unit in selected_units)
        workers_with_resources = [unit for unit in selected_units 
                                if unit.name == 'worker' and hasattr(unit, 'resource_amount') and unit.resource_amount > 0]
        
        # If hovering over an object, determine smart cursor
        if clicked_object:
            # Resource nodes - show gather cursor if we have workers
            if clicked_object in self.game.resources and has_workers:
                return 'gather'
            
            # Enemy units/buildings - show attack cursor if we have combat units
            elif clicked_object in self.game.units or clicked_object in self.game.buildings:
                if hasattr(clicked_object, 'player') and clicked_object.player != self.game.players[0]:
                    if has_combat_units:
                        return 'attack'
            
            # Friendly buildings - show deposit cursor if we have workers with resources
            elif clicked_object in self.game.buildings:
                if hasattr(clicked_object, 'player') and clicked_object.player == self.game.players[0]:
                    if workers_with_resources:
                        # Check if any worker can drop off at this building
                        for worker in workers_with_resources:
                            if self._can_drop_off_at_building_smart(worker, clicked_object):
                                return 'deposit'
        
        # Default cursor based on selected units (when not hovering over objects)
        if has_combat_units or has_workers:
            return 'move'
            
        return None
    
    def _can_drop_off_at_building_smart(self, worker, building):
        """Check if worker can drop off resources at the building (for smart cursor)"""
        if not hasattr(worker, 'resource_type') or not worker.resource_type:
            return False
            
        resource_type = worker.resource_type
        building_name = building.name
        
        # Castle accepts all resources
        if building_name == "castle":
            return True
        # Mine accepts gold
        elif building_name == "mine" and resource_type == "gold":
            return True
        # Quarry accepts stone  
        elif building_name == "quarry" and resource_type == "stone":
            return True
        # Lumbermill accepts wood types
        elif building_name == "lumbermill" and resource_type == "wood":
            return True
            
        return False
    
    def set_smart_cursor_for_units(self, selected_units):
        """Set default cursor when units are selected (not in command mode)"""
        if not SMART_CURSORS_ENABLED or self.active_command_mode:
            return
            
        # Set move cursor as default when units are selected
        smart_cursor = self.get_smart_cursor_for_target(None, selected_units)
        if smart_cursor and smart_cursor in self.command_cursors:
            try:
                pygame.mouse.set_cursor(self.command_cursors[smart_cursor]['normal'])
            except:
                pass
