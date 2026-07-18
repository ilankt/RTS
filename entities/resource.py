from entities.game_object import GameObject
from core.config import RESOURCE_LIMITS


class Resource(GameObject):
    """Resource entity class"""
    def __init__(self, name, sprite, x=0, y=0, radius=0):
        super().__init__(name, [1, 1], 0, sprite, x, y, radius)
        # Initialize resource amount based on resource type
        self.amount_remaining = RESOURCE_LIMITS.get(name, 100)  # Default to 100 if not specified
        self.gatherers = []  # Track units gathering from this resource
        self.sprite_variant = None  # §11.1 biome art (e.g. "wood_desert")


def assign_biome_sprite(resource, game_map):
    """§11.1 biome-matched trees: wood standing on desert renders the
    desert tree. Called wherever a resource gains a position — placement,
    regrowth, and save restore (after terrain is back)."""
    if getattr(resource, "name", None) != "wood" or game_map is None:
        return
    grid_pos = game_map.world_to_grid(resource.x, resource.y)
    if grid_pos and game_map.grid[grid_pos[1]][grid_pos[0]] == "desert":
        resource.sprite_variant = "wood_desert"
    else:
        resource.sprite_variant = None