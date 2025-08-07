"""Zone-based building placement system for AI"""
import math
import random
import pygame
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
from .building_categories import BuildingCategorizer, BuildingCategory, PlacementStrategy
from core.config import TILE_WIDTH, TILE_HEIGHT


class Zone:
    """Represents a logical zone for building placement"""
    
    def __init__(self, name: str, center_x: float, center_y: float, radius: float, zone_type: str):
        self.name = name
        self.center_x = center_x
        self.center_y = center_y
        self.radius = radius
        self.zone_type = zone_type  # economic, military, defensive, central
        self.buildings = []  # Buildings placed in this zone
        self.reserved_positions = []  # Positions reserved for future buildings
        self.density = 0.0  # How crowded this zone is (0-1)
        
    def contains_point(self, x: float, y: float) -> bool:
        """Check if point is within zone"""
        distance = math.sqrt((x - self.center_x)**2 + (y - self.center_y)**2)
        return distance <= self.radius
    
    def get_available_positions(self, min_spacing: float = 80) -> List[Tuple[float, float]]:
        """Get available positions in zone with minimum spacing"""
        positions = []
        
        # Generate grid of potential positions
        grid_size = min_spacing
        start_x = self.center_x - self.radius
        start_y = self.center_y - self.radius
        
        x = start_x
        while x <= self.center_x + self.radius:
            y = start_y
            while y <= self.center_y + self.radius:
                if self.contains_point(x, y):
                    # Check if position is far enough from existing buildings
                    valid = True
                    for building in self.buildings:
                        dist = math.sqrt((x - building.x)**2 + (y - building.y)**2)
                        if dist < min_spacing:
                            valid = False
                            break
                    
                    if valid:
                        positions.append((x, y))
                
                y += grid_size
            x += grid_size
        
        return positions


class BuildingPlacementManager:
    """Manages optimal building placement using zones and categories"""
    
    def __init__(self, ai_system, player):
        self.ai_system = ai_system
        self.player = player
        self.game = ai_system.game
        self.categorizer = BuildingCategorizer()
        
        # Zones for this player
        self.zones = {}
        self.zone_update_timer = 0
        self.zone_update_interval = 10.0  # Update zones every 10 seconds
        
        # Placement scoring weights
        self.scoring_weights = {
            "distance_to_target": 0.3,
            "zone_priority": 0.25,
            "terrain_suitability": 0.2,
            "resource_proximity": 0.15,
            "defensive_value": 0.1
        }
        
        # Placement cache to avoid recalculation
        self.placement_cache = {}
        self.cache_timeout = 30.0  # Cache valid for 30 seconds
        
    def update(self, delta_time: float) -> None:
        """Update zones and placement data"""
        self.zone_update_timer += delta_time
        
        if self.zone_update_timer >= self.zone_update_interval:
            self._update_zones()
            self._clear_old_cache()
            self.zone_update_timer = 0
    
    def find_optimal_position(self, building_type: str) -> Optional[Tuple[float, float]]:
        """Find optimal position for building type"""
        # Check cache first
        current_time = pygame.time.get_ticks() / 1000.0
        cache_key = f"{building_type}_{int(current_time / 10)}"
        if cache_key in self.placement_cache:
            return self.placement_cache[cache_key]
        
        props = self.categorizer.get_building_properties(building_type)
        if not props:
            return None
        
        # Get candidate positions based on placement strategy
        candidates = self._get_candidate_positions(building_type, props)
        if not candidates:
            return None
        
        # Score all candidates
        scored_candidates = []
        for x, y in candidates:
            score = self._score_position(x, y, building_type, props)
            if score > 0:  # Only consider valid positions
                scored_candidates.append((x, y, score))
        
        if not scored_candidates:
            return None
        
        # Sort by score and pick best position
        scored_candidates.sort(key=lambda c: c[2], reverse=True)
        best_position = (scored_candidates[0][0], scored_candidates[0][1])
        
        # Cache result
        self.placement_cache[cache_key] = best_position
        
        return best_position
    
    def reserve_position(self, x: float, y: float, building_type: str) -> None:
        """Reserve a position for future building"""
        # Find which zone this position belongs to
        for zone in self.zones.values():
            if zone.contains_point(x, y):
                zone.reserved_positions.append((x, y, building_type))
                break
    
    def release_reservation(self, x: float, y: float) -> None:
        """Release a reserved position"""
        for zone in self.zones.values():
            zone.reserved_positions = [
                (rx, ry, bt) for rx, ry, bt in zone.reserved_positions
                if not (abs(rx - x) < 10 and abs(ry - y) < 10)
            ]
    
    def get_zone_for_building(self, building_type: str) -> Optional[Zone]:
        """Get best zone for building type"""
        props = self.categorizer.get_building_properties(building_type)
        if not props:
            return None
        
        best_zone = None
        best_score = -1
        
        for zone in self.zones.values():
            priority = self.categorizer.get_zone_priority(building_type, zone.zone_type)
            density_penalty = zone.density * 0.5  # Penalize crowded zones
            score = priority - density_penalty
            
            if score > best_score:
                best_score = score
                best_zone = zone
        
        return best_zone
    
    def _update_zones(self) -> None:
        """Update zone definitions based on current base layout"""
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return
        
        # Clear existing zones
        self.zones.clear()
        
        # Central zone around castle
        self.zones["central"] = Zone(
            "central", castle.x, castle.y, 150, "central"
        )
        
        # Military zone
        military_angle = 0  # Could be based on enemy direction
        military_x = castle.x + 200 * math.cos(military_angle)
        military_y = castle.y + 200 * math.sin(military_angle)
        self.zones["military"] = Zone(
            "military", military_x, military_y, 120, "military"
        )
        
        # Economic zones near resource clusters
        resource_clusters = self._find_resource_clusters()
        for i, (cluster_x, cluster_y, resources) in enumerate(resource_clusters):
            zone_name = f"economic_{i}"
            self.zones[zone_name] = Zone(
                zone_name, cluster_x, cluster_y, 180, "economic"
            )
        
        # Defensive zones at perimeter
        perimeter_positions = self._get_perimeter_positions(castle.x, castle.y, 350)
        for i, (px, py) in enumerate(perimeter_positions[:4]):  # Max 4 defensive zones
            zone_name = f"defensive_{i}"
            self.zones[zone_name] = Zone(
                zone_name, px, py, 100, "defensive"
            )
        
        # Update zone densities
        self._update_zone_densities()
    
    def _find_resource_clusters(self) -> List[Tuple[float, float, List]]:
        """Find clusters of resources for economic zone placement"""
        memory = self.ai_system.player_memory[self.player]
        all_resources = []
        
        for resource_type, resources in memory["resource_locations"].items():
            for resource in resources:
                all_resources.append((resource.x, resource.y, resource_type))
        
        if not all_resources:
            return []
        
        # Simple clustering algorithm
        clusters = []
        used_resources = set()
        
        for i, (x, y, res_type) in enumerate(all_resources):
            if i in used_resources:
                continue
            
            # Start new cluster
            cluster_resources = [(x, y, res_type)]
            cluster_x, cluster_y = x, y
            used_resources.add(i)
            
            # Find nearby resources
            for j, (x2, y2, res_type2) in enumerate(all_resources):
                if j in used_resources:
                    continue
                
                distance = math.sqrt((x - x2)**2 + (y - y2)**2)
                if distance < 200:  # Cluster radius
                    cluster_resources.append((x2, y2, res_type2))
                    used_resources.add(j)
                    
                    # Update cluster center
                    total_x = sum(rx for rx, ry, rt in cluster_resources)
                    total_y = sum(ry for rx, ry, rt in cluster_resources)
                    cluster_x = total_x / len(cluster_resources)
                    cluster_y = total_y / len(cluster_resources)
            
            if len(cluster_resources) >= 2:  # Only create cluster if multiple resources
                clusters.append((cluster_x, cluster_y, cluster_resources))
        
        return clusters
    
    def _get_perimeter_positions(self, center_x: float, center_y: float, radius: float) -> List[Tuple[float, float]]:
        """Get positions around perimeter for defensive placement"""
        positions = []
        num_positions = 8
        
        for i in range(num_positions):
            angle = (i / num_positions) * 2 * math.pi
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            
            # Check if position is within map bounds
            if (0 < x < self.game.game_map.width * TILE_WIDTH and 
                0 < y < self.game.game_map.height * TILE_HEIGHT):
                positions.append((x, y))
        
        return positions
    
    def _update_zone_densities(self) -> None:
        """Update density of each zone based on buildings"""
        for zone in self.zones.values():
            zone.buildings = []
            
            # Count buildings in zone
            for building in self.game.buildings:
                if (building.player == self.player and 
                    zone.contains_point(building.x, building.y)):
                    zone.buildings.append(building)
            
            # Calculate density (buildings per area)
            area = math.pi * zone.radius**2
            zone.density = len(zone.buildings) / (area / 10000)  # Normalize by area
    
    def _get_candidate_positions(self, building_type: str, props) -> List[Tuple[float, float]]:
        """Get candidate positions based on building placement strategy"""
        candidates = []
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return []
        
        if props.placement_strategy == PlacementStrategy.NEAR_RESOURCES:
            # Find positions near required resources
            for resource_type in props.required_resource_types:
                if resource_type in memory["resource_locations"]:
                    for resource in memory["resource_locations"][resource_type]:
                        # Generate positions around resource
                        for angle in [0, math.pi/2, math.pi, 3*math.pi/2]:
                            for distance in [80, 120, 160]:
                                x = resource.x + distance * math.cos(angle)
                                y = resource.y + distance * math.sin(angle)
                                candidates.append((x, y))
        
        elif props.placement_strategy == PlacementStrategy.NEAR_CASTLE:
            # Generate positions around castle
            for angle in range(0, 360, 30):
                rad = math.radians(angle)
                for distance in range(int(props.min_distance_from_castle), 
                                   int(props.max_distance_from_castle), 40):
                    x = castle.x + distance * math.cos(rad)
                    y = castle.y + distance * math.sin(rad)
                    candidates.append((x, y))
        
        elif props.placement_strategy == PlacementStrategy.CLUSTERED:
            # Find existing buildings of same category and cluster near them
            same_category_buildings = []
            for building in self.game.buildings:
                if (building.player == self.player and 
                    self.categorizer.get_building_category(building.name) == props.category):
                    same_category_buildings.append(building)
            
            if same_category_buildings:
                for building in same_category_buildings:
                    for angle in range(0, 360, 45):
                        rad = math.radians(angle)
                        distance = props.cluster_radius
                        x = building.x + distance * math.cos(rad)
                        y = building.y + distance * math.sin(rad)
                        candidates.append((x, y))
            else:
                # No existing buildings, use castle as reference
                for angle in range(0, 360, 30):
                    rad = math.radians(angle)
                    distance = 150
                    x = castle.x + distance * math.cos(rad)
                    y = castle.y + distance * math.sin(rad)
                    candidates.append((x, y))
        
        else:
            # Default: generate positions around castle
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                for distance in range(100, 300, 50):
                    x = castle.x + distance * math.cos(rad)
                    y = castle.y + distance * math.sin(rad)
                    candidates.append((x, y))
        
        # Filter candidates to valid map positions
        valid_candidates = []
        for x, y in candidates:
            if (0 < x < self.game.game_map.width * TILE_WIDTH and 
                0 < y < self.game.game_map.height * TILE_HEIGHT):
                valid_candidates.append((x, y))
        
        return valid_candidates
    
    def _score_position(self, x: float, y: float, building_type: str, props) -> float:
        """Score a position for building placement"""
        if not self._is_valid_build_position(x, y, building_type):
            return 0.0
        
        score = 0.0
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return 0.0

        # Adjust scoring weights based on building type
        current_scoring_weights = self.scoring_weights.copy()
        if props.placement_strategy == PlacementStrategy.NEAR_RESOURCES:
            current_scoring_weights["resource_proximity"] = 0.9  # Make this the dominant factor
            current_scoring_weights["distance_to_target"] = 0.05 # Drastically reduce castle proximity weight
            current_scoring_weights["zone_priority"] = 0.05      # Drastically reduce zone weight
        
        # Distance to castle scoring
        distance_to_castle = math.sqrt((x - castle.x)**2 + (y - castle.y)**2)
        if props.min_distance_from_castle <= distance_to_castle <= props.max_distance_from_castle:
            # Ideal distance range
            ideal_distance = (props.min_distance_from_castle + props.max_distance_from_castle) / 2
            distance_score = 1.0 - abs(distance_to_castle - ideal_distance) / ideal_distance
        else:
            # Outside ideal range
            distance_score = 0.3
        
        score += distance_score * current_scoring_weights["distance_to_target"]
        
        # Zone priority scoring
        best_zone = self.get_zone_for_building(building_type)
        if best_zone and best_zone.contains_point(x, y):
            zone_score = self.categorizer.get_zone_priority(building_type, best_zone.zone_type)
            score += zone_score * current_scoring_weights["zone_priority"]
        
        # Terrain suitability
        grid_pos = self.game.game_map.world_to_grid(x, y)
        if grid_pos:
            col, row = grid_pos
            if (0 <= col < self.game.game_map.width and 
                0 <= row < self.game.game_map.height):
                terrain = self.game.game_map.grid[row][col]
                if terrain in props.terrain_preferences:
                    terrain_score = 1.0
                else:
                    terrain_score = 0.3
            else:
                terrain_score = 0.0
        else:
            terrain_score = 0.0
        
        score += terrain_score * current_scoring_weights["terrain_suitability"]
        
        # Resource proximity (for economic buildings)
        if props.required_resource_types:
            min_resource_distance = float('inf')
            for resource_type in props.required_resource_types:
                if resource_type in memory["resource_locations"]:
                    for resource in memory["resource_locations"][resource_type]:
                        distance = math.sqrt((x - resource.x)**2 + (y - resource.y)**2)
                        min_resource_distance = min(min_resource_distance, distance)
            
            if min_resource_distance < float('inf'):
                # Closer to resources is better
                resource_score = max(0, 1.0 - min_resource_distance / 300)
                score += resource_score * current_scoring_weights["resource_proximity"]
        
        # Defensive value (for defensive positioning)
        if props.defensive_value > 0:
            # Prefer positions that can cover more area or protect key buildings
            defensive_score = props.defensive_value
            score += defensive_score * current_scoring_weights["defensive_value"]
        
        return min(1.0, score)  # Cap at 1.0
    
    def _is_valid_build_position(self, x: float, y: float, building_type: str) -> bool:
        """Check if position is valid for building"""
        building_template = self.game.game_data["buildings"][building_type]
        radius = building_template.radius
        min_distance = radius + 30
        
        # Check collisions with existing buildings
        for building in self.game.buildings:
            distance = math.sqrt((x - building.x)**2 + (y - building.y)**2)
            if distance < min_distance + building.radius:
                return False
        
        # Check collisions with construction sites
        for site in self.game.construction_sites:
            distance = math.sqrt((x - site.x)**2 + (y - site.y)**2)
            if distance < min_distance + site.radius:
                return False
        
        # Check collisions with resources
        for resource in self.game.resources:
            distance = math.sqrt((x - resource.x)**2 + (y - resource.y)**2)
            if distance < min_distance + resource.radius:
                return False
        
        # Check terrain using world_to_grid for accuracy
        grid_pos = self.game.game_map.world_to_grid(x, y)
        if not grid_pos:
            return False
            
        col, row = grid_pos
        if (col < 0 or col >= self.game.game_map.width or
            row < 0 or row >= self.game.game_map.height):
            return False
            
        terrain = self.game.game_map.grid[row][col]
        if terrain not in ["grass", "plains", "dirt"]:
            return False
        
        return True
    
    def _clear_old_cache(self) -> None:
        """Clear old cache entries"""
        current_time = pygame.time.get_ticks() / 1000.0
        self.placement_cache = {
            key: value for key, value in self.placement_cache.items()
            if current_time - int(key.split('_')[-1]) * 10 < self.cache_timeout
        }