import pygame
import numpy as np
from systems.animation import Animation


def tint_surface(surface, color):
    """Tints a surface with a given color, affecting only whitish pixels."""
    import numpy as np
    
    # Convert to array for fast pixel manipulation
    arr = pygame.surfarray.array3d(surface).copy().astype(np.float32)
    
    # Create mask for whitish pixels
    mask = (arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] > 200)
    
    # Apply tinting only to masked pixels - multiply by color components
    arr[:,:,0][mask] = arr[:,:,0][mask] * color[0] / 255.0
    arr[:,:,1][mask] = arr[:,:,1][mask] * color[1] / 255.0
    arr[:,:,2][mask] = arr[:,:,2][mask] * color[2] / 255.0
    
    # Convert back to uint8
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    
    # Create new surface from array
    tinted_surface = pygame.surfarray.make_surface(arr)
    
    # Handle alpha channel
    if surface.get_flags() & pygame.SRCALPHA:
        tinted_surface = tinted_surface.convert_alpha()
        alpha_arr = pygame.surfarray.array_alpha(surface)
        pygame.surfarray.pixels_alpha(tinted_surface)[:] = alpha_arr
    
    return tinted_surface


def tint_surface_blue(surface, color):
    """Tints a surface with a given color, affecting only blue pixels around RGB(72,88,132) or RGB(70,151,172)."""
    import numpy as np
    
    # Convert to array for fast pixel manipulation
    arr = pygame.surfarray.array3d(surface).copy().astype(np.float32)
    
    # Define blue color targets with tolerance
    blue1 = np.array([72, 88, 132])   # First blue target
    blue2 = np.array([70, 151, 172])  # Second blue target  
    tolerance = 25  # Color tolerance for detection
    
    # Create masks for both blue colors with tolerance
    diff1 = np.abs(arr - blue1)
    diff2 = np.abs(arr - blue2)
    
    mask1 = (diff1[:,:,0] <= tolerance) & (diff1[:,:,1] <= tolerance) & (diff1[:,:,2] <= tolerance)
    mask2 = (diff2[:,:,0] <= tolerance) & (diff2[:,:,1] <= tolerance) & (diff2[:,:,2] <= tolerance)
    
    # Combine masks
    mask = mask1 | mask2
    
    # Replace blue pixels with player color
    arr[:,:,0][mask] = color[0]
    arr[:,:,1][mask] = color[1] 
    arr[:,:,2][mask] = color[2]
    
    # Convert back to uint8
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    
    # Create new surface from array
    tinted_surface = pygame.surfarray.make_surface(arr)
    
    # Handle alpha channel
    if surface.get_flags() & pygame.SRCALPHA:
        tinted_surface = tinted_surface.convert_alpha()
        alpha_arr = pygame.surfarray.array_alpha(surface)
        pygame.surfarray.pixels_alpha(tinted_surface)[:] = alpha_arr
    
    return tinted_surface


UNIT_TYPE_TINTS = {
    # Multiplicative RGB tint applied after player tint, so units that share
    # a sprite sheet (warrior/spearman/cavalry, archer/healer) read distinct
    # at a glance.
    "spearman": (180, 230, 180),  # greenish - light infantry
    "cavalry":  (240, 200, 160),  # tan/warm - mounted
    "healer":   (200, 230, 240),  # cool cyan - support
}


def apply_unit_type_tint(surface, color):
    """Multiply RGB by `color/255`, leaving alpha untouched."""
    tinted = surface.copy()
    overlay = pygame.Surface(surface.get_size())
    overlay.fill(color)
    tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    return tinted


class SpriteManager:
    """Manages loading and tinting of game sprites"""

    def __init__(self, game_data, players):
        self.game_data = game_data
        self.players = players
        self.sprites = self.load_sprites()

    def load_sprites(self):
        sprites = {"buildings": {}, "resources": {}, "units": {}}

        # Load and tint building sprites
        for building_name, building_data in self.game_data["buildings"].items():
            original_sprite = pygame.image.load(building_data.sprite).convert_alpha()
            sprites["buildings"][building_name] = [tint_surface(original_sprite, p.color) for p in self.players]

        # Load and tint construction sprite
        construction_sprite = pygame.image.load("assets/sprites/Buildings/Construction.png").convert_alpha()
        sprites["buildings"]["construction"] = [tint_surface(construction_sprite, p.color) for p in self.players]

        # Load resource sprites (no tinting)
        for resource_name, resource_data in self.game_data["resources"].items():
            sprites["resources"][resource_name] = pygame.image.load(resource_data.sprite).convert_alpha()

        # Load and tint unit animation sheets
        for unit_name, unit_data in self.game_data["units"].items():
            sprites["units"][unit_name] = {}
            type_tint = UNIT_TYPE_TINTS.get(unit_name)
            for anim_name, anim_path in unit_data.animations.items():
                original_sheet = pygame.image.load(anim_path).convert_alpha()
                player_sheets = [tint_surface_blue(original_sheet, p.color) for p in self.players]
                if type_tint:
                    player_sheets = [apply_unit_type_tint(s, type_tint) for s in player_sheets]
                sprites["units"][unit_name][anim_name] = player_sheets

        return sprites
    
    def get_building_sprite(self, building_name, player_index):
        """Get a tinted building sprite for a specific player"""
        return self.sprites["buildings"][building_name][player_index]
    
    def get_resource_sprite(self, resource_name):
        """Get a resource sprite (no tinting)"""
        return self.sprites["resources"][resource_name]
    
    def get_unit_animation_sheet(self, unit_name, animation_name, player_index):
        """Get a tinted unit animation sheet for a specific player"""
        return self.sprites["units"][unit_name][animation_name][player_index]