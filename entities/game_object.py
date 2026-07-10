class GameObject:
    """Base class for all game objects"""
    def __init__(self, name, size, hp, sprite, x, y, radius, player=None):
        self.name = name
        self.size = size  # Keep size for now, might be useful for other things
        self.hp = hp
        self.sprite = sprite
        self.x = x
        self.y = y
        self.radius = radius
        self.selected = False
        self.player = player
        # False once removed from the game's lists; O(1) liveness check that
        # replaces `obj in game.<list>` membership scans in hot paths.
        self.in_world = True