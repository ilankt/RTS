import pygame
import json
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT, BUILDING_BUTTON_HEIGHT, BUILDING_ICON_SIZE
from systems.upgrade_effects import has_required_buildings
from utils.debug_logger import debug_log


class BuildingMenu:
    """Manages the two-tier building selection menu"""
    
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.name_font = pygame.font.Font(None, 17)
        self.cost_font = pygame.font.Font(None, 16)
        
        # Menu state
        self.show_menu = False
        self.show_category = None  # None, 'economy', or 'military'
        self.building_buttons = []
        self.selected_building_type = None
        self.building_buttons_populated = False
        
        # Category button rects
        self.category_buttons = {}
        self.cancel_menu_rect = None
        
        # Pre-load building icons
        self.building_icons = {}
        self.icon_size = BUILDING_ICON_SIZE
        self._load_building_icons()
        
        # Load category icons
        self.category_icons = {}
        self._load_category_icons()
    
    # Tile-grid geometry (§8.2 GUI rework)
    TILE_W = 86
    TILE_H = 92
    TILE_GAP = 4
    TILE_ICON = 38
    GRID_COLS = 2
    GRID_TOP = 32

    def _wrap_name(self, name, max_width):
        """Split a display name into lines that fit the tile width."""
        words = name.split()
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.name_font.size(candidate)[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    RESOURCE_LETTER = {"gold": "G", "wood": "W", "stone": "S", "food": "F"}

    def _compact_costs(self, building):
        """"150G 75W" — short enough to never clip a tile."""
        costs = building.get('costs', {})
        return " ".join(
            f"{amount}{self.RESOURCE_LETTER.get(resource, resource[0].upper())}"
            for resource, amount in costs.items() if amount > 0
        )

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
                    sprite_path = building.get('sprite', f"assets/sprites/Buildings/{building['name'].title()}.png")
                    building_sprite = pygame.image.load(sprite_path).convert_alpha()
                    # Pre-scale to icon size
                    building_icon = pygame.transform.scale(building_sprite, (self.icon_size, self.icon_size))
                    self.building_icons[building['name']] = building_icon
                except:
                    # Create placeholder if sprite not found
                    placeholder = pygame.Surface((self.icon_size, self.icon_size), pygame.SRCALPHA)
                    placeholder.fill((100, 100, 100, 200))
                    self.building_icons[building['name']] = placeholder
        except:
            pass
    
    def _load_category_icons(self):
        """Load building category icons"""
        try:
            self.category_icons['build_econ'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/build_econ_icon.png").convert_alpha(), (70, 70))
            self.category_icons['build_mil'] = pygame.transform.smoothscale(
                pygame.image.load("assets/ui/build_mil_icon.png").convert_alpha(), (70, 70))
        except:
            # Icons not loaded yet, will use text buttons as fallback
            pass
    
    def open_menu(self):
        """Open the building menu"""
        self.show_menu = True
        self.show_category = None
        self.building_buttons = []
        self.building_buttons_populated = False
    
    def close_menu(self):
        """Close the building menu"""
        self.show_menu = False
        self.show_category = None
        self.selected_building_type = None
        self.building_buttons = []
        self.building_buttons_populated = False
    
    def draw(self, screen):
        """Draw the building menu if open"""
        if not self.show_menu:
            return
            
        # Define UI panel area (same as main UI panel)
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT + 8
        ui_width = MINIMAP_WIDTH - 16
        ui_height = SCREEN_HEIGHT - MINIMAP_HEIGHT - 40
        
        # Opaque menu surface (semi-transparency let the unit panel behind
        # bleed through as ghost boxes)
        menu_surface = pygame.Surface((ui_width, ui_height), pygame.SRCALPHA)
        menu_surface.fill((30, 30, 30, 255))
        
        # Draw border
        pygame.draw.rect(menu_surface, (100, 100, 100), (0, 0, ui_width, ui_height), 2)
        
        if self.show_category is None:
            # Show category selection
            title_text = self.small_font.render("Building Categories", True, (255, 255, 255))
            menu_surface.blit(title_text, (8, 8))
        
            # Category buttons
            button_width = 100
            button_height = 80
            button_spacing = 10
            start_x = (ui_width - 2 * button_width - button_spacing) // 2
            start_y = 40
            
            # Economy category button
            econ_rect = pygame.Rect(start_x, start_y, button_width, button_height)
            econ_color = (50, 80, 50)
            pygame.draw.rect(menu_surface, econ_color, econ_rect)
            pygame.draw.rect(menu_surface, (150, 150, 150), econ_rect, 2)
            
            # Draw icon if available
            if 'build_econ' in self.category_icons:
                icon_rect = self.category_icons['build_econ'].get_rect()
                icon_rect.centerx = econ_rect.centerx
                icon_rect.centery = econ_rect.centery - 10
                menu_surface.blit(self.category_icons['build_econ'], icon_rect)
            else:
                # Fallback to text
                text = self.button_font.render("Economy", True, (255, 255, 255))
                text_rect = text.get_rect()
                text_rect.center = econ_rect.center
                menu_surface.blit(text, text_rect)
            
            # Military category button
            mil_rect = pygame.Rect(start_x + button_width + button_spacing, start_y, button_width, button_height)
            mil_color = (80, 50, 50)
            pygame.draw.rect(menu_surface, mil_color, mil_rect)
            pygame.draw.rect(menu_surface, (150, 150, 150), mil_rect, 2)
            
            # Draw icon if available
            if 'build_mil' in self.category_icons:
                icon_rect = self.category_icons['build_mil'].get_rect()
                icon_rect.centerx = mil_rect.centerx
                icon_rect.centery = mil_rect.centery - 10
                menu_surface.blit(self.category_icons['build_mil'], icon_rect)
            else:
                # Fallback to text
                text = self.button_font.render("Military", True, (255, 255, 255))
                text_rect = text.get_rect()
                text_rect.center = mil_rect.center
                menu_surface.blit(text, text_rect)
            
            # Store button rects for click detection
            self.category_buttons['economy'] = pygame.Rect(ui_x + econ_rect.x, ui_y + econ_rect.y, 
                                                         econ_rect.width, econ_rect.height)
            self.category_buttons['military'] = pygame.Rect(ui_x + mil_rect.x, ui_y + mil_rect.y,
                                                          mil_rect.width, mil_rect.height)
        else:
            # Show buildings for selected category
            title = "Economy Buildings" if self.show_category == 'economy' else "Military Buildings"
            title_text = self.small_font.render(title, True, (255, 255, 255))
            menu_surface.blit(title_text, (8, 8))
        
        # Draw building buttons with icons (use pre-populated button list)
        if not self.building_buttons_populated:
            self._populate_building_buttons()
        
        padding = 6  # Still needed for cancel button
        human_player = self.game.players[0]
        
        # Draw the tile grid (§8.2 GUI rework: icon tiles instead of clipped
        # text rows — 8 entries fit on screen with room to spare)
        hovered_info = None
        for button_info in self.building_buttons:
            building = button_info['building']

            # Re-check availability (resources/building prerequisites may have changed)
            can_build_now, reason = self._availability(human_player, building)
            button_info['can_afford'] = can_build_now
            button_info['reason'] = reason
            tile = button_info['draw_rect']
            is_hovered = button_info['click_rect'].collidepoint(pygame.mouse.get_pos())

            if can_build_now:
                fill, border, name_color = (42, 52, 42), (110, 160, 110), (235, 235, 235)
            elif reason.startswith("Requires"):
                fill, border, name_color = (45, 42, 32), (120, 105, 60), (170, 155, 110)
            else:
                fill, border, name_color = (50, 38, 38), (140, 90, 90), (190, 140, 130)
            if is_hovered:
                fill = tuple(min(255, c + 25) for c in fill)
                border = (240, 240, 240)

            pygame.draw.rect(menu_surface, fill, tile, border_radius=4)
            pygame.draw.rect(menu_surface, border, tile, 2, border_radius=4)

            # Icon centered at the top of the tile, dimmed when unavailable
            if building['name'] in self.building_icons:
                icon = self.building_icons[building['name']]
                if icon.get_width() != self.TILE_ICON:
                    icon = pygame.transform.smoothscale(icon, (self.TILE_ICON, self.TILE_ICON))
                if not can_build_now:
                    icon = icon.copy()
                    icon.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
                menu_surface.blit(icon, (tile.centerx - self.TILE_ICON // 2, tile.y + 5))

            # Name, wrapped to at most two lines that actually fit the tile
            display_name = building.get('display_name', building['name'].replace('_', ' ').title())
            name_y = tile.y + 6 + self.TILE_ICON
            for line in self._wrap_name(display_name, tile.width - 8)[:2]:
                text = self.name_font.render(line, True, name_color)
                menu_surface.blit(text, (tile.centerx - text.get_width() // 2, name_y))
                name_y += 14

            # Compact cost line ("150G 75W") that never clips
            cost_line = self._compact_costs(building)
            if cost_line:
                cost_color = (200, 200, 160) if can_build_now else (200, 120, 110)
                text = self.cost_font.render(cost_line, True, cost_color)
                menu_surface.blit(text, (tile.centerx - text.get_width() // 2, tile.bottom - 16))

            if is_hovered:
                hovered_info = (building, reason)

        # Tooltip last so no tile draws over it
        if hovered_info is not None:
            self._draw_building_tooltip(menu_surface, hovered_info[0], hovered_info[1], ui_width, ui_height)
        
        # Cancel button at bottom with improved styling
        cancel_button_rect = pygame.Rect(padding, ui_height - BUILDING_BUTTON_HEIGHT - padding, 
                                       ui_width - 2*padding, BUILDING_BUTTON_HEIGHT)
        cancel_color = (100, 50, 50)
        pygame.draw.rect(menu_surface, cancel_color, cancel_button_rect)
        pygame.draw.rect(menu_surface, (200, 100, 100), cancel_button_rect, 2)
        
        # Draw cancel text with "Back" if in category, otherwise "Cancel"
        cancel_text = "Back" if self.show_category else "Cancel"
        text = self.button_font.render(cancel_text, True, (255, 255, 255))
        text_rect = text.get_rect()
        text_rect.center = cancel_button_rect.center
        menu_surface.blit(text, text_rect)
        
        # Store cancel button rect for click detection
        self.cancel_menu_rect = pygame.Rect(ui_x + cancel_button_rect.x, 
                                          ui_y + cancel_button_rect.y,
                                          cancel_button_rect.width, 
                                          cancel_button_rect.height)
        
        # Blit the menu surface to the screen
        screen.blit(menu_surface, (ui_x, ui_y))
    
    def handle_click(self, pos):
        """Handle mouse clicks on the building menu"""
        if not self.show_menu:
            return False
            
        # Check cancel button
        if hasattr(self, 'cancel_menu_rect') and self.cancel_menu_rect.collidepoint(pos):
            if self.show_category:
                # Go back to category selection
                self.show_category = None
                self.building_buttons = []
                self.building_buttons_populated = False
            else:
                # Close menu entirely
                self.close_menu()
            return True
        
        # Check category buttons if no category selected
        if self.show_category is None and hasattr(self, 'category_buttons'):
            for category, rect in self.category_buttons.items():
                if rect.collidepoint(pos):
                    self.show_category = category
                    self.building_buttons_populated = False
                    self._populate_building_buttons()
                    return True
        
        # Check building buttons if category is selected
        if self.show_category is not None:
            for i, button_info in enumerate(self.building_buttons):
                if button_info['click_rect'].collidepoint(pos):
                    debug_log.log(
                        f"Clicked on building {i}: {button_info['building']['name']}, can_afford: {button_info['can_afford']}",
                        "UI",
                    )
                    if button_info['can_afford']:
                        # Select building and notify game
                        building_data = button_info['building']
                        self.close_menu()
                        # Notify game to enter building placement mode
                        self.game.enter_building_placement_mode(building_data)
                        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                            self.game.sound_manager.play_ui_click()
                        return True
                    else:
                        debug_log.log(f"Cannot afford {button_info['building']['name']}", "UI")
                        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                            self.game.sound_manager.play_error()
                        return True
        
        return False
    
    def _populate_building_buttons(self):
        """Populate building buttons when menu is opened"""
        try:
            # Load building data
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            
            # Define building categories
            economy_buildings = ['farm', 'house', 'lumbermill', 'mine', 'quarry']
            military_buildings = ['barracks', 'stable', 'blacksmith', 'siege_workshop', 'watchtower',
                                  'wooden_wall', 'wall', 'gate']
            
            # Filter buildings based on category
            if self.show_category == 'economy':
                building_order = economy_buildings
            elif self.show_category == 'military':
                building_order = military_buildings
            else:
                # If no category selected, don't show any buildings
                self.building_buttons = []
                self.building_buttons_populated = True
                return
            
            buildable_buildings = []
            for building_name in building_order:
                for building in buildings_data:
                    if building['name'] == building_name and building.get('buildable', True):
                        buildable_buildings.append(building)
                        break
            
            # Clear and repopulate buttons
            self.building_buttons = []
            
            # Define UI panel area (same as main UI panel)
            ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
            ui_y = MINIMAP_HEIGHT + 8
            ui_width = MINIMAP_WIDTH - 16
            
            human_player = self.game.players[0]

            # Tile grid (§8.2): GRID_COLS columns of fixed-size tiles
            grid_x = (ui_width - (self.GRID_COLS * self.TILE_W + (self.GRID_COLS - 1) * self.TILE_GAP)) // 2

            for i, building in enumerate(buildable_buildings):
                row, col = divmod(i, self.GRID_COLS)
                button_rect = pygame.Rect(
                    grid_x + col * (self.TILE_W + self.TILE_GAP),
                    self.GRID_TOP + row * (self.TILE_H + self.TILE_GAP),
                    self.TILE_W, self.TILE_H,
                )

                # Check if player can build now
                can_afford, reason = self._availability(human_player, building)

                # Store button info for click detection AND drawing
                self.building_buttons.append({
                    'click_rect': pygame.Rect(ui_x + button_rect.x, ui_y + button_rect.y, button_rect.width, button_rect.height),
                    'draw_rect': button_rect,  # Store visual rectangle for consistent drawing
                    'building': building,
                    'can_afford': can_afford,
                    'reason': reason,
                    'visible': True
                })
                
            self.building_buttons_populated = True
        except:
            # If loading fails, ensure buttons list exists
            self.building_buttons = []
            self.building_buttons_populated = False
    
    def _can_afford(self, player, building):
        """Check if player can afford the building"""
        costs = building.get('costs', {})
        return all(player.resources.get(resource, 0) >= amount for resource, amount in costs.items())

    def _availability(self, player, building):
        """Return (can_build, reason) for a building button."""
        if getattr(self.game, "is_building_disabled", None) \
                and self.game.is_building_disabled(building.get('name')):
            return False, "Disabled by mutator"
        requirements = building.get('requires', [])
        if requirements and not has_required_buildings(self.game, player, requirements):
            return False, "Requires " + ", ".join(r.replace('_', ' ').title() for r in requirements)
        if not self._can_afford(player, building):
            return False, "Insufficient resources"
        return True, "Ready"

    def _format_costs(self, building):
        """Format nested building costs for display."""
        costs = building.get('costs', {})
        if not costs:
            return ""
        return ", ".join(
            f"{resource.title()}: {amount}"
            for resource, amount in costs.items()
            if amount > 0
        )

    def _draw_building_tooltip(self, surface, building, reason, ui_width, ui_height):
        tooltip_h = 95
        tooltip_rect = pygame.Rect(6, ui_height - BUILDING_BUTTON_HEIGHT - tooltip_h - 12, ui_width - 12, tooltip_h)
        pygame.draw.rect(surface, (12, 12, 12), tooltip_rect)
        pygame.draw.rect(surface, (120, 120, 120), tooltip_rect, 1)

        costs = self._format_costs(building)
        lines = [
            building.get('role', ''),
            f"Cost: {costs}" if costs else "",
            reason,
        ]
        if building.get('strong_against'):
            lines.append("Strong: " + ", ".join(x.title() for x in building['strong_against'][:2]))
        if building.get('weak_against'):
            lines.append("Weak: " + ", ".join(x.title() for x in building['weak_against'][:2]))

        y = tooltip_rect.y + 6
        for line in [line for line in lines if line][:5]:
            rendered = self.small_font.render(line[:28], True, (230, 230, 230))
            surface.blit(rendered, (tooltip_rect.x + 6, y))
            y += 17
