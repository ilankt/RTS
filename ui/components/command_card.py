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
from ui.components.icon_loader import COST_GLYPH_ORDER
from ui import fonts as ui_fonts


# Castle listed last (§8.12): rebuildable after a loss — expensive comeback
ECONOMY_BUILDINGS = ['farm', 'house', 'lumbermill', 'mine', 'quarry', 'market', 'castle']
MILITARY_BUILDINGS = ['barracks', 'stable', 'blacksmith', 'siege_workshop', 'temple',
                      'watchtower', 'wooden_wall', 'wall', 'gate']

# §8.2.2: only a fallback now — costs render as glyph+number pairs. Kept so a
# missing glyph degrades to the old abbreviation instead of showing nothing.
RESOURCE_LETTER = {"gold": "G", "wood": "W", "stone": "S", "food": "F"}


class CommandCard:
    """The context-sensitive action card in the right sidebar."""

    # Fixed geometry, panel-local (panel is MINIMAP_WIDTH-16 wide)
    GRID_COLS = 2
    GRID_ROWS = 4
    TILE_W = 86
    TILE_H = 74
    TILE_GAP = 4
    TILE_ICON = 28        # base action-icon size (kept for compatibility)
    # §8.2.2 icon-first anatomy: the name moved to the hover tooltip, so the
    # icon fills (near) the whole tile — a square capped by the 74px tile
    # height. Cost/label overlay a dark scrim at the bottom.
    TILE_ICON_FILL = 70
    COST_GLYPH = 11       # inline resource glyph px — compact so 3 fit one row
    CHIPS_TOP = 122      # tab chips row (build context only)
    CHIP_H = 22
    GRID_TOP = 150       # same y for every context: fixed anatomy
    STRIP_H = 18

    SLOT_ACTIONS = tuple(f"card_slot_{i}" for i in range(GRID_COLS * GRID_ROWS))

    def __init__(self, game, icon_loader):
        self.game = game
        self.icon_loader = icon_loader
        # §8.2.2 shared fonts: a clean system face, larger than the old
        # default-font literals (which read small and uneven at these sizes).
        self.name_font = ui_fonts.label()       # chip + action-tile labels
        self.cost_font = ui_fonts.body()        # tooltip text + measurement
        self.tile_num_font = ui_fonts.font(15)     # 1-2 resource tile cost
        self.tile_num_font_sm = ui_fonts.font(11)  # 3-resource tile cost (compact)
        self.tip_title_font = ui_fonts.font(21, True)  # tooltip title row
        self.key_font = ui_fonts.badge()        # hotkey / queue badges

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
                        # Tech tiles are always cost-bearing → large icon
                        self.tech_icons[tech["id"]] = pygame.transform.smoothscale(
                            icon, (self.TILE_ICON_FILL, self.TILE_ICON_FILL))
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
                elif len(own_buildings) == 1 and own_buildings[0].name == 'market':
                    self._fill_market(content, own_buildings[0], human)
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
            costs = building.get('costs', {})
            tooltip = [display, building.get('role', ''),
                       self._cost_row(costs, building.get('build_duration'))]
            if building.get('strong_against'):
                tooltip.append("Strong: " + ", ".join(
                    x.title() for x in building['strong_against'][:2]))
            if building.get('weak_against'):
                tooltip.append("Weak: " + ", ".join(
                    x.title() for x in building['weak_against'][:2]))
            tooltip.append(reason)
            content['slots'][i] = {
                'kind': 'build', 'name': name, 'data': building,
                'label': display,
                'icon': self._icon('building', name),
                'costs': costs,
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
            # build_time lives in the raw JSON (production_manager.units_data),
            # not on the Unit template object — so the tooltip clock needs it
            # from there (the old text tooltip silently showed no unit time).
            build_time = self.game.production_manager.units_data.get(
                unit_type, {}).get('build_time')
            tooltip = [display, getattr(template, "role", ""),
                       self._cost_row(costs, build_time)]
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
                'label': display,
                'icon': self._icon('unit', unit_type),
                'costs': costs,
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
                       self._cost_row(tech.get("costs", {}), tech.get("research_time")),
                       reason]
            research_info = self.game.research_manager.get_research_info(building)
            in_progress = research_info and research_info['tech_id'] == tech['id']
            content['slots'][slot] = {
                'kind': 'tech', 'tech_id': tech['id'], 'building': building,
                'label': display, 'icon': self.tech_icons.get(tech['id']),
                'costs': tech.get('costs', {}),
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

    def _fill_market(self, content, market, human):
        """§8.9 market: sell tiles down the left column, buy tiles down the
        right. Shift-click trades a batch of 5 lots."""
        from core.config import (MARKET_TRADE_LOT, MARKET_SELL_GOLD,
                                 MARKET_BUY_GOLD, MARKET_TRADEABLE)
        from systems import market as market_rules

        content['context'] = 'market'
        content['building'] = market
        for row, resource in enumerate(MARKET_TRADEABLE):
            can_sell = market_rules.can_sell(human, resource)
            content['slots'][row * 2] = {
                'kind': 'trade', 'direction': 'sell', 'resource': resource,
                'label': f'Sell {MARKET_TRADE_LOT} {resource.title()}',
                'icon': self._icon('building', 'market'),
                'cost': f'+{MARKET_SELL_GOLD}G',
                'enabled': can_sell,
                'reason': 'Ready' if can_sell else f'Need {MARKET_TRADE_LOT} {resource}',
                'tooltip': [f'Sell {MARKET_TRADE_LOT} {resource} for {MARKET_SELL_GOLD} gold',
                            'Shift: trade 5 lots.'],
            }
            can_buy = market_rules.can_buy(human, resource)
            content['slots'][row * 2 + 1] = {
                'kind': 'trade', 'direction': 'buy', 'resource': resource,
                'label': f'Buy {MARKET_TRADE_LOT} {resource.title()}',
                'icon': self._icon('building', 'market'),
                'cost': f'-{MARKET_BUY_GOLD}G',
                'enabled': can_buy,
                'reason': 'Ready' if can_buy else f'Need {MARKET_BUY_GOLD} gold',
                'tooltip': [f'Buy {MARKET_TRADE_LOT} {resource} for {MARKET_BUY_GOLD} gold',
                            'Shift: trade 5 lots.'],
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

    def _icon(self, kind, name, size=None):
        size = size or self.TILE_ICON_FILL
        key = (kind, name, size)
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
        icon = pygame.transform.smoothscale(source, (size, size))
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
    def _cost_row(costs, seconds=None):
        """A tooltip/tile cost entry: rendered as glyph+number pairs, not text.

        Returned as a dict so it can sit inline in a tooltip line list and be
        told apart from the plain strings around it.
        """
        return {'costs': {r: a for r, a in (costs or {}).items() if a > 0},
                'duration': seconds}

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
        self._hovered_rect = None
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

        # §8.2.2 icon-first anatomy: the icon fills (near) the whole tile — the
        # name lives in the hover tooltip. Cost/label overlay a scrim below.
        icon = slot.get('icon')
        if icon is not None:
            if not slot['enabled'] and state is None:
                icon = icon.copy()
                icon.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            icon_rect = icon.get_rect(center=(tile.centerx, tile.centery))
            progress = slot.get('progress')
            if progress is not None and progress < 1.0:
                self._draw_icon_with_radial_progress(surface, icon, icon_rect, progress)
            else:
                surface.blit(icon, icon_rect)

        # Bottom overlay: glyph cost row (cost tiles) or the state label
        # (action tiles), on a dark scrim so it reads over the icon.
        costs = slot.get('costs')
        if costs:
            self._draw_tile_cost_glyphs(surface, tile, costs, slot['enabled'])
        else:
            label = slot.get('cost') or slot.get('label') or ''
            if label:
                if slot['kind'] in ('stance', 'formation'):
                    label_color = (185, 210, 240)
                else:
                    label_color = (235, 235, 220) if slot['enabled'] else (210, 140, 130)
                self._draw_tile_scrim(surface, tile, 1, self.name_font.get_height())
                text = self.name_font.render(label, True, label_color)
                if text.get_width() > tile.width - 6:
                    text = pygame.transform.smoothscale(
                        text, (tile.width - 6, text.get_height()))
                surface.blit(text, (tile.centerx - text.get_width() // 2,
                                    tile.bottom - text.get_height() - 3))

        # Border frames the filled icon; badges sit on top of everything.
        pygame.draw.rect(surface, border, tile, 2, border_radius=4)

        key_name = self._slot_key_name(index)
        if key_name:
            badge = pygame.Rect(tile.x + 2, tile.y + 2, 16, 16)
            pygame.draw.rect(surface, (15, 15, 18), badge, border_radius=3)
            pygame.draw.rect(surface, (90, 90, 80), badge, 1, border_radius=3)
            key_text = self.key_font.render(key_name.upper()[:1], True, (225, 215, 150))
            surface.blit(key_text, (badge.centerx - key_text.get_width() // 2,
                                    badge.centery - key_text.get_height() // 2))

        badge_count = slot.get('badge') or 0
        if badge_count > 1:
            center = (tile.right - 12, tile.y + 12)
            pygame.draw.circle(surface, (200, 50, 50), center, 10)
            pygame.draw.circle(surface, (255, 255, 255), center, 10, 1)
            count_text = self.key_font.render(str(badge_count), True, (255, 255, 255))
            surface.blit(count_text, (center[0] - count_text.get_width() // 2,
                                      center[1] - count_text.get_height() // 2))

    # Bright number colors so the glyph carries the hue and the digits stay
    # legible on the dark tile; red when the player can't afford it (§8.2.2).
    _COST_NUM_OK = (228, 228, 208)
    _COST_NUM_NO = (208, 128, 118)
    # Only used to tint the letter fallback when a glyph asset is missing, so
    # the abbreviation still reads as its resource (matches the glyph hues).
    _RESOURCE_TINT = {'gold': (245, 200, 60), 'wood': (196, 142, 92),
                      'stone': (185, 190, 196), 'food': (230, 125, 95)}

    def _draw_tile_scrim(self, surface, tile, rows, row_h):
        """Dark scrim behind the bottom `rows` of overlay text so numbers stay
        legible over a full-bleed icon (§8.2.2)."""
        height = min(tile.height - 4, rows * row_h + 4)
        scrim = pygame.Surface((tile.width - 4, height), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 150))
        surface.blit(scrim, (tile.x + 2, tile.bottom - 2 - height))

    def _draw_tile_cost_glyphs(self, surface, tile, costs, enabled):
        """Cost as glyph+number pairs, packed centered and bottom-aligned on a
        scrim. The size adapts to the resource count: readable for the common
        1-2 resource case, compact for the rare 3-resource one so it stays a
        single thin row instead of a fat block over the icon (the archer,
        75/50/40, was the complaint). Only the castle's 3x3-digit cost still
        wraps to two rows — unavoidable in an 86px tile, measured."""
        num_color = self._COST_NUM_OK if enabled else self._COST_NUM_NO
        three = sum(1 for r in COST_GLYPH_ORDER if costs.get(r, 0) > 0) >= 3
        glyph_px = 10 if three else 14
        num_font = self.tile_num_font_sm if three else self.tile_num_font
        gap, pair_gap = 1, (2 if three else 4)
        row_h = glyph_px + 4

        # Build renderables in the fixed resource order so a cost's layout is
        # stable regardless of dict order.
        pairs = []
        for resource in COST_GLYPH_ORDER:
            amount = costs.get(resource, 0)
            if amount <= 0:
                continue
            glyph = self.icon_loader.get_cost_glyph(resource, glyph_px)
            number = num_font.render(str(amount), True, num_color)
            fallback = None
            if glyph is None:
                fallback = num_font.render(
                    RESOURCE_LETTER.get(resource, resource[0].upper()),
                    True, self._RESOURCE_TINT.get(resource, num_color))
            width = (glyph_px if glyph is not None else fallback.get_width()) + gap + number.get_width()
            pairs.append((glyph, fallback, number, width))

        usable = tile.width - 6
        rows, current, current_w = [], [], 0
        for pair in pairs:
            add = pair[3] + (pair_gap if current else 0)
            if current and current_w + add > usable:
                rows.append((current, current_w))
                current, current_w = [pair], pair[3]
            else:
                current.append(pair)
                current_w += add
        if current:
            rows.append((current, current_w))
        rows = rows[:2]  # two rows is the ceiling; three resources max

        self._draw_tile_scrim(surface, tile, len(rows), row_h)
        total_h = len(rows) * row_h
        y = tile.bottom - 4 - total_h
        for row_pairs, row_w in rows:
            x = tile.centerx - row_w // 2
            for glyph, fallback, number, width in row_pairs:
                mark = glyph if glyph is not None else fallback
                surface.blit(mark, (x, y + (row_h - mark.get_height()) // 2 - 1))
                x += (glyph_px if glyph is not None else fallback.get_width()) + gap
                surface.blit(number, (x, y + (row_h - number.get_height()) // 2 - 1))
                x += number.get_width() + pair_gap
            y += row_h

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

    TOOLTIP_WIDTH = 236
    TOOLTIP_PAD_X = 11
    TOOLTIP_PAD_Y = 9
    TOOLTIP_GLYPH = 16
    TOOLTIP_LINE_STEP = 16  # kept for tests; body line height is TIP_BODY_STEP
    TIP_BODY_STEP = 21
    TIP_COST_H = 24
    TIP_RULE_H = 9

    def _wrap_tooltip_line(self, text, max_width):
        """Measured word-wrap. §8.2.2: the old blind `line[:34]` cap chopped
        gate/stable/fletching/market mid-word ("Wall segment your units can
        pass w") — wrap by pixel measurement instead, never drop characters."""
        words = text.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}" if current else word
            if self.cost_font.size(candidate)[0] <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def draw_tooltip(self, screen):
        """Rich hover flyout beside the hovered tile (§8.2.2): a bold title, a
        divider rule, then the body — role, a glyph cost+duration row, and any
        counters — with real line spacing. Content-sized, no character caps."""
        if self._hovered_slot is None:
            return
        raw_lines = [line for line in self._hovered_slot.get('tooltip', []) if line]
        if not raw_lines:
            return
        title_font = self.tip_title_font
        width = self.TOOLTIP_WIDTH
        usable = width - 2 * self.TOOLTIP_PAD_X

        # Typed, measured rows: (kind, payload, height).
        rows = []
        for index, raw in enumerate(raw_lines):
            if index == 0:  # title + divider
                rows.append(('title', str(raw), title_font.get_height() + 4))
                rows.append(('rule', None, self.TIP_RULE_H))
            elif isinstance(raw, dict):
                if raw.get('costs') or raw.get('duration'):
                    rows.append(('costs', (raw.get('costs') or {}, raw.get('duration')),
                                 self.TIP_COST_H))
            else:
                for piece in self._wrap_tooltip_line(raw, usable):
                    rows.append(('text', piece, self.TIP_BODY_STEP))

        height = 2 * self.TOOLTIP_PAD_Y + sum(h for _k, _p, h in rows)
        anchor = getattr(self, '_hovered_rect', None) or self._panel_rect
        y = min(max(6, anchor.y), SCREEN_HEIGHT - height - 6)
        rect = pygame.Rect(self._panel_rect.x - width - 8, y, width, height)
        pygame.draw.rect(screen, (18, 18, 24), rect, border_radius=7)
        pygame.draw.rect(screen, (150, 132, 80), rect, 2, border_radius=7)

        x = rect.x + self.TOOLTIP_PAD_X
        ty = rect.y + self.TOOLTIP_PAD_Y
        for kind, payload, h in rows:
            if kind == 'title':
                screen.blit(title_font.render(payload, True, (245, 238, 215)), (x, ty))
            elif kind == 'rule':
                pygame.draw.line(screen, (90, 82, 60),
                                 (x, ty + 2), (rect.right - self.TOOLTIP_PAD_X, ty + 2))
            elif kind == 'costs':
                self._draw_tooltip_cost_row(screen, x, ty, payload[0], payload[1])
            else:
                screen.blit(self.cost_font.render(payload, True, (222, 222, 226)), (x, ty))
            ty += h

    def _draw_tooltip_cost_row(self, screen, x, y, costs, seconds):
        """Cost as glyph+number pairs then a clock+seconds, on one line — the
        tooltip is wide enough that even the castle's three resources fit."""
        glyph_px = self.TOOLTIP_GLYPH
        num_color = (232, 232, 236)
        mid = y + self.TIP_COST_H // 2

        def blit_pair(glyph_name, text, label, tint):
            nonlocal x
            glyph = self.icon_loader.get_cost_glyph(glyph_name, glyph_px)
            if glyph is not None:
                screen.blit(glyph, (x, mid - glyph_px // 2))
                x += glyph_px + 3
            else:
                mark = self.cost_font.render(label, True, tint)
                screen.blit(mark, (x, mid - mark.get_height() // 2))
                x += mark.get_width() + 3
            number = self.cost_font.render(text, True, num_color)
            screen.blit(number, (x, mid - number.get_height() // 2))
            x += number.get_width() + 12

        for resource in COST_GLYPH_ORDER:
            amount = costs.get(resource, 0)
            if amount > 0:
                blit_pair(resource, str(amount),
                          RESOURCE_LETTER.get(resource, resource[0].upper()),
                          self._RESOURCE_TINT.get(resource, num_color))
        if seconds:
            blit_pair('time', f"{seconds:.0f}s", "T", (170, 196, 214))

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
        elif kind == 'trade':
            from systems import market as market_rules
            human = self.game.players[0]
            action = (market_rules.sell if slot['direction'] == 'sell'
                      else market_rules.buy)
            lots = 5 if self._shift_held() else 1
            done = 0
            for _ in range(lots):
                if not action(human, slot['resource']):
                    break
                done += 1
            self._play(done > 0)
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
