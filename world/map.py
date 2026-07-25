import pygame
import json
import random
import math
from collections import deque
from perlin_noise import PerlinNoise
from core.config import TILE_WIDTH, TILE_HEIGHT, SPAWN_SAFE_TERRAIN

# §11.1 anti-repetition: tile types whose single bitmap gets DERIVED
# variants (hex-symmetric flips + 180° rotation — the flat-top silhouette
# still interlocks). High-coverage organic ground only: adjacent identical
# bitmaps read as obvious cloning there, while rare structural tiles
# (stone, lava) don't repeat enough to matter. Real per-variant art in
# tileset.json ("variants": [[col,row], ...]) overrides derivation.
DERIVED_VARIANT_TILES = {"grass", "desert", "swamp", "dirt",
                         "water_shallow", "water_deep"}

# §11.1 edge transitions: the HIGHER-priority terrain feathers into its
# lower-priority hex neighbours, so biome borders blend instead of cutting
# a hard sawtooth. Grass creeps over everything, land over water, shallow
# over deep. Purely visual — gameplay reads the grid, never this.
TERRAIN_BLEND_PRIORITY = {"water_deep": 0, "water_shallow": 1, "dirt": 2,
                          "desert": 3, "swamp": 4, "grass": 5}
# Two blend profiles (user feedback 2026-07-18: straight-gradient fronts
# rounded into scalloped "bites" at land borders, and the shallow->deep
# line stayed too stark):
# - land bleeds: shallower feather with a NOISE-RAGGED front — organic
#   creep (grass tufts into sand) instead of airbrush circles
# - water-into-water: much wider, perfectly smooth feather — a gradual
#   depth gradient
TRANSITION_FEATHER_LAND = 24
TRANSITION_FEATHER_WATER = 52
TRANSITION_RAGGEDNESS = 0.95  # 0 = smooth gradient, ~1 = strongly ragged


class Map:
    def __init__(self, width, height, game):
        self.width = width
        self.height = height
        self.game = game
        self.tileset = self.load_tileset("assets/tiles/tileset.json")
        # Also builds self.tile_variants: {name: [Surface, ...]}
        self.tile_images = self.load_tile_images("assets/tiles/tileset.png")
        self.scaled_tile_images = {}
        self.scaled_tile_variants = {}
        # §11.1 edge transitions: per-direction feather masks + pre-blended
        # neighbour-bleed surfaces, cached at sheet resolution then scaled
        self.transition_base = self._build_transition_bases()
        self.scaled_transitions = {}
        self.edge_overlays = {}
        self.current_zoom = None
        # Regenerate rather than accept a drowned map: the wetter generator
        # (2026-07-25 — bigger lakes, higher sea level) can on a rare seed
        # flood so much ground that spawns and economy can't fit. Accept only
        # when the largest land component still covers most of the world.
        for _attempt in range(6):
            self.grid = self.generate_perlin_map()
            if len(self.largest_land_component()) >= 0.55 * self.width * self.height:
                break
        self.build_transitions()
        self.scale_tiles(1.0)

    def load_tileset(self, filename):
        with open(filename) as f:
            return json.load(f)

    def load_tile_images(self, filename):
        """Base image per tile name; also fills self.tile_variants with the
        full variant list per name (sheet-provided variants when the JSON
        has them, derived flips for DERIVED_VARIANT_TILES, else just the
        base)."""
        images = {}
        self.tile_variants = {}
        tileset_image = pygame.image.load(filename).convert_alpha()
        tile_w = self.tileset["tile_width"]
        tile_h = self.tileset["tile_height"]

        def cut(location):
            rect = pygame.Rect(location[0] * tile_w, location[1] * tile_h,
                               tile_w, tile_h)
            return tileset_image.subsurface(rect)

        for tile_info in self.tileset["tiles"]:
            name = tile_info["name"]
            base = cut(tile_info["location"])
            images[name] = base
            sheet_variants = [cut(loc) for loc in tile_info.get("variants", ())]
            if sheet_variants:
                self.tile_variants[name] = [base] + sheet_variants
            elif name in DERIVED_VARIANT_TILES:
                self.tile_variants[name] = [
                    base,
                    pygame.transform.flip(base, True, False),
                    pygame.transform.flip(base, False, True),
                    pygame.transform.rotate(base, 180),
                ]
            else:
                self.tile_variants[name] = [base]
        return images

    @staticmethod
    def _value_noise(x, y, salt):
        """Deterministic smooth value noise in [0, 1] — coarse hash grid
        with bilinear interpolation. No RNG streams involved."""
        import math

        def lattice(ix, iy):
            h = math.sin(ix * 127.1 + iy * 311.7 + salt * 74.7) * 43758.5453
            return h - math.floor(h)

        cell = 9.0
        fx, fy = x / cell, y / cell
        ix, iy = int(fx), int(fy)
        tx, ty = fx - ix, fy - iy
        a = lattice(ix, iy)
        b = lattice(ix + 1, iy)
        c = lattice(ix, iy + 1)
        d = lattice(ix + 1, iy + 1)
        top = a + (b - a) * tx
        bottom = c + (d - c) * tx
        return top + (bottom - top) * ty

    def _build_edge_masks(self, feather, raggedness):
        """Six feather masks at sheet resolution — direction order matches
        hex_neighbors: N, S, NW, SW, NE, SE. Alpha fades from the hex edge
        `feather` px inward; `raggedness` > 0 warps the front with smooth
        noise so the blend line creeps organically instead of scalloping
        into circles (user feedback). Clipped to the hex silhouette."""
        tile_w = self.tileset["tile_width"]
        tile_h = self.tileset["tile_height"]
        quarter, half_h = tile_w * 0.25, tile_h * 0.5

        # Edge segments in direction order (see hex vertex layout in draw())
        edges = [
            ((quarter, 0), (tile_w - quarter, 0)),                    # N
            ((quarter, tile_h), (tile_w - quarter, tile_h)),          # S
            ((0, half_h), (quarter, 0)),                              # NW
            ((quarter, tile_h), (0, half_h)),                         # SW
            ((tile_w - quarter, 0), (tile_w, half_h)),                # NE
            ((tile_w, half_h), (tile_w - quarter, tile_h)),           # SE
        ]
        center = (tile_w * 0.5, tile_h * 0.5)
        lines = []  # (nx, ny, d0) with inward-positive distance
        for (x1, y1), (x2, y2) in edges:
            nx, ny = y2 - y1, x1 - x2  # a normal of the edge
            length = max(1e-9, (nx * nx + ny * ny) ** 0.5)
            nx, ny = nx / length, ny / length
            d0 = nx * x1 + ny * y1
            if nx * center[0] + ny * center[1] - d0 < 0:
                nx, ny, d0 = -nx, -ny, -d0  # flip so inside is positive
            lines.append((nx, ny, d0))

        buffers = [bytearray(tile_w * tile_h * 4) for _ in range(6)]
        for y in range(tile_h):
            row_base = y * tile_w * 4
            for x in range(tile_w):
                dists = [nx * (x + 0.5) + ny * (y + 0.5) - d0
                         for nx, ny, d0 in lines]
                if min(dists) < -0.5:
                    continue  # outside the hex silhouette
                offset = row_base + x * 4
                for index, dist in enumerate(dists):
                    fade = 1.0 - dist / feather
                    if raggedness and -0.6 < fade < 1.4:
                        # Warp the front: each direction gets its own noise
                        # field so neighbouring overlays don't rhyme
                        noise = self._value_noise(x, y, index)
                        fade += (noise - 0.5) * raggedness
                    alpha = int(min(1.0, max(0.0, fade)) * 255)
                    if alpha:
                        buf = buffers[index]
                        buf[offset] = buf[offset + 1] = buf[offset + 2] = 255
                        buf[offset + 3] = alpha
        return [pygame.image.frombuffer(bytes(buf), (tile_w, tile_h), "RGBA")
                for buf in buffers]

    def _build_transition_bases(self):
        """(terrain, direction) -> that terrain's texture pre-masked with
        the direction's feather, at sheet resolution. Blitted over a
        neighbouring tile it reads as this terrain bleeding across the
        shared edge. Water bleeding into water uses the wide smooth
        profile (a depth gradient); everything else uses the shallower
        ragged profile (organic creep). Uses each terrain's base variant —
        the feather hides any variant mismatch."""
        from core.config import WATER_TERRAIN

        land_masks = self._build_edge_masks(TRANSITION_FEATHER_LAND,
                                            TRANSITION_RAGGEDNESS)
        water_masks = self._build_edge_masks(TRANSITION_FEATHER_WATER, 0.0)
        bases = {}
        for name, image in self.tile_images.items():
            masks = water_masks if name in WATER_TERRAIN else land_masks
            for direction, mask in enumerate(masks):
                blended = image.convert_alpha()
                blended.blit(mask, (0, 0),
                             special_flags=pygame.BLEND_RGBA_MULT)
                bases[(name, direction)] = blended
        return bases

    def build_transitions(self):
        """Precompute, per map cell, which neighbours bleed into it (sparse
        dict — most cells are biome interior). Terrain only changes at
        generation and save-restore, so this runs once per map, not per
        frame."""
        overlays = {}
        priority = TERRAIN_BLEND_PRIORITY
        for r in range(self.height):
            for c in range(self.width):
                own = priority.get(self.grid[r][c], 0)
                entry = []
                for direction, (nr, nc) in enumerate(self.hex_neighbors(r, c)):
                    if not (0 <= nr < self.height and 0 <= nc < self.width):
                        continue
                    name = self.grid[nr][nc]
                    if priority.get(name, 0) > own:
                        entry.append((direction, name))
                if entry:
                    overlays[(r, c)] = entry
        self.edge_overlays = overlays

    def scale_tiles(self, zoom):
        if self.current_zoom == zoom:
            return

        self.current_zoom = zoom
        tile_width = int(TILE_WIDTH * zoom)
        tile_height = int(TILE_HEIGHT * zoom)

        self.scaled_tile_variants = {
            name: [pygame.transform.scale(v, (tile_width, tile_height))
                   for v in variant_list]
            for name, variant_list in self.tile_variants.items()
        }
        # Back-compat: "the" image for a name = its base variant
        self.scaled_tile_images = {
            name: variants[0]
            for name, variants in self.scaled_tile_variants.items()
        }
        self.scaled_transitions = {
            key: pygame.transform.scale(surface, (tile_width, tile_height))
            for key, surface in self.transition_base.items()
        }

    @staticmethod
    def hex_neighbors(row, col):
        """The six true hex neighbours of an offset-grid cell. Flat-top
        layout with ODD columns shifted DOWN half a tile (see draw()) —
        the offsets are parity-dependent, and this is the codebase's one
        authoritative statement of them (§11.2 reachability BFS)."""
        if col % 2 == 0:
            return ((row - 1, col), (row + 1, col),
                    (row - 1, col - 1), (row, col - 1),
                    (row - 1, col + 1), (row, col + 1))
        return ((row - 1, col), (row + 1, col),
                (row, col - 1), (row + 1, col - 1),
                (row, col + 1), (row + 1, col + 1))

    def largest_land_component(self):
        """The set of (r, c) tiles in the biggest connected walkable region
        (true hex adjacency). Spawn selection confines castles to it —
        before this, a 5x5-safe POCKET sealed off by water could be picked
        as a spawn and that player's economy was stranded for the match
        (§11.2 reachability work exposed it)."""
        from core.config import BLOCKED_TERRAIN

        best = set()
        seen_all = set()
        for r in range(self.height):
            for c in range(self.width):
                if (r, c) in seen_all or self.grid[r][c] in BLOCKED_TERRAIN:
                    continue
                component = {(r, c)}
                frontier = [(r, c)]
                seen_all.add((r, c))
                while frontier:
                    cr, cc = frontier.pop()
                    for nr, nc in self.hex_neighbors(cr, cc):
                        if not (0 <= nr < self.height and 0 <= nc < self.width):
                            continue
                        if (nr, nc) in seen_all or self.grid[nr][nc] in BLOCKED_TERRAIN:
                            continue
                        seen_all.add((nr, nc))
                        component.add((nr, nc))
                        frontier.append((nr, nc))
                if len(component) > len(best):
                    best = component
        return best

    @staticmethod
    def variant_index(row, col, count):
        """Which variant a map cell shows. Deterministic from the cell's
        coordinates — same map, same look, across frames, zooms, and
        saves — and never touches the seeded RNG stream the map gen and
        balance sims depend on."""
        if count <= 1:
            return 0
        return (row * 2654435761 + col * 40503) % count

    def water_distance_map(self):
        """Per-tile hex-BFS distance (in tiles) to the nearest water tile.
        Water tiles are 0; a map with no water at all is all-infinity."""
        from core.config import WATER_TERRAIN

        inf = float("inf")
        dist = [[inf] * self.width for _ in range(self.height)]
        frontier = deque()
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c] in WATER_TERRAIN:
                    dist[r][c] = 0
                    frontier.append((r, c))
        while frontier:
            r, c = frontier.popleft()
            d = dist[r][c] + 1
            for nr, nc in self.hex_neighbors(r, c):
                if 0 <= nr < self.height and 0 <= nc < self.width and d < dist[nr][nc]:
                    dist[nr][nc] = d
                    frontier.append((nr, nc))
        return dist

    def generate_perlin_map(self):
        """§11.1 simplified roster: 4 grounds + 2 waters. Everything that
        used to be a special tile (forest, mountains, lava) is now a PROP
        placed on these grounds. self.elevation is kept — mountain-prop
        placement (§11.2) ridges the high ground the stone tiles used to
        mark."""
        grid = [[None for _ in range(self.width)] for _ in range(self.height)]
        self.elevation = [[0.0 for _ in range(self.width)] for _ in range(self.height)]
        seed = random.randint(0, 100000)

        # Multiple noise layers for different features
        elevation_noise = PerlinNoise(octaves=5, seed=seed)
        moisture_noise = PerlinNoise(octaves=3, seed=seed + 1000)
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
                self.elevation[r][c] = elevation

                moisture = moisture_noise([nx, ny])

                # Sea level raised -0.12/-0.02 → -0.10/0.0 (2026-07-25,
                # user: not enough lakes/oceans; spawn selection is now
                # water-aware so wetter maps stay playable)
                if elevation < -0.10:
                    grid[r][c] = "water_deep"
                elif elevation < 0.0:
                    grid[r][c] = "water_shallow"
                elif elevation < 0.06:
                    grid[r][c] = "dirt"        # shores and mudflats
                elif moisture > 0.28 and elevation < 0.22:
                    grid[r][c] = "swamp"       # wet lowlands
                elif moisture < -0.22:
                    grid[r][c] = "desert"
                else:
                    grid[r][c] = "grass"

        # Post-processing: inland lakes, coastal shallows, smoothing
        self._create_lakes(grid, seed + 4000)
        self._ring_deep_water(grid)
        self._smooth_terrain(grid)

        return grid
    
    def _create_lakes(self, grid, seed):
        """Inland lakes carved into the wet lowlands. Cores come from
        low-frequency noise — the very wettest start DEEP, and
        _ring_deep_water shallows their shores afterward — then the carved
        set floods two rings outward with falling probability, so lakes
        read as BODIES of water with ragged shores instead of puddle
        chains (2026-07-25, user: not enough lakes)."""
        lake_noise = PerlinNoise(octaves=2, seed=seed)

        core = []
        for r in range(2, self.height - 2):
            for c in range(2, self.width - 2):
                if grid[r][c] in ("grass", "swamp"):
                    lake_val = lake_noise([c / self.width * 3, r / self.height * 3])
                    if lake_val > 0.32:
                        core.append((r, c))
                        grid[r][c] = ("water_deep" if lake_val > 0.42
                                      else "water_shallow")

        edge = core
        for chance in (0.45, 0.30):
            next_edge = []
            for r, c in edge:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if not (2 <= rr < self.height - 2
                                and 2 <= cc < self.width - 2):
                            continue
                        if (grid[rr][cc] in ("grass", "swamp", "dirt")
                                and random.random() < chance):
                            grid[rr][cc] = "water_shallow"
                            next_edge.append((rr, cc))
            edge = next_edge

    def _ring_deep_water(self, grid):
        """Every deep-water tile that touches land becomes shallow: coasts
        always read shallow -> deep, never land -> abyss."""
        from core.config import WATER_TERRAIN

        deep_to_ring = []
        for r in range(self.height):
            for c in range(self.width):
                if grid[r][c] != "water_deep":
                    continue
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        rr, cc = r + dr, c + dc
                        if (0 <= rr < self.height and 0 <= cc < self.width
                                and grid[rr][cc] not in WATER_TERRAIN):
                            deep_to_ring.append((r, c))
                            break
                    else:
                        continue
                    break
        for r, c in deep_to_ring:
            grid[r][c] = "water_shallow"

    def _smooth_terrain(self, grid):
        """Kill single-tile speckle so biomes read as regions."""
        from core.config import WATER_TERRAIN

        new_grid = [row[:] for row in grid]

        for r in range(1, self.height - 1):
            for c in range(1, self.width - 1):
                neighbors = {}
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        terrain = grid[r + dr][c + dc]
                        neighbors[terrain] = neighbors.get(terrain, 0) + 1

                current = grid[r][c]
                water_neighbors = sum(neighbors.get(t, 0) for t in WATER_TERRAIN)

                if current not in WATER_TERRAIN and water_neighbors >= 6:
                    # Land speck inside a body of water drowns
                    new_grid[r][c] = "water_shallow"
                elif current in WATER_TERRAIN and water_neighbors <= 1:
                    # Isolated puddle dries into shore
                    new_grid[r][c] = "dirt"
                elif current not in WATER_TERRAIN:
                    # A lone ground tile inside another biome joins it
                    for name, count in neighbors.items():
                        if count >= 6 and name not in WATER_TERRAIN:
                            new_grid[r][c] = name
                            break

        # Copy back
        for r in range(self.height):
            for c in range(self.width):
                grid[r][c] = new_grid[r][c]

    # Preferred min hex-distance (tiles) from a spawn to ANY water tile
    # (2026-07-25, user: "the castle is right on the water" — measured 1-2
    # tiles on every seed before this). Relaxes one tile at a time only
    # when a wet map leaves too few candidate spawns.
    SPAWN_WATER_CLEARANCE = 5

    def find_spawn_locations(self, num_players):
        """Find safe spawn locations for players, spread as far apart as possible"""
        import math

        # Define safe terrain for spawning
        safe_terrain = SPAWN_SAFE_TERRAIN

        # §11.2: spawns are confined to the LARGEST land component — a
        # safe-looking pocket sealed off by water stranded whoever spawned
        # there (found by the mountain-reachability BFS, but pre-existing).
        mainland = self.largest_land_component()
        water_dist = self.water_distance_map()

        # Find all potential spawn areas (safe terrain with some space around)
        base_candidates = []
        for r in range(5, self.height - 5):  # Leave border margin
            for c in range(5, self.width - 5):
                if (r, c) not in mainland:
                    continue
                if self.grid[r][c] in safe_terrain:
                    # Check if there's enough safe terrain in a 5x5 area around this point
                    safe_count = 0
                    for dr in range(-2, 3):
                        for dc in range(-2, 3):
                            if self.grid[r + dr][c + dc] in safe_terrain:
                                safe_count += 1

                    if safe_count >= 15:  # At least 15 out of 25 tiles are safe
                        base_candidates.append((r, c))

        # Highest water clearance that still leaves room: prefer a pool big
        # enough for the max-min-distance spread below (10x players), else
        # the highest clearance that can seat everyone at all.
        potential_spawns = []
        for clearance in range(self.SPAWN_WATER_CLEARANCE, 0, -1):
            filtered = [(r, c) for r, c in base_candidates
                        if water_dist[r][c] >= clearance]
            if not potential_spawns and len(filtered) >= num_players:
                potential_spawns = filtered
            if len(filtered) >= num_players * 10:
                potential_spawns = filtered
                break

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
        safe_terrain = SPAWN_SAFE_TERRAIN

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
                    # (§11.2: incl. mountains/fountains — a worker spawned
                    # inside a ridge is born wedged)
                    collision = False
                    all_objects = (self.game.buildings + self.game.units
                                   + self.game.resources
                                   + list(getattr(self.game, "fountains", ()))
                                   + list(getattr(self.game, "mountains", ()))
                                   + [p for p in getattr(self.game, "props", ())
                                      if getattr(p, "blocks", False)])
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
        # Match the hex grid positioning used in draw()
        col, row = grid_x, grid_y
        world_x = col * TILE_WIDTH * 0.75
        world_y = row * TILE_HEIGHT
        if col % 2 != 0:
            world_y += TILE_HEIGHT / 2
        return world_x, world_y
    
    def world_to_grid_fast(self, world_x, world_y):
        """Approximate world->grid without the 9-neighbor refinement.

        Bins by column stride/row height only; may be off by one tile right at
        hex boundaries. Use for tile-granular consumers (fog, minimap), not for
        exact terrain lookups."""
        col = int(world_x / (TILE_WIDTH * 0.75))
        if col < 0 or col >= self.width:
            return None
        if col % 2 == 0:
            row = int(world_y / TILE_HEIGHT)
        else:
            row = int((world_y - TILE_HEIGHT / 2) / TILE_HEIGHT)
        if row < 0 or row >= self.height:
            return None
        return (col, row)

    def world_to_grid(self, world_x, world_y):
        """Convert world coordinates to grid coordinates (inverse of grid_to_world)"""
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
        best_dist_sq = float('inf')
        
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
                    dist_sq = (world_x - center_x) ** 2 + (world_y - center_y) ** 2
                    
                    if dist_sq < best_dist_sq:
                        best_dist_sq = dist_sq
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
                variants = self.scaled_tile_variants[tile_name]
                tile_image = variants[self.variant_index(row, col, len(variants))]

                # Calculate position for hex grid
                x = col * tile_width * 0.75
                y = row * tile_height
                if col % 2 != 0:
                    y += tile_height / 2

                position = (x + camera.x, y + camera.y)
                surface.blit(tile_image, position)

                # §11.1 edge transitions: neighbours of higher blend
                # priority feather across this tile's shared edges
                cell_overlays = self.edge_overlays.get((row, col))
                if cell_overlays:
                    for direction, name in cell_overlays:
                        surface.blit(self.scaled_transitions[(name, direction)],
                                     position)
