"""Unified sidebar command card (§8.2.1 Phase A).

One context-sensitive card replaces the old building_menu / production_panel /
action-button code paths. Fixed anatomy inside the right sidebar panel, top to
bottom: selection header (unit_panel) -> tab chips row -> a fixed 2x4 tile
grid -> status strip. What the tiles DO switches with the selection:

- own worker(s)            -> [Economy | Military] tab chips (always visible,
                              no drill-down; E swaps, last tab remembered)
                              + build tiles for the active tab
- own production building  -> unit tiles (+ tech tiles at the blacksmith)
- own military units       -> Stop / Stance / Formation tiles (bottom rows,
                              so W/A/S keep panning the camera with an army
                              selected)
- own construction site    -> Cancel tile
- own gate                 -> Open/Close tile

Grid hotkeys are position-mapped (card_slot_0..7 = Q W / A S / Z X / C V by
default, rebindable via keybindings.json). A slot key is only consumed while
a tile occupies that slot; otherwise it falls through to the global bindings
and to WASD camera pan.
"""
import json
import math

import pygame

from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT
from systems.upgrade_effects import has_required_buildings


# Castle listed last (§8.12): rebuildable after a loss — expensive comeback
ECONOMY_BUILDINGS = ['farm', 'house', 'lumbermill', 'mine', 'quarry', 'castle']
MILITARY_BUILDINGS = ['barracks', 'stable', 'blacksmith', 'siege_workshop',
                      'watchtower', 'wooden_wall', 'wall', 'gate']

RESOURCE_LETTER = {"gold": "G", "wood": "W", "stone": "S", "food": "F"}


class CommandCard:
    """The context-sensitive action card in the right sidebar."""

    # Fixed geometry, panel-local (panel is MINIMAP_WIDTH-16 wide)
    GRID_COLS = 2
    GRID_ROWS = 4
    TILE_W = 86
    TILE_H = 74
    TILE_GAP = 4
    TILE_ICON = 28
    CHIPS_TOP = 122      # tab chips row (build context only)
    CHIP_H = 22
    GRID_TOP = 150       # same y for every context: fixed anatomy
    STRIP_H = 18

    SLOT_ACTIONS = tuple(f"card_slot_{i}" for i in range(GRID_COLS * GRID_ROWS))

    def __init__(self, game, icon_loader):
        self.game = game
        self.icon_loader = icon_loader
        self.name_font = pygame.font.Font(None, 16)
        self.cost_font = pygame.font.Font(None, 15)
        self.key_font = pygame.font.Font(None, 14)
        self.small_font = pygame.font.Font(None, 20)

        self.active_tab = 'economy'   # remembered across selections
        self._content = None          # rebuilt every draw / on demand
        self._chip_rects = []         # [(tab, screen rect)]
        self._slot_rects = []         # [(slot_index, screen rect)]
        self._hovered_slot = None
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._icon_cache = {}         # (kind, name) -> 28px surface

        self.buildings_data = {}      # raw JSON dicts, name -> data
        try:
            with open('data/buildings.json', 'r') as f:
                for building in json.load(f):
                    self.buildings_data[building['name']] = building
        except (OSError, ValueError):
            pass

        self.tech_icons = {}
        try:
            with open('data/techs.json', 'r') as f:
                for tech in json.load(f):
                    icon_path = tech.get("icon")
                    if not icon_path:
                        continue
                    try:
                        icon = pygame.image.load(icon_path).convert_alpha()
                        self.tech_icons[tech["id"]] = pygame.transform.smoothscale(
                            icon, (self.TILE_ICON, self.TILE_ICON))
                    except Exception:
                        continue
        except (OSError, ValueError):
            self.tech_icons = {}

    # ------------------------------------------------------------------ #
    # content model                                                      #
    # ------------------------------------------------------------------ #

    def _human(self):
        players = getattr(self.game, "players", None)
        if players and getattr(players[0], "human", False):
            return players[0]
        return None

    def _scan_selection(self):
        selected = []
        for obj in (self.game.units + self.game.buildings +
                    self.game.resources + self.game.construction_sites):
            if getattr(obj, "selected", False):
                selected.append(obj)
        return selected

    def refresh(self, selected_objects=None):
        """Rebuild the card model for the current selection."""
        if selected_objects is None:
            selected_objects = self._scan_selection()
        self._content = self._build_content(selected_objects)
        return self._content

    def _build_content(self, selected):
        content = {'context': None, 'chips': None,
                   'slots': [None] * (self.GRID_COLS * self.GRID_ROWS),
                   'strip': None, 'building': None}
        human = self._human()
        if human is None:
            return content

        own_units = [o for o in selected
                     if o in self.game.units and o.player is human]
        combat_units = [u for u in own_units if not getattr(u, 'can_build', False)]
        workers = [u for u in own_units if getattr(u, 'can_build', False)]

        if combat_units:
            self._fill_military(content, own_units, combat_units)
        elif workers:
            self._fill_build(content, human)
        else:
            own_sites = [o for o in selected
                         if o in self.game.construction_sites and o.player is human]
            own_buildings = [o for o in selected
                             if o in self.game.buildings and o.player is human]
            if own_sites:
                self._fill_construction(content, own_sites[0])
            elif own_buildings:
                if len(own_buildings) == 1 and getattr(own_buildings[0], 'is_gate', False):
                    self._fill_gate(content, own_buildings[0])
                else:
                    self._fill_production(content, own_buildings, human)
        return content

    # ---- build card (the §8.2.1 headline: no drill-down, ever) ------- #

    def _fill_build(self, content, human):
        content['context'] = 'build'
        content['chips'] = [('economy', 'Economy'), ('military', 'Military')]
        order = ECONOMY_BUILDINGS if self.active_tab == 'economy' else MILITARY_BUILDINGS
        for i, name in enumerate(order):
            building = self.buildings_data.get(name)
            if building is None or not building.get('buildable', True):
                continue
            enabled, reason = self._availability(human, building)
            display = building.get('display_name', name.replace('_', ' ').title())
            tooltip = [display, building.get('role', ''),
                       self._cost_line(building.get('costs', {}),
                                       building.get('build_duration'))]
            if building.get('strong_against'):
                tooltip.append("Strong: " + ", ".join(
                    x.title() for x in building['strong_against'][:2]))
            if building.get('weak_against'):
                tooltip.append("Weak: " + ", ".join(
                    x.title() for x in building['weak_against'][:2]))
            tooltip.append(reason)
            content['slots'][i] = {
                'kind': 'build', 'name': name, 'data': building,
                'label': display, 'icon': self._icon('building', name),
                'cost': self._compact_costs(building.get('costs', {})),
                'enabled': enabled, 'reason': reason, 'tooltip': tooltip,
            }

    # ---- production / research card ----------------------------------- #

    def _fill_production(self, content, buildings, human):
        """Production card for one or several selected buildings (§8.2.1
        Phase B, SC2 model): tiles are the union of producible types; a tile
        press queues at the producer with the shortest queue."""
        producers = [b for b in buildings if getattr(b, 'can_produce', None)]
        research_rows = []
        if len(buildings) == 1 and hasattr(self.game, 'research_manager'):
            research_rows = self.game.research_manager.available_for_building(buildings[0])
        has_garrison = len(buildings) == 1 and bool(getattr(buildings[0], 'garrison', None))
        if not producers and not research_rows and not has_garrison:
            return

        content['context'] = 'production'
        content['building'] = buildings[0]
        content['buildings'] = buildings

        # §8.9 garrison: last slot empties a sheltering castle/watchtower
        if len(buildings) == 1 and getattr(buildings[0], 'garrison', None):
            count = len(buildings[0].garrison)
            content['slots'][7] = {
                'kind': 'ungarrison', 'building': buildings[0],
                'label': f'Ungarrison ({count})',
                'icon': self._icon('building', buildings[0].name), 'cost': '',
                'enabled': True, 'reason': 'Ready',
                'tooltip': [f'Ungarrison {count} unit(s)',
                            'Sheltered units are safe; each one speeds tower fire.'],
            }
        cost_lookup = self.game.game_data.get("costs", {})
        single = producers[0] if len(buildings) == 1 and producers else None
        production_info = (self.game.production_manager.get_production_info(single)
                           if single else None)

        unit_types = []
        for producer in producers:
            for unit_type in producer.can_produce:
                if unit_type not in unit_types:
                    unit_types.append(unit_type)

        slot = 0
        for unit_type in unit_types:
            if slot >= len(content['slots']):
                break
            type_producers = [b for b in producers if unit_type in b.can_produce]
            costs = cost_lookup.get(unit_type, {})
            can_afford = all(human.resources.get(r, 0) >= a for r, a in costs.items())
            template = self.game.game_data.get("units", {}).get(unit_type)
            display = getattr(template, "display_name", unit_type.title())
            tooltip = [display, getattr(template, "role", ""),
                       self._cost_line(costs, getattr(template, "build_time", None))]
            if getattr(template, "strong_against", None):
                tooltip.append("Strong: " + ", ".join(
                    x.title() for x in template.strong_against[:2]))
            if getattr(template, "weak_against", None):
                tooltip.append("Weak: " + ", ".join(
                    x.title() for x in template.weak_against[:2]))
            if len(type_producers) > 1:
                tooltip.append(f"{len(type_producers)} buildings — shortest queue")
            in_production = production_info and production_info['unit_type'] == unit_type
            content['slots'][slot] = {
                'kind': 'unit', 'unit_type': unit_type,
                'building': type_producers[0], 'producers': type_producers,
                'label': display, 'icon': self._icon('unit', unit_type),
                'cost': self._compact_costs(costs),
                'enabled': can_afford,
                'reason': "Ready" if can_afford else "Insufficient resources",
                'tooltip': tooltip,
                'progress': production_info['progress'] if in_production else None,
                'badge': sum(self.game.production_manager.get_unit_count_in_production(
                    b, unit_type) for b in type_producers),
            }
            slot += 1

        for tech, can_research, reason in research_rows:
            if slot >= len(content['slots']):
                break
            building = buildings[0]
            display = tech.get("display_name", tech["id"])
            state = 'done' if reason == "Already researched" else (
                'queued' if reason in ("Already in progress", "Already queued") else None)
            tooltip = [display, tech.get("tooltip", ""),
                       self._cost_line(tech.get("costs", {}), tech.get("research_time")),
                       reason]
            research_info = self.game.research_manager.get_research_info(building)
            in_progress = research_info and research_info['tech_id'] == tech['id']
            content['slots'][slot] = {
                'kind': 'tech', 'tech_id': tech['id'], 'building': building,
                'label': display, 'icon': self.tech_icons.get(tech['id']),
                'cost': self._compact_costs(tech.get('costs', {})),
                'enabled': can_research, 'reason': reason, 'tooltip': tooltip,
                'state': state,
                'progress': research_info['progress'] if in_progress else None,
            }
            slot += 1

        if single:
            content['strip'] = self._strip_for(single)
        elif not producers:
            content['strip'] = self._strip_for(buildings[0])  # research-only
        else:
            content['strip'] = self._group_strip(producers)

    def _strip_for(self, building):
        if building is not None:
            production_info = self.game.production_manager.get_production_info(building)
            if production_info:
                queued = len(getattr(building, "production_queue", ()))
                label = f"{production_info['unit_type'].title()} {int(production_info['progress'] * 100)}%"
                if queued:
                    label += f" · queue {queued}"
                return {'progress': production_info['progress'], 'label': label,
                        'color': (110, 170, 110)}
        research_info = None
        if building is not None and hasattr(self.game, 'research_manager'):
            research_info = self.game.research_manager.get_research_info(building)
        if research_info:
            label = f"{research_info['display_name'][:18]} {int(research_info['progress'] * 100)}%"
            if research_info.get('queue_length'):
                label += f" · queue {research_info['queue_length']}"
            return {'progress': research_info['progress'], 'label': label,
                    'color': (90, 150, 220)}
        return None

    def _group_strip(self, producers):
        """Aggregate strip for a multi-building selection."""
        active = sum(1 for b in producers if getattr(b, 'current_production', None))
        queued = sum(len(getattr(b, 'production_queue', ()) or ()) for b in producers)
        if not active and not queued:
            return None
        label = f"{active}/{len(producers)} producing"
        if queued:
            label += f" · {queued} queued"
        return {'progress': active / max(1, len(producers)), 'label': label,
                'color': (110, 170, 110)}

    # ---- military / construction / gate cards -------------------------- #

    def _fill_military(self, content, own_units, combat_units):
        content['context'] = 'military'
        # Bottom rows (Z/X/C) on purpose: an army selection must not steal
        # the W/A/S camera-pan keys.
        stance = next((u.stance for u in combat_units if hasattr(u, 'stance')), None)
        formation = getattr(self.game.selection_manager, 'formation_type', 'ring')
        content['slots'][4] = {
            'kind': 'stop', 'label': 'Stop', 'icon': self._icon('action', 'stop'),
            'cost': '', 'enabled': True, 'reason': 'Ready',
            'tooltip': ['Stop', 'Halt all selected units and clear their orders.'],
        }
        if stance is not None:
            content['slots'][5] = {
                'kind': 'stance', 'label': 'Stance',
                'icon': self._icon('action', 'attack'),
                'cost': stance.replace('_', ' ').title(), 'enabled': True,
                'reason': 'Ready',
                'tooltip': ['Stance', 'Cycle aggressive / defensive / stand ground'
                            ' / no attack.', 'Also on S.'],
            }
        if len(own_units) > 1:
            content['slots'][6] = {
                'kind': 'formation', 'label': 'Formation',
                'icon': self._icon('action', 'move'),
                'cost': formation.title(), 'enabled': True, 'reason': 'Ready',
                'tooltip': ['Formation', 'Cycle ring / line / box / wedge for group'
                            ' moves.', 'Also on F.'],
            }

    def _fill_construction(self, content, site):
        content['context'] = 'construction'
        content['slots'][0] = {
            'kind': 'cancel_construction', 'site': site, 'label': 'Cancel',
            'icon': self._icon('action', 'cancel'), 'cost': '',
            'enabled': True, 'reason': 'Ready',
            'tooltip': ['Cancel construction', 'Remove the foundation and refund'
                        ' its cost.'],
        }

    def _fill_gate(self, content, gate):
        content['context'] = 'gate'
        is_open = getattr(gate, 'passable', False)  # passable == open
        label = 'Close Gate' if is_open else 'Open Gate'
        content['slots'][0] = {
            'kind': 'gate', 'label': label,
            'icon': self._icon('building', 'gate'), 'cost': '',
            'enabled': True, 'reason': 'Ready',
            'tooltip': [label, 'Open gates let units path through; closed gates'
                        ' seal the wall.', 'Also on G.'],
        }

    # ------------------------------------------------------------------ #
    # shared helpers                                                     #
    # ------------------------------------------------------------------ #

    def _icon(self, kind, name):
        key = (kind, name)
        cached = self._icon_cache.get(key)
        if cached is not None:
            return cached
        source = None
        if kind == 'building':
            source = self.icon_loader.building_icons.get(name)
        elif kind == 'unit':
            source = self.icon_loader.unit_production_icons.get(name)
        elif kind == 'action':
            source = self.icon_loader.action_icons.get(name)
        if source is None:
            return None
        icon = pygame.transform.smoothscale(source, (self.TILE_ICON, self.TILE_ICON))
        self._icon_cache[key] = icon
        return icon

    @staticmethod
    def _can_afford(player, building):
        costs = building.get('costs', {})
        return all(player.resources.get(resource, 0) >= amount
                   for resource, amount in costs.items())

    def _availability(self, player, building):
        """(can_build, reason) for a build tile."""
        if getattr(self.game, "is_building_disabled", None) \
                and self.game.is_building_disabled(building.get('name')):
            return False, "Disabled by mutator"
        requirements = building.get('requires', [])
        if requirements and not has_required_buildings(self.game, player, requirements):
            return False, "Requires " + ", ".join(
                r.replace('_', ' ').title() for r in requirements)
        if not self._can_afford(player, building):
            return False, "Insufficient resources"
        return True, "Ready"

    @staticmethod
    def _format_costs(building):
        """Long form: "Wood: 150, Stone: 100"."""
        costs = building.get('costs', {})
        if not costs:
            return ""
        return ", ".join(f"{resource.title()}: {amount}"
                         for resource, amount in costs.items() if amount > 0)

    @staticmethod
    def _compact_costs(costs):
        """"150G 75W" — short enough to never clip a tile."""
        return " ".join(
            f"{amount}{RESOURCE_LETTER.get(resource, resource[0].upper())}"
            for resource, amount in costs.items() if amount > 0
        )

    @staticmethod
    def _cost_line(costs, seconds):
        parts = [f"{amount} {resource.title()}"
                 for resource, amount in costs.items() if amount > 0]
        line = "Cost: " + ", ".join(parts) if parts else ""
        if seconds:
            line = (line + f" - {seconds:.0f}s") if line else f"Time: {seconds:.0f}s"
        return line

    def _wrap_name(self, name, max_width):
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

    # ------------------------------------------------------------------ #
    # drawing                                                            #
    # ------------------------------------------------------------------ #

    def draw(self, panel_surface, ui_x, ui_y, panel_w, panel_h, selected_objects):
        """Draw chips + grid + strip onto the sidebar panel surface."""
        content = self.refresh(selected_objects)
        self._panel_rect = pygame.Rect(ui_x, ui_y, panel_w, panel_h)
        self._chip_rects = []
        self._slot_rects = []
        self._hovered_slot = None
        if content['context'] is None:
            return

        mouse_pos = pygame.mouse.get_pos()
        grid_x = (panel_w - (self.GRID_COLS * self.TILE_W +
                             (self.GRID_COLS - 1) * self.TILE_GAP)) // 2

        # Tab chips (build context): always visible, one click/keypress away
        if content['chips']:
            for c, (tab, label) in enumerate(content['chips']):
                chip = pygame.Rect(grid_x + c * (self.TILE_W + self.TILE_GAP),
                                   self.CHIPS_TOP, self.TILE_W, self.CHIP_H)
                active = tab == self.active_tab
                hovered = chip.move(ui_x, ui_y).collidepoint(mouse_pos)
                fill = (60, 70, 55) if active else (32, 32, 36)
                border = (190, 200, 150) if active else (90, 90, 95)
                if hovered and not active:
                    fill = (46, 46, 52)
                pygame.draw.rect(panel_surface, fill, chip, border_radius=4)
                pygame.draw.rect(panel_surface, border, chip, 2 if active else 1,
                                 border_radius=4)
                color = (235, 235, 210) if active else (150, 150, 150)
                text = self.name_font.render(label, True, color)
                panel_surface.blit(text, (chip.centerx - text.get_width() // 2,
                                          chip.centery - text.get_height() // 2))
                self._chip_rects.append((tab, chip.move(ui_x, ui_y)))
            # tab-swap hint
            hint = self.key_font.render("E", True, (140, 140, 120))
            panel_surface.blit(hint, (grid_x + 2 * self.TILE_W + self.TILE_GAP - 8,
                                      self.CHIPS_TOP - 12))

        # Fixed 2x4 tile grid — empty slots draw as faint sockets so the
        # position-mapped hotkeys always point at the same spot on screen
        for i in range(self.GRID_COLS * self.GRID_ROWS):
            row, col = divmod(i, self.GRID_COLS)
            tile = pygame.Rect(grid_x + col * (self.TILE_W + self.TILE_GAP),
                               self.GRID_TOP + row * (self.TILE_H + self.TILE_GAP),
                               self.TILE_W, self.TILE_H)
            slot = content['slots'][i]
            screen_tile = tile.move(ui_x, ui_y)
            if slot is None:
                # Warm stone socket (not flat black) so empty slots still read
                # as empty but stay in the panel's stone/wood palette.
                pygame.draw.rect(panel_surface, (42, 38, 34), tile, border_radius=4)
                pygame.draw.rect(panel_surface, (70, 62, 52), tile, 1, border_radius=4)
                continue
            self._slot_rects.append((i, screen_tile))
            hovered = screen_tile.collidepoint(mouse_pos)
            if hovered:
                self._hovered_slot = slot
                self._hovered_rect = screen_tile
            self._draw_tile(panel_surface, tile, slot, i, hovered)

        # Status strip (production/research progress + queue depth)
        strip = content.get('strip')
        if strip:
            bar = pygame.Rect(grid_x, self.GRID_TOP + self.GRID_ROWS *
                              (self.TILE_H + self.TILE_GAP) + 2,
                              self.GRID_COLS * self.TILE_W + self.TILE_GAP,
                              self.STRIP_H - 4)
            pygame.draw.rect(panel_surface, (50, 50, 50), bar)
            fill_w = int(bar.width * min(1.0, strip['progress']))
            pygame.draw.rect(panel_surface, strip['color'],
                             (bar.x, bar.y, fill_w, bar.height))
            pygame.draw.rect(panel_surface, (110, 110, 110), bar, 1)
            label = self.cost_font.render(strip['label'], True, (240, 240, 240))
            panel_surface.blit(label, (bar.centerx - label.get_width() // 2,
                                       bar.centery - label.get_height() // 2))

    def _draw_tile(self, surface, tile, slot, index, hovered):
        state = slot.get('state')
        if state == 'done':
            fill, border, name_color = (35, 70, 42), (80, 170, 100), (150, 210, 160)
        elif state == 'queued':
            fill, border, name_color = (45, 45, 78), (120, 120, 210), (185, 185, 235)
        elif slot['enabled']:
            fill, border, name_color = (42, 52, 42), (110, 160, 110), (235, 235, 235)
        elif slot['reason'].startswith(("Requires", "Disabled", "Missing")):
            fill, border, name_color = (45, 42, 32), (120, 105, 60), (170, 155, 110)
        else:
            fill, border, name_color = (50, 38, 38), (140, 90, 90), (190, 140, 130)
        if hovered:
            fill = tuple(min(255, c + 25) for c in fill)
            border = (240, 240, 240)

        pygame.draw.rect(surface, fill, tile, border_radius=4)
        pygame.draw.rect(surface, border, tile, 2, border_radius=4)

        icon = slot.get('icon')
        if icon is not None:
            if not slot['enabled'] and state is None:
                icon = icon.copy()
                icon.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            icon_rect = icon.get_rect(midtop=(tile.centerx, tile.y + 4))
            progress = slot.get('progress')
            if progress is not None and progress < 1.0:
                self._draw_icon_with_radial_progress(surface, icon, icon_rect, progress)
            else:
                surface.blit(icon, icon_rect)

        # Position-mapped hotkey badge, top-left corner
        key_name = self._slot_key_name(index)
        if key_name:
            badge = pygame.Rect(tile.x + 2, tile.y + 2, 13, 13)
            pygame.draw.rect(surface, (15, 15, 18), badge, border_radius=3)
            key_text = self.key_font.render(key_name.upper()[:1], True, (210, 200, 140))
            surface.blit(key_text, (badge.centerx - key_text.get_width() // 2,
                                    badge.centery - key_text.get_height() // 2))

        # Queue-depth badge, top-right corner
        badge_count = slot.get('badge') or 0
        if badge_count > 1:
            center = (tile.right - 11, tile.y + 11)
            pygame.draw.circle(surface, (200, 50, 50), center, 9)
            pygame.draw.circle(surface, (255, 255, 255), center, 9, 1)
            count_text = self.key_font.render(str(badge_count), True, (255, 255, 255))
            surface.blit(count_text, (center[0] - count_text.get_width() // 2,
                                      center[1] - count_text.get_height() // 2))

        name_y = tile.y + 4 + self.TILE_ICON + 2
        for line in self._wrap_name(slot['label'], tile.width - 8)[:2]:
            text = self.name_font.render(line, True, name_color)
            surface.blit(text, (tile.centerx - text.get_width() // 2, name_y))
            name_y += 11

        cost_line = slot.get('cost') or ''
        if cost_line:
            if slot['kind'] in ('stance', 'formation'):
                cost_color = (170, 200, 230)
            else:
                cost_color = (200, 200, 160) if slot['enabled'] else (200, 120, 110)
            text = self.cost_font.render(cost_line, True, cost_color)
            surface.blit(text, (tile.centerx - text.get_width() // 2,
                                tile.bottom - 13))

    def _draw_icon_with_radial_progress(self, surface, icon, icon_rect, progress):
        darkened = icon.copy()
        overlay = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 128))
        darkened.blit(overlay, (0, 0), special_flags=pygame.BLEND_ALPHA_SDL2)
        surface.blit(darkened, icon_rect)
        if progress <= 0:
            return
        size = icon.get_size()
        mask = pygame.Surface(size, pygame.SRCALPHA)
        cx, cy = size[0] // 2, size[1] // 2
        radius = max(cx, cy) + 2
        angle = progress * 360
        points = [(cx, cy)]
        for a in range(0, int(angle) + 2, 2):
            a = min(a, angle)
            rad = math.radians(-90 + a)
            points.append((cx + radius * math.cos(rad), cy + radius * math.sin(rad)))
        if len(points) >= 3:
            pygame.draw.polygon(mask, (255, 255, 255, 255), points)
        revealed = pygame.Surface(size, pygame.SRCALPHA)
        revealed.blit(icon, (0, 0))
        revealed.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(revealed, icon_rect)

    def draw_tooltip(self, screen):
        """Rich hover tooltip as a flyout NEXT TO the hovered tile (the old
        screen-bottom box floated detached from the panel — read as a stray
        overlapping box, user-reported)."""
        if self._hovered_slot is None:
            return
        lines = [line for line in self._hovered_slot.get('tooltip', []) if line][:5]
        if not lines:
            return
        width = 210
        height = 12 + 16 * len(lines)
        anchor = getattr(self, '_hovered_rect', None) or self._panel_rect
        y = min(max(6, anchor.y), SCREEN_HEIGHT - height - 6)
        tooltip_rect = pygame.Rect(self._panel_rect.x - width - 6, y, width, height)
        pygame.draw.rect(screen, (10, 10, 14), tooltip_rect, border_radius=6)
        pygame.draw.rect(screen, (150, 132, 80), tooltip_rect, 1, border_radius=6)
        text_y = tooltip_rect.y + 6
        for i, line in enumerate(lines):
            color = (235, 220, 170) if i == 0 else (225, 225, 225)
            text = self.cost_font.render(line[:34], True, color)
            screen.blit(text, (tooltip_rect.x + 8, text_y))
            text_y += 16

    # ------------------------------------------------------------------ #
    # input                                                              #
    # ------------------------------------------------------------------ #

    def _slot_key_name(self, index):
        bindings = getattr(self.game, 'keybindings', None)
        if bindings is None:
            return None
        return bindings.bindings.get(f"card_slot_{index}")

    def _keycode_slot(self, keycode):
        """Which slot index a keycode maps to, or None."""
        bindings = getattr(self.game, 'keybindings', None)
        if bindings is None:
            return None
        for i in range(self.GRID_COLS * self.GRID_ROWS):
            if bindings.matches(f"card_slot_{i}", keycode):
                return i
        return None

    def consumes_key(self, keycode):
        """True while this keycode currently drives the card (used to mute
        the matching WASD camera-pan key; arrows/edge-scroll always pan)."""
        content = self._content
        if content is None or content['context'] is None:
            return False
        bindings = getattr(self.game, 'keybindings', None)
        if bindings is not None and content['chips'] \
                and bindings.matches("card_tab_swap", keycode):
            return True
        slot_index = self._keycode_slot(keycode)
        return slot_index is not None and content['slots'][slot_index] is not None

    def handle_hotkey(self, keycode):
        """Keydown hook, ahead of the global bindings. Returns True when
        consumed; unoccupied slot keys fall through."""
        if getattr(self.game, 'game_over_state', None) or getattr(self.game, 'game_paused', False):
            return False
        content = self.refresh()
        if content['context'] is None:
            return False
        bindings = getattr(self.game, 'keybindings', None)
        if bindings is not None and content['chips'] \
                and bindings.matches("card_tab_swap", keycode):
            self.active_tab = 'military' if self.active_tab == 'economy' else 'economy'
            self._play(True)
            return True
        slot_index = self._keycode_slot(keycode)
        if slot_index is None:
            return False
        slot = content['slots'][slot_index]
        if slot is None:
            return False
        return self._activate(slot)

    def handle_click(self, pos):
        """Left clicks. The card owns the whole sidebar region below the
        minimap — clicks there never fall through to the map."""
        if not self._panel_rect.collidepoint(pos):
            return False
        for tab, rect in self._chip_rects:
            if rect.collidepoint(pos):
                if tab != self.active_tab:
                    self.active_tab = tab
                    self._play(True)
                return True
        content = self._content
        for index, rect in self._slot_rects:
            if rect.collidepoint(pos):
                slot = content['slots'][index] if content else None
                if slot is not None:
                    self._activate(slot)
                return True
        return True  # consumed: empty panel area

    def handle_right_click(self, pos):
        """Right-click a production tile: remove last queued of that type
        (full refund) or cancel the in-progress one (50% refund)."""
        if not self._panel_rect.collidepoint(pos):
            # Consume stray right-clicks over the whole right column so no
            # world command fires through the HUD
            return pos[0] >= SCREEN_WIDTH - MINIMAP_WIDTH
        content = self._content
        for index, rect in self._slot_rects:
            if not rect.collidepoint(pos):
                continue
            slot = content['slots'][index] if content else None
            if slot is None or slot['kind'] != 'unit':
                return True
            self._cancel_unit(slot)
            return True
        return True

    # ------------------------------------------------------------------ #
    # activation                                                         #
    # ------------------------------------------------------------------ #

    def _activate(self, slot):
        if not slot['enabled']:
            self._play(False)
            return True
        kind = slot['kind']
        if kind == 'build':
            self.game.enter_building_placement_mode(slot['data'])
            self._play(True)
        elif kind == 'unit':
            count = self._batch_size() if self._shift_held() else 1
            self._queue_unit(slot, count)
        elif kind == 'tech':
            ok, _ = self.game.research_manager.start_research(
                slot['building'], slot['tech_id'])
            self._play(ok)
        elif kind == 'stop':
            human = self._human()
            for unit in self.game.units:
                if unit.selected and unit.player is human and hasattr(unit, 'stop'):
                    unit.stop()
            self._play(True)
        elif kind == 'stance':
            self.game._cycle_selected_unit_stances()
            self._play(True)
        elif kind == 'formation':
            self.game.selection_manager.cycle_formation()
            self._play(True)
        elif kind == 'cancel_construction':
            # (the old panel's button called a nonexistent game method and
            # would have crashed on click — go through the building system)
            self.game.building_system.cancel_construction(slot['site'])
            self._play(True)
        elif kind == 'gate':
            self.game._toggle_selected_gates()
            self._play(True)
        elif kind == 'ungarrison':
            from systems import garrison
            garrison.eject_all(self.game, slot['building'])
            self._play(True)
        else:
            return False
        return True

    # ---- Phase B: shortest-queue routing + batch queueing ------------- #

    @staticmethod
    def _shift_held():
        keys = pygame.key.get_pressed()
        return keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

    def _batch_size(self):
        """Shift-queue batch size (settings-configurable, default 5)."""
        try:
            return max(1, int(getattr(self.game, 'batch_queue_size', 5)))
        except (TypeError, ValueError):
            return 5

    @staticmethod
    def _queue_depth(building):
        depth = len(getattr(building, 'production_queue', ()) or ())
        if getattr(building, 'current_production', None):
            depth += 1
        return depth

    def _queue_unit(self, slot, count):
        """Queue `count` units, each at the currently shortest queue among
        the slot's producers (SC2 model). Stops when a queue is full or
        resources run out."""
        producers = slot.get('producers') or [slot['building']]
        started = 0
        for _ in range(count):
            producer = min(producers, key=self._queue_depth)
            ok, _ = self.game.production_manager.start_production(
                producer, slot['unit_type'])
            if not ok:
                break
            started += 1
        self._play(started > 0)

    def _cancel_unit(self, slot):
        """Right-click semantics across producers: remove a queued unit of
        that type from the deepest queue (full refund), else cancel an
        in-progress one (50% refund)."""
        producers = slot.get('producers') or [slot['building']]
        unit_type = slot['unit_type']
        queued = [b for b in producers
                  if unit_type in (getattr(b, 'production_queue', ()) or ())]
        if queued:
            target = max(queued, key=self._queue_depth)
            success, _ = self.game.production_manager.cancel_queued(target, unit_type)
        else:
            success = False
            for producer in producers:
                current = getattr(producer, 'current_production', None)
                if current and current.get('unit_type') == unit_type:
                    success, _ = self.game.production_manager.cancel_production(producer)
                    break
        self._play(success)

    def _play(self, ok):
        sound = getattr(self.game, 'sound_manager', None)
        if not sound:
            return
        if ok:
            sound.play_ui_click()
        else:
            sound.play_error()
