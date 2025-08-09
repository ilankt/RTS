import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT, MAP_VIEW_WIDTH, TOP_BAR_HEIGHT, TOP_BAR_START_X, TOP_BAR_SPACING, TOP_BAR_ROW_Y, TOP_BAR_ITEMS, BUILDING_BUTTON_HEIGHT, BUILDING_ICON_SIZE, CURSOR_SIZE, SMART_CURSORS_ENABLED
import json
from entities.objects import ConstructionSite


class UIManager:
    """Manages UI rendering and information display"""
    
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.stat_font = pygame.font.Font(None, 18)  # For unit stats
        self.build_button_rect = None
        self.cancel_construction_rect = None
        self.show_building_menu = False
        self.show_building_category = None  # None, 'economy', or 'military'
        self.building_buttons = []
        self.selected_building_type = None
        self.building_buttons_populated = False  # Track if buttons are ready
        
        # Action buttons
        self.action_buttons = []
        self.action_icons = {}
        self.hover_action_button = None  # Track which action button is being hovered
        
        # Unit production
        self.unit_production_icons = {}
        self.unit_production_buttons = []
        self.hover_production_button = None
        
        # Command mode system
        self.active_command_mode = None  # 'move', 'gather', 'deposit', 'attack', or None
        self.command_cursors = {}  # Store loaded cursor data
        self.default_cursor = None  # Store default system cursor
        self.current_cursor_tinted = False  # Track if cursor is currently red-tinted
        
        # Pre-load building icons for better performance
        self.building_icons = {}
        self.icon_size = BUILDING_ICON_SIZE  # Use config value
        self._load_building_icons()
        
        # Try to load action icons
        try:
            # Load and pre-scale action icons with smoothscale for quality
            self.action_icons['move'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/move_icon.png").convert_alpha(), (60, 60))
            self.action_icons['stop'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/stop_icon.png").convert_alpha(), (60, 60))
            self.action_icons['attack'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/attack_icon.png").convert_alpha(), (60, 60))
            self.action_icons['gather'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/gather_icon.png").convert_alpha(), (60, 60))
            self.action_icons['deposit'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/deposit_icon.png").convert_alpha(), (60, 60))
            self.action_icons['build'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/build_icon.png").convert_alpha(), (60, 60))
            self.action_icons['cancel'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/cancel_icon.png").convert_alpha(), (24, 24))
            
            # Load building category icons
            self.action_icons['build_econ'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/build_econ_icon.png").convert_alpha(), (70, 70))
            self.action_icons['build_mil'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/build_mil_icon.png").convert_alpha(), (70, 70))
        except:
            # Icons not loaded yet, will use text buttons as fallback
            pass
        
        # Load command mode cursors
        self._load_command_cursors()
        
        # Load unit production icons from JSON data
        self._load_unit_production_icons()
        
        # Pre-load and cache unit panel icons for performance
        self.unit_panel_icons = {}  # Cache for unit icons at different sizes
        self._load_unit_panel_icons()
    
    def _load_building_icons(self):
        """Pre-load and cache building icons for better performance"""
        try:
            # Load building data
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            
            # Include all buildings and pre-load icons
            buildable_buildings = buildings_data
            
            for building in buildable_buildings:
                try:
                    sprite_path = f"assets/sprites/Buildings/{building['name'].title()}.png"
                    building_sprite = pygame.image.load(sprite_path).convert_alpha()
                    # Pre-scale to icon size
                    building_icon = pygame.transform.scale(building_sprite, (self.icon_size, self.icon_size))
                    self.building_icons[building['name']] = building_icon
                except:
                    # Create placeholder if sprite not found
                    placeholder = pygame.Surface((self.icon_size, self.icon_size))
                    placeholder.fill((100, 100, 100))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, self.icon_size, self.icon_size), 1)
                    self.building_icons[building['name']] = placeholder
        except:
            # If loading fails, building icons will be empty and we'll use placeholders
            pass
    
    def _load_unit_production_icons(self):
        """Load unit production icons from units.json"""
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            
            for unit in units_data:
                unit_name = unit['name']
                icon_path = unit.get('icon')
                
                if icon_path:
                    try:
                        unit_icon = pygame.image.load(icon_path).convert_alpha()
                        self.unit_production_icons[unit_name] = pygame.transform.smoothscale(unit_icon, (60, 60))
                    except:
                        # Create placeholder if icon file not found
                        placeholder = pygame.Surface((60, 60))
                        placeholder.fill((100, 100, 150))
                        pygame.draw.rect(placeholder, (150, 150, 200), (0, 0, 60, 60), 2)
                        # Add text to show unit name
                        font = pygame.font.Font(None, 16)
                        text = font.render(unit_name[:4].upper(), True, (255, 255, 255))
                        text_rect = text.get_rect(center=(30, 30))
                        placeholder.blit(text, text_rect)
                        self.unit_production_icons[unit_name] = placeholder
        except:
            # Fallback placeholders
            for unit_type in ['worker', 'warrior', 'archer']:
                placeholder = pygame.Surface((60, 60))
                placeholder.fill((100, 100, 150))
                pygame.draw.rect(placeholder, (150, 150, 200), (0, 0, 60, 60), 2)
                self.unit_production_icons[unit_type] = placeholder
    
    def _load_unit_panel_icons(self):
        """Pre-load and cache unit panel icons at different sizes for performance"""
        # Define the unit types and required sizes
        unit_types = ['worker', 'warrior', 'archer']
        sizes = {
            'single': 64,  # For single unit selection
            'multi': 48    # For multi-unit selection
        }
        
        for unit_type in unit_types:
            self.unit_panel_icons[unit_type] = {}
            icon_path = f"assets/ui/Units/{unit_type}_icon.png"
            
            try:
                # Load the original icon once
                original_icon = pygame.image.load(icon_path).convert_alpha()
                
                # Pre-scale to both required sizes and cache them
                for size_name, size_pixels in sizes.items():
                    scaled_icon = pygame.transform.scale(original_icon, (size_pixels, size_pixels))
                    self.unit_panel_icons[unit_type][size_name] = scaled_icon
                
            except:
                # Create placeholder icons for missing files
                for size_name, size_pixels in sizes.items():
                    placeholder = pygame.Surface((size_pixels, size_pixels))
                    placeholder.fill((100, 100, 100))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, size_pixels, size_pixels), 2)
                    # Add text to indicate unit type
                    font = pygame.font.Font(None, max(12, size_pixels // 4))
                    text = font.render(unit_type[:4].upper(), True, (255, 255, 255))
                    text_rect = text.get_rect(center=(size_pixels // 2, size_pixels // 2))
                    placeholder.blit(text, text_rect)
                    self.unit_panel_icons[unit_type][size_name] = placeholder
    
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
                    print(f"Failed to load cursor for {command_mode}: {e}")
                    # Create fallback cursor data
                    self.command_cursors[command_mode] = {
                        'normal': self.default_cursor,
                        'tinted': self.default_cursor
                    }
                    
        except Exception as e:
            print(f"Failed to initialize cursor system: {e}")
            self.command_cursors = {}
    
    def _create_cursor_from_surface(self, surface):
        """Convert a pygame surface to cursor data with center hotspot"""
        try:
            # Create mask and hotspot for cursor
            mask = pygame.mask.from_surface(surface)
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
        
        print(f"Entered {command_mode} command mode")
    
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
            
        print("Exited command mode")
    
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
    
    def get_selected_objects(self):
        """Get all selected objects"""
        selected_objects = []
        all_objects = self.game.units + self.game.buildings + self.game.resources + self.game.construction_sites
        
        for obj in all_objects:
            if obj.selected:
                selected_objects.append(obj)
        
        return selected_objects
    
    def get_selected_object_info(self):
        """Get information about the currently selected object"""
        all_objects = self.game.units + self.game.buildings + self.game.resources + self.game.construction_sites
        
        # Find any selected object (prioritize units/buildings over resources)
        for obj in all_objects:
            if obj.selected:
                info = {
                    "name": obj.name.title(),
                    "type": "Unit" if obj in self.game.units else "Building" if obj in self.game.buildings else "Construction" if obj in self.game.construction_sites else "Resource",
                    "object": obj
                }
                
                # Add player info if available
                if hasattr(obj, 'player') and obj.player:
                    info["owner"] = obj.player.name
                    info["player_color"] = obj.player.color
                else:
                    info["owner"] = "Neutral"
                    info["player_color"] = (128, 128, 128)  # Gray for neutral
                
                # Add HP for units and buildings
                if hasattr(obj, 'hp'):
                    info["hp"] = obj.hp
                
                return info
        
        return None
    
    def draw_ui_panel(self, screen):
        """Draw the UI panel on the right side"""
        # Define UI panel area (right side, below minimap)
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT
        ui_width = MINIMAP_WIDTH
        ui_height = SCREEN_HEIGHT - MINIMAP_HEIGHT
        
        # Draw background panel
        panel_surface = pygame.Surface((ui_width, ui_height))
        panel_surface.fill((50, 50, 50))  # Dark gray background
        pygame.draw.rect(panel_surface, (100, 100, 100), (0, 0, ui_width, ui_height), 2)  # Border
        
        # Get all selected objects
        selected_objects = self.get_selected_objects()
        
        # Handle multi-unit selection
        if len(selected_objects) > 1:
            self._draw_multi_selection(panel_surface, selected_objects)
            selected_info = None  # Clear for later checks
        elif len(selected_objects) == 1:
            # Get selected object info for single selection
            selected_info = self.get_selected_object_info()
        else:
            selected_info = None
            
        if selected_info:
            y_offset = 10
            
            # For units, show new layout
            if selected_info["type"] == "Unit":
                unit = selected_info["object"]
                
                # Draw unit icon (centered) - use cached icon for performance
                icon_size = 64
                icon_x = (ui_width - icon_size) // 2
                
                # Get cached icon if available
                if unit.name in self.unit_panel_icons and 'single' in self.unit_panel_icons[unit.name]:
                    cached_icon = self.unit_panel_icons[unit.name]['single']
                    panel_surface.blit(cached_icon, (icon_x, y_offset))
                else:
                    # Fallback placeholder (this should rarely happen with proper pre-loading)
                    placeholder = pygame.Surface((icon_size, icon_size))
                    placeholder.fill((100, 100, 100))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                    panel_surface.blit(placeholder, (icon_x, y_offset))
                
                y_offset += icon_size + 10
                
                # Draw health bar
                bar_width = 150
                bar_height = 20
                bar_x = (ui_width - bar_width) // 2
                
                # Get max HP from unit data
                max_hp = self._get_unit_max_hp(unit)
                hp_percentage = unit.hp / max_hp if max_hp > 0 else 0
                
                # Background bar
                pygame.draw.rect(panel_surface, (60, 60, 60), (bar_x, y_offset, bar_width, bar_height))
                # Health fill
                fill_width = int(bar_width * hp_percentage)
                health_color = self._get_health_color(hp_percentage)
                pygame.draw.rect(panel_surface, health_color, (bar_x, y_offset, fill_width, bar_height))
                # Border
                pygame.draw.rect(panel_surface, (100, 100, 100), (bar_x, y_offset, bar_width, bar_height), 2)
                
                # HP text
                hp_text = self.stat_font.render(f"{unit.hp}/{max_hp} HP", True, (255, 255, 255))
                hp_text_rect = hp_text.get_rect(center=(ui_width // 2, y_offset + bar_height // 2))
                panel_surface.blit(hp_text, hp_text_rect)
                
                y_offset += bar_height + 15
                
                # Combat stats for fighting units (exclude workers)
                if hasattr(unit, 'can_attack') and unit.can_attack and unit.name != 'worker':
                    # Damage range and type
                    damage_text = self.stat_font.render(f"Damage: {unit.min_damage}-{unit.max_damage} ({unit.attack_type.title()})", True, (255, 200, 100))
                    panel_surface.blit(damage_text, (10, y_offset))
                    y_offset += 20
                    
                    # Attack range
                    range_text = self.stat_font.render(f"Range: {unit.attack_range}", True, (100, 200, 255))
                    panel_surface.blit(range_text, (10, y_offset))
                    y_offset += 20
                    
                    # Attack speed
                    speed_text = self.stat_font.render(f"Attack Speed: {unit.attack_speed:.1f}/s", True, (200, 255, 100))
                    panel_surface.blit(speed_text, (10, y_offset))
                    y_offset += 25
                
                # Armor info
                armor_text = self.stat_font.render(f"Armor: {unit.armor_type.title()} ({unit.armor_value})", True, (200, 200, 200))
                panel_surface.blit(armor_text, (10, y_offset))
                y_offset += 25
                
                # Owner info
                owner_color = selected_info["player_color"]
                owner_text = self.small_font.render(f"Owner: {selected_info['owner']}", True, owner_color)
                panel_surface.blit(owner_text, (10, y_offset))
                y_offset += 25
                
                # Show worker carrying capacity if worker
                if unit.name == "worker" and hasattr(unit, 'resource_amount') and unit.resource_amount > 0:
                    resource_display = unit.resource_type.replace('_', ' ').title() if unit.resource_type else 'Unknown'
                    capacity_text = self.small_font.render(
                        f"Carrying: {int(unit.resource_amount)} {resource_display}", 
                        True, (255, 200, 100)
                    )
                    panel_surface.blit(capacity_text, (10, y_offset))
                    y_offset += 25
            else:
                # Original layout for non-units
                # Object name
                name_text = self.font.render(selected_info["name"], True, (255, 255, 255))
                panel_surface.blit(name_text, (10, y_offset))
                y_offset += 35
                
                # Object type
                type_text = self.font.render(f"Type: {selected_info['type']}", True, (200, 200, 200))
                panel_surface.blit(type_text, (10, y_offset))
                y_offset += 30
                
                # Owner
                owner_color = selected_info["player_color"]
                owner_text = self.font.render(f"Owner: {selected_info['owner']}", True, owner_color)
                panel_surface.blit(owner_text, (10, y_offset))
                y_offset += 30
                
                # HP (if available)
                if "hp" in selected_info:
                    hp_text = self.font.render(f"HP: {selected_info['hp']}", True, (255, 255, 255))
                    panel_surface.blit(hp_text, (10, y_offset))
                    y_offset += 30
                
                # Combat stats for buildings that can attack (like watchtowers)
                obj = selected_info["object"]
                if (selected_info["type"] == "Building" and 
                    hasattr(obj, 'can_attack') and obj.can_attack):
                    y_offset += 10  # Add some spacing
                    
                    # Combat stats header
                    combat_header = self.font.render("Combat Stats:", True, (255, 200, 100))
                    panel_surface.blit(combat_header, (10, y_offset))
                    y_offset += 25
                    
                    # Damage range and type
                    damage_text = self.stat_font.render(
                        f"Damage: {obj.min_damage}-{obj.max_damage} ({obj.attack_type.title()})", 
                        True, (255, 200, 100)
                    )
                    panel_surface.blit(damage_text, (10, y_offset))
                    y_offset += 20
                    
                    # Attack range
                    range_text = self.stat_font.render(f"Range: {obj.attack_range}", True, (100, 200, 255))
                    panel_surface.blit(range_text, (10, y_offset))
                    y_offset += 20
                    
                    # Attack speed
                    speed_text = self.stat_font.render(f"Attack Speed: {obj.attack_speed:.1f}/s", True, (200, 255, 100))
                    panel_surface.blit(speed_text, (10, y_offset))
                    y_offset += 20
                    
                    # Armor info
                    armor_text = self.stat_font.render(
                        f"Armor: {obj.armor_type.title()} ({obj.armor_value})", 
                        True, (200, 200, 200)
                    )
                    panel_surface.blit(armor_text, (10, y_offset))
                    y_offset += 25
                
            
            # Draw action buttons for units
            if selected_info["type"] == "Unit" and selected_info["object"].player == self.game.players[0]:
                self.draw_action_buttons(panel_surface, ui_x, ui_y, ui_width, y_offset, selected_info["object"])
            else:
                # Close building menu if non-builder unit is selected or no unit selected
                if self.show_building_menu:
                    self.show_building_menu = False
                    self.show_building_category = None
                    self.building_buttons = []
                    self.building_buttons_populated = False
                        
            # Show resource amount if selected
            if selected_info["type"] == "Resource":
                for resource in self.game.resources:
                    if resource.selected:
                        amount_text = self.small_font.render(
                            f"Remaining: {int(resource.amount_remaining)}", 
                            True, (100, 255, 100)
                        )
                        panel_surface.blit(amount_text, (10, y_offset))
                        y_offset += 25
                        break
                        
            # Show construction progress if selected
            if selected_info["type"] == "Construction":
                construction_site = selected_info["object"]
                if isinstance(construction_site, ConstructionSite):
                    # Progress bar
                    progress = construction_site.construction_progress / construction_site.construction_duration
                    bar_width = 150
                    bar_height = 20
                    bar_x = 25
                    bar_y = y_offset + 10
                    
                    # Draw progress bar background
                    pygame.draw.rect(panel_surface, (50, 50, 50), 
                                   (bar_x, bar_y, bar_width, bar_height))
                    # Draw progress bar fill
                    fill_width = int(bar_width * progress)
                    pygame.draw.rect(panel_surface, (0, 200, 0), 
                                   (bar_x, bar_y, fill_width, bar_height))
                    # Draw progress bar border
                    pygame.draw.rect(panel_surface, (150, 150, 150), 
                                   (bar_x, bar_y, bar_width, bar_height), 2)
                    
                    # Progress text
                    progress_text = self.small_font.render(
                        f"Progress: {int(progress * 100)}%", 
                        True, (255, 255, 255)
                    )
                    panel_surface.blit(progress_text, (bar_x, bar_y + bar_height + 5))
                    y_offset = bar_y + bar_height + 30
                    
                    # Cancel button
                    button_width = 120
                    button_height = 30
                    button_x = (ui_width - button_width) // 2
                    button_y = y_offset + 10
                    
                    # Store button rect for click detection
                    self.cancel_construction_rect = pygame.Rect(
                        ui_x + button_x, ui_y + button_y, button_width, button_height
                    )
                    
                    # Draw button
                    pygame.draw.rect(panel_surface, (200, 50, 50), 
                                   (button_x, button_y, button_width, button_height))
                    pygame.draw.rect(panel_surface, (255, 255, 255), 
                                   (button_x, button_y, button_width, button_height), 2)
                    
                    # Draw button text
                    cancel_text = self.button_font.render("Cancel", True, (255, 255, 255))
                    text_rect = cancel_text.get_rect(center=(button_x + button_width // 2, 
                                                            button_y + button_height // 2))
                    panel_surface.blit(cancel_text, text_rect)
                    y_offset = button_y + button_height + 10
        else:
            # No selection - close building menu
            if self.show_building_menu:
                self.show_building_menu = False
                self.show_building_category = None
                self.building_buttons = []
                self.building_buttons_populated = False
            no_selection_text = self.font.render("No Selection", True, (150, 150, 150))
            panel_surface.blit(no_selection_text, (10, 20))
        
        
        # Draw action buttons for multi-selection or single unit
        if len(selected_objects) > 1:
            # Multi-selection: show action buttons if all selected are units from player
            selected_units = [obj for obj in selected_objects if obj in self.game.units and obj.player == self.game.players[0]]
            if selected_units:
                # Use the first unit as reference for button types
                self.draw_action_buttons(panel_surface, ui_x, ui_y, ui_width, 200, selected_units[0])
        
        # Blit the panel to the main screen
        screen.blit(panel_surface, (ui_x, ui_y))
        
        # Draw unit production panel if a production building is selected
        if selected_info and selected_info["type"] == "Building":
            selected_building = selected_info["object"]
            if (selected_building.player == self.game.players[0] and 
                hasattr(selected_building, 'can_produce') and selected_building.can_produce):
                self.draw_unit_production_panel(screen, selected_building)
        
        # Draw building menu if showing
        if self.show_building_menu:
            self.draw_building_menu(screen)
    
    def draw_action_buttons(self, panel_surface, ui_x, ui_y, ui_width, y_offset, unit):
        """Draw action buttons for the selected unit in 2x2 grid with labels"""
        self.action_buttons = []
        
        # Determine which buttons to show based on unit type
        buttons_to_show = ['move', 'stop']
        
        # Workers get gather/deposit and build, other units get attack
        if hasattr(unit, 'can_build') and unit.can_build:
            # Check if worker has resources to determine gather vs deposit
            has_resources = hasattr(unit, 'resource_amount') and unit.resource_amount > 0
            gather_or_deposit = 'deposit' if has_resources else 'gather'
            buttons_to_show.extend([gather_or_deposit, 'build'])
        else:
            buttons_to_show.append('attack')
        
        # Button configuration for 2x2 grid - bigger buttons that barely fit sidebar
        button_size = 85  # 1.5x bigger, fits sidebar width
        button_spacing = 6
        grid_width = 2 * button_size + button_spacing
        start_x = (ui_width - grid_width) // 2
        start_y = y_offset + 20
        
        # Action labels
        action_labels = {
            'move': 'Move',
            'stop': 'Stop', 
            'gather': 'Gather',
            'deposit': 'Deposit',
            'build': 'Build',
            'attack': 'Attack'
        }
        
        # Get mouse position for hover detection
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw buttons in 2x2 grid
        for i, action in enumerate(buttons_to_show):
            # Calculate grid position (2 columns)
            col = i % 2
            row = i // 2
            
            button_x = start_x + col * (button_size + button_spacing)
            button_y = start_y + row * (button_size + 20)  # Extra space for label
            button_rect = pygame.Rect(button_x, button_y, button_size, button_size)
            
            # Create click rect for this button
            click_rect = pygame.Rect(ui_x + button_x, ui_y + button_y, button_size, button_size)
            
            # Store button info for click detection
            self.action_buttons.append({
                'rect': click_rect,
                'action': action
            })
            
            # Check if mouse is hovering over this button
            is_hovering = click_rect.collidepoint(mouse_pos)
            
            # Draw button background with hover effect
            if is_hovering:
                # Bright highlight when hovering
                button_color = (120, 120, 120)
                border_color = (255, 255, 0)  # Yellow border when hovering
                border_width = 3
            elif action == 'build' and self.show_building_menu:
                # Build button active state
                button_color = (0, 150, 0)
                border_color = (150, 150, 150)
                border_width = 2
            elif action == self.active_command_mode:
                # Command mode button active state
                button_color = (150, 100, 0)  # Orange-ish for active command
                border_color = (255, 150, 0)  # Bright orange border
                border_width = 3
            else:
                # Normal state
                button_color = (80, 80, 80)
                border_color = (150, 150, 150)
                border_width = 2
                
            pygame.draw.rect(panel_surface, button_color, button_rect)
            pygame.draw.rect(panel_surface, border_color, button_rect, border_width)
            
            # Draw icon or text
            if action in self.action_icons:
                # Icons are already pre-scaled, just blit them
                icon_rect = self.action_icons[action].get_rect(center=button_rect.center)
                panel_surface.blit(self.action_icons[action], icon_rect)
            else:
                # Fallback to text if icon not loaded
                action_text = self.font.render(action.capitalize()[:4], True, (255, 255, 255))
                text_rect = action_text.get_rect(center=button_rect.center)
                panel_surface.blit(action_text, text_rect)
            
            # Draw label below button
            label_text = self.small_font.render(action_labels[action], True, (200, 200, 200))
            label_x = button_x + button_size // 2 - label_text.get_width() // 2
            label_y = button_y + button_size + 2
            panel_surface.blit(label_text, (label_x, label_y))
    
    def draw_building_menu(self, screen):
        """Draw the building selection menu"""
        # Define UI panel area (same as main UI panel)
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT
        ui_width = MINIMAP_WIDTH
        ui_height = SCREEN_HEIGHT - MINIMAP_HEIGHT
        
        # Draw menu background (use panel area)
        menu_surface = pygame.Surface((ui_width, ui_height))
        menu_surface.fill((50, 50, 50))
        pygame.draw.rect(menu_surface, (100, 100, 100), (0, 0, ui_width, ui_height), 2)
        
        padding = 6
        
        if self.show_building_category is None:
            # Show category selection
            title_text = self.small_font.render("Building Categories", True, (255, 255, 255))
            menu_surface.blit(title_text, (8, 8))
            
            # Draw category buttons
            button_y = 40
            button_size = 85
            button_spacing = 8
            
            # Economy button
            econ_button_x = (ui_width - button_size * 2 - button_spacing) // 2
            econ_button_rect = pygame.Rect(econ_button_x, button_y, button_size, button_size)
            
            # Military button
            mil_button_x = econ_button_x + button_size + button_spacing
            mil_button_rect = pygame.Rect(mil_button_x, button_y, button_size, button_size)
            
            # Get current mouse position for hover detection
            mouse_pos = pygame.mouse.get_pos()
            mouse_in_menu = (mouse_pos[0] - ui_x, mouse_pos[1] - ui_y)
            
            # Draw economy button
            econ_hover = econ_button_rect.collidepoint(mouse_in_menu)
            button_color = (100, 100, 100) if econ_hover else (70, 70, 70)
            border_color = (255, 255, 0) if econ_hover else (150, 150, 150)
            border_width = 3 if econ_hover else 1
            
            pygame.draw.rect(menu_surface, button_color, econ_button_rect)
            pygame.draw.rect(menu_surface, border_color, econ_button_rect, border_width)
            
            # Draw economy icon or text
            if 'build_econ' in self.action_icons:
                icon = self.action_icons['build_econ']
                icon_rect = icon.get_rect(center=econ_button_rect.center)
                menu_surface.blit(icon, icon_rect)
            else:
                text = self.button_font.render("Economy", True, (255, 255, 255))
                text_rect = text.get_rect(center=econ_button_rect.center)
                menu_surface.blit(text, text_rect)
            
            # Draw economy label
            label = self.small_font.render("Economy", True, (255, 255, 255))
            label_rect = label.get_rect(centerx=econ_button_rect.centerx, top=econ_button_rect.bottom + 5)
            menu_surface.blit(label, label_rect)
            
            # Draw military button
            mil_hover = mil_button_rect.collidepoint(mouse_in_menu)
            button_color = (100, 100, 100) if mil_hover else (70, 70, 70)
            border_color = (255, 255, 0) if mil_hover else (150, 150, 150)
            border_width = 3 if mil_hover else 1
            
            pygame.draw.rect(menu_surface, button_color, mil_button_rect)
            pygame.draw.rect(menu_surface, border_color, mil_button_rect, border_width)
            
            # Draw military icon or text
            if 'build_mil' in self.action_icons:
                icon = self.action_icons['build_mil']
                icon_rect = icon.get_rect(center=mil_button_rect.center)
                menu_surface.blit(icon, icon_rect)
            else:
                text = self.button_font.render("Military", True, (255, 255, 255))
                text_rect = text.get_rect(center=mil_button_rect.center)
                menu_surface.blit(text, text_rect)
            
            # Draw military label
            label = self.small_font.render("Military", True, (255, 255, 255))
            label_rect = label.get_rect(centerx=mil_button_rect.centerx, top=mil_button_rect.bottom + 5)
            menu_surface.blit(label, label_rect)
            
            # Store button rects for click detection (adjusted for screen position)
            self.category_buttons = {
                'economy': pygame.Rect(ui_x + econ_button_rect.x, ui_y + econ_button_rect.y, 
                                     econ_button_rect.width, econ_button_rect.height),
                'military': pygame.Rect(ui_x + mil_button_rect.x, ui_y + mil_button_rect.y, 
                                      mil_button_rect.width, mil_button_rect.height)
            }
        else:
            # Show buildings for selected category
            title = "Economy Buildings" if self.show_building_category == 'economy' else "Military Buildings"
            title_text = self.small_font.render(title, True, (255, 255, 255))
            menu_surface.blit(title_text, (8, 8))
        
        # Draw building buttons with icons (use pre-populated button list)
        if not self.building_buttons_populated:
            self._populate_building_buttons()
        
        padding = 6  # Still needed for cancel button
        human_player = self.game.players[0]
        
        # Get current mouse position for hover detection
        mouse_pos = pygame.mouse.get_pos()
        
        for i, button_info in enumerate(self.building_buttons):
            building = button_info['building']
            
            # Re-check affordability (resources may have changed)
            can_afford = True
            costs = building.get('costs', {})
            for resource, amount in costs.items():
                if human_player.resources.get(resource, 0) < amount:
                    can_afford = False
                    break
            
            # Update affordability in button info
            button_info['can_afford'] = can_afford
            
            # Use the stored draw rectangle (consistent with click area)
            button_rect = button_info['draw_rect']
            
            # Check if mouse is hovering over this button
            is_hovering = button_info['click_rect'].collidepoint(mouse_pos)
            
            # Draw button background with hover effect
            if is_hovering:
                # Bright highlight when hovering
                button_color = (100, 150, 100) if can_afford else (150, 100, 100)
                border_color = (255, 255, 0)  # Yellow border when hovering
                border_width = 3
            else:
                # Normal colors
                button_color = (60, 80, 60) if can_afford else (80, 60, 60)
                border_color = (150, 150, 150)
                border_width = 1
                
            pygame.draw.rect(menu_surface, button_color, button_rect)
            pygame.draw.rect(menu_surface, border_color, button_rect, border_width)
            
            # Draw pre-loaded building icon (centered vertically in button)
            icon_x = button_rect.x + 6
            icon_y = button_rect.y + (button_rect.height - self.icon_size) // 2
            
            # Use pre-loaded icon if available
            if building['name'] in self.building_icons:
                menu_surface.blit(self.building_icons[building['name']], (icon_x, icon_y))
            else:
                # Fallback: draw placeholder rectangle
                pygame.draw.rect(menu_surface, (100, 100, 100), 
                               (icon_x, icon_y, self.icon_size, self.icon_size))
                pygame.draw.rect(menu_surface, (150, 150, 150), 
                               (icon_x, icon_y, self.icon_size, self.icon_size), 1)
            
            # Draw building name (moved right, better positioned)
            name_x = icon_x + self.icon_size + 12  # More space from icon
            name_font = pygame.font.Font(None, 18)
            name_text = name_font.render(building['name'].title(), True, (255, 255, 255))
            menu_surface.blit(name_text, (name_x, icon_y + 2))
            
            # Draw costs with proper capitalization (positioned below name)
            cost_y = icon_y + 20
            cost_font = pygame.font.Font(None, 14)  # Smaller font to fit better
            for resource, amount in costs.items():
                color = (200, 200, 200) if human_player.resources.get(resource, 0) >= amount else (255, 100, 100)
                # Capitalize resource names
                resource_name = resource.replace('_', ' ').title()
                cost_text = cost_font.render(f"{resource_name}: {amount}", True, color)
                menu_surface.blit(cost_text, (name_x, cost_y))
                cost_y += 12  # Tighter spacing for smaller font
            
            # Position is pre-calculated in draw_rect, no need to increment y
        
        # Draw cancel/back button at bottom (smaller)
        cancel_button_height = 30
        cancel_button_y = ui_height - cancel_button_height - padding
        cancel_button_rect = pygame.Rect(padding, cancel_button_y, ui_width - 2 * padding, cancel_button_height)
        
        pygame.draw.rect(menu_surface, (150, 50, 50), cancel_button_rect)
        pygame.draw.rect(menu_surface, (200, 200, 200), cancel_button_rect, 2)
        
        # Draw cancel text or icon
        if 'cancel' in self.action_icons:
            # Cancel icon is already pre-scaled to 24x24
            icon_rect = self.action_icons['cancel'].get_rect(center=cancel_button_rect.center)
            menu_surface.blit(self.action_icons['cancel'], icon_rect)
        else:
            cancel_text = self.button_font.render("Cancel", True, (255, 255, 255))
            text_rect = cancel_text.get_rect(center=cancel_button_rect.center)
            menu_surface.blit(cancel_text, text_rect)
        
        # Store cancel button rect for click detection
        self.cancel_building_menu_rect = pygame.Rect(ui_x + cancel_button_rect.x, 
                                                   ui_y + cancel_button_rect.y,
                                                   cancel_button_rect.width, 
                                                   cancel_button_rect.height)
        
        # Blit menu to screen
        screen.blit(menu_surface, (ui_x, ui_y))
    
    def handle_click(self, pos):
        """Handle mouse clicks on UI elements"""
        # Check building menu clicks FIRST when menu is showing
        if self.show_building_menu:
            # Check cancel button
            if hasattr(self, 'cancel_building_menu_rect') and self.cancel_building_menu_rect.collidepoint(pos):
                self.show_building_menu = False
                self.show_building_category = None
                self.selected_building_type = None
                self.building_buttons = []  # Clear buttons when menu is closed
                self.building_buttons_populated = False
                return True
            
            # Check category buttons if no category selected
            if self.show_building_category is None and hasattr(self, 'category_buttons'):
                for category, rect in self.category_buttons.items():
                    if rect.collidepoint(pos):
                        self.show_building_category = category
                        self.building_buttons_populated = False  # Force repopulation
                        self._populate_building_buttons()
                        return True
            
            # Check building buttons if category is selected
            if self.show_building_category is not None:
                for i, button_info in enumerate(self.building_buttons):
                    if button_info['click_rect'].collidepoint(pos):
                        print(f"Clicked on building {i}: {button_info['building']['name']}, can_afford: {button_info['can_afford']}")
                        if button_info['can_afford']:
                            print(f"Selecting building: {button_info['building']['name']}")
                            self.selected_building_type = button_info['building']
                            self.show_building_menu = False
                            self.show_building_category = None
                            self.building_buttons = []  # Clear buttons when menu is closed
                            self.building_buttons_populated = False
                            # Notify game to enter building placement mode
                            self.game.enter_building_placement_mode(self.selected_building_type)
                            return True
                        else:
                            print(f"Cannot afford building: {button_info['building']['name']}")
                            return True  # Still consume the click even if can't afford
        
        # Check unit production button clicks
        if hasattr(self, 'unit_production_buttons') and self.unit_production_buttons:
            if self.handle_production_button_click(pos):
                return True
        
        # Check action button clicks (only if building menu is not showing)
        for button in self.action_buttons:
            if button['rect'].collidepoint(pos):
                if button['action'] == 'build':
                    self.show_building_menu = not self.show_building_menu
                    if self.show_building_menu:
                        self.show_building_category = None  # Reset to category selection
                        self.building_buttons = []  # Clear any existing buttons
                        self.building_buttons_populated = False
                    else:
                        self.show_building_category = None
                        self.building_buttons = []  # Clear buttons when menu is closed
                        self.building_buttons_populated = False
                elif button['action'] == 'move':
                    # Toggle move command mode
                    if self.active_command_mode == 'move':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('move')
                elif button['action'] == 'stop':
                    # Stop selected units and clear any active command mode
                    self.clear_command_mode()
                    for unit in self.game.units:
                        if unit.selected and unit.player == self.game.players[0]:
                            unit.stop()
                elif button['action'] == 'gather':
                    # Toggle gather command mode
                    if self.active_command_mode == 'gather':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('gather')
                elif button['action'] == 'deposit':
                    # Toggle deposit command mode
                    if self.active_command_mode == 'deposit':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('deposit')
                elif button['action'] == 'attack':
                    # Toggle attack command mode
                    if self.active_command_mode == 'attack':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('attack')
                return True
            
        # Check cancel construction button click
        if self.cancel_construction_rect and self.cancel_construction_rect.collidepoint(pos):
            # Find selected construction site
            for site in self.game.construction_sites:
                if site.selected:
                    self.game.cancel_construction(site)
                    return True
                    
        return False
    
    def draw_top_bar(self, screen):
        """Draw the top resource bar"""
        if not self.game.players:
            return
            
        human_player = self.game.players[0]  # First player is human
        
        # Top bar dimensions - spans screen width minus minimap
        top_bar_height = TOP_BAR_HEIGHT
        top_bar_width = SCREEN_WIDTH - MINIMAP_WIDTH  # Leaves space for minimap (1280 - 200 = 1080)
        
        # Create a surface for the resource bar
        resource_bar = pygame.Surface((top_bar_width, top_bar_height))
        resource_bar.fill((30, 30, 30))  # Darker background for resource bar
        
        # Draw a subtle border
        pygame.draw.rect(resource_bar, (80, 80, 80), (0, 0, top_bar_width, top_bar_height), 2)
        
        # Fonts
        resource_font = pygame.font.Font(None, 32)  # Larger font for resources
        info_font = pygame.font.Font(None, 24)      # Smaller font for info row
        
        # === SINGLE ROW: Resources + Housing ===
        all_items = TOP_BAR_ITEMS
        start_x = TOP_BAR_START_X
        spacing = TOP_BAR_SPACING
        row_y = TOP_BAR_ROW_Y
        
        for i, item in enumerate(all_items):
            x_pos = start_x + (i * spacing)
            
            # Draw icon
            if item in self.game.resource_icons:
                icon_rect = self.game.resource_icons[item].get_rect()
                icon_rect.x = x_pos
                icon_rect.y = row_y
                resource_bar.blit(self.game.resource_icons[item], icon_rect)
                
                # Draw amount/value next to icon
                if item == "house":
                    # Housing display
                    current_pop = len([unit for unit in self.game.units if unit.player == human_player])
                    max_pop = 20 + (len([building for building in self.game.buildings if building.player == human_player and building.name == "house"]) * 5)
                    text = f"{current_pop}/{max_pop}"
                    text_surface = info_font.render(text, True, (200, 200, 200))
                else:
                    # Resource amount
                    amount = int(human_player.resources.get(item, 0))
                    text_surface = resource_font.render(str(amount), True, (255, 255, 255))
                
                text_x = x_pos + icon_rect.width + 5  # Small gap between icon and text
                text_y = row_y + (icon_rect.height - text_surface.get_height()) // 2  # Center with icon
                resource_bar.blit(text_surface, (text_x, text_y))
        
        # Blit the resource bar to the main screen at the very top
        screen.blit(resource_bar, (0, 0))
    
    def _get_unit_max_hp(self, unit):
        """Get maximum HP for a unit from units.json data"""
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            for unit_data in units_data:
                if unit_data['name'] == unit.name:
                    return unit_data['hp']
        except:
            pass
        return unit.hp  # Fallback to current HP
    
    def _get_health_color(self, hp_percentage):
        """Get health bar color based on percentage"""
        if hp_percentage >= 0.5:
            return (30, 200, 30)  # Green
        elif hp_percentage >= 0.25:
            return (200, 200, 0)  # Yellow
        else:
            return (200, 0, 0)  # Red
    
    def _draw_multi_selection(self, panel_surface, selected_objects):
        """Draw multi-unit selection with small icons and health bars"""
        # Title
        title_text = self.font.render(f"{len(selected_objects)} Units Selected", True, (255, 255, 255))
        panel_surface.blit(title_text, (10, 10))
        
        # Small icon configuration
        icon_size = 48
        icon_spacing = 4
        icons_per_row = 4
        start_x = 10
        start_y = 50
        
        # Draw each selected unit
        for i, unit in enumerate(selected_objects):
            # Skip non-units in multi-selection
            if unit not in self.game.units:
                continue
                
            # Calculate position in grid
            row = i // icons_per_row
            col = i % icons_per_row
            x = start_x + col * (icon_size + icon_spacing)
            y = start_y + row * (icon_size + icon_spacing + 15)  # Extra space for health bar
            
            # Draw unit icon - use cached icon for performance
            if unit.name in self.unit_panel_icons and 'multi' in self.unit_panel_icons[unit.name]:
                cached_icon = self.unit_panel_icons[unit.name]['multi']
                panel_surface.blit(cached_icon, (x, y))
            else:
                # Fallback placeholder (this should rarely happen with proper pre-loading)
                placeholder = pygame.Surface((icon_size, icon_size))
                placeholder.fill((100, 100, 100))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                panel_surface.blit(placeholder, (x, y))
            
            # Draw small health bar below icon
            bar_y = y + icon_size + 2
            bar_width = icon_size
            bar_height = 4
            
            # Get health percentage
            max_hp = self._get_unit_max_hp(unit)
            hp_percentage = unit.hp / max_hp if max_hp > 0 else 0
            
            # Background bar
            pygame.draw.rect(panel_surface, (60, 60, 60), (x, bar_y, bar_width, bar_height))
            # Health fill
            fill_width = int(bar_width * hp_percentage)
            health_color = self._get_health_color(hp_percentage)
            pygame.draw.rect(panel_surface, health_color, (x, bar_y, fill_width, bar_height))
            # Border
            pygame.draw.rect(panel_surface, (100, 100, 100), (x, bar_y, bar_width, bar_height), 1)
    
    def _populate_building_buttons(self):
        """Populate building buttons when menu is opened"""
        try:
            # Load building data
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            
            # Define building categories
            economy_buildings = ["house", "farm", "lumbermill", "mine", "quarry"]
            military_buildings = ["barracks", "watchtower", "castle"]
            
            # Filter buildings based on category
            if self.show_building_category == 'economy':
                building_order = economy_buildings
            elif self.show_building_category == 'military':
                building_order = military_buildings
            else:
                # If no category selected, don't show any buildings
                self.building_buttons = []
                self.building_buttons_populated = True
                return
            
            buildable_buildings = []
            for building_name in building_order:
                for building in buildings_data:
                    if building['name'] == building_name:
                        buildable_buildings.append(building)
                        break
            
            # Clear and repopulate buttons
            self.building_buttons = []
            
            # Define UI panel area (same as main UI panel)
            ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
            ui_y = MINIMAP_HEIGHT
            ui_width = MINIMAP_WIDTH
            padding = 6
            y = 30
            
            human_player = self.game.players[0]
            
            for i, building in enumerate(buildable_buildings):
                # Check if player can afford this building
                can_afford = True
                costs = building.get('costs', {})
                for resource, amount in costs.items():
                    if human_player.resources.get(resource, 0) < amount:
                        can_afford = False
                        break
                
                # Use calculated optimal button height
                button_height = BUILDING_BUTTON_HEIGHT
                button_rect = pygame.Rect(padding, y, ui_width - 2 * padding, button_height)
                
                # Store button info for click detection AND drawing
                self.building_buttons.append({
                    'click_rect': pygame.Rect(ui_x + button_rect.x, ui_y + button_rect.y, button_rect.width, button_rect.height),
                    'draw_rect': button_rect,  # Store visual rectangle for consistent drawing
                    'building': building,
                    'can_afford': can_afford
                })
                
                y += button_height + 2  # Tighter spacing to fit all buildings
                
            self.building_buttons_populated = True
        except:
            # If loading fails, ensure buttons list exists
            self.building_buttons = []
            self.building_buttons_populated = False
    
    def draw_unit_production_panel(self, screen, selected_building):
        """Draw unit production UI for production buildings"""
        if not selected_building or not hasattr(selected_building, 'can_produce') or not selected_building.can_produce:
            return
        
        # Define UI panel area
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT + 200  # Below main info panel
        ui_width = MINIMAP_WIDTH
        padding = 6
        
        # Production panel title
        title_font = pygame.font.Font(None, 24)
        title_text = title_font.render("Unit Production", True, (255, 255, 255))
        screen.blit(title_text, (ui_x + padding, ui_y + padding))
        
        # Clear production buttons for this frame
        self.unit_production_buttons = []
        
        button_y = ui_y + 35
        button_size = 75
        button_spacing = 5
        
        human_player = self.game.players[0]
        
        # Load unit data for costs
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            units_dict = {unit['name']: unit for unit in units_data}
        except:
            units_dict = {}
        
        for i, unit_type in enumerate(selected_building.can_produce):
            if unit_type not in units_dict:
                continue
            
            unit_data = units_dict[unit_type]
            costs = unit_data.get('costs', {})
            
            # Check if player can afford this unit
            can_afford = True
            for resource, amount in costs.items():
                if human_player.resources.get(resource, 0) < amount:
                    can_afford = False
                    break
            
            # Button position - each unit gets its own row (like building menu)
            button_x = ui_x + padding
            button_y_offset = button_y + i * (button_size + 25)  # Each unit in a new row
            
            # Create button rect
            button_rect = pygame.Rect(button_x, button_y_offset, button_size, button_size)
            
            # Store button info
            self.unit_production_buttons.append({
                'rect': button_rect,
                'unit_type': unit_type,
                'unit_data': unit_data,
                'can_afford': can_afford,
                'building': selected_building
            })
            
            # Draw button background
            button_color = (0, 100, 0) if can_afford else (100, 0, 0)
            if self.hover_production_button == i:
                button_color = tuple(min(255, c + 50) for c in button_color)
            
            pygame.draw.rect(screen, button_color, button_rect)
            pygame.draw.rect(screen, (255, 255, 255), button_rect, 2)
            
            # Draw unit icon with radial progress if producing
            production_info = self.game.production_manager.get_production_info(selected_building)
            is_producing = production_info and production_info['unit_type'] == unit_type
            progress = production_info['progress'] if is_producing else 0
            
            if unit_type in self.unit_production_icons:
                icon = self.unit_production_icons[unit_type]
                icon_rect = icon.get_rect(center=button_rect.center)
                
                if is_producing and progress < 1.0:
                    # Draw icon with radial progress
                    self._draw_icon_with_radial_progress(screen, icon, icon_rect, progress)
                else:
                    # Draw normal icon
                    screen.blit(icon, icon_rect)
                
                # Draw queue number if there are multiple units of this specific type
                unit_count = self.game.production_manager.get_unit_count_in_production(selected_building, unit_type)
                if unit_count > 1:  # Only show number if more than 1 unit of this type
                    self._draw_queue_number(screen, button_rect, unit_count)
            
            # Draw costs below button
            cost_y = button_rect.bottom + 2
            cost_text = self._format_costs(costs)
            cost_font = pygame.font.Font(None, 16)
            cost_surface = cost_font.render(cost_text, True, (255, 255, 255) if can_afford else (255, 100, 100))
            screen.blit(cost_surface, (button_x, cost_y))
    
    def _format_costs(self, costs):
        """Format resource costs for display"""
        if not costs:
            return "Free"
        
        cost_parts = []
        for resource, amount in costs.items():
            cost_parts.append(f"{amount} {resource.title()}")
        
        return ", ".join(cost_parts)
    
    def _draw_icon_with_radial_progress(self, screen, icon, icon_rect, progress):
        """Draw icon with radial clockwise progress effect"""
        import math
        
        # Create darkened version of icon (50% darker)
        darkened_icon = icon.copy()
        dark_overlay = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
        dark_overlay.fill((0, 0, 0, 128))
        darkened_icon.blit(dark_overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
        
        # Draw darkened icon first
        screen.blit(darkened_icon, icon_rect)
        
        if progress > 0:
            # Create surface for the progress mask
            mask_size = icon.get_size()
            mask = pygame.Surface(mask_size, pygame.SRCALPHA)
            mask.fill((0, 0, 0, 0))  # Transparent
            
            # Calculate center and radius
            center_x = mask_size[0] // 2
            center_y = mask_size[1] // 2
            radius = max(center_x, center_y) + 2  # Ensure full coverage
            
            # Calculate angle (0 to 360 degrees, starting from top, going clockwise)
            angle = progress * 360
            
            if angle > 0:
                # Create points for pie slice (starting from top, going clockwise)
                points = [(center_x, center_y)]  # Center point
                
                # Start from top (-90 degrees) and go clockwise
                start_angle = -90
                step = 2  # Degree steps for smoother circle
                
                # Add points around the arc
                for a in range(0, int(angle) + step, step):
                    if a > angle:
                        a = angle
                    rad = math.radians(start_angle + a)
                    x = center_x + radius * math.cos(rad)
                    y = center_y + radius * math.sin(rad)
                    points.append((x, y))
                
                # Draw filled polygon
                if len(points) >= 3:
                    pygame.draw.polygon(mask, (255, 255, 255, 255), points)
            
            # Create a temporary surface to apply the mask
            temp_surface = pygame.Surface(mask_size, pygame.SRCALPHA)
            temp_surface.blit(icon, (0, 0))
            
            # Use the mask to create the visible progress portion
            temp_surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            # Draw the progress portion over the darkened icon
            screen.blit(temp_surface, icon_rect)
    
    def _draw_queue_number(self, screen, button_rect, queue_count):
        """Draw queue number in top-left corner of button"""
        # Create small circle background
        circle_radius = 12
        circle_center = (button_rect.left + circle_radius, button_rect.top + circle_radius)
        
        # Draw circle background
        pygame.draw.circle(screen, (200, 50, 50), circle_center, circle_radius)
        pygame.draw.circle(screen, (255, 255, 255), circle_center, circle_radius, 2)
        
        # Draw number text
        font = pygame.font.Font(None, 20)
        text = font.render(str(queue_count), True, (255, 255, 255))
        text_rect = text.get_rect(center=circle_center)
        screen.blit(text, text_rect)
    
    def handle_production_button_click(self, mouse_pos):
        """Handle clicks on unit production buttons"""
        for i, button in enumerate(self.unit_production_buttons):
            if button['rect'].collidepoint(mouse_pos):
                if button['can_afford']:
                    # Start production
                    success, message = self.game.production_manager.start_production(
                        button['building'], button['unit_type']
                    )
                    print(f"Production: {message}")
                    return True
                else:
                    print(f"Cannot afford {button['unit_type']}")
                    return True
        return False
    
    def handle_production_hover(self, mouse_pos):
        """Handle hover effects for production buttons"""
        self.hover_production_button = None
        for i, button in enumerate(self.unit_production_buttons):
            if button['rect'].collidepoint(mouse_pos):
                self.hover_production_button = i
                break