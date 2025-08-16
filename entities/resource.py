from entities.game_object import GameObject
from core.config import RESOURCE_LIMITS


class Resource(GameObject):
    """Resource entity class"""
    def __init__(self, name, sprite, x=0, y=0, radius=0):
        super().__init__(name, [1, 1], 0, sprite, x, y, radius)
        # Initialize resource amount based on resource type
        self.amount_remaining = RESOURCE_LIMITS.get(name, 100)  # Default to 100 if not specified
        self.gatherers = []  # Track units gathering from this resource