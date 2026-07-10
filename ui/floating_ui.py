import pygame

class FloatingNotification:
    """Represents a floating text notification that moves up and fades out"""
    
    def __init__(self, text, x, y, color, duration=1.0):
        self.text = text
        self.x = x
        self.y = y
        self.start_y = y
        self.color = color
        self.duration = duration
        self.elapsed_time = 0.0
        self.alive = True
        
    def update(self, delta_time):
        """Update notification position and fade"""
        self.elapsed_time += delta_time
        
        # Move upward
        self.y = self.start_y - (self.elapsed_time * 30)  # Move up 30 pixels per second
        
        # Check if expired
        if self.elapsed_time >= self.duration:
            self.alive = False
            
    def get_alpha(self):
        """Get current alpha based on elapsed time"""
        fade_progress = self.elapsed_time / self.duration
        return max(0, 255 * (1.0 - fade_progress))

class FloatingUI:
    """Handles floating UI elements for units, buildings, and construction sites"""
    
    def __init__(self, game):
        self.game = game
        
        # Health bar configuration
        self.health_bar_width = 32
        self.health_bar_height = 4
        self.health_bar_offset_y = -40  # Pixels above object
        
        # Health bar colors
        self.health_colors = {
            'high': (30, 200, 30),    # 50-100% health - Green
            'medium': (200, 200, 0),  # 25-50% health - Yellow  
            'low': (200, 0, 0),       # 0-25% health - Red
            'background': (60, 60, 60), # Background bar color
            'construction': (100, 150, 255)  # Construction progress - Blue
        }
        
        # Resource notification colors (darker, more subdued)
        self.resource_colors = {
            'gold': (200, 180, 60),     # Darker golden yellow
            'stone': (140, 140, 140),   # Darker gray
            'wood': (60, 180, 60),      # Darker green
            'food': (180, 100, 30)      # Darker orange-brown
        }
        
        # Active floating notifications
        self.notifications = []
        
        # Font for notifications (medium sized and bold)
        self.font = pygame.font.Font(None, 29)  # Reduced from 36 to 29 (20% reduction)
        self.font.set_bold(True)  # Make it bold
    
    def get_health_color(self, health_percentage):
        """Get health bar color based on health percentage"""
        if health_percentage >= 0.5:
            return self.health_colors['high']
        elif health_percentage >= 0.25:
            return self.health_colors['medium']
        else:
            return self.health_colors['low']
    
    def draw_health_bar(self, surface, obj, camera):
        """Draw health bar for a unit or building"""
        # Calculate screen position
        screen_x = (obj.x * camera.zoom) + camera.x
        screen_y = (obj.y * camera.zoom) + camera.y
        
        # Check if object is visible on screen
        if (screen_x < -50 or screen_x > surface.get_width() + 50 or 
            screen_y < -50 or screen_y > surface.get_height() + 50):
            return
        
        # Calculate health percentage
        if hasattr(obj, 'hp') and obj.hp > 0:
            # For buildings, get max HP from building data
            if hasattr(obj, 'building_name'):  # Construction site
                max_hp = obj.building_data.get('hp', 100)
                current_hp = obj.hp
            else:
                # For units and completed buildings, find max HP from data
                max_hp = self._get_max_hp(obj)
                current_hp = obj.hp
            
            health_percentage = current_hp / max_hp
        else:
            health_percentage = 0
        
        # Always show health bars (remove this condition to show all health bars)
        # if health_percentage >= 1.0 and not hasattr(obj, 'construction_progress'):
        #     return
            
        self._draw_bar(surface, screen_x, screen_y, health_percentage, 
                      self.get_health_color(health_percentage), camera.zoom)
    
    def draw_construction_bar(self, surface, construction_site, camera):
        """Draw construction progress bar for construction sites"""
        # Calculate screen position
        screen_x = (construction_site.x * camera.zoom) + camera.x
        screen_y = (construction_site.y * camera.zoom) + camera.y
        
        # Check if object is visible on screen
        if (screen_x < -50 or screen_x > surface.get_width() + 50 or 
            screen_y < -50 or screen_y > surface.get_height() + 50):
            return
        
        # Calculate construction percentage
        construction_percentage = construction_site.construction_progress / construction_site.construction_duration
        construction_percentage = min(1.0, construction_percentage)  # Cap at 100%
        
        self._draw_bar(surface, screen_x, screen_y, construction_percentage,
                      self.health_colors['construction'], camera.zoom)
    
    def _draw_bar(self, surface, screen_x, screen_y, percentage, color, zoom):
        """Draw a progress bar at the specified screen position"""
        # Scale bar size with zoom, clamped to a readable range at both ends
        # (unclamped scaling made bars detach from their units at max zoom).
        bar_width = max(16, min(int(self.health_bar_width * zoom), 48))
        bar_height = max(2, min(int(self.health_bar_height * zoom), 6))
        offset_y = max(int(self.health_bar_offset_y * zoom), -64)

        # Calculate bar position (centered above object)
        bar_x = int(screen_x - bar_width / 2)
        bar_y = int(screen_y + offset_y)

        # Draw background bar
        background_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(surface, self.health_colors['background'], background_rect)

        # Draw progress bar - anything alive shows at least 1px of fill
        if percentage > 0:
            progress_width = max(1, round(bar_width * min(percentage, 1.0)))
            progress_rect = pygame.Rect(bar_x, bar_y, progress_width, bar_height)
            pygame.draw.rect(surface, color, progress_rect)
        
        # Draw border
        pygame.draw.rect(surface, (0, 0, 0), background_rect, 1)
    
    def _get_max_hp(self, obj):
        """Get maximum HP for an object from cached game data."""
        # Units are the only objects with movement_speed; avoids an O(n)
        # list-membership scan per bar per frame.
        if getattr(obj, "movement_speed", None) is not None:
            templates = self.game.game_data["units"]
        else:
            templates = self.game.game_data["buildings"]
        template = templates.get(obj.name)
        if template:
            return template.hp
        return getattr(obj, 'hp', 100)
    
    def add_resource_notification(self, building, resource_type, amount):
        """Add a floating resource notification above a building"""
        color = self.resource_colors.get(resource_type, (255, 255, 255))
        text = f"+{int(amount)}"
        
        # Position above the building
        notification = FloatingNotification(
            text=text,
            x=building.x,
            y=building.y - 60,  # Start 60 pixels above building
            color=color,
            duration=1.0
        )
        
        self.notifications.append(notification)
    
    def add_buff_notification(self, target, text):
        """Gold float above a unit that just received an upgrade (§7.2)."""
        self.notifications.append(FloatingNotification(
            text=text,
            x=target.x + (hash(id(target)) % 16 - 8),
            y=target.y - 40,
            color=(255, 215, 80),
            duration=1.4,
        ))

    def add_damage_notification(self, target, damage_amount, is_critical=False, is_resisted=False):
        """Add a floating damage number above a target"""
        if damage_amount <= 0:
            return

        # Color based on damage type (§8.4 legibility: counter beats resisted)
        if is_critical:
            color = (255, 50, 50)  # Bright red for counter hits
            text = f"{int(damage_amount)}!"
        elif is_resisted:
            color = (160, 160, 175)  # Gray for type-disadvantaged hits
            text = f"{int(damage_amount)} resisted"
        else:
            color = (255, 200, 100)  # Orange-yellow for normal
            text = str(int(damage_amount))
        
        notification = FloatingNotification(
            text=text,
            x=target.x + (hash(id(target)) % 20 - 10),  # Slight horizontal jitter
            y=target.y - 30,
            color=color,
            duration=0.8
        )
        
        self.notifications.append(notification)
    
    def update_notifications(self, delta_time):
        """Update all floating notifications"""
        # Update existing notifications
        for notification in self.notifications[:]:  # Copy list to avoid modification during iteration
            notification.update(delta_time)
            if not notification.alive:
                self.notifications.remove(notification)
    
    def _draw_outlined_text(self, surface, text, font, color, x, y, alpha):
        """Draw text with black outline for better visibility"""
        outline_color = (0, 0, 0)  # Black outline
        outline_width = 2
        
        # Draw outline by rendering text at multiple offset positions
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:  # Skip center position
                    outline_surface = font.render(text, True, outline_color)
                    outline_surface.set_alpha(alpha)
                    outline_rect = outline_surface.get_rect()
                    outline_rect.centerx = x + dx
                    outline_rect.centery = y + dy
                    surface.blit(outline_surface, outline_rect)
        
        # Draw main text on top
        text_surface = font.render(text, True, color)
        text_surface.set_alpha(alpha)
        text_rect = text_surface.get_rect()
        text_rect.centerx = x
        text_rect.centery = y
        surface.blit(text_surface, text_rect)

    def draw_notifications(self, surface, camera):
        """Draw all floating notifications"""
        for notification in self.notifications:
            # Calculate screen position
            screen_x = (notification.x * camera.zoom) + camera.x
            screen_y = (notification.y * camera.zoom) + camera.y
            
            # Check if notification is visible on screen
            if (screen_x < -100 or screen_x > surface.get_width() + 100 or 
                screen_y < -100 or screen_y > surface.get_height() + 100):
                continue
                
            # Get alpha for fading
            alpha = int(notification.get_alpha())
            if alpha <= 0:
                continue
            
            # Draw outlined text for maximum visibility
            self._draw_outlined_text(
                surface, 
                notification.text, 
                self.font, 
                notification.color, 
                int(screen_x), 
                int(screen_y), 
                alpha
            )
    
    def draw_all_floating_ui(self, surface, camera, delta_time=1/60.0):
        """Draw all floating UI elements for visible objects"""
        # Update notifications first
        self.update_notifications(delta_time)
        
        # Draw health bars for all units
        for unit in self.game.units:
            self.draw_health_bar(surface, unit, camera)
        
        # Draw health bars for all buildings
        for building in self.game.buildings:
            self.draw_health_bar(surface, building, camera)
        
        # Draw construction progress bars for construction sites
        for construction_site in self.game.construction_sites:
            self.draw_construction_bar(surface, construction_site, camera)
            
        # Draw floating notifications
        self.draw_notifications(surface, camera)
