import math

from ui import fonts as ui_fonts
import pygame
from core.config import (SCREEN_WIDTH, SIDEBAR_WIDTH, TOP_BAR_HEIGHT,
                         TOP_BAR_START_X, TOP_BAR_SPACING, TOP_BAR_ROW_Y,
                         TOP_BAR_ITEMS, px)
from ui.hud_background import NineSliceFrame


class ResourceBar:
    """Manages the top resource display bar"""

    # Idle-worker alert tuning (launch feedback: silent idling read as
    # "workers randomly stopped"). A rise in the human's idle count chimes
    # once and pulses the badge so a stopped worker gets noticed.
    IDLE_FLASH_MS = 1200           # how long the badge pulses after a rise
    IDLE_ALERT_COOLDOWN_MS = 8000  # half the previous maximum notification frequency
    IDLE_ALERT_DELAY_S = 4.0
    IDLE_ALERT_WARMUP_S = 2.0      # no alerts this early — match-start settle

    def __init__(self, game):
        self.game = game
        # Shared regular face, measured at resolution-scaled design sizes.
        self.font = ui_fonts.font(23)
        self.resource_font = ui_fonts.font(22)
        self.info_font = ui_fonts.font(16)
        self.small_font = ui_fonts.font(13)
        # Idle-worker alert state
        self._idle_flash_until = 0
        self._idle_alert_cooldown_until = 0
        self._idle_since = {}
        self._idle_notified = set()
        # Use the banner's centre as the background. RenderingSystem draws
        # one shared outer frame around this bar and the map; retain these
        # content insets for the existing resource and idle-badge layout.
        self.frame = NineSliceFrame("assets/ui/hud_top_bar.png",
                                    src_inset=(105, 100, 105, 100),
                                    dst_inset=(px(38), px(22), px(38), px(22)))

    def draw(self, screen):
        """Draw the top resource bar"""
        if not self.game.players:
            return

        human_player = self.game.players[0]  # First player is human

        # Top bar dimensions - spans screen width minus minimap
        top_bar_height = TOP_BAR_HEIGHT
        top_bar_width = SCREEN_WIDTH - SIDEBAR_WIDTH  # Leaves space for the sidebar

        # The shared frame owns the edges and separator, so the resource
        # background must not add another set of rails and corner caps.
        resource_bar = pygame.Surface((top_bar_width, top_bar_height))
        background = self.frame.render_center(top_bar_width, top_bar_height)
        if background is not None:
            resource_bar.blit(background, (0, 0))
        else:
            resource_bar.fill((30, 30, 30))  # Darker background for resource bar

        # === SINGLE ROW: Resources + Housing ===
        all_items = TOP_BAR_ITEMS
        start_x = TOP_BAR_START_X
        spacing = TOP_BAR_SPACING
        row_y = TOP_BAR_ROW_Y

        for i, item in enumerate(all_items):
            x_pos = start_x + (i * spacing)

            # Draw icon
            if item in self.game.resource_icons:
                icon_rect = self.game.resource_icons[item].get_rect()
                icon_rect.x = x_pos
                icon_rect.y = row_y
                resource_bar.blit(self.game.resource_icons[item], icon_rect)

                # Draw amount/value next to icon
                if item == "house":
                    # Housing display — same numbers the training gate uses
                    # (systems/population.py), INCLUDING queued units, so a
                    # denied train button never contradicts the readout.
                    from systems.population import population_cap, population_usage

                    current_pop = population_usage(self.game, human_player)
                    max_pop = population_cap(self.game, human_player)
                    text = f"{current_pop}/{max_pop}"
                    color = (240, 120, 90) if current_pop >= max_pop else (200, 200, 200)
                    text_surface = self.resource_font.render(text, True, color)
                else:
                    # Resource amount
                    amount = int(human_player.resources.get(item, 0))
                    text = f"{amount}"
                    text_surface = self.resource_font.render(text, True, (255, 255, 255))

                # Position text next to icon
                text_x = x_pos + icon_rect.width + px(5)  # Small gap between icon and text
                text_y = row_y - px(2)
                resource_bar.blit(text_surface, (text_x, text_y))

                # Income rate readout (§8.3): +X/s under the stockpile
                if item != "house" and hasattr(self.game, "income_rate"):
                    rate = self.game.income_rate(item)
                    if rate > 0.05:
                        rate_label = ui_fonts.fit_text(self.small_font, f"+{rate:.1f}/s",
                                                       spacing-icon_rect.width-px(12))
                        rate_surface = self.small_font.render(rate_label, True, (120, 220, 120))
                        resource_bar.blit(rate_surface, (text_x, row_y + px(31)))

        # Idle-worker badge, drawn onto the banner before it goes to screen.
        from systems.ages import age_name
        from systems.factions import normalize_faction
        faction = normalize_faction(getattr(human_player, 'faction', None)).title()
        age_label = self.small_font.render(f'{age_name(human_player)} / {faction}', True, (235, 205, 145))
        resource_bar.blit(age_label, (start_x + 3 * spacing, row_y + px(31)))
        self._draw_idle_badge(resource_bar, top_bar_width, top_bar_height)

        # Blit the resource bar to the main screen at the very top
        screen.blit(resource_bar, (0, 0))

    def _draw_idle_badge(self, surface, bar_w, bar_h):
        """Idle-worker badge (§7.4): amber count + F1 hint, only when nonzero.
        A single pill vertically centred at the right end of the banner (where
        the debug speed/fog widgets used to sit), clear of the population
        counter and inside the frame border."""
        idle_workers = self.game.selection_manager.get_idle_workers()
        idle_count = len(idle_workers)
        # Detection runs every frame (even at zero) so the baseline tracks and
        # a rise off zero still alerts.
        self._update_idle_alert(idle_workers)
        if not idle_count:
            return
        badge_w, badge_h = px(120), px(30)
        content = self.frame.content_rect(bar_w, bar_h)
        x = content.right - badge_w - px(6)
        y = (bar_h - badge_h) // 2
        bg_rect = pygame.Rect(x, y, badge_w, badge_h)

        now = pygame.time.get_ticks()
        if now < self._idle_flash_until:
            # Shimmer the badge for a moment after a worker goes idle.
            pulse = 0.5 + 0.5 * math.sin(now * 0.018)
            bg_color = (int(70 + 45 * pulse), int(55 + 40 * pulse), 20)
            border_color = (255, int(200 + 40 * pulse), int(90 + 70 * pulse))
            border_w = max(3, px(3))
            # Soft outer ring to pull the eye toward the badge.
            pygame.draw.rect(surface, border_color, bg_rect.inflate(px(8), px(8)),
                             max(2, px(2)), border_radius=7)
        else:
            bg_color = (70, 55, 20)
            border_color = (230, 180, 60)
            border_w = max(2, px(2))

        pygame.draw.rect(surface, bg_color, bg_rect, border_radius=5)
        pygame.draw.rect(surface, border_color, bg_rect, border_w, border_radius=5)
        text_surface = self.info_font.render(f"Idle: {idle_count} (F1)", True, (255, 210, 90))
        surface.blit(text_surface, text_surface.get_rect(center=bg_rect.center))

    def _update_idle_alert(self, idle_workers):
        """A worker must remain idle through the grace period; coalesce batches."""
        now = pygame.time.get_ticks()
        sim_time = getattr(self.game, 'sim_time_elapsed', 0.0)
        current = set(idle_workers)
        self._idle_since = {w: t for w, t in self._idle_since.items() if w in current}
        self._idle_notified.intersection_update(current)
        for worker in current:
            self._idle_since.setdefault(worker, sim_time)
        pending = {w for w, t in self._idle_since.items()
                   if sim_time - t >= self.IDLE_ALERT_DELAY_S} - self._idle_notified
        if (pending and sim_time >= self.IDLE_ALERT_WARMUP_S
                and now >= self._idle_alert_cooldown_until):
            self._idle_notified.update(pending)
            self._idle_flash_until = now + self.IDLE_FLASH_MS
            sound = getattr(self.game, "sound_manager", None)
            if sound is not None:
                sound.play_idle_worker()
            self._idle_alert_cooldown_until = now + self.IDLE_ALERT_COOLDOWN_MS
