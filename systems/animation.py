import pygame

class Animation:
    def __init__(self, animation_sheet, frame_width, frame_height, animation_speed):
        self.animation_sheet = animation_sheet
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.animation_speed = animation_speed
        self.frames = self.load_frames()
        self.current_frame_index = 0
        self.time_accumulator = 0.0  # Accumulate time in seconds instead of using real time

    def load_frames(self):
        frames = []
        sheet_width, sheet_height = self.animation_sheet.get_size()
        for y in range(0, sheet_height, self.frame_height):
            for x in range(0, sheet_width, self.frame_width):
                # Check if the frame is within the bounds of the animation sheet
                if x + self.frame_width <= sheet_width and y + self.frame_height <= sheet_height:
                    frames.append(self.animation_sheet.subsurface(pygame.Rect(x, y, self.frame_width, self.frame_height)))
        return frames

    def update(self, custom_speed=None, delta_time=None):
        # If no delta_time provided, fall back to real-time (for backwards compatibility)
        if delta_time is None:
            # Fallback to real-time behavior
            now = pygame.time.get_ticks()
            if not hasattr(self, 'last_update'):
                self.last_update = now
            speed_to_use = custom_speed if custom_speed is not None else self.animation_speed
            if now - self.last_update > speed_to_use:
                self.last_update = now
                self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)
        else:
            # Use game time with delta_time
            self.time_accumulator += delta_time * 1000.0  # Convert to milliseconds
            speed_to_use = custom_speed if custom_speed is not None else self.animation_speed
            
            # Check if enough time has passed for next frame
            while self.time_accumulator >= speed_to_use:
                self.time_accumulator -= speed_to_use
                self.current_frame_index = (self.current_frame_index + 1) % len(self.frames)

    def get_current_frame(self):
        return self.frames[self.current_frame_index]
    
    def set_animation_speed(self, new_speed):
        """Set a new animation speed in milliseconds"""
        self.animation_speed = new_speed
