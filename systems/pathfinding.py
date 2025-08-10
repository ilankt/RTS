import heapq
import math
from typing import List, Tuple, Optional, Set
from core.config import TILE_WIDTH, TILE_HEIGHT, DEBUG_PATHFINDING


class PathNode:
    """Node used in A* pathfinding"""
    def __init__(self, x: float, y: float, g: float = 0, h: float = 0, parent=None):
        self.x = x
        self.y = y
        self.g = g  # Cost from start
        self.h = h  # Heuristic cost to goal
        self.f = g + h  # Total cost
        self.parent = parent
    
    def __lt__(self, other):
        return self.f < other.f
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))


class Pathfinding:
    """A* pathfinding system that works in world coordinates while respecting hex tiles"""
    
    def __init__(self, game_map, game):
        self.game_map = game_map
        self.game = game
        self.grid_size = 8  # World units per navigation grid cell - reduced from 20 for finer navigation
        self.drop_off_target = None  # Building to allow collision with
        self.gathering_target = None  # Resource to allow collision with
        self.building_target = None  # Construction site to allow collision with
        self.current_unit = None  # The unit currently pathfinding
        self.spatial_grid = {}  # Spatial partitioning for collision detection
        self.path_cache = {}  # Cache for computed paths
        self.cache_hits = 0
        self.cache_misses = 0
        self._build_spatial_grid()
        
    def _build_spatial_grid(self):
        """Build spatial grid for efficient collision detection"""
        self.spatial_grid.clear()
        self.spatial_cell_size = 64  # Size of each spatial cell
        
        # Add all static objects to spatial grid
        for obj in self.game.buildings + self.game.resources + self.game.construction_sites:
            self._add_to_spatial_grid(obj)
            
    def _add_to_spatial_grid(self, obj):
        """Add an object to the spatial grid"""
        # Calculate which cells this object overlaps
        min_x = int((obj.x - obj.radius) / self.spatial_cell_size)
        max_x = int((obj.x + obj.radius) / self.spatial_cell_size)
        min_y = int((obj.y - obj.radius) / self.spatial_cell_size)
        max_y = int((obj.y + obj.radius) / self.spatial_cell_size)
        
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cell_key = (cell_x, cell_y)
                if cell_key not in self.spatial_grid:
                    self.spatial_grid[cell_key] = []
                self.spatial_grid[cell_key].append(obj)
    
    def _get_nearby_objects(self, x: float, y: float, radius: float):
        """Get objects that might collide at given position"""
        # Calculate which cells to check
        min_x = int((x - radius) / self.spatial_cell_size)
        max_x = int((x + radius) / self.spatial_cell_size)
        min_y = int((y - radius) / self.spatial_cell_size)
        max_y = int((y + radius) / self.spatial_cell_size)
        
        nearby_objects = set()
        for cell_x in range(min_x, max_x + 1):
            for cell_y in range(min_y, max_y + 1):
                cell_key = (cell_x, cell_y)
                if cell_key in self.spatial_grid:
                    nearby_objects.update(self.spatial_grid[cell_key])
        
        return list(nearby_objects)
    
    def _get_cache_key(self, start: Tuple[float, float], goal: Tuple[float, float]) -> str:
        """Generate cache key for path"""
        # Round to grid size for cache key
        start_key = (round(start[0] / self.grid_size), round(start[1] / self.grid_size))
        goal_key = (round(goal[0] / self.grid_size), round(goal[1] / self.grid_size))
        return f"{start_key}_{goal_key}"
    
    def _is_path_still_valid(self, path: List[Tuple[float, float]], unit_radius: float) -> bool:
        """Check if a cached path is still valid (no new obstacles)"""
        if not path or len(path) < 2:
            return True
            
        # Check if path segments are still clear
        for i in range(len(path) - 1):
            if not self._simple_line_clear(path[i], path[i + 1], unit_radius):
                return False
        return True
    
    def find_path(self, start: Tuple[float, float], goal: Tuple[float, float], 
                  unit_radius: float = 20, unit=None) -> Optional[List[Tuple[float, float]]]:
        """
        Find a path from start to goal in world coordinates.
        Returns a list of waypoints or None if no path exists.
        """
        # Rebuild spatial grid for dynamic objects
        self._build_spatial_grid()
        
        # Store the current unit for collision checking
        self.current_unit = unit
        # Store original goal for final adjustment
        original_goal = goal
        
        # Check cache first
        cache_key = self._get_cache_key(start, goal)
        if cache_key in self.path_cache:
            cached_path = self.path_cache[cache_key]
            if self._is_path_still_valid(cached_path, unit_radius):
                self.cache_hits += 1
                if DEBUG_PATHFINDING and self.cache_hits % 100 == 0:
                    # Path cache stats
                    pass
                return cached_path[:]
        
        self.cache_misses += 1
        
        # Check if we can move directly first - PRIORITIZE DIRECT MOVEMENT
        distance = math.sqrt((goal[0] - start[0])**2 + (goal[1] - start[1])**2)
        
        # Check if goal is on unwalkable terrain first
        goal_hex = self.game_map.world_to_grid(goal[0], goal[1])
        if goal_hex:
            tile_type = self.game_map.grid[goal_hex[1]][goal_hex[0]]
            if tile_type in {"water", "lava"}:
                # Find nearest walkable position to goal
                goal = self._find_nearest_walkable(goal[0], goal[1], unit_radius)
                if not goal:
                    return None
                goal = (goal.x, goal.y)
                # Recalculate distance after goal adjustment
                distance = math.sqrt((goal[0] - start[0])**2 + (goal[1] - start[1])**2)
        
        
        # Check if the exact goal position is blocked by permanent obstacles
        # If so, find the closest reachable position instead
        if self._is_position_permanently_blocked(goal[0], goal[1], unit_radius):
            closest_reachable = self._find_closest_reachable_position(start, goal, unit_radius)
            if closest_reachable:
                goal = closest_reachable
                if DEBUG_PATHFINDING:
                    # Target blocked - redirecting to closest reachable position
                    pass
            else:
                if DEBUG_PATHFINDING:
                    # No reachable position found near target
                    pass
                return None
        
        # ALWAYS try direct movement first - no distance limit
        if self._simple_line_clear(start, goal, unit_radius):
            direct_path = [goal]
            self.path_cache[cache_key] = direct_path
            return direct_path
        
        # Snap positions to grid
        start_node = PathNode(
            round(start[0] / self.grid_size) * self.grid_size,
            round(start[1] / self.grid_size) * self.grid_size
        )
        goal_node = PathNode(
            round(goal[0] / self.grid_size) * self.grid_size,
            round(goal[1] / self.grid_size) * self.grid_size
        )
        
        # Check if start and goal are walkable
        if not self._is_walkable(start_node.x, start_node.y, unit_radius):
            # Find nearest walkable position for start
            start_node = self._find_nearest_walkable(start[0], start[1], unit_radius)
            if not start_node:
                return None
                
        if not self._is_walkable(goal_node.x, goal_node.y, unit_radius):
            # Find nearest walkable position for goal
            goal_node = self._find_nearest_walkable(goal[0], goal[1], unit_radius)
            if not goal_node:
                return None
        
        # A* algorithm
        open_set = []
        open_dict = {}  # Map (x,y) to node for O(1) lookup
        closed_set: Set[PathNode] = set()
        
        start_node.h = self._heuristic(start_node, goal_node)
        start_node.f = start_node.h
        heapq.heappush(open_set, start_node)
        open_dict[(start_node.x, start_node.y)] = start_node
        
        while open_set:
            current = heapq.heappop(open_set)
            current_key = (current.x, current.y)
            
            # Remove from open dict
            if current_key in open_dict:
                del open_dict[current_key]
            
            # Check if we reached the goal
            if abs(current.x - goal_node.x) < self.grid_size and \
               abs(current.y - goal_node.y) < self.grid_size:
                path = self._reconstruct_path(current, goal)
                # Cache the path
                self.path_cache[cache_key] = path[:]
                # Limit cache size
                if len(self.path_cache) > 100:
                    # Remove oldest entries
                    oldest_keys = list(self.path_cache.keys())[:20]
                    for key in oldest_keys:
                        del self.path_cache[key]
                return path
            
            closed_set.add(current)
            
            # Check neighbors
            for neighbor_pos in self._get_neighbors(current.x, current.y):
                neighbor = PathNode(neighbor_pos[0], neighbor_pos[1])
                
                if neighbor in closed_set:
                    continue
                
                if not self._is_walkable(neighbor.x, neighbor.y, unit_radius):
                    continue
                
                # Calculate tentative g score
                tentative_g = current.g + self._distance(current, neighbor)
                
                # Check if this path to neighbor is better
                neighbor_key = (neighbor.x, neighbor.y)
                existing = open_dict.get(neighbor_key)
                
                if existing and tentative_g >= existing.g:
                    continue
                
                # This path is the best so far
                neighbor.g = tentative_g
                neighbor.h = self._heuristic(neighbor, goal_node)
                neighbor.f = neighbor.g + neighbor.h
                neighbor.parent = current
                
                if existing:
                    # Update existing node - remove old one and add new
                    open_set.remove(existing)
                    heapq.heapify(open_set)
                
                heapq.heappush(open_set, neighbor)
                open_dict[neighbor_key] = neighbor
        
        # Cache the failure too
        self.path_cache[cache_key] = None
        return None  # No path found
    
    def _is_walkable(self, x: float, y: float, unit_radius: float) -> bool:
        """Check if a world position is walkable (no unwalkable tiles or obstacles)"""
        # Check center and 8 points around the unit's full radius
        # This ensures the unit doesn't overlap with water tiles
        check_points = [
            (x, y),  # Center
            (x + unit_radius, y),  # Right
            (x - unit_radius, y),  # Left
            (x, y + unit_radius),  # Bottom
            (x, y - unit_radius),  # Top
            (x + unit_radius * 0.7, y + unit_radius * 0.7),  # Bottom-right
            (x - unit_radius * 0.7, y + unit_radius * 0.7),  # Bottom-left
            (x + unit_radius * 0.7, y - unit_radius * 0.7),  # Top-right
            (x - unit_radius * 0.7, y - unit_radius * 0.7),  # Top-left
        ]
        
        for check_x, check_y in check_points:
            # Convert to hex coordinates
            hex_coord = self.game_map.world_to_grid(check_x, check_y)
            if hex_coord is None:
                return False
                
            col, row = hex_coord
            
            # Check map bounds
            if row < 0 or row >= self.game_map.height or col < 0 or col >= self.game_map.width:
                return False
            
            # Check tile type
            tile_type = self.game_map.grid[row][col]
            if tile_type in {"water", "lava"}:
                return False
        
        # Check collisions with game objects
        return not self._check_collision(x, y, unit_radius)
    
    def _check_collision(self, x: float, y: float, radius: float) -> bool:
        """Check if position collides with any game object with consistent 2-unit buffer"""
        collision_buffer = 2  # Consistent buffer for all collision checks
        
        # Get nearby objects from spatial grid
        nearby_objects = self._get_nearby_objects(x, y, radius + 50)  # Extra margin for safety
        
        # Check static objects from spatial grid
        for obj in nearby_objects:
            # Skip collision check with drop-off target
            if self.drop_off_target and obj == self.drop_off_target:
                continue
            # Skip collision check with gathering target
            if self.gathering_target and obj == self.gathering_target:
                continue
            # Skip collision check with building target (for workers approaching construction sites)
            if hasattr(self, 'building_target') and self.building_target and obj == self.building_target:
                continue
            dist = math.sqrt((obj.x - x)**2 + (obj.y - y)**2)
            if dist < (obj.radius + radius + collision_buffer):
                return True
        
        # Check other units (dynamic objects not in spatial grid)
        for unit in self.game.units:
            if self.current_unit and unit == self.current_unit:  # Skip only the current pathfinding unit
                continue
            dist = math.sqrt((unit.x - x)**2 + (unit.y - y)**2)
            if dist < (unit.radius + radius + collision_buffer):
                return True
        
        return False
    
    def _get_neighbors(self, x: float, y: float) -> List[Tuple[float, float]]:
        """Get neighboring positions in world coordinates"""
        neighbors = []
        # 8-directional movement
        directions = [
            (-1, -1), (0, -1), (1, -1),
            (-1, 0),           (1, 0),
            (-1, 1),  (0, 1),  (1, 1)
        ]
        
        for dx, dy in directions:
            nx = x + dx * self.grid_size
            ny = y + dy * self.grid_size
            neighbors.append((nx, ny))
        
        return neighbors
    
    def _heuristic(self, node1: PathNode, node2: PathNode) -> float:
        """Calculate heuristic distance between nodes (Euclidean)"""
        return math.sqrt((node1.x - node2.x)**2 + (node1.y - node2.y)**2)
    
    def _distance(self, node1: PathNode, node2: PathNode) -> float:
        """Calculate actual distance between nodes"""
        return math.sqrt((node1.x - node2.x)**2 + (node1.y - node2.y)**2)
    
    def _reconstruct_path(self, node: PathNode, final_goal: Tuple[float, float]) -> List[Tuple[float, float]]:
        """Reconstruct path from goal to start"""
        path = []
        current = node
        
        while current:
            path.append((current.x, current.y))
            current = current.parent
        
        path.reverse()
        
        # Add final goal if it's different from last waypoint
        if path and (abs(path[-1][0] - final_goal[0]) > 1 or abs(path[-1][1] - final_goal[1]) > 1):
            path.append(final_goal)
        
        # Smooth the path with unit radius consideration
        return self._smooth_path(path, self.current_unit.radius if self.current_unit else 20)
    
    def _smooth_path(self, path: List[Tuple[float, float]], unit_radius: float = 20) -> List[Tuple[float, float]]:
        """Remove unnecessary waypoints for smoother movement while ensuring traversability"""
        if len(path) <= 2:
            return path
        
        smoothed = [path[0]]
        i = 0
        
        while i < len(path) - 1:
            # Try to skip ahead, but not too far to maintain smooth movement
            j = min(i + 5, len(path) - 1)  # Limit look-ahead to prevent over-smoothing
            found_clear = False
            
            while j > i + 1:
                # Check if we can move from path[i] to path[j] with proper clearance
                if self._path_segment_clear(path[i], path[j], unit_radius):
                    # Add intermediate point if distance is large
                    dist = math.sqrt((path[j][0] - path[i][0])**2 + (path[j][1] - path[i][1])**2)
                    if dist > self.grid_size * 4:  # If distance > 4 grid cells, add midpoint
                        mid_x = (path[i][0] + path[j][0]) / 2
                        mid_y = (path[i][1] + path[j][1]) / 2
                        smoothed.append((mid_x, mid_y))
                    
                    i = j - 1
                    found_clear = True
                    break
                j -= 1
            
            if not found_clear:
                i += 1
                
            if i < len(path):
                smoothed.append(path[i])
        
        return smoothed
    
    def _path_segment_clear(self, start: Tuple[float, float], end: Tuple[float, float], unit_radius: float) -> bool:
        """Check if a path segment is completely clear for a unit of given radius"""
        # Sample more points for better accuracy
        dist = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
        
        if dist < 0.1:
            return True
        
        # Check every few units along the path
        steps = max(2, int(dist / (unit_radius / 2)))
        
        for i in range(steps + 1):
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            # Check terrain
            hex_coord = self.game_map.world_to_grid(x, y)
            if hex_coord:
                col, row = hex_coord
                if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                    tile_type = self.game_map.grid[row][col]
                    if tile_type in {"water", "lava"}:
                        return False
            
            # Get nearby objects from spatial grid
            nearby_objects = self._get_nearby_objects(x, y, unit_radius + 50)
            
            # Check for obstacles with proper clearance
            for obj in nearby_objects:
                if self.drop_off_target and obj == self.drop_off_target:
                    continue
                if self.gathering_target and obj == self.gathering_target:
                    continue
                dist_to_obj = math.sqrt((obj.x - x)**2 + (obj.y - y)**2)
                required_clearance = obj.radius + unit_radius + 2
                if dist_to_obj < required_clearance:
                    return False
            
            # Units need some clearance but can be closer
            for unit in self.game.units:
                if self.current_unit and unit == self.current_unit:
                    continue
                dist_to_unit = math.sqrt((unit.x - x)**2 + (unit.y - y)**2)
                required_clearance = unit.radius + unit_radius + 1
                if dist_to_unit < required_clearance:
                    return False
        
        return True
    
    def _line_of_sight(self, start: Tuple[float, float], end: Tuple[float, float], unit_radius: float = 20) -> bool:
        """Check if there's a clear line of sight between two points with consistent collision detection"""
        # Sample points along the line
        dist = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
        
        # For very short distances, just check the endpoints
        if dist < self.grid_size:
            return self._is_walkable(end[0], end[1], unit_radius)
        
        # More frequent sampling for longer distances
        steps = int(dist / (self.grid_size / 2)) + 1  # Check every half grid cell
        
        for i in range(1, steps + 1):  # Skip checking start point
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            # Check terrain first
            hex_coord = self.game_map.world_to_grid(x, y)
            if hex_coord:
                col, row = hex_coord
                if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                    tile_type = self.game_map.grid[row][col]
                    if tile_type in {"water", "lava"}:
                        return False
            
            # Check collisions with consistent 2-unit buffer
            if self._check_collision(x, y, unit_radius):
                return False
        
        return True
    
    def _simple_line_clear(self, start: Tuple[float, float], end: Tuple[float, float], unit_radius: float = 20) -> bool:
        """Simple check if we can move directly between two points with consistent collision detection"""
        # First check if endpoints are walkable with full radius check
        if not self._is_walkable(start[0], start[1], unit_radius):
            return False
        if not self._is_walkable(end[0], end[1], unit_radius):
            return False
        
        # Check for obstacles with consistent collision detection
        # Sample points along the path
        dist = math.sqrt((end[0] - start[0])**2 + (end[1] - start[1])**2)
        steps = max(2, int(dist / 30))  # Check every 30 units for better accuracy
        
        for i in range(1, steps):  # Skip start and end points
            t = i / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            
            # Check terrain with unit radius consideration
            if not self._is_walkable(x, y, unit_radius):
                return False
            
            # Consistent collision buffer: 2 units for all object types
            collision_buffer = 2
            
            # Get nearby objects from spatial grid
            nearby_objects = self._get_nearby_objects(x, y, unit_radius + 50)
            
            # Check static obstacles with consistent buffer
            for obj in nearby_objects:
                if self.drop_off_target and obj == self.drop_off_target:
                    continue
                if self.gathering_target and obj == self.gathering_target:
                    continue
                dist_to_obj = math.sqrt((obj.x - x)**2 + (obj.y - y)**2)
                if dist_to_obj < (obj.radius + unit_radius + collision_buffer):
                    return False
            
            # Check dynamic units
            for unit in self.game.units:
                if self.current_unit and unit == self.current_unit:
                    continue
                dist_to_unit = math.sqrt((unit.x - x)**2 + (unit.y - y)**2)
                if dist_to_unit < (unit.radius + unit_radius + collision_buffer):
                    return False
        
        return True
    
    
    def _find_nearest_walkable(self, x: float, y: float, radius: float) -> Optional[PathNode]:
        """Find the nearest walkable position to the given coordinates"""
        # Search in expanding circles
        for distance in range(self.grid_size, self.grid_size * 10, self.grid_size):
            # Check 8 directions at this distance
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                nx = x + distance * math.cos(rad)
                ny = y + distance * math.sin(rad)
                
                # Snap to grid
                nx = round(nx / self.grid_size) * self.grid_size
                ny = round(ny / self.grid_size) * self.grid_size
                
                if self._is_walkable(nx, ny, radius):
                    return PathNode(nx, ny)
        
        return None
    
    def _is_position_permanently_blocked(self, x: float, y: float, unit_radius: float) -> bool:
        """Check if a position is permanently blocked by immovable obstacles"""
        # Get nearby objects from spatial grid
        nearby_objects = self._get_nearby_objects(x, y, unit_radius + 50)
        
        # Check static obstacles
        for obj in nearby_objects:
            # Skip if this is a drop-off target (can approach it)
            if self.drop_off_target and obj == self.drop_off_target:
                continue
            # Skip if this is a gathering target (can approach it)
            if self.gathering_target and obj == self.gathering_target:
                continue
            
            dist = math.sqrt((obj.x - x)**2 + (obj.y - y)**2)
            if dist < (obj.radius + unit_radius):
                return True
        
        # Check unwalkable terrain
        hex_coord = self.game_map.world_to_grid(x, y)
        if hex_coord:
            col, row = hex_coord
            if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                tile_type = self.game_map.grid[row][col]
                if tile_type in {"water", "lava"}:
                    return True
        
        return False
    
    def _find_closest_reachable_position(self, start: Tuple[float, float], 
                                       target: Tuple[float, float], 
                                       unit_radius: float) -> Optional[Tuple[float, float]]:
        """Find the closest reachable position to a blocked target"""
        # Calculate direction from start to target
        dx = target[0] - start[0]
        dy = target[1] - start[1]
        target_distance = math.sqrt(dx*dx + dy*dy)
        
        if target_distance == 0:
            return None
        
        # Normalize direction
        dx_norm = dx / target_distance
        dy_norm = dy / target_distance
        
        # Start from a reasonable distance and work backwards towards start
        # Try to get as close as possible to the target
        search_distances = []
        
        # Generate search distances: start close to target, work backwards
        # Add safety limit to prevent excessive computation
        max_search_distance = min(int(target_distance) + 40, 500)  # Cap at 500 pixels
        for offset in range(0, max_search_distance, 10):
            if offset < target_distance:
                search_distances.append(target_distance - offset)
        
        # Also try some positions around the target in a circle
        best_position = None
        best_distance_to_target = float('inf')
        
        for search_dist in search_distances:
            # Try the direct approach first
            test_x = start[0] + dx_norm * search_dist
            test_y = start[1] + dy_norm * search_dist
            
            if (self._is_walkable(test_x, test_y, unit_radius) and 
                not self._is_position_permanently_blocked(test_x, test_y, unit_radius)):
                # Check if we can actually reach this position
                if self._simple_line_clear(start, (test_x, test_y), unit_radius):
                    dist_to_target = math.sqrt((test_x - target[0])**2 + (test_y - target[1])**2)
                    if dist_to_target < best_distance_to_target:
                        best_position = (test_x, test_y)
                        best_distance_to_target = dist_to_target
        
        # If direct approach didn't work, try positions in a circle around the target
        if not best_position:
            for radius in range(20, 100, 10):  # Try different radii
                for angle in range(0, 360, 30):  # Try different angles
                    rad = math.radians(angle)
                    test_x = target[0] + radius * math.cos(rad)
                    test_y = target[1] + radius * math.sin(rad)
                    
                    if (self._is_walkable(test_x, test_y, unit_radius) and 
                        not self._is_position_permanently_blocked(test_x, test_y, unit_radius)):
                        # Check if we can actually reach this position
                        if self._simple_line_clear(start, (test_x, test_y), unit_radius):
                            dist_to_target = math.sqrt((test_x - target[0])**2 + (test_y - target[1])**2)
                            if dist_to_target < best_distance_to_target:
                                best_position = (test_x, test_y)
                                best_distance_to_target = dist_to_target
                
                # If we found a good position at this radius, stop searching
                if best_position:
                    break
        
        return best_position