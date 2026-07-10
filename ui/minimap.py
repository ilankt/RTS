import pygame
from core.config import SCREEN_WIDTH, TILE_WIDTH, TILE_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT

# Colorblind-safe resource palette (§8.1): amber / green / grey
RESOURCE_COLORS = {
    "gold": (255, 195, 60),
    "wood": (70, 160, 60),
    "stone": (170, 170, 175),
}
PING_DURATION_MS = 2000


class Minimap:
    def __init__(self, game, width, height):
        self.game = game
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))
        self.map_texture = self.create_map_texture()
        self.dragging = False
        # Object dots are redrawn at ~4 Hz onto a cached layer (D5)
        self._dots_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        self._next_dots_frame = -1
        # Active alert pings: [(mini_x, mini_y, start_ticks)]
        self._pings = []

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

    def world_to_mini(self, x, y):
        world_width = self.game.game_map.width * TILE_WIDTH * 0.75
        world_height = self.game.game_map.height * TILE_HEIGHT
        return int((x / world_width) * self.width), int((y / world_height) * self.height)

    def add_ping(self, world_x, world_y):
        """Flash an alert ping at a world position (§7.4 / §8.1)."""
        mini = self.world_to_mini(world_x, world_y)
        self._pings.append((mini[0], mini[1], pygame.time.get_ticks()))

    def _render_dots(self):
        """Redraw the object-dot layer: owner colors, resource colors, fog-aware."""
        self._dots_surface.fill((0, 0, 0, 0))
        game = self.game
        fog = getattr(game, "fog_of_war", None)
        fog_on = bool(fog and fog.enabled)
        human = game.players[0] if game.players and game.players[0].human else None

        # Resources: colored by type; hidden until explored
        for resource in game.resources:
            if fog_on and human and not fog.is_explored(human, resource.x, resource.y):
                continue
            mini_x, mini_y = self.world_to_mini(resource.x, resource.y)
            color = RESOURCE_COLORS.get(resource.name, (200, 200, 120))
            pygame.draw.rect(self._dots_surface, color, (mini_x, mini_y, 2, 2))

        # Buildings: owner color, larger/brighter than units; enemies only when
        # their tile has been explored (they don't move)
        for building in game.buildings:
            own = human is not None and building.player is human
            if fog_on and human and not own and not fog.is_explored(human, building.x, building.y):
                continue
            mini_x, mini_y = self.world_to_mini(building.x, building.y)
            color = getattr(building.player, "color", (220, 220, 220))
            pygame.draw.rect(self._dots_surface, color, (mini_x - 1, mini_y - 1, 4, 4))
            pygame.draw.rect(self._dots_surface, (255, 255, 255), (mini_x - 1, mini_y - 1, 4, 4), 1)

        # Units: owner color; enemies only while currently visible
        for unit in game.units:
            own = human is not None and unit.player is human
            if fog_on and human and not own and not fog.is_visible(human, unit.x, unit.y):
                continue
            mini_x, mini_y = self.world_to_mini(unit.x, unit.y)
            color = getattr(unit.player, "color", (220, 220, 220))
            pygame.draw.rect(self._dots_surface, color, (mini_x, mini_y, 2, 2))

    def _draw_pings(self):
        """Expanding alert rings, drawn live over the cached dot layer."""
        if not self._pings:
            return
        now = pygame.time.get_ticks()
        alive = []
        for mini_x, mini_y, started in self._pings:
            age = now - started
            if age > PING_DURATION_MS:
                continue
            alive.append((mini_x, mini_y, started))
            progress = age / PING_DURATION_MS
            radius = 3 + int(progress * 10)
            pygame.draw.circle(self.surface, (255, 60, 60), (mini_x, mini_y), radius, 1)
        self._pings = alive

    def draw(self, screen):
        self.surface.blit(self.map_texture, (0, 0))

        # Redraw the object-dot layer at a few Hz, not every frame
        frame = getattr(self.game, "frame_counter", 0)
        if frame >= self._next_dots_frame or self._next_dots_frame < 0:
            self._next_dots_frame = frame + 15
            self._render_dots()
        self.surface.blit(self._dots_surface, (0, 0))
        self._draw_pings()

        # Draw camera view
        cam_rect = pygame.Rect(
            (-self.game.camera.x / (self.game.game_map.width * TILE_WIDTH * 0.75 * self.game.camera.zoom)) * self.width,
            (-self.game.camera.y / (self.game.game_map.height * TILE_HEIGHT * self.game.camera.zoom)) * self.height,
            (MAP_VIEW_WIDTH / (self.game.game_map.width * TILE_WIDTH * 0.75 * self.game.camera.zoom)) * self.width,
            (MAP_VIEW_HEIGHT / (self.game.game_map.height * TILE_HEIGHT * self.game.camera.zoom)) * self.height
        )
        pygame.draw.rect(self.surface, (255, 255, 255), cam_rect, 1)

        screen.blit(self.surface, (SCREEN_WIDTH - self.width, 0))
