import pygame
import json
import random
import math
from perlin_noise import PerlinNoise
from core.config import TILE_WIDTH, TILE_HEIGHT

class Map:
    def __init__(self, width, height, game):
        self.width = width
        self.height = height
        self.game = game
        self.tileset = self.load_tileset("assets/tiles/tileset.json")
        self.tile_images = self.load_tile_images("assets/tiles/tileset.png")
        self.scaled_tile_images = {}
        self.current_zoom = None
        self.grid = self.generate_perlin_map()
        self.scale_tiles(1.0)

    def load_tileset(self, filename):
        with open(filename) as f:
            return json.load(f)

    def load_tile_images(self, filename):
        images = {}
        tileset_image = pygame.image.load(filename).convert_alpha()
        for tile_info in self.tileset["tiles"]:
            name = tile_info["name"]
            location = tile_info["location"]
            x = location[0] * self.tileset["tile_width"]
            y = location[1] * self.tileset["tile_height"]
            rect = pygame.Rect(x, y, self.tileset["tile_width"], self.tileset["tile_height"])
            images[name] = tileset_image.subsurface(rect)
        return images

    def scale_tiles(self, zoom):
        if self.current_zoom == zoom:
            return

        self.current_zoom = zoom
        self.scaled_tile_images = {}
        tile_width = int(TILE_WIDTH * zoom)
        tile_height = int(TILE_HEIGHT * zoom)

        for name, image in self.tile_images.items():
            self.scaled_tile_images[name] = pygame.transform.scale(image, (tile_width, tile_height))

    def generate_perlin_map(self):
        grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        seed = random.randint(0, 100000)
        
        # Multiple noise layers for different features
        elevation_noise = PerlinNoise(octaves=5, seed=seed)
        moisture_noise = PerlinNoise(octaves=3, seed=seed + 1000)
        temperature_noise = PerlinNoise(octaves=2, seed=seed + 2000)
        detail_noise = PerlinNoise(octaves=8, seed=seed + 3000)

        # Generate elevation map with island tendency
        center_x, center_y = self.width / 2, self.height / 2
        max_dist = ((self.width / 2) ** 2 + (self.height / 2) ** 2) ** 0.5

        for r in range(self.height):
            for c in range(self.width):
                # Normalized coordinates
                nx = c / self.width
                ny = r / self.height
                
                # Distance from center for island shape
                dist_x = c - center_x
                dist_y = r - center_y
                distance = (dist_x ** 2 + dist_y ** 2) ** 0.5
                normalized_dist = distance / max_dist
                
                # Create island tendency (higher in center, lower at edges)
                island_factor = max(0, 1 - normalized_dist * 1.2)
                
                # Combine noises
                elevation = elevation_noise([nx, ny]) * 0.7 + detail_noise([nx * 4, ny * 4]) * 0.3
                elevation = elevation * 0.8 + island_factor * 0.4
                
                moisture = moisture_noise([nx, ny])
                temperature = temperature_noise([nx, ny])
                
                # Determine terrain type based on elevation, moisture, and temperature
                if elevation < -0.15:
                    grid[r][c] = "water"  # Deep ocean
                elif elevation < -0.05:
                    grid[r][c] = "water"  # Shallow water
                elif elevation < 0.05:
                    # Coastal areas
                    if moisture < -0.3:
                        grid[r][c] = "cracked_dirt"  # Dry shoreline
                    elif moisture < 0.0:
                        grid[r][c] = "dirt"  # Beach/mudflats
                    else:
                        grid[r][c] = "plains"  # Coastal plains
                elif elevation < 0.25:
                    # Lowlands
                    if temperature > 0.4 and moisture < -0.2:
                        grid[r][c] = "desert"  # Hot desert
                    elif temperature > 0.2 and moisture < -0.4:
                        grid[r][c] = "cracked_dirt"  # Badlands
                    elif moisture > 0.3:
                        grid[r][c] = "forest"  # Dense forests
                    elif moisture > 0.0:
                        grid[r][c] = "grass"   # Grasslands
                    else:
                        grid[r][c] = "plains"  # Dry plains
                elif elevation < 0.45:
                    # Hills
                    if temperature > 0.5 and moisture < -0.1:
                        grid[r][c] = "desert_hills"  # Desert hills
                    elif moisture < -0.3:
                        grid[r][c] = "rocky"   # Dry rocky hills
                    elif moisture > 0.2:
                        grid[r][c] = "forest"  # Forested hills
                    else:
                        grid[r][c] = "grass"   # Grassy hills
                elif elevation < 0.7:
                    # Mountains
                    if temperature > 0.6:
                        grid[r][c] = "dark_stone"  # Hot mountains
                    else:
                        grid[r][c] = "stone"   # Regular mountains
                else:
                    # High peaks - potential volcanic activity
                    if temperature > 0.5 and random.random() < 0.3:
                        grid[r][c] = "lava"    # Volcanic peaks
                    else:
                        grid[r][c] = "dark_stone"  # High peaks

        # Post-processing: Create lakes
        self._create_lakes(grid, seed + 4000)
        
        # Smooth transitions
        self._smooth_terrain(grid)
        
        return grid
    
    def _create_lakes(self, grid, seed):
        """Create some inland lakes and volcanic features"""
        lake_noise = PerlinNoise(octaves=2, seed=seed)
        volcanic_noise = PerlinNoise(octaves=3, seed=seed + 1000)
        
        for r in range(2, self.height - 2):
            for c in range(2, self.width - 2):
                # Create lakes in suitable terrain
                if grid[r][c] in ["grass", "plains", "forest"]:
                    lake_val = lake_noise([c/self.width * 3, r/self.height * 3])
                    if lake_val > 0.35:  # Threshold for lakes
                        # Create a small lake
                        grid[r][c] = "water"
                        # Make neighboring tiles more likely to be water
                        for dr in [-1, 0, 1]:
                            for dc in [-1, 0, 1]:
                                if 0 <= r+dr < self.height and 0 <= c+dc < self.width:
                                    if grid[r+dr][c+dc] in ["grass", "plains", "forest", "dirt"] and random.random() < 0.25:
                                        grid[r+dr][c+dc] = "water"
                
                # Create volcanic regions
                elif grid[r][c] in ["dark_stone", "stone"]:
                    volcanic_val = volcanic_noise([c/self.width * 2, r/self.height * 2])
                    if volcanic_val > 0.3:
                        # Create lava pools
                        grid[r][c] = "lava"
                        # Spread lava to nearby high elevation areas
                        for dr in [-1, 0, 1]:
                            for dc in [-1, 0, 1]:
                                if 0 <= r+dr < self.height and 0 <= c+dc < self.width:
                                    if grid[r+dr][c+dc] in ["dark_stone", "stone"] and random.random() < 0.15:
                                        grid[r+dr][c+dc] = "lava"
    
    def _smooth_terrain(self, grid):
        """Smooth terrain transitions to make them more natural"""
        # Create a copy to avoid modifying while iterating
        new_grid = [row[:] for row in grid]
        
        # Define terrain compatibility groups
        water_types = {"water"}
        coastal_types = {"dirt", "cracked_dirt", "plains"}
        vegetation_types = {"grass", "forest", "plains"}
        arid_types = {"desert", "desert_hills", "cracked_dirt"}
        mountain_types = {"stone", "dark_stone", "rocky"}
        volcanic_types = {"lava", "dark_stone"}
        
        for r in range(1, self.height - 1):
            for c in range(1, self.width - 1):
                # Count neighboring terrain types
                neighbors = {}
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        terrain = grid[r+dr][c+dc]
                        neighbors[terrain] = neighbors.get(terrain, 0) + 1
                
                current = grid[r][c]
                
                # Water propagation rules
                if neighbors.get("water", 0) >= 6:
                    new_grid[r][c] = "water"
                elif current == "water" and neighbors.get("water", 0) <= 1:
                    # Isolated water becomes appropriate land
                    coastal_neighbors = sum(neighbors.get(t, 0) for t in coastal_types)
                    if coastal_neighbors > 0:
                        new_grid[r][c] = "dirt"
                    else:
                        land_types = [(t, c) for t, c in neighbors.items() if t not in water_types]
                        if land_types:
                            new_grid[r][c] = max(land_types, key=lambda x: x[1])[0]
                
                # Oasis effect - desert near water becomes grassland
                elif current in arid_types and neighbors.get("water", 0) >= 2:
                    new_grid[r][c] = "grass"
                
                # Forest transition - grass surrounded by forest becomes forest
                elif current == "grass" and neighbors.get("forest", 0) >= 4:
                    new_grid[r][c] = "forest"
                
                # Desert expansion in hot areas
                elif current in {"plains", "dirt"} and neighbors.get("desert", 0) >= 3:
                    if random.random() < 0.3:  # 30% chance
                        new_grid[r][c] = "cracked_dirt"
                
                # Mountain transitions
                elif current == "rocky" and neighbors.get("stone", 0) >= 4:
                    new_grid[r][c] = "stone"
                
                # Volcanic cooling - isolated lava becomes dark stone
                elif current == "lava" and neighbors.get("lava", 0) <= 1:
                    new_grid[r][c] = "dark_stone"
        
        # Copy back
        for r in range(self.height):
            for c in range(self.width):
                grid[r][c] = new_grid[r][c]

    def find_spawn_locations(self, num_players):
        """Find safe spawn locations for players, spread as far apart as possible"""
        import math
        
        # Define safe terrain for spawning
        safe_terrain = {"grass", "plains", "forest", "dirt"}
        
        # Find all potential spawn areas (safe terrain with some space around)
        potential_spawns = []
        for r in range(5, self.height - 5):  # Leave border margin
            for c in range(5, self.width - 5):
                if self.grid[r][c] in safe_terrain:
                    # Check if there's enough safe terrain in a 5x5 area around this point
                    safe_count = 0
                    for dr in range(-2, 3):
                        for dc in range(-2, 3):
                            if self.grid[r + dr][c + dc] in safe_terrain:
                                safe_count += 1
                    
                    if safe_count >= 15:  # At least 15 out of 25 tiles are safe
                        potential_spawns.append((r, c))
        
        if len(potential_spawns) < num_players:
            # Fallback: just find any safe terrain
            potential_spawns = []
            for r in range(2, self.height - 2):
                for c in range(2, self.width - 2):
                    if self.grid[r][c] in safe_terrain:
                        potential_spawns.append((r, c))
        
        if len(potential_spawns) < num_players:
            raise ValueError(f"Not enough safe spawn locations for {num_players} players")
        
        # Select spawn locations to maximize distance between players
        selected_spawns = []
        
        # Start with a random spawn location
        import random
        first_spawn = random.choice(potential_spawns)
        selected_spawns.append(first_spawn)
        potential_spawns.remove(first_spawn)
        
        # For each remaining player, select the spawn that's farthest from all existing spawns
        for _ in range(num_players - 1):
            best_spawn = None
            best_min_distance = -1
            
            for candidate in potential_spawns:
                # Calculate minimum distance to any existing spawn
                min_distance = float('inf')
                for existing in selected_spawns:
                    distance = math.sqrt((candidate[0] - existing[0])**2 + (candidate[1] - existing[1])**2)
                    min_distance = min(min_distance, distance)
                
                # Keep track of the candidate with the largest minimum distance
                if min_distance > best_min_distance:
                    best_min_distance = min_distance
                    best_spawn = candidate
            
            if best_spawn:
                selected_spawns.append(best_spawn)
                potential_spawns.remove(best_spawn)
        
        return selected_spawns
    
    def find_safe_spawn_position(self, radius, center_pos=None, search_range=None):
        """Find a safe position to spawn an object of a given radius, optionally near a center point."""
        safe_terrain = {"grass", "plains", "forest", "dirt"}

        for _ in range(200):  # More attempts to find a suitable position
            if center_pos and search_range:
                min_dist, max_dist = search_range
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(min_dist, max_dist)
                world_x = center_pos[0] + distance * math.cos(angle)
                world_y = center_pos[1] + distance * math.sin(angle)
                grid_pos = self.world_to_grid(world_x, world_y)
                if not grid_pos:
                    continue
                col, row = grid_pos
            else:
                # Find a random spot anywhere, avoiding map edges
                row = random.randint(5, self.height - 6)
                col = random.randint(5, self.width - 6)
                world_x, world_y = self.grid_to_world(col, row)

            if self.grid[row][col] in safe_terrain:
                # Check terrain in a small area around the point for consistency
                is_safe_terrain = True
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        check_row, check_col = row + i, col + j
                        if not (0 <= check_row < self.height and 0 <= check_col < self.width and self.grid[check_row][check_col] in safe_terrain):
                            is_safe_terrain = False
                            break
                    if not is_safe_terrain:
                        break
                
                if is_safe_terrain:
                    # Check for collisions with all existing game objects
                    collision = False
                    all_objects = self.game.buildings + self.game.units + self.game.resources
                    for obj in all_objects:
                        dist = math.sqrt((world_x - obj.x)**2 + (world_y - obj.y)**2)
                        if dist < (obj.radius + radius + 5): # 5px buffer
                            collision = True
                            break
                    
                    if not collision:
                        return (world_x, world_y)

        return None # Could not find a safe position

    def grid_to_world(self, grid_x, grid_y):
        """Convert grid coordinates to world coordinates (matching hex grid positioning)"""
        from core.config import TILE_WIDTH, TILE_HEIGHT
        # Match the hex grid positioning used in draw()
        col, row = grid_x, grid_y
        world_x = col * TILE_WIDTH * 0.75
        world_y = row * TILE_HEIGHT
        if col % 2 != 0:
            world_y += TILE_HEIGHT / 2
        return world_x, world_y
    
    def world_to_grid(self, world_x, world_y):
        """Convert world coordinates to grid coordinates (inverse of grid_to_world)"""
        from core.config import TILE_WIDTH, TILE_HEIGHT
        
        # First approximation for column
        col = int(world_x / (TILE_WIDTH * 0.75))
        
        # Check if col is in bounds
        if col < 0 or col >= self.width:
            return None
            
        # Calculate row based on column parity
        if col % 2 == 0:
            row = int(world_y / TILE_HEIGHT)
        else:
            row = int((world_y - TILE_HEIGHT / 2) / TILE_HEIGHT)
        
        # Bounds check
        if row < 0 or row >= self.height:
            return None
            
        # Verify and refine by checking neighboring tiles
        # This is needed because hex grids can be tricky at tile boundaries
        best_col, best_row = col, row
        best_dist = float('inf')
        
        # Check the guessed tile and its neighbors
        for dc in [-1, 0, 1]:
            for dr in [-1, 0, 1]:
                check_col = col + dc
                check_row = row + dr
                
                if 0 <= check_col < self.width and 0 <= check_row < self.height:
                    # Get center of this tile
                    center_x, center_y = self.grid_to_world(check_col, check_row)
                    center_x += TILE_WIDTH * 0.375  # Half of 0.75 (hex width factor)
                    center_y += TILE_HEIGHT / 2
                    
                    # Calculate distance to our point
                    dist = ((world_x - center_x) ** 2 + (world_y - center_y) ** 2) ** 0.5
                    
                    if dist < best_dist:
                        best_dist = dist
                        best_col = check_col
                        best_row = check_row
        
        return (best_col, best_row)

    def draw(self, surface, camera):
        tile_width = int(TILE_WIDTH * camera.zoom)
        tile_height = int(TILE_HEIGHT * camera.zoom)

        # Culling
        start_col = max(0, int(-camera.x / (tile_width * 0.75)) - 1)
        end_col = min(self.width, int((-camera.x + surface.get_width()) / (tile_width * 0.75)) + 1)
        start_row = max(0, int(-camera.y / tile_height) - 1)
        end_row = min(self.height, int((-camera.y + surface.get_height()) / tile_height) + 1)

        for row in range(start_row, end_row):
            for col in range(start_col, end_col):
                tile_name = self.grid[row][col]
                tile_image = self.scaled_tile_images[tile_name]

                # Calculate position for hex grid
                x = col * tile_width * 0.75
                y = row * tile_height
                if col % 2 != 0:
                    y += tile_height / 2

                surface.blit(tile_image, (x + camera.x, y + camera.y))

