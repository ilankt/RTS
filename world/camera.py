import pygame
from core.config import CAMERA_SPEED, MIN_ZOOM, MAX_ZOOM, ZOOM_STEP

class Camera:
    def __init__(self, width, height):
        self.x = 0
        self.y = 0
        self.width = width
        self.height = height
        self.speed = CAMERA_SPEED
        self.zoom = 1.0

    def move(self, dx=0, dy=0):
        self.x += dx
        self.y += dy

    def zoom_in(self):
        self.zoom = min(self.zoom + ZOOM_STEP, MAX_ZOOM)

    def zoom_out(self):
        self.zoom = max(self.zoom - ZOOM_STEP, MIN_ZOOM)