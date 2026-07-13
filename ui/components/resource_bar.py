import pygame
from core.config import SCREEN_WIDTH, MINIMAP_WIDTH, TOP_BAR_HEIGHT, TOP_BAR_START_X, TOP_BAR_SPACING, TOP_BAR_ROW_Y, TOP_BAR_ITEMS
from ui.hud_background import NineSliceFrame


class ResourceBar:
    """Manages the top resource display bar"""

    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.resource_font = pygame.font.Font(None, 32)  # Larger font for resources
        self.info_font = pygame.font.Font(None, 24)      # Smaller font for info row
        self.small_font = pygame.font.Font(None, 20)
        # Framed banner art (a full four-sided frame): 9-slice keeps all four
        # rails + corner end-caps crisp. src insets are the ~100 px border in
        # the source; dst draws thinner rails top/bottom (room for resources)
        # and real end-caps left/right so the banner never looks chopped.
        self.frame = NineSliceFrame("assets/ui/hud_top_bar.png",
                                    src_inset=(105, 100, 105, 100),
                                    dst_inset=(38, 22, 38, 22))

    def draw(self, screen):
        """Draw the top resource bar"""
        if not self.game.players:
            return

        human_player = self.game.players[0]  # First player is human

        # Top bar dimensions - spans screen width minus minimap
        top_bar_height = TOP_BAR_HEIGHT
        top_bar_width = SCREEN_WIDTH - MINIMAP_WIDTH  # Leaves space for minimap

        # Create a surface for the resource bar — framed panel art if present,
        # else the old flat dark fill + border.
        resource_bar = pygame.Surface((top_bar_width, top_bar_height))
        background = self.frame.render(top_bar_width, top_bar_height)
        if background is not None:
            resource_bar.blit(background, (0, 0))
        else:
            resource_bar.fill((30, 30, 30))  # Darker background for resource bar
            pygame.draw.rect(resource_bar, (80, 80, 80), (0, 0, top_bar_width, top_bar_height), 2)

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
                    # Housing display
                    current_pop = len([unit for unit in self.game.units if unit.player == human_player])
                    max_pop = 20 + (len([building for building in self.game.buildings
                                      if building.player == human_player and building.name == "house"]) * 5)
                    text = f"{current_pop}/{max_pop}"
                    text_surface = self.info_font.render(text, True, (200, 200, 200))
                else:
                    # Resource amount
                    amount = int(human_player.resources.get(item, 0))
                    text = f"{amount}"
                    text_surface = self.resource_font.render(text, True, (255, 255, 255))

                # Position text next to icon
                text_x = x_pos + icon_rect.width + 5  # Small gap between icon and text
                text_y = row_y + (icon_rect.height - text_surface.get_height()) // 2  # Center with icon
                resource_bar.blit(text_surface, (text_x, text_y))

                # Income rate readout (§8.3): +X/s under the stockpile
                if item != "house" and hasattr(self.game, "income_rate"):
                    rate = self.game.income_rate(item)
                    if rate > 0.05:
                        rate_surface = self.info_font.render(f"+{rate:.1f}/s", True, (120, 220, 120))
                        resource_bar.blit(rate_surface, (text_x, text_y + text_surface.get_height()))

        # Idle-worker badge, drawn onto the banner before it goes to screen.
        self._draw_idle_badge(resource_bar, top_bar_width, top_bar_height)

        # Blit the resource bar to the main screen at the very top
        screen.blit(resource_bar, (0, 0))

    def _draw_idle_badge(self, surface, bar_w, bar_h):
        """Idle-worker badge (§7.4): amber count + F1 hint, only when nonzero.
        A single pill vertically centred at the right end of the banner (where
        the debug speed/fog widgets used to sit), clear of the population
        counter and inside the frame border."""
        idle_count = len(self.game.selection_manager.get_idle_workers())
        if not idle_count:
            return
        badge_w, badge_h = 120, 30
        content = self.frame.content_rect(bar_w, bar_h)
        x = content.right - badge_w - 6
        y = (bar_h - badge_h) // 2
        bg_rect = pygame.Rect(x, y, badge_w, badge_h)
        pygame.draw.rect(surface, (70, 55, 20), bg_rect, border_radius=5)
        pygame.draw.rect(surface, (230, 180, 60), bg_rect, 2, border_radius=5)
        text_surface = self.info_font.render(f"Idle: {idle_count} (F1)", True, (255, 210, 90))
        surface.blit(text_surface, text_surface.get_rect(center=bg_rect.center))
