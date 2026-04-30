import pygame
import json
import math
from core.config import SCREEN_WIDTH, MINIMAP_WIDTH, MINIMAP_HEIGHT


class ProductionPanel:
    """Manages the unit production interface for buildings"""
    
    def __init__(self, game):
        self.game = game
        self.small_font = pygame.font.Font(None, 24)
        self.cost_font = pygame.font.Font(None, 16)
        
        # Production icons
        self.unit_production_icons = {}
        self.unit_production_buttons = []
        self.hover_production_button = None
        
        # Load unit production icons from JSON data
        self._load_unit_production_icons()
    
    def _load_unit_production_icons(self):
        """Load unit production icons from their sprites"""
        try:
            # Load unit data
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            
            # Pre-load and scale unit icons
            for unit in units_data:
                unit_type = unit['name']
                sprite_path = f"assets/ui/Units/{unit_type}_icon.png"
                
                try:
                    unit_icon = pygame.image.load(sprite_path).convert_alpha()
                    # Scale to production button size
                    unit_icon = pygame.transform.scale(unit_icon, (60, 60))
                    self.unit_production_icons[unit_type] = unit_icon
                except:
                    # Create placeholder if icon not found
                    placeholder = pygame.Surface((60, 60))
                    placeholder.fill((100, 50, 50))
                    pygame.draw.rect(placeholder, (150, 100, 100), (0, 0, 60, 60), 2)
                    # Add text
                    text = self.cost_font.render(unit_type[:4].upper(), True, (255, 255, 255))
                    text_rect = text.get_rect(center=(30, 30))
                    placeholder.blit(text, text_rect)
                    self.unit_production_icons[unit_type] = placeholder
        except:
            # If loading fails, create placeholders for common units
            for unit_type in ['worker', 'warrior', 'archer']:
                placeholder = pygame.Surface((60, 60))
                placeholder.fill((100, 50, 50))
                pygame.draw.rect(placeholder, (150, 100, 100), (0, 0, 60, 60), 2)
                self.unit_production_icons[unit_type] = placeholder
    
    def draw(self, screen, selected_building):
        """Draw unit production UI for production buildings"""
        if not selected_building or not hasattr(selected_building, 'can_produce') or not selected_building.can_produce:
            return
        
        # Define UI panel area
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT + 200  # Below main info panel
        ui_width = MINIMAP_WIDTH
        padding = 6
        
        # Production panel title
        title_text = self.small_font.render("Unit Production", True, (255, 255, 255))
        screen.blit(title_text, (ui_x + padding, ui_y + padding))
        
        # Clear production buttons for this frame
        self.unit_production_buttons = []
        
        button_y = ui_y + 35
        button_size = 75
        button_spacing = 5

        human_player = self.game.players[0]

        # Use cached cost data from game_data
        cost_lookup = self.game.game_data.get("costs", {})

        for i, unit_type in enumerate(selected_building.can_produce):
            costs = cost_lookup.get(unit_type, {})
            
            # Check if player can afford this unit
            can_afford = True
            for resource, amount in costs.items():
                if human_player.resources.get(resource, 0) < amount:
                    can_afford = False
                    break
            
            # Button position - each unit gets its own row
            button_x = ui_x + padding
            button_y_offset = button_y + i * (button_size + 25)
            
            # Create button rect
            button_rect = pygame.Rect(button_x, button_y_offset, button_size, button_size)
            
            # Store button info
            self.unit_production_buttons.append({
                'rect': button_rect,
                'unit_type': unit_type,
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
            cost_surface = self.cost_font.render(cost_text, True, (255, 255, 255) if can_afford else (255, 100, 100))
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
    
    def handle_click(self, mouse_pos):
        """Handle clicks on unit production buttons"""
        for i, button in enumerate(self.unit_production_buttons):
            if button['rect'].collidepoint(mouse_pos):
                if button['can_afford']:
                    self.game.production_manager.start_production(
                        button['building'], button['unit_type']
                    )
                return True
        return False
    
    def handle_hover(self, mouse_pos):
        """Handle hover effects for production buttons"""
        self.hover_production_button = None
        for i, button in enumerate(self.unit_production_buttons):
            if button['rect'].collidepoint(mouse_pos):
                self.hover_production_button = i
                break