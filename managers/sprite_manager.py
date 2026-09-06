import pygame
import numpy as np


def tint_surface(surface, color):
    """Tints a surface with a given color, affecting only whitish pixels."""
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


def tint_directional_team(surface, color):
    result = surface.copy()
    pixels = pygame.surfarray.pixels3d(result)
    rgb = pixels.astype(np.float32)
    mask = (rgb[:, :, 2] > rgb[:, :, 0] * 1.3) & (rgb[:, :, 1] > rgb[:, :, 0] * 1.15) & (rgb[:, :, 2] > rgb[:, :, 1] * 1.1)
    shade = rgb[:, :, 2] / 200.0
    for channel in range(3):
        pixels[:, :, channel][mask] = np.clip(color[channel] * shade[mask], 0, 255).astype(np.uint8)
    del pixels
    return result


UNIT_TYPE_TINTS = {
    # Multiplicative RGB tint applied after player tint, so units that SHARE
    # a sprite sheet read distinct at a glance. Spearman/cavalry/ram got
    # dedicated sheets (sprite pipeline, 2026) — tinting those only washed
    # out their colors and made them read small/feeble. Healer got its own
    # sheet 2026-07-17 (temple/healer enablement), so its tint is gone too.
}


def tint_building_team(surface, color):
    """Recolor saturated blue cloth, preserving stone, wood and slate roofs."""
    result = surface.copy()
    pixels = pygame.surfarray.pixels3d(result)
    rgb = pixels.astype(np.float32)
    mask = (rgb[:, :, 2] > rgb[:, :, 0] * 2.0) & (rgb[:, :, 2] > rgb[:, :, 1] * 1.25)
    shade = rgb[:, :, 2] / 200.0
    for channel in range(3):
        pixels[:, :, channel][mask] = np.clip(color[channel] * shade[mask], 0, 255).astype(np.uint8)
    del pixels
    return result


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

        # §11.1 biome-matched trees: wood placed on desert renders the
        # desert tree (resource.sprite_variant = "wood_desert")
        try:
            sprites["resources"]["wood_desert"] = pygame.image.load(
                "assets/sprites/Resources/TREE_DESERT.png").convert_alpha()
        except (pygame.error, FileNotFoundError):
            pass  # generic tree everywhere when the variant art is missing

        # Load and tint unit animation sheets
        for unit_name, unit_data in self.game_data["units"].items():
            sprites["units"][unit_name] = {}
            type_tint = UNIT_TYPE_TINTS.get(unit_name)
            for anim_name, anim_path in unit_data.animations.items():
                original_sheet = pygame.image.load(anim_path).convert_alpha()
                tint = tint_directional_team if getattr(unit_data, "animation_directions", 1) == 8 else tint_surface_blue
                player_sheets = [tint(original_sheet, p.color) for p in self.players]
                if type_tint:
                    player_sheets = [apply_unit_type_tint(s, type_tint) for s in player_sheets]
                sprites["units"][unit_name][anim_name] = player_sheets

        return sprites
    
    def get_building_sprite(self, building_name, player_index):
        """Get a tinted building sprite for a specific player"""
        from systems.ages import building_sprite_path
        template=self.game_data['buildings'].get(building_name)
        fallback=getattr(template,'sprite','')
        path=building_sprite_path(building_name,self.players[player_index],fallback)
        if path and path!=fallback:
            cache = getattr(self, '_age_building_cache', None)
            if cache is None:
                self._age_building_cache = cache = {}
            key = (path, player_index, tuple(self.players[player_index].color))
            if key not in cache:
                source = pygame.image.load(path).convert_alpha()
                cache[key] = tint_building_team(source, self.players[player_index].color)
            return cache[key]
        return self.sprites["buildings"][building_name][player_index]

    def age_unit_sheets(self,variant,player_index):
        """Load only the requested player's variant, avoiding 14 full armies in RAM."""
        from systems.ages import UNIT_ART
        cache=getattr(self,'_age_unit_cache',None)
        if cache is None: self._age_unit_cache=cache={}
        key=(variant,player_index)
        if key not in cache:
            cache[key]={action:tint_directional_team(pygame.image.load(path).convert_alpha(),self.players[player_index].color)
                        for action,path in UNIT_ART[variant]['animations'].items()}
        return cache[key]

    def upgraded_unit_sheets(self, name, player_index):
        """Lazy-load the existing swordsman/archer art when a line upgrades."""
        cache = self.sprites['units']
        key = name + '_bronze'
        if key not in cache:
            folder = {'warrior': 'Warrior', 'archer': 'Archer'}[name]
            actions = ['idle', 'run', 'attack', 'guard'] if name == 'warrior' else ['idle', 'run', 'shoot']
            cache[key] = {}
            for action in actions:
                sheet = pygame.image.load(f'assets/sprites/Units/{folder}/{folder}_{action.title()}.png').convert_alpha()
                cache[key][action] = [tint_surface_blue(sheet, p.color) for p in self.players]
        return {action: sheets[player_index] for action, sheets in cache[key].items()}
    
    def get_resource_sprite(self, resource_name):
        """Get a resource sprite (no tinting). Unknown variant names fall
        back to the base wood sprite rather than KeyError."""
        sprite = self.sprites["resources"].get(resource_name)
        if sprite is None and "_" in resource_name:
            sprite = self.sprites["resources"].get(resource_name.split("_")[0])
        return sprite
    
    def get_unit_animation_sheet(self, unit_name, animation_name, player_index):
        """Get a tinted unit animation sheet for a specific player"""
        return self.sprites["units"][unit_name][animation_name][player_index]
