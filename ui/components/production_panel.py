import pygame
import json
import math
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT


class ProductionPanel:
    """Manages the unit production interface for buildings"""
    
    def __init__(self, game):
        self.game = game
        self.small_font = pygame.font.Font(None, 24)
        self.cost_font = pygame.font.Font(None, 16)
        
        # Production icons
        self.unit_production_icons = {}
        self.tech_icons = {}
        self.unit_production_buttons = []
        self.hover_production_button = None
        
        # Load unit production icons from JSON data
        self._load_unit_production_icons()
        self._load_tech_icons()
    
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
                    sprite_path = unit.get('icon', sprite_path)
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

    def _load_tech_icons(self):
        """Load blacksmith research icons from tech metadata."""
        try:
            with open('data/techs.json', 'r') as f:
                techs_data = json.load(f)

            for tech in techs_data:
                icon_path = tech.get("icon")
                if not icon_path:
                    continue
                try:
                    icon = pygame.image.load(icon_path).convert_alpha()
                    self.tech_icons[tech["id"]] = pygame.transform.smoothscale(icon, (34, 34))
                except:
                    continue
        except:
            self.tech_icons = {}
    
    def draw(self, screen, selected_building):
        """Draw unit production UI for production buildings"""
        research_rows = []
        if selected_building and hasattr(self.game, "research_manager"):
            research_rows = self.game.research_manager.available_for_building(selected_building)
        can_produce = bool(
            selected_building
            and hasattr(selected_building, 'can_produce')
            and selected_building.can_produce
        )
        if not selected_building or (not can_produce and not research_rows):
            self.unit_production_buttons = []  # stale rects must not eat clicks
            return
        
        # Define UI panel area
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT + 200  # Below main info panel
        padding = 6
        
        # Production panel title
        title = "Production" if can_produce else "Research"
        title_text = self.small_font.render(title, True, (255, 255, 255))
        screen.blit(title_text, (ui_x + padding, ui_y + padding))
        
        # Clear production buttons for this frame
        self.unit_production_buttons = []
        
        button_y = ui_y + 35
        button_size = 75

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
                'kind': 'unit',
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

        next_y = button_y + len(selected_building.can_produce) * (button_size + 25)
        if research_rows:
            self._draw_research_section(screen, selected_building, research_rows, ui_x, max(next_y, ui_y + 35), padding)

        self._draw_hover_tooltip(screen, ui_x, ui_y, selected_building)

    def _draw_research_section(self, screen, selected_building, research_rows, ui_x, start_y, padding):
        header_y = start_y
        if selected_building.can_produce:
            header = self.small_font.render("Research", True, (255, 255, 255))
            screen.blit(header, (ui_x + padding, header_y))
            header_y += 22

        research_info = self.game.research_manager.get_research_info(selected_building)
        if research_info:
            progress_rect = pygame.Rect(ui_x + padding, header_y, MINIMAP_WIDTH - 2 * padding - 12, 14)
            pygame.draw.rect(screen, (55, 55, 55), progress_rect)
            fill = pygame.Rect(progress_rect.x, progress_rect.y, int(progress_rect.width * research_info["progress"]), progress_rect.height)
            pygame.draw.rect(screen, (90, 150, 220), fill)
            label = self.cost_font.render(research_info["display_name"][:24], True, (255, 255, 255))
            screen.blit(label, (progress_rect.x, progress_rect.y - 16))
            header_y += 24

        row_h = 46
        row_w = MINIMAP_WIDTH - 2 * padding - 12
        for i, (tech, can_research, reason) in enumerate(research_rows):
            row_rect = pygame.Rect(ui_x + padding, header_y + i * (row_h + 5), row_w, row_h)
            is_hovered = row_rect.collidepoint(pygame.mouse.get_pos())
            done = reason == "Already researched"
            queued = reason == "Already in progress"
            if done:
                color = (35, 80, 45)
                border = (80, 170, 100)
            elif can_research:
                color = (35, 75, 105)
                border = (90, 170, 230)
            elif reason == "Insufficient resources":
                color = (95, 35, 35)
                border = (180, 70, 70)
            else:
                color = (80, 70, 35)
                border = (170, 140, 60)
            if queued:
                color = (55, 55, 90)
                border = (120, 120, 210)
            if is_hovered:
                color = tuple(min(255, c + 30) for c in color)

            pygame.draw.rect(screen, color, row_rect)
            pygame.draw.rect(screen, border, row_rect, 2)
            text_x = row_rect.x + 6
            icon = self.tech_icons.get(tech["id"])
            if icon:
                icon_rect = icon.get_rect()
                icon_rect.x = row_rect.x + 5
                icon_rect.centery = row_rect.centery
                screen.blit(icon, icon_rect)
                text_x = icon_rect.right + 6

            name = self.cost_font.render(tech.get("display_name", tech["id"])[:24], True, (255, 255, 255))
            screen.blit(name, (text_x, row_rect.y + 5))
            sub = "Done" if done else ("Queued" if queued else (self._format_costs(tech.get("costs", {})) or reason))
            sub_text = self.cost_font.render(sub[:28], True, (220, 220, 220))
            screen.blit(sub_text, (text_x, row_rect.y + 25))
            self.unit_production_buttons.append({
                'rect': row_rect,
                'kind': 'tech',
                'tech_id': tech['id'],
                'tech': tech,
                'can_afford': can_research,
                'reason': reason,
                'building': selected_building,
            })
    
    def _format_costs(self, costs):
        """Format resource costs for display"""
        if not costs:
            return "Free"
        
        cost_parts = []
        for resource, amount in costs.items():
            cost_parts.append(f"{amount} {resource.title()}")
        
        return ", ".join(cost_parts)

    def _draw_hover_tooltip(self, screen, ui_x, ui_y, selected_building):
        hovered = None
        for button in self.unit_production_buttons:
            if button['rect'].collidepoint(pygame.mouse.get_pos()):
                hovered = button
                break
        if not hovered:
            return

        tooltip_rect = pygame.Rect(ui_x + 6, SCREEN_HEIGHT - 95, MINIMAP_WIDTH - 12, 88)
        pygame.draw.rect(screen, (10, 10, 10), tooltip_rect)
        pygame.draw.rect(screen, (120, 120, 120), tooltip_rect, 1)

        lines = []
        if hovered.get('kind') == 'unit':
            unit = self.game.game_data.get("units", {}).get(hovered["unit_type"])
            lines = [
                getattr(unit, "display_name", hovered["unit_type"].title()),
                getattr(unit, "role", ""),
            ]
            if getattr(unit, "strong_against", None):
                lines.append("Strong: " + ", ".join(x.title() for x in unit.strong_against[:2]))
            if getattr(unit, "weak_against", None):
                lines.append("Weak: " + ", ".join(x.title() for x in unit.weak_against[:2]))
        else:
            tech = hovered.get("tech", {})
            lines = [
                tech.get("display_name", hovered.get("tech_id", "")),
                tech.get("tooltip", ""),
                hovered.get("reason", ""),
            ]

        y = tooltip_rect.y + 6
        for line in [line for line in lines if line][:4]:
            text = self.cost_font.render(line[:30], True, (230, 230, 230))
            screen.blit(text, (tooltip_rect.x + 6, y))
            y += 18
    
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
                    if button.get('kind') == 'tech':
                        success, _ = self.game.research_manager.start_research(
                            button['building'], button['tech_id']
                        )
                    else:
                        success, _ = self.game.production_manager.start_production(
                            button['building'], button['unit_type']
                        )
                    if success and hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                        self.game.sound_manager.play_ui_click()
                    elif hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                        self.game.sound_manager.play_error()
                elif hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                    self.game.sound_manager.play_error()
                return True
        return False
    
    def handle_right_click(self, mouse_pos):
        """Right-click a unit button: remove a queued unit (full refund), or
        cancel the in-progress one (50% refund) when nothing is queued (§7.4)."""
        for button in self.unit_production_buttons:
            if not button['rect'].collidepoint(mouse_pos):
                continue
            if button.get('kind') == 'tech':
                return True  # consume the click; tech cancel not offered here
            building = button['building']
            unit_type = button['unit_type']
            success, _ = self.game.production_manager.cancel_queued(building, unit_type)
            if not success and building.current_production \
                    and building.current_production.get('unit_type') == unit_type:
                success, _ = self.game.production_manager.cancel_production(building)
            sound = getattr(self.game, 'sound_manager', None)
            if sound:
                sound.play_ui_click() if success else sound.play_error()
            return True
        return False

    def handle_hover(self, mouse_pos):
        """Handle hover effects for production buttons"""
        self.hover_production_button = None
        for i, button in enumerate(self.unit_production_buttons):
            if button['rect'].collidepoint(mouse_pos):
                self.hover_production_button = i
                break
