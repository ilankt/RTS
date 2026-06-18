import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT
from entities import ConstructionSite

# Import UI components
from ui.components.cursor_manager import CursorManager
from ui.components.building_menu import BuildingMenu
from ui.components.unit_panel import UnitPanel
from ui.components.production_panel import ProductionPanel
from ui.components.resource_bar import ResourceBar
from ui.components.icon_loader import IconLoader


class UIManager:
    """Manages UI rendering and information display"""
    
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.stat_font = pygame.font.Font(None, 18)
        
        # Initialize UI components
        self.icon_loader = IconLoader()
        self.cursor_manager = CursorManager(game)
        self.building_menu = BuildingMenu(game)
        self.unit_panel = UnitPanel(game)
        self.production_panel = ProductionPanel(game)
        self.resource_bar = ResourceBar(game)
        
        # Action buttons
        self.action_buttons = []
        self.hover_action_button = None
        
        # Cancel construction button
        self.cancel_construction_rect = None
        
    # Delegate cursor methods to cursor manager
    def set_command_mode(self, command_mode):
        self.cursor_manager.set_command_mode(command_mode)
    
    def clear_command_mode(self):
        self.cursor_manager.clear_command_mode()
    
    def update_cursor_for_target(self, is_valid_target):
        self.cursor_manager.update_cursor_for_target(is_valid_target)
    
    def get_smart_cursor_for_target(self, clicked_object, selected_units):
        return self.cursor_manager.get_smart_cursor_for_target(clicked_object, selected_units)
    
    def set_smart_cursor_for_units(self, selected_units):
        self.cursor_manager.set_smart_cursor_for_units(selected_units)
    
    # Delegate to unit panel
    def get_selected_objects(self):
        return self.unit_panel.get_selected_objects()
    
    def get_selected_object_info(self):
        return self.unit_panel.get_selected_object_info()
    
    # Properties for compatibility
    @property
    def active_command_mode(self):
        return self.cursor_manager.active_command_mode
    
    @property
    def show_building_menu(self):
        return self.building_menu.show_menu
    
    @show_building_menu.setter
    def show_building_menu(self, value):
        if value:
            self.building_menu.open_menu()
        else:
            self.building_menu.close_menu()
    
    @property
    def selected_building_type(self):
        return self.building_menu.selected_building_type
    
    @selected_building_type.setter
    def selected_building_type(self, value):
        self.building_menu.selected_building_type = value
    
    # Icon access for compatibility
    @property
    def action_icons(self):
        return self.icon_loader.action_icons
    
    @property
    def building_icons(self):
        return self.icon_loader.building_icons
    
    @property
    def unit_production_icons(self):
        return self.icon_loader.unit_production_icons
    
    # Cursor access for compatibility
    @property
    def command_cursors(self):
        return self.cursor_manager.command_cursors
    
    def draw_ui_panel(self, screen):
        """Draw the main UI panel on the right side of the screen"""
        # Define UI panel area
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT + 8
        ui_width = MINIMAP_WIDTH - 16
        ui_height = SCREEN_HEIGHT - MINIMAP_HEIGHT - 40
        
        # Create a surface for the panel
        panel_surface = pygame.Surface((ui_width, ui_height))
        panel_surface.fill((20, 20, 20))
        
        # Draw a border
        pygame.draw.rect(panel_surface, (50, 50, 50), (0, 0, ui_width, ui_height), 2)
        
        # Get all selected objects
        selected_objects = self.get_selected_objects()
        
        # Draw unit panel content and get selected info + y_offset
        selected_info, y_offset = self.unit_panel.draw_panel(panel_surface, ui_width, selected_objects)
        
        # Handle single selection
        if len(selected_objects) == 1 and selected_info:
            # Draw action buttons for units
            if (selected_info["type"] == "Unit" and
                selected_info["object"].player == self.game.players[0] and
                getattr(selected_info["object"].player, "human", False)):
                self.draw_action_buttons(panel_surface, ui_x, ui_y, ui_width, y_offset, selected_info["object"])
            else:
                # Close building menu if non-builder unit is selected or no unit selected
                if self.show_building_menu:
                    self.show_building_menu = False
            
            # Show construction cancel button if selected
            if selected_info["type"] == "Construction":
                construction_site = selected_info["object"]
                if isinstance(construction_site, ConstructionSite):
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
        else:
            # No selection or multi-selection - close building menu
            if self.show_building_menu:
                self.show_building_menu = False
        
        # Draw action buttons for multi-selection
        if len(selected_objects) > 1:
            # Multi-selection: show action buttons if all selected are units from player
            selected_units = [
                obj for obj in selected_objects
                if obj in self.game.units and obj.player == self.game.players[0] and getattr(obj.player, "human", False)
            ]
            if selected_units:
                # Use the first unit as reference for button types
                self.draw_action_buttons(panel_surface, ui_x, ui_y, ui_width, 200, selected_units[0])
        
        # Blit the panel to the main screen
        screen.blit(panel_surface, (ui_x, ui_y))
        
        # Draw unit production panel if a production building is selected
        if selected_info and selected_info["type"] == "Building":
            selected_building = selected_info["object"]
            if (selected_building.player == self.game.players[0] and 
                getattr(selected_building.player, "human", False) and
                hasattr(selected_building, 'can_produce') and selected_building.can_produce):
                self.production_panel.draw(screen, selected_building)
        
        # Draw building menu if showing
        self.building_menu.draw(screen)
    
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
        
        # Get mouse position for hover detection
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw buttons in 2x2 grid
        for i, action in enumerate(buttons_to_show):
            # Calculate grid position (2 columns)
            col = i % 2
            row = i // 2
            
            button_x = start_x + col * (button_size + button_spacing)
            button_y = start_y + row * (button_size + 20)  # Extra space for label
            
            # Create button rect
            button_rect = pygame.Rect(button_x, button_y, button_size, button_size)
            
            # Check if mouse is hovering over this button
            screen_button_rect = pygame.Rect(ui_x + button_x, ui_y + button_y, button_size, button_size)
            is_hovered = screen_button_rect.collidepoint(mouse_pos)
            
            # Draw button background
            button_color = (70, 70, 70)  # Neutral dark gray
            border_color = (150, 150, 150)
            border_width = 2
            
            # Special state for active command mode
            if action == self.active_command_mode:
                button_color = (100, 100, 150)  # Blue tint
                border_color = (180, 180, 220)
                border_width = 3
            elif action == 'build' and self.show_building_menu:
                # Build button active state
                button_color = (0, 150, 0)
                border_color = (150, 150, 150)
                border_width = 3
            elif is_hovered:
                # Hover state
                button_color = (90, 90, 90)  # Lighter gray
                border_color = (200, 200, 200)
                border_width = 3
            
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
            
            # Store button info for click detection
            self.action_buttons.append({
                'rect': screen_button_rect,
                'action': action,
                'hovered': is_hovered
            })
            
            # Update hover state
            if is_hovered:
                self.hover_action_button = action
    
    def draw_top_bar(self, screen):
        """Draw the top resource bar"""
        self.resource_bar.draw(screen)
    
    def handle_click(self, pos):
        """Handle mouse clicks on UI elements"""
        # Check building menu clicks FIRST when menu is showing
        if self.building_menu.handle_click(pos):
            return True
        
        # Check production button clicks
        if self.production_panel.handle_click(pos):
            return True
        
        # Check action button clicks
        for button in self.action_buttons:
            if button['rect'].collidepoint(pos):
                # Handle different button actions
                if button['action'] == 'build':
                    self.show_building_menu = not self.show_building_menu
                elif button['action'] == 'move':
                    # Toggle move command mode
                    if self.active_command_mode == 'move':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('move')
                elif button['action'] == 'stop':
                    # Stop selected units
                    selected_units = [
                        unit for unit in self.game.units
                        if unit.selected and unit.player == self.game.players[0] and getattr(unit.player, "human", False)
                    ]
                    for unit in selected_units:
                        if hasattr(unit, 'stop'):
                            unit.stop()
                elif button['action'] == 'gather':
                    # Enter gather command mode
                    if self.active_command_mode == 'gather':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('gather')
                elif button['action'] == 'deposit':
                    # Enter deposit command mode
                    if self.active_command_mode == 'deposit':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('deposit')
                elif button['action'] == 'attack':
                    # Enter attack command mode
                    if self.active_command_mode == 'attack':
                        self.clear_command_mode()
                    else:
                        self.set_command_mode('attack')
                
                return True
        
        # Check cancel construction button
        if self.cancel_construction_rect and self.cancel_construction_rect.collidepoint(pos):
            # Find selected construction site
            for site in self.game.construction_sites:
                if site.selected:
                    # Cancel construction
                    self.game.cancel_construction(site)
                    return True
        
        return False
    
    def handle_production_hover(self, mouse_pos):
        """Handle hover effects for production buttons"""
        self.production_panel.handle_hover(mouse_pos)
