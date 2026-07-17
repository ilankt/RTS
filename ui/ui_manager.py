import pygame
from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, MINIMAP_WIDTH, MINIMAP_HEIGHT

# Import UI components
from ui.components.cursor_manager import CursorManager
from ui.components.unit_panel import UnitPanel
from ui.components.command_card import CommandCard
from ui.components.global_queue import GlobalQueueStrip
from ui.components.resource_bar import ResourceBar
from ui.components.icon_loader import IconLoader
from ui.hud_background import NineSliceFrame


class UIManager:
    """Manages UI rendering and information display.

    Sidebar anatomy (§8.2.1 Phase A), top to bottom: minimap -> selection
    header (unit_panel) -> command card (tab chips + fixed 2x4 tile grid +
    status strip). The card is the single context-sensitive surface for
    build / production / research / army actions — the old building menu,
    production panel, and action-button paths are gone.
    """

    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.small_font = pygame.font.Font(None, 20)
        self.button_font = pygame.font.Font(None, 24)
        self.stat_font = pygame.font.Font(None, 18)

        # Initialize UI components
        self.icon_loader = IconLoader()
        self.cursor_manager = CursorManager(game)
        self.unit_panel = UnitPanel(game, self.icon_loader)
        self.command_card = CommandCard(game, self.icon_loader)
        self.global_queue = GlobalQueueStrip(game, self.icon_loader,
                                             self.command_card.tech_icons)
        self.resource_bar = ResourceBar(game)
        # Asymmetric frame: thick ornate wood rail on the map-facing (left)
        # edge + top/bottom, thin plain stone on the screen edge (right). dst
        # insets leave a 180 px inner column — just enough for the tile grid
        # and 4-wide multi-select icons to sit INSIDE the frame, not over it.
        self.sidebar_frame = NineSliceFrame("assets/ui/hud_side_panel.png",
                                            src_inset=(150, 125, 45, 125),
                                            dst_inset=(14, 16, 6, 16))

        # Alert feed (§7.4): fading toasts under the top bar, plus a
        # persistent scrolling log behind them (§8.2, toggled with L)
        self.alerts = []  # [(text, start_ticks)]
        self.alert_history = []  # [(text, sim_time)] — newest last
        self.show_event_log = False
        self._alert_last = {}  # throttle_key -> last ticks

    ALERT_DURATION_MS = 4000
    ALERT_MAX_VISIBLE = 5
    HISTORY_MAX = 50
    LOG_VISIBLE_LINES = 10

    def add_alert(self, text, world_pos=None, throttle_key=None, throttle_ms=0):
        """HUD toast + optional minimap ping. Returns False when throttled."""
        now = pygame.time.get_ticks()
        if throttle_key is not None:
            last = self._alert_last.get(throttle_key)
            if last is not None and now - last < throttle_ms:
                return False
            self._alert_last[throttle_key] = now
        self.alerts.append((text, now))
        self.alerts = self.alerts[-self.ALERT_MAX_VISIBLE:]
        self.alert_history.append((text, getattr(self.game, "sim_time_elapsed", 0.0)))
        self.alert_history = self.alert_history[-self.HISTORY_MAX:]
        if world_pos is not None and getattr(self.game, "minimap", None):
            self.game.minimap.add_ping(world_pos[0], world_pos[1])
        return True

    def toggle_event_log(self):
        self.show_event_log = not self.show_event_log

    def draw_event_log(self, screen):
        """Scrolling log of past alerts, stamped with game time (§8.2)."""
        if not self.show_event_log:
            return
        from core.config import TOP_BAR_HEIGHT, SCREEN_HEIGHT

        entries = self.alert_history[-self.LOG_VISIBLE_LINES:]
        line_height = 20
        panel_height = max(1, len(entries)) * line_height + 30
        panel = pygame.Surface((340, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 170))
        title = self.small_font.render("Event log (L)", True, (200, 180, 100))
        panel.blit(title, (8, 5))
        y = 26
        for text, sim_time in entries:
            minutes, seconds = divmod(int(sim_time), 60)
            line = self.small_font.render(f"{minutes:02d}:{seconds:02d}  {text}"[:44], True, (220, 220, 220))
            panel.blit(line, (8, y))
            y += line_height
        screen.blit(panel, (10, SCREEN_HEIGHT - panel_height - 40))

    def draw_alerts(self, screen):
        """Stacked fading alert toasts below the top bar."""
        if not self.alerts:
            return
        from core.config import TOP_BAR_HEIGHT

        now = pygame.time.get_ticks()
        self.alerts = [a for a in self.alerts if now - a[1] <= self.ALERT_DURATION_MS]
        y = TOP_BAR_HEIGHT + 8
        for text, start in self.alerts:
            age = now - start
            fade_window = self.ALERT_DURATION_MS - 1000
            alpha = 255 if age < fade_window else max(0, int(255 * (1 - (age - fade_window) / 1000)))
            surface = self.font.render(text, True, (255, 230, 120))
            surface.set_alpha(alpha)
            backdrop = pygame.Surface((surface.get_width() + 16, surface.get_height() + 6), pygame.SRCALPHA)
            backdrop.fill((0, 0, 0, min(150, alpha)))
            screen.blit(backdrop, (10, y - 3))
            screen.blit(surface, (18, y))
            y += surface.get_height() + 10

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
        """Draw the sidebar: selection header + command card. The panel
        fills the WHOLE right column below the minimap — the old inset
        margins let the screen's background gray show around it as a
        second, offset rectangle (user-reported)."""
        ui_x = SCREEN_WIDTH - MINIMAP_WIDTH
        ui_y = MINIMAP_HEIGHT
        ui_width = MINIMAP_WIDTH
        ui_height = SCREEN_HEIGHT - MINIMAP_HEIGHT

        panel_surface = pygame.Surface((ui_width, ui_height))
        background = self.sidebar_frame.render(ui_width, ui_height)
        selected_objects = self.get_selected_objects()
        if background is not None:
            # Framed panel: paint the stone-and-rails frame, then draw all
            # content into the inner rectangle so the tiles sit INSIDE the
            # frame instead of overlapping the rails.
            panel_surface.blit(background, (0, 0))
            inner = self.sidebar_frame.content_rect(ui_width, ui_height)
            content = panel_surface.subsurface(inner)
            self.unit_panel.draw_panel(content, inner.width, selected_objects)
            self.command_card.draw(content, ui_x + inner.x, ui_y + inner.y,
                                   inner.width, inner.height, selected_objects)
        else:
            panel_surface.fill((20, 20, 20))
            # Seam only on the map-facing edge; the other sides hug the screen
            pygame.draw.line(panel_surface, (50, 50, 50), (0, 0), (0, ui_height), 2)
            self.unit_panel.draw_panel(panel_surface, ui_width, selected_objects)
            self.command_card.draw(panel_surface, ui_x, ui_y, ui_width, ui_height,
                                   selected_objects)

        screen.blit(panel_surface, (ui_x, ui_y))

        # Global build-queue strip (§8.2.1 Phase C), left map edge
        self.global_queue.draw(screen)

        # NOTE: the hover tooltip is NOT drawn here — "last within
        # draw_ui_panel" wasn't last at all: the ornate map border (drawn
        # later in draw_frame) overpainted its right edge by 32 px (§8.2.2).
        # rendering_system.draw_frame draws it after every other overlay.

    def draw_top_bar(self, screen):
        """Draw the top resource bar"""
        self.resource_bar.draw(screen)

    def handle_click(self, pos):
        """Handle mouse clicks on UI elements"""
        if self.global_queue.handle_click(pos):
            return True
        return self.command_card.handle_click(pos)

    def handle_right_click(self, pos):
        """Right-clicks over the sidebar (production cancel etc.)."""
        return self.command_card.handle_right_click(pos)
