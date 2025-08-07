import pygame

class Animation:
    def __init__(self, animation_sheet, frame_width, frame_height, animation_speed):
        self.animation_sheet = animation_sheet
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.animation_speed = animation_speed
        self.frames = self.load_frames()
        self.current_frame_index = 0
        self.last_update = pygame.time.get_ticks()

    def load_frames(self):
        frames = []
        sheet_width, sheet_height = self.animation_sheet.get_size()
        for y in range(0, sheet_height, self.frame_height):
            for x in range(0, sheet_width, self.frame_width):
                # Check if the frame is within the bounds of the animation sheet
                if x + self.frame_width <= sheet_width and y + self.frame_height <= sheet_height:
                    frames.append(self.animation_sheet.subsurface(pygame.Rect(x, y, self.frame_width, self.frame_height)))
        return frames

    def update(self, custom_speed=None):
        now = pygame.time.get_ticks()
        speed_to_use = custom_speed if custom_speed is not None else self.animation_speed
        if now - self.last_update > speed_to_use:
            self.last_update = now
            self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

    def get_current_frame(self):
        return self.frames[self.current_frame_index]
    
    def set_animation_speed(self, new_speed):
        """Set a new animation speed in milliseconds"""
        self.animation_speed = new_speed
