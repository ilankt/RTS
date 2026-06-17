import pygame
from core.config import SCREEN_WIDTH, TILE_WIDTH, TILE_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT

class Minimap:
    def __init__(self, game, width, height):
        self.game = game
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))
        self.map_texture = self.create_map_texture()
        self.dragging = False

    def create_map_texture(self):
        map_texture = pygame.Surface((self.game.game_map.width, self.game.game_map.height))
        for y, row in enumerate(self.game.game_map.grid):
            for x, tile_name in enumerate(row):
                tile_image = self.game.game_map.tile_images[tile_name]
                avg_color = pygame.transform.average_color(tile_image)
                map_texture.set_at((x, y), avg_color)
        return pygame.transform.scale(map_texture, (self.width, self.height))

    def handle_click(self, mouse_pos):
        self.dragging = True
        self.handle_drag(mouse_pos)

    def handle_drag(self, mouse_pos):
        if self.dragging:
            mini_x, mini_y = mouse_pos
            mini_x -= (SCREEN_WIDTH - self.width)
            
            # Convert minimap coordinates to world coordinates
            world_x = (mini_x / self.width) * (self.game.game_map.width * TILE_WIDTH * 0.75)
            world_y = (mini_y / self.height) * (self.game.game_map.height * TILE_HEIGHT)

            # Center the camera on the clicked position
            self.game.camera.x = -world_x * self.game.camera.zoom + MAP_VIEW_WIDTH / 2
            self.game.camera.y = -world_y * self.game.camera.zoom + MAP_VIEW_HEIGHT / 2

    def handle_release(self):
        self.dragging = False

    def draw(self, screen):
        self.surface.blit(self.map_texture, (0, 0))

        # Draw objects
        for obj in self.game.units + self.game.buildings + self.game.resources:
            mini_x = int((obj.x / (self.game.game_map.width * TILE_WIDTH * 0.75)) * self.width)
            mini_y = int((obj.y / (self.game.game_map.height * TILE_HEIGHT)) * self.height)
            
            # Scale object size for minimap
            size_x = max(2, int(obj.size[0] * (self.width / self.game.game_map.width)))
            size_y = max(2, int(obj.size[1] * (self.height / self.game.game_map.height)))

            pygame.draw.rect(self.surface, (0, 255, 0), (mini_x, mini_y, size_x, size_y))

        # Draw camera view
        cam_rect = pygame.Rect(
            (-self.game.camera.x / (self.game.game_map.width * TILE_WIDTH * 0.75 * self.game.camera.zoom)) * self.width,
            (-self.game.camera.y / (self.game.game_map.height * TILE_HEIGHT * self.game.camera.zoom)) * self.height,
            (MAP_VIEW_WIDTH / (self.game.game_map.width * TILE_WIDTH * 0.75 * self.game.camera.zoom)) * self.width,
            (MAP_VIEW_HEIGHT / (self.game.game_map.height * TILE_HEIGHT * self.game.camera.zoom)) * self.height
        )
        pygame.draw.rect(self.surface, (255, 255, 255), cam_rect, 1)

        screen.blit(self.surface, (SCREEN_WIDTH - self.width, 0))
