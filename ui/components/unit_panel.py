import pygame
from entities import ConstructionSite
from ui import fonts as ui_fonts


class UnitPanel:
    """The compact selection header at the top of the sidebar (§8.2.1).

    Budget: everything fits above the command card's chips row
    (HEADER_HEIGHT px) — portrait + name + hp bar + a few dense stat lines,
    or grouped icons with count badges for multi-selections.
    """

    HEADER_HEIGHT = 118
    PORTRAIT = 64          # §8.2.2: was 48 — "the icon is way too small"

    def __init__(self, game, icon_loader=None):
        self.game = game
        self.icon_loader = icon_loader
        # §8.2.2 shared fonts (clean system face, bigger than the old default)
        self.name_font = ui_fonts.title()       # selection name
        self.small_font = ui_fonts.body()        # multi-select title, misc
        self.stat_font = ui_fonts.font(17)       # dense stat lines
        self.dense_font = ui_fonts.bar_text()    # value inside the hp bar
        self._building_icon_cache = {}
        
        # Pre-load and cache unit panel icons for performance
        self.unit_panel_icons = {}
        self._load_unit_panel_icons()
        
    def _load_unit_panel_icons(self):
        """Load unit portrait sources; the header scales them on demand
        (§8.2.2 portrait-centric header wants several sizes)."""
        unit_types = ['worker', 'warrior', 'archer', 'spearman', 'cavalry', 'ram', 'healer']
        sizes = {'single': 64, 'multi': 48, 'group': 40}
        self._unit_icon_sources = {}
        self._unit_icon_cache = {}

        for unit_type in unit_types:
            self.unit_panel_icons[unit_type] = {}
            icon_path = f"assets/ui/Units/{unit_type}_icon.png"
            try:
                original_icon = pygame.image.load(icon_path).convert_alpha()
                self._unit_icon_sources[unit_type] = original_icon
                for size_name, size_pixels in sizes.items():
                    self.unit_panel_icons[unit_type][size_name] = \
                        pygame.transform.smoothscale(original_icon, (size_pixels, size_pixels))
            except Exception:
                for size_name, size_pixels in sizes.items():
                    placeholder = pygame.Surface((size_pixels, size_pixels))
                    placeholder.fill((100, 100, 100))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, size_pixels, size_pixels), 2)
                    self.unit_panel_icons[unit_type][size_name] = placeholder

    def _unit_icon(self, name, size):
        """A unit portrait scaled to `size` px, cached (§8.2.2)."""
        key = (name, size)
        cached = self._unit_icon_cache.get(key)
        if cached is None:
            source = self._unit_icon_sources.get(name)
            if source is None:
                return self.unit_panel_icons.get(name, {}).get('single')
            cached = pygame.transform.smoothscale(source, (size, size))
            self._unit_icon_cache[key] = cached
        return cached
    
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
    
    def _draw_overlay_bar(self, panel_surface, current, maximum, rect, color=None):
        """hp/progress bar drawn OVER the bottom of the sprite (§8.2.2: the
        HP overlays the portrait at its base), value text centered inside."""
        fraction = (current / maximum) if maximum > 0 else 0
        fraction = max(0.0, min(1.0, fraction))
        backing = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        backing.fill((0, 0, 0, 170))
        panel_surface.blit(backing, rect.topleft)
        fill_color = color or self._get_health_color(fraction)
        pygame.draw.rect(panel_surface, fill_color,
                         (rect.x, rect.y, int(rect.width * fraction), rect.height))
        pygame.draw.rect(panel_surface, (30, 30, 30), rect, 1)
        text = self.dense_font.render(f"{int(current)}/{int(maximum)}", True, (255, 255, 255))
        panel_surface.blit(text, (rect.centerx - text.get_width() // 2,
                                  rect.centery - text.get_height() // 2))

    def _draw_stat_lines(self, panel_surface, lines, start_y, pitch=15, max_lines=3):
        for text, color in lines[:max_lines]:
            rendered = self.stat_font.render(text, True, color)
            if rendered.get_width() > 178:
                rendered = pygame.transform.smoothscale(
                    rendered, (178, rendered.get_height()))
            panel_surface.blit(rendered, (6, start_y))
            start_y += pitch

    def _single_selection_model(self, selected_info):
        """Return (portrait_icon, hp_tuple_or_None, stat_lines) for the
        current single selection. hp_tuple = (current, maximum, color)."""
        obj = selected_info["object"]
        stype = selected_info["type"]
        lines = []

        if stype == "Unit":
            hp = (obj.hp, self._get_unit_max_hp(obj), None)
            if getattr(obj, 'can_attack', False) and obj.name != 'worker':
                lines.append((
                    f"DMG {obj.get_effective_min_damage()}-{obj.get_effective_max_damage()}"
                    f" {obj.attack_type.title()}  RNG {int(obj.get_effective_attack_range())}",
                    (255, 200, 100)))
            lines.append((
                f"ARM {obj.get_effective_armor_value()} {obj.armor_type.title()}"
                + (f"  SPD {obj.attack_speed:.1f}/s" if getattr(obj, 'can_attack', False)
                   and obj.name != 'worker' else ""),
                (200, 200, 200)))
            strong = [t.replace('_', ' ').title()
                      for t in getattr(obj, 'strong_against', ()) or () if t]
            weak = [t.replace('_', ' ').title()
                    for t in getattr(obj, 'weak_against', ()) or () if t]
            if strong or weak:
                parts = []
                if strong:
                    parts.append("Str " + "/".join(strong[:2]))
                if weak:
                    parts.append("Wk " + "/".join(weak[:2]))
                lines.append(("  ".join(parts), (150, 210, 150)))
            if obj.name == "worker" and getattr(obj, 'resource_amount', 0) > 0:
                res = (obj.resource_type or 'unknown').replace('_', ' ').title()
                lines.append((f"Carrying: {int(obj.resource_amount)} {res}", (255, 200, 100)))
            return 'unit', hp, lines  # caller resolves the icon at the sprite size

        if stype == "Construction":
            hp = None
            if isinstance(obj, ConstructionSite):
                progress = obj.construction_progress / obj.construction_duration
                hp = (progress * 100, 100, (80, 130, 220))
                lines.append((f"Building... {int(progress * 100)}%", (180, 200, 240)))
            return None, hp, lines

        # Building or resource
        hp = (obj.hp, self._get_object_max_hp(obj), None) if hasattr(obj, 'hp') else None
        if stype == "Building" and getattr(obj, 'can_attack', False):
            lines.append((
                f"DMG {obj.get_effective_min_damage()}-{obj.get_effective_max_damage()}"
                f" {obj.attack_type.title()}  RNG {int(obj.get_effective_attack_range())}",
                (255, 200, 100)))
            lines.append((f"ARM {obj.get_effective_armor_value()} {obj.armor_type.title()}"
                          f"  SPD {obj.attack_speed:.1f}/s", (200, 200, 200)))
        if stype == "Resource":
            lines.append((f"Remaining: {int(obj.amount_remaining)}", (100, 255, 100)))
        return ('building' if stype == "Building" else None), hp, lines

    def _draw_single_selection(self, panel_surface, ui_width, selected_info):
        """§8.2.2 portrait-centric header: name on top, a big centered sprite
        below it, the HP bar overlaid at the base of the sprite, and any stat
        lines beneath. The sprite shrinks a little when there are stats so
        everything stays inside the fixed header height."""
        if not selected_info:
            return None, self.HEADER_HEIGHT

        obj = selected_info["object"]
        stype = selected_info["type"]
        cx = ui_width // 2

        icon_kind, hp, lines = self._single_selection_model(selected_info)

        # Name centered at the top.
        name_color = selected_info["player_color"] if selected_info["owner"] != "Neutral" \
            else (225, 225, 225)
        name_text = self.name_font.render(selected_info["name"][:18], True, name_color)
        if name_text.get_width() > ui_width - 8:
            name_text = pygame.transform.smoothscale(
                name_text, (ui_width - 8, name_text.get_height()))
        panel_surface.blit(name_text, (cx - name_text.get_width() // 2, 2))
        sprite_top = 2 + name_text.get_height() + 2

        # Sprite size: big with no stats, a touch smaller when stats follow.
        avail = self.HEADER_HEIGHT - sprite_top - 2
        sprite = min(84, avail) if not lines else min(64, avail - 2 * 15)
        sprite = max(40, sprite)

        # Resolve the portrait icon at the chosen size.
        if stype == "Unit":
            icon = self._unit_icon(obj.name, sprite)
        elif icon_kind == 'building':
            icon = self._get_building_icon(obj, sprite)
        elif stype != "Construction":
            icon = self._get_building_icon(obj, sprite)  # resource: no icon -> None
        else:
            icon = None

        sprite_rect = pygame.Rect(cx - sprite // 2, sprite_top, sprite, sprite)
        if icon is not None:
            panel_surface.blit(icon, sprite_rect.topleft)
        else:
            placeholder = pygame.Surface((sprite, sprite))
            placeholder.fill((80, 80, 90))
            pygame.draw.rect(placeholder, (140, 140, 150), (0, 0, sprite, sprite), 2)
            panel_surface.blit(placeholder, sprite_rect.topleft)

        # HP overlaid across the base of the sprite.
        if hp is not None:
            bar_h = 15
            bar_rect = pygame.Rect(sprite_rect.x, sprite_rect.bottom - bar_h,
                                   sprite_rect.width, bar_h)
            self._draw_overlay_bar(panel_surface, hp[0], hp[1], bar_rect, hp[2])

        if lines:
            self._draw_stat_lines(panel_surface, lines, start_y=sprite_rect.bottom + 3)
        return selected_info, self.HEADER_HEIGHT

    def _draw_multi_selection(self, panel_surface, selected_objects):
        """Compact multi-selection header: grouped 40px icons + count badges
        + aggregate health bars, two rows max. Groups units by type, then
        buildings by type (§8.2.1 Phase B: buildings multi-select too)."""
        groups = [('unit', name, members) for name, members
                  in self.group_selected_units(selected_objects)]
        building_groups = {}
        for obj in selected_objects:
            if obj in self.game.buildings:
                building_groups.setdefault(obj.name, []).append(obj)
        groups += [('building', name, members) for name, members
                   in sorted(building_groups.items(), key=lambda kv: -len(kv[1]))]

        unit_count = sum(len(m) for kind, _n, m in groups if kind == 'unit')
        total = sum(len(m) for _k, _n, m in groups)
        if unit_count:
            formation = getattr(self.game.selection_manager, 'formation_type', 'ring')
            title_text = f"{total} selected — {formation.title()} (F)"
        else:
            title_text = f"{total} buildings selected"
        title = self.small_font.render(title_text, True, (230, 230, 230))
        panel_surface.blit(title, (8, 8))

        icon_size = 40
        icon_spacing = 4
        icons_per_row = 4
        start_x = 8
        start_y = 28

        for i, (kind, name, members) in enumerate(groups):
            row = i // icons_per_row
            col = i % icons_per_row
            x = start_x + col * (icon_size + icon_spacing)
            y = start_y + row * (icon_size + icon_spacing + 8)

            if kind == 'unit':
                icon = self.unit_panel_icons.get(name, {}).get('group')
            else:
                icon = self._get_building_icon(members[0], size=icon_size)
            if icon is not None:
                panel_surface.blit(icon, (x, y))
            else:
                placeholder = pygame.Surface((icon_size, icon_size))
                placeholder.fill((100, 100, 100))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 2)
                panel_surface.blit(placeholder, (x, y))

            count_text = self.dense_font.render(f"x{len(members)}", True, (255, 255, 255))
            badge = pygame.Rect(x + icon_size - count_text.get_width() - 5, y + 1,
                                count_text.get_width() + 4, count_text.get_height() + 1)
            pygame.draw.rect(panel_surface, (0, 0, 0), badge)
            panel_surface.blit(count_text, (badge.x + 2, badge.y + 1))

            bar_y = y + icon_size + 1
            total_hp = sum(m.hp for m in members)
            if kind == 'unit':
                total_max = sum(self._get_unit_max_hp(m) for m in members)
            else:
                total_max = sum(self._get_object_max_hp(m) for m in members)
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
    
    def _get_building_icon(self, obj, size=PORTRAIT):
        """Building portrait via the shared icon loader (cached per size)."""
        name = getattr(obj, 'name', None)
        if name is None or self.icon_loader is None:
            return None
        key = (name, size)
        cached = self._building_icon_cache.get(key)
        if cached is not None:
            return cached
        source = self.icon_loader.building_icons.get(name)
        if source is None:
            return None
        icon = pygame.transform.smoothscale(source, (size, size))
        self._building_icon_cache[key] = icon
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
