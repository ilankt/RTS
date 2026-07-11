import pygame
from entities import ConstructionSite


class UnitPanel:
    """The compact selection header at the top of the sidebar (§8.2.1).

    Budget: everything fits above the command card's chips row
    (HEADER_HEIGHT px) — portrait + name + hp bar + a few dense stat lines,
    or grouped icons with count badges for multi-selections.
    """

    HEADER_HEIGHT = 118

    def __init__(self, game, icon_loader=None):
        self.game = game
        self.icon_loader = icon_loader
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.stat_font = pygame.font.Font(None, 18)
        self.dense_font = pygame.font.Font(None, 16)
        self._building_icon_cache = {}
        
        # Pre-load and cache unit panel icons for performance
        self.unit_panel_icons = {}
        self._load_unit_panel_icons()
        
    def _load_unit_panel_icons(self):
        """Pre-load and cache unit panel icons at different sizes for performance"""
        # Define the unit types and required sizes
        unit_types = ['worker', 'warrior', 'archer', 'spearman', 'cavalry', 'ram', 'healer']
        sizes = {
            'single': 64,  # For single unit selection
            'multi': 48,   # Single-selection portrait
            'group': 40    # Multi-selection grouped icons
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
        
        for obj in all_objects:
            if obj.selected:
                # Check if ConstructionSite
                if isinstance(obj, ConstructionSite):
                    return {
                        "name": f"{obj.building_type.title()} (Under Construction)",
                        "type": "Construction",
                        "owner": obj.player.name if obj.player else "Unknown",
                        "player_color": obj.player.color if obj.player else (100, 100, 100),
                        "object": obj
                    }
                
                # Regular object info
                obj_type = obj.__class__.__name__
                
                # Determine type for display
                if obj in self.game.units:
                    display_type = "Unit"
                elif obj in self.game.buildings:
                    display_type = "Building"
                elif obj in self.game.resources:
                    display_type = "Resource"
                else:
                    display_type = obj_type
                
                info = {
                    "name": getattr(obj, "display_name", obj.name if hasattr(obj, 'name') else obj_type),
                    "type": display_type,
                    "owner": obj.player.name if hasattr(obj, 'player') and obj.player else "Neutral",
                    "player_color": obj.player.color if hasattr(obj, 'player') and obj.player else (100, 100, 100),
                    "object": obj
                }
                
                # Add HP if available
                if hasattr(obj, 'hp'):
                    info["hp"] = f"{obj.hp}"
                
                return info
        
        return None
    
    def draw_panel(self, panel_surface, ui_width, selected_objects):
        """Draw the compact selection header. Returns (selected_info, header_h)."""
        if len(selected_objects) > 1:
            self._draw_multi_selection(panel_surface, selected_objects)
            return None, self.HEADER_HEIGHT
        elif len(selected_objects) == 1:
            selected_info = self.get_selected_object_info()
            return self._draw_single_selection(panel_surface, ui_width, selected_info)
        else:
            no_selection_text = self.small_font.render("No Selection", True, (120, 120, 120))
            panel_surface.blit(no_selection_text, (10, 14))
            return None, self.HEADER_HEIGHT
    
    def _draw_portrait(self, panel_surface, icon):
        """48px portrait at the top-left of the header."""
        if icon is not None:
            panel_surface.blit(icon, (8, 6))
        else:
            placeholder = pygame.Surface((48, 48))
            placeholder.fill((80, 80, 90))
            pygame.draw.rect(placeholder, (140, 140, 150), (0, 0, 48, 48), 2)
            panel_surface.blit(placeholder, (8, 6))

    def _draw_header_bar(self, panel_surface, current, maximum, y, color=None):
        """Slim hp/progress bar right of the portrait, value text inside."""
        bar = pygame.Rect(62, y, 110, 12)
        fraction = (current / maximum) if maximum > 0 else 0
        fraction = max(0.0, min(1.0, fraction))
        pygame.draw.rect(panel_surface, (55, 55, 55), bar)
        fill_color = color or self._get_health_color(fraction)
        pygame.draw.rect(panel_surface, fill_color, (bar.x, bar.y, int(bar.width * fraction), bar.height))
        pygame.draw.rect(panel_surface, (105, 105, 105), bar, 1)
        text = self.dense_font.render(f"{int(current)}/{int(maximum)}", True, (255, 255, 255))
        panel_surface.blit(text, (bar.centerx - text.get_width() // 2,
                                  bar.centery - text.get_height() // 2))

    def _draw_stat_lines(self, panel_surface, lines, start_y=60, pitch=14):
        for text, color in lines[:4]:
            rendered = self.dense_font.render(text[:30], True, color)
            panel_surface.blit(rendered, (8, start_y))
            start_y += pitch

    def _draw_single_selection(self, panel_surface, ui_width, selected_info):
        """Compact single-selection header: portrait row + dense stat lines."""
        if not selected_info:
            return None, self.HEADER_HEIGHT

        obj = selected_info["object"]
        name_color = selected_info["player_color"] if selected_info["owner"] != "Neutral" \
            else (220, 220, 220)
        name_text = self.small_font.render(selected_info["name"][:16], True, name_color)
        panel_surface.blit(name_text, (62, 8))

        lines = []
        if selected_info["type"] == "Unit":
            icon = self.unit_panel_icons.get(obj.name, {}).get('multi')
            self._draw_portrait(panel_surface, icon)
            self._draw_header_bar(panel_surface, obj.hp, self._get_unit_max_hp(obj), 30)

            if hasattr(obj, 'can_attack') and obj.can_attack and obj.name != 'worker':
                lines.append((
                    f"DMG {obj.get_effective_min_damage()}-{obj.get_effective_max_damage()}"
                    f" {obj.attack_type.title()}  RNG {int(obj.get_effective_attack_range())}",
                    (255, 200, 100)))
            lines.append((
                f"ARM {obj.get_effective_armor_value()} {obj.armor_type.title()}"
                + (f"  SPD {obj.attack_speed:.1f}/s" if getattr(obj, 'can_attack', False)
                   and obj.name != 'worker' else ""),
                (200, 200, 200)))
            strong = [t for t in getattr(obj, 'strong_against', ()) or () if t]
            weak = [t for t in getattr(obj, 'weak_against', ()) or () if t]
            if strong:
                lines.append(("Strong: " + ", ".join(
                    t.replace('_', ' ').title() for t in strong), (120, 230, 120)))
            if weak:
                lines.append(("Weak: " + ", ".join(
                    t.replace('_', ' ').title() for t in weak), (235, 140, 110)))
            if obj.name == "worker" and getattr(obj, 'resource_amount', 0) > 0:
                resource = (obj.resource_type or 'unknown').replace('_', ' ').title()
                lines.append((f"Carrying: {int(obj.resource_amount)} {resource}",
                              (255, 200, 100)))
        elif selected_info["type"] == "Construction":
            self._draw_portrait(panel_surface, None)
            if isinstance(obj, ConstructionSite):
                progress = obj.construction_progress / obj.construction_duration
                self._draw_header_bar(panel_surface, progress * 100, 100, 30,
                                      color=(80, 130, 220))
                lines.append((f"Building... {int(progress * 100)}%", (180, 200, 240)))
        else:
            self._draw_portrait(panel_surface, self._get_building_icon(obj))
            if hasattr(obj, 'hp'):
                self._draw_header_bar(panel_surface, obj.hp, self._get_object_max_hp(obj), 30)
            if selected_info["type"] == "Building" and getattr(obj, 'can_attack', False):
                lines.append((
                    f"DMG {obj.get_effective_min_damage()}-{obj.get_effective_max_damage()}"
                    f" {obj.attack_type.title()}  RNG {int(obj.get_effective_attack_range())}",
                    (255, 200, 100)))
                lines.append((f"ARM {obj.get_effective_armor_value()} {obj.armor_type.title()}"
                              f"  SPD {obj.attack_speed:.1f}/s", (200, 200, 200)))
            if selected_info["type"] == "Resource":
                lines.append((f"Remaining: {int(obj.amount_remaining)}", (100, 255, 100)))

        self._draw_stat_lines(panel_surface, lines)
        return selected_info, self.HEADER_HEIGHT

    def _draw_multi_selection(self, panel_surface, selected_objects):
        """Compact multi-selection header: grouped 40px icons + count badges
        + aggregate health bars, two rows max (7 unit types exist)."""
        groups = self.group_selected_units(selected_objects)
        unit_count = sum(len(units) for _n, units in groups)
        formation = getattr(self.game.selection_manager, 'formation_type', 'ring')
        title = self.small_font.render(
            f"{unit_count} selected — {formation.title()} (F)", True, (230, 230, 230))
        panel_surface.blit(title, (8, 8))

        icon_size = 40
        icon_spacing = 4
        icons_per_row = 4
        start_x = 8
        start_y = 28

        for i, (name, units) in enumerate(groups):
            row = i // icons_per_row
            col = i % icons_per_row
            x = start_x + col * (icon_size + icon_spacing)
            y = start_y + row * (icon_size + icon_spacing + 8)

            cached = self.unit_panel_icons.get(name, {}).get('group')
            if cached is not None:
                panel_surface.blit(cached, (x, y))
            else:
                placeholder = pygame.Surface((icon_size, icon_size))
                placeholder.fill((100, 100, 100))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                panel_surface.blit(placeholder, (x, y))

            count_text = self.dense_font.render(f"x{len(units)}", True, (255, 255, 255))
            badge = pygame.Rect(x + icon_size - count_text.get_width() - 5, y + 1,
                                count_text.get_width() + 4, count_text.get_height() + 1)
            pygame.draw.rect(panel_surface, (0, 0, 0), badge)
            panel_surface.blit(count_text, (badge.x + 2, badge.y + 1))

            bar_y = y + icon_size + 1
            total_hp = sum(u.hp for u in units)
            total_max = sum(self._get_unit_max_hp(u) for u in units)
            hp_percentage = total_hp / total_max if total_max > 0 else 0
            pygame.draw.rect(panel_surface, (60, 60, 60), (x, bar_y, icon_size, 4))
            fill_width = int(icon_size * hp_percentage)
            pygame.draw.rect(panel_surface, self._get_health_color(hp_percentage),
                             (x, bar_y, fill_width, 4))

    def group_selected_units(self, selected_objects):
        """Selected units grouped by type, biggest group first: [(name, [units])]."""
        groups = {}
        for obj in selected_objects:
            if obj in self.game.units:
                groups.setdefault(obj.name, []).append(obj)
        return sorted(groups.items(), key=lambda item: -len(item[1]))
    
    def _get_building_icon(self, obj):
        """48px building portrait via the shared icon loader (cached)."""
        name = getattr(obj, 'name', None)
        if name is None or self.icon_loader is None:
            return None
        cached = self._building_icon_cache.get(name)
        if cached is not None:
            return cached
        source = self.icon_loader.building_icons.get(name)
        if source is None:
            return None
        icon = pygame.transform.smoothscale(source, (48, 48))
        self._building_icon_cache[name] = icon
        return icon

    def _get_object_max_hp(self, obj):
        """Max hp for buildings (falls back to current hp)."""
        template = self.game.game_data.get("buildings", {}).get(getattr(obj, 'name', None))
        if template is not None and hasattr(template, 'hp'):
            return template.hp
        return max(getattr(obj, 'hp', 1), 1)

    def _get_unit_max_hp(self, unit):
        """Get the maximum HP for a unit from cached game data."""
        template = self.game.game_data["units"].get(unit.name)
        if template:
            return template.hp
        return 100
    
    def _get_health_color(self, hp_percentage):
        """Get health bar color based on HP percentage"""
        if hp_percentage >= 0.75:
            return (0, 200, 0)  # Green
        elif hp_percentage >= 0.5:
            return (200, 200, 0)  # Yellow
        elif hp_percentage >= 0.25:
            return (200, 200, 0)  # Yellow
        else:
            return (200, 0, 0)  # Red
