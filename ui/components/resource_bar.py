import pygame
from core.config import SCREEN_WIDTH, MINIMAP_WIDTH, TOP_BAR_HEIGHT, TOP_BAR_START_X, TOP_BAR_SPACING, TOP_BAR_ROW_Y, TOP_BAR_ITEMS


class ResourceBar:
    """Manages the top resource display bar"""
    
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.Font(None, 30)
        self.resource_font = pygame.font.Font(None, 32)  # Larger font for resources
        self.info_font = pygame.font.Font(None, 24)      # Smaller font for info row
        self.small_font = pygame.font.Font(None, 20)
    
    def draw(self, screen):
        """Draw the top resource bar"""
        if not self.game.players:
            return
            
        human_player = self.game.players[0]  # First player is human
        
        # Top bar dimensions - spans screen width minus minimap
        top_bar_height = TOP_BAR_HEIGHT
        top_bar_width = SCREEN_WIDTH - MINIMAP_WIDTH  # Leaves space for minimap
        
        # Create a surface for the resource bar
        resource_bar = pygame.Surface((top_bar_width, top_bar_height))
        resource_bar.fill((30, 30, 30))  # Darker background for resource bar
        
        # Draw a subtle border
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
        
        # Blit the resource bar to the main screen at the very top
        screen.blit(resource_bar, (0, 0))
        
        # Draw game speed indicator
        self._draw_speed_indicator(screen)
    
    def _draw_speed_indicator(self, screen):
        """Draw game speed indicator in top-right corner of resource bar"""
        # Position in top-right of resource bar area
        x = SCREEN_WIDTH - MINIMAP_WIDTH - 120  # Leave margin from minimap
        y = 10
        
        # Get current game speed
        speed = getattr(self.game, 'game_speed', 1.0)
        
        # Create background box
        bg_rect = pygame.Rect(x, y, 100, 30)
        pygame.draw.rect(screen, (40, 40, 40), bg_rect)
        pygame.draw.rect(screen, (100, 100, 100), bg_rect, 2)
        
        # Draw speed text
        speed_text = f"Speed: {speed:.0f}x"
        if speed > 1.0:
            # Use different color for increased speed
            color = (100, 255, 100)  # Green for fast
        else:
            color = (255, 255, 255)  # White for normal
            
        text_surface = self.font.render(speed_text, True, color)
        text_rect = text_surface.get_rect(center=bg_rect.center)
        screen.blit(text_surface, text_rect)
        
        # Draw keyboard hint below
        hint_text = "[ ] to adjust"
        hint_surface = self.small_font.render(hint_text, True, (150, 150, 150))
        hint_rect = hint_surface.get_rect(centerx=bg_rect.centerx, top=bg_rect.bottom + 2)
        screen.blit(hint_surface, hint_rect)