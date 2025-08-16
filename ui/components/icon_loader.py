import pygame
import json


class IconLoader:
    """Manages loading and caching of all game icons"""
    
    def __init__(self):
        self.action_icons = {}
        self.building_icons = {}
        self.unit_production_icons = {}
        
        # Load all icons
        self._load_action_icons()
        self._load_building_icons()
        self._load_unit_production_icons()
    
    def _load_action_icons(self):
        """Load action button icons"""
        action_icon_files = {
            'move': ('assets/ui/move_icon.png', 60),
            'stop': ('assets/ui/stop_icon.png', 60),
            'attack': ('assets/ui/attack_icon.png', 60),
            'gather': ('assets/ui/gather_icon.png', 60),
            'deposit': ('assets/ui/deposit_icon.png', 60),
            'build': ('assets/ui/build_icon.png', 60),
            'cancel': ('assets/ui/cancel_icon.png', 24),
            'build_econ': ('assets/ui/build_econ_icon.png', 70),
            'build_mil': ('assets/ui/build_mil_icon.png', 70)
        }
        
        for action, (path, size) in action_icon_files.items():
            try:
                icon = pygame.image.load(path).convert_alpha()
                self.action_icons[action] = pygame.transform.smoothscale(icon, (size, size))
            except:
                # Create placeholder if icon not found
                placeholder = pygame.Surface((size, size), pygame.SRCALPHA)
                placeholder.fill((100, 100, 100, 200))
                pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, size, size), 2)
                self.action_icons[action] = placeholder
    
    def _load_building_icons(self):
        """Pre-load and cache building icons for better performance"""
        try:
            # Load building data
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            
            icon_size = 60  # Standard building icon size
            
            for building in buildings_data:
                try:
                    sprite_path = f"assets/sprites/Buildings/{building['name'].title()}.png"
                    building_sprite = pygame.image.load(sprite_path).convert_alpha()
                    # Pre-scale to icon size
                    building_icon = pygame.transform.scale(building_sprite, (icon_size, icon_size))
                    self.building_icons[building['name']] = building_icon
                except:
                    # Create placeholder if sprite not found
                    placeholder = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                    placeholder.fill((100, 100, 100, 200))
                    pygame.draw.rect(placeholder, (150, 150, 150), (0, 0, icon_size, icon_size), 1)
                    self.building_icons[building['name']] = placeholder
        except:
            # If loading fails, building icons will be empty
            pass
    
    def _load_unit_production_icons(self):
        """Load unit production icons from units.json"""
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            
            for unit in units_data:
                unit_name = unit['name']
                icon_path = f"assets/ui/Units/{unit_name}_icon.png"
                
                try:
                    unit_icon = pygame.image.load(icon_path).convert_alpha()
                    self.unit_production_icons[unit_name] = pygame.transform.smoothscale(unit_icon, (60, 60))
                except:
                    # Create placeholder if icon file not found
                    placeholder = pygame.Surface((60, 60))
                    placeholder.fill((100, 100, 150))
                    pygame.draw.rect(placeholder, (150, 150, 200), (0, 0, 60, 60), 2)
                    # Add text label
                    font = pygame.font.Font(None, 20)
                    text = font.render(unit_name[:4].upper(), True, (255, 255, 255))
                    text_rect = text.get_rect(center=(30, 30))
                    placeholder.blit(text, text_rect)
                    self.unit_production_icons[unit_name] = placeholder
                    
        except:
            # Create basic placeholders for common units
            for unit_type in ['worker', 'warrior', 'archer']:
                placeholder = pygame.Surface((60, 60))
                placeholder.fill((100, 50, 50))
                pygame.draw.rect(placeholder, (150, 100, 100), (0, 0, 60, 60), 2)
                self.unit_production_icons[unit_type] = placeholder
    
    def get_action_icon(self, action):
        """Get an action icon by name"""
        return self.action_icons.get(action)
    
    def get_building_icon(self, building_name):
        """Get a building icon by name"""
        return self.building_icons.get(building_name)
    
    def get_unit_production_icon(self, unit_name):
        """Get a unit production icon by name"""
        return self.unit_production_icons.get(unit_name)