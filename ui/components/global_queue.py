"""Global build-queue strip (§8.2.1 Phase C, AoE4 model).

A slim overlay on the left edge of the map view listing every unit and tech
the human player has in production anywhere: icon, name, live progress bar,
and a +N badge for queued extras. Click a row to jump the camera to (and
select) the producer; Ctrl+click cancels the in-progress item with the
standard refund rules (50% for in-progress work).

The plan drafted this "docked under the minimap", but the command card's
fixed grid owns that space — the left edge is where AoE4 docks its global
queue too.
"""
import pygame

from core.config import TOP_BAR_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT, px
from ui.fonts import fit_text


class GlobalQueueStrip:
    # Design px at UI scale 1.0; __init__ re-binds them scaled (§8.2.2).
    ROW_W = 170
    ROW_H = 26
    ROW_GAP = 3
    ICON = 20
    MAX_ROWS = 8
    X = 8
    TOP = TOP_BAR_HEIGHT + 170  # below the alert-toast stack

    def __init__(self, game, icon_loader, tech_icons):
        self.game = game
        self.icon_loader = icon_loader
        self.tech_icons = tech_icons  # shared with the command card
        self.ROW_W = px(self.ROW_W)
        self.ROW_H = max(px(self.ROW_H), 0)
        self.ROW_GAP = px(self.ROW_GAP)
        self.ICON = px(self.ICON)
        self.X = px(self.X)
        self.TOP = TOP_BAR_HEIGHT + px(170)
        self.name_font = pygame.font.Font(None, px(16))
        self._icon_cache = {}
        self._rows = []  # [(screen rect, item)]

    def _human(self):
        players = getattr(self.game, "players", None)
        if players and getattr(players[0], "human", False):
            return players[0]
        return None

    def _icon(self, kind, key):
        cache_key = (kind, key)
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached
        source = (self.icon_loader.unit_production_icons.get(key)
                  if kind == 'unit' else self.tech_icons.get(key))
        if source is None:
            return None
        icon = pygame.transform.smoothscale(source, (self.ICON, self.ICON))
        self._icon_cache[cache_key] = icon
        return icon

    def _items(self):
        human = self._human()
        if human is None:
            return []
        items = []
        for building in self.game.buildings:
            if getattr(building, 'player', None) is not human:
                continue
            info = self.game.production_manager.get_production_info(building)
            if info:
                items.append({
                    'building': building, 'kind': 'unit',
                    'key': info['unit_type'],
                    'label': info['unit_type'].replace('_', ' ').title(),
                    'progress': info['progress'],
                    'queued': len(getattr(building, 'production_queue', ()) or ()),
                })
            research = None
            if hasattr(self.game, 'research_manager'):
                research = self.game.research_manager.get_research_info(building)
            if research:
                items.append({
                    'building': building, 'kind': 'tech',
                    'key': research['tech_id'],
                    'label': research['display_name'],
                    'progress': research['progress'],
                    'queued': research.get('queue_length', 0),
                })
        return items

    def draw(self, screen):
        items = self._items()
        self._rows = []
        if not items:
            return
        y = self.TOP
        shown = items[:self.MAX_ROWS]
        for item in shown:
            rect = pygame.Rect(self.X, y, self.ROW_W, self.ROW_H)
            self._rows.append((rect, item))

            row = pygame.Surface((self.ROW_W, self.ROW_H), pygame.SRCALPHA)
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            row.fill((0, 0, 0, 190 if hovered else 150))
            color = (110, 170, 110) if item['kind'] == 'unit' else (90, 150, 220)

            icon = self._icon(item['kind'], item['key'])
            if icon is not None:
                row.blit(icon, (px(3), (self.ROW_H - self.ICON) // 2 - px(1)))
            # The +N badge survives truncation — the name gives way, not it
            suffix = f" +{item['queued']}" if item['queued'] else ""
            text_x = self.ICON + px(8)
            avail = self.ROW_W - text_x - px(4) - self.name_font.size(suffix)[0]
            label = fit_text(self.name_font, item['label'], avail) + suffix
            text = self.name_font.render(label, True, (235, 235, 235))
            row.blit(text, (text_x, (self.ROW_H - text.get_height()) // 2 - px(1)))

            # Progress bar along the bottom edge
            bar_h = max(2, px(3))
            bar_y = self.ROW_H - bar_h - px(2)
            bar_w = int((self.ROW_W - px(4)) * min(1.0, item['progress']))
            pygame.draw.rect(row, (60, 60, 60), (px(2), bar_y, self.ROW_W - px(4), bar_h))
            pygame.draw.rect(row, color, (px(2), bar_y, bar_w, bar_h))
            if hovered:
                pygame.draw.rect(row, (220, 220, 220), row.get_rect(), 1)

            screen.blit(row, rect.topleft)
            y += self.ROW_H + self.ROW_GAP

        if len(items) > self.MAX_ROWS:
            more = self.name_font.render(f"+{len(items) - self.MAX_ROWS} more",
                                         True, (180, 180, 180))
            screen.blit(more, (self.X + px(4), y + px(1)))

    def handle_click(self, pos):
        """Click = jump camera to + select the producer; Ctrl+click = cancel
        the in-progress item (50% refund). Returns True when consumed."""
        for rect, item in self._rows:
            if not rect.collidepoint(pos):
                continue
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]:
                if item['kind'] == 'unit':
                    ok, _ = self.game.production_manager.cancel_production(item['building'])
                else:
                    ok, _ = self.game.research_manager.cancel_research(item['building'])
                self._feedback(ok)
            else:
                self._jump_to(item['building'])
                self._feedback(True)
            return True
        return False

    def _jump_to(self, building):
        camera = self.game.camera
        camera.x = -building.x * camera.zoom + MAP_VIEW_WIDTH / 2
        camera.y = -building.y * camera.zoom + MAP_VIEW_HEIGHT / 2
        selection = self.game.selection_manager
        selection._clear_all_selections()
        building.selected = True
        selection.selected_objects.append(building)

    def _feedback(self, ok):
        sound = getattr(self.game, 'sound_manager', None)
        if not sound:
            return
        if ok:
            sound.play_ui_click()
        else:
            sound.play_error()
