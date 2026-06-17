import random
from core.config import CAMERA_SPEED, MIN_ZOOM, MAX_ZOOM, ZOOM_STEP

class Camera:
    def __init__(self, width, height):
        self.x = 0
        self.y = 0
        self.width = width
        self.height = height
        self.speed = CAMERA_SPEED
        self.zoom = 1.0
        
        # Screen shake
        self.shake_amount = 0.0
        self.shake_decay = 5.0  # Decay per second

    def move(self, dx=0, dy=0):
        self.x += dx
        self.y += dy
    
    def add_shake(self, amount):
        """Add screen shake intensity"""
        self.shake_amount = max(self.shake_amount, amount)
    
    def update_shake(self, delta_time):
        """Update and return current shake offset"""
        self.shake_amount = max(0.0, self.shake_amount - self.shake_decay * delta_time)
        if self.shake_amount > 0:
            offset_x = random.uniform(-self.shake_amount, self.shake_amount)
            offset_y = random.uniform(-self.shake_amount, self.shake_amount)
            return (offset_x, offset_y)
        return (0, 0)

    def zoom_in(self):
        self.zoom = min(self.zoom + ZOOM_STEP, MAX_ZOOM)

    def zoom_out(self):
        self.zoom = max(self.zoom - ZOOM_STEP, MIN_ZOOM)
