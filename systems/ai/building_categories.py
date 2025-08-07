"""Building categorization system for AI planning"""
from enum import Enum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


class BuildingCategory(Enum):
    """Categories of buildings for AI placement and planning"""
    ECONOMIC = "economic"          # Resource gathering buildings
    INFRASTRUCTURE = "infrastructure"  # Housing and utilities
    MILITARY_PRODUCTION = "military_production"  # Unit training facilities
    DEFENSIVE = "defensive"        # Towers, walls, gates
    UPGRADE = "upgrade"           # Research and upgrade buildings
    COMMAND = "command"           # Castle, command centers


class PlacementStrategy(Enum):
    """Placement strategies for different building types"""
    NEAR_RESOURCES = "near_resources"     # Place near specific resource types
    NEAR_CASTLE = "near_castle"           # Place within castle vicinity
    PERIMETER = "perimeter"               # Place at base perimeter for defense
    CENTRAL = "central"                   # Place centrally for accessibility
    CLUSTERED = "clustered"               # Group with similar buildings
    SPREAD = "spread"                     # Spread evenly across territory
    CHOKE_POINTS = "choke_points"         # Place at strategic narrow areas


@dataclass
class BuildingProperties:
    """Properties that define how AI should handle each building type"""
    category: BuildingCategory
    placement_strategy: PlacementStrategy
    priority: float                       # 0-1, higher = more important
    min_distance_from_castle: float      # Minimum distance from castle
    max_distance_from_castle: float      # Maximum distance from castle
    cluster_radius: float                # How close to group with similar buildings
    required_resource_types: List[str]   # Resources this building needs nearby
    terrain_preferences: List[str]       # Preferred terrain types
    defensive_value: float               # 0-1, how much this building helps defense
    can_overlap_zones: bool              # Can be placed in multiple zones


class BuildingCategorizer:
    """Categorizes buildings and provides placement guidance"""
    
    def __init__(self):
        # Current building definitions
        self.building_definitions = {
            # Economic Buildings
            "mine": BuildingProperties(
                category=BuildingCategory.ECONOMIC,
                placement_strategy=PlacementStrategy.NEAR_RESOURCES,
                priority=0.8,
                min_distance_from_castle=50,
                max_distance_from_castle=500,
                cluster_radius=100,
                required_resource_types=["gold"],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.1,
                can_overlap_zones=False
            ),
            "quarry": BuildingProperties(
                category=BuildingCategory.ECONOMIC,
                placement_strategy=PlacementStrategy.NEAR_RESOURCES,
                priority=0.7,
                min_distance_from_castle=50,
                max_distance_from_castle=500,
                cluster_radius=100,
                required_resource_types=["stone"],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.1,
                can_overlap_zones=False
            ),
            "lumbermill": BuildingProperties(
                category=BuildingCategory.ECONOMIC,
                placement_strategy=PlacementStrategy.NEAR_RESOURCES,
                priority=0.7,
                min_distance_from_castle=50,
                max_distance_from_castle=500,
                cluster_radius=100,
                required_resource_types=["wood"],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.1,
                can_overlap_zones=False
            ),
            "farm": BuildingProperties(
                category=BuildingCategory.ECONOMIC,
                placement_strategy=PlacementStrategy.CLUSTERED,
                priority=0.6,
                min_distance_from_castle=80,
                max_distance_from_castle=300,
                cluster_radius=80,
                required_resource_types=[],
                terrain_preferences=["grass", "plains"],
                defensive_value=0.0,
                can_overlap_zones=True
            ),
            
            # Infrastructure Buildings
            "house": BuildingProperties(
                category=BuildingCategory.INFRASTRUCTURE,
                placement_strategy=PlacementStrategy.CLUSTERED,
                priority=0.5,
                min_distance_from_castle=100,
                max_distance_from_castle=250,
                cluster_radius=60,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.0,
                can_overlap_zones=True
            ),
            
            # Military Production Buildings
            "barracks": BuildingProperties(
                category=BuildingCategory.MILITARY_PRODUCTION,
                placement_strategy=PlacementStrategy.NEAR_CASTLE,
                priority=0.8,
                min_distance_from_castle=80,
                max_distance_from_castle=200,
                cluster_radius=120,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.3,
                can_overlap_zones=True
            ),
            
            # Command Buildings
            "castle": BuildingProperties(
                category=BuildingCategory.COMMAND,
                placement_strategy=PlacementStrategy.CENTRAL,
                priority=1.0,
                min_distance_from_castle=0,
                max_distance_from_castle=0,
                cluster_radius=0,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=1.0,
                can_overlap_zones=True
            ),
        }
        
        # Future building definitions (for planning)
        self.future_building_definitions = {
            # Defensive Buildings
            "tower": BuildingProperties(
                category=BuildingCategory.DEFENSIVE,
                placement_strategy=PlacementStrategy.PERIMETER,
                priority=0.6,
                min_distance_from_castle=150,
                max_distance_from_castle=400,
                cluster_radius=200,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt", "hills"],
                defensive_value=0.8,
                can_overlap_zones=False
            ),
            "wall": BuildingProperties(
                category=BuildingCategory.DEFENSIVE,
                placement_strategy=PlacementStrategy.PERIMETER,
                priority=0.4,
                min_distance_from_castle=100,
                max_distance_from_castle=300,
                cluster_radius=50,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.5,
                can_overlap_zones=False
            ),
            
            # Upgrade Buildings
            "blacksmith": BuildingProperties(
                category=BuildingCategory.UPGRADE,
                placement_strategy=PlacementStrategy.CENTRAL,
                priority=0.7,
                min_distance_from_castle=60,
                max_distance_from_castle=180,
                cluster_radius=100,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.2,
                can_overlap_zones=True
            ),
            "university": BuildingProperties(
                category=BuildingCategory.UPGRADE,
                placement_strategy=PlacementStrategy.CENTRAL,
                priority=0.6,
                min_distance_from_castle=60,
                max_distance_from_castle=200,
                cluster_radius=120,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.1,
                can_overlap_zones=True
            ),
            
            # Additional Military Production
            "archery_range": BuildingProperties(
                category=BuildingCategory.MILITARY_PRODUCTION,
                placement_strategy=PlacementStrategy.NEAR_CASTLE,
                priority=0.7,
                min_distance_from_castle=80,
                max_distance_from_castle=220,
                cluster_radius=120,
                required_resource_types=[],
                terrain_preferences=["grass", "plains", "dirt"],
                defensive_value=0.3,
                can_overlap_zones=True
            ),
            "stable": BuildingProperties(
                category=BuildingCategory.MILITARY_PRODUCTION,
                placement_strategy=PlacementStrategy.NEAR_CASTLE,
                priority=0.7,
                min_distance_from_castle=120,
                max_distance_from_castle=250,
                cluster_radius=150,
                required_resource_types=[],
                terrain_preferences=["grass", "plains"],
                defensive_value=0.2,
                can_overlap_zones=True
            ),
        }
    
    def get_building_properties(self, building_name: str) -> Optional[BuildingProperties]:
        """Get properties for a building type"""
        return self.building_definitions.get(building_name) or \
               self.future_building_definitions.get(building_name)
    
    def get_buildings_by_category(self, category: BuildingCategory) -> List[str]:
        """Get all building names in a category"""
        buildings = []
        all_definitions = {**self.building_definitions, **self.future_building_definitions}
        
        for name, props in all_definitions.items():
            if props.category == category:
                buildings.append(name)
        
        return buildings
    
    def get_building_category(self, building_name: str) -> Optional[BuildingCategory]:
        """Get category for a building"""
        props = self.get_building_properties(building_name)
        return props.category if props else None
    
    def is_building_implemented(self, building_name: str) -> bool:
        """Check if building is currently implemented"""
        return building_name in self.building_definitions
    
    def get_placement_strategy(self, building_name: str) -> Optional[PlacementStrategy]:
        """Get placement strategy for a building"""
        props = self.get_building_properties(building_name)
        return props.placement_strategy if props else None
    
    def should_cluster_with(self, building1: str, building2: str) -> bool:
        """Check if two buildings should be clustered together"""
        props1 = self.get_building_properties(building1)
        props2 = self.get_building_properties(building2)
        
        if not props1 or not props2:
            return False
        
        # Same category buildings often cluster
        if props1.category == props2.category:
            return True
        
        # Special clustering rules
        clustering_rules = {
            # Infrastructure can cluster with economic
            (BuildingCategory.INFRASTRUCTURE, BuildingCategory.ECONOMIC): True,
            # Military production buildings cluster together
            (BuildingCategory.MILITARY_PRODUCTION, BuildingCategory.MILITARY_PRODUCTION): True,
            # Upgrade buildings cluster with command
            (BuildingCategory.UPGRADE, BuildingCategory.COMMAND): True,
        }
        
        key1 = (props1.category, props2.category)
        key2 = (props2.category, props1.category)
        
        return clustering_rules.get(key1, False) or clustering_rules.get(key2, False)
    
    def get_zone_priority(self, building_name: str, zone_type: str) -> float:
        """Get priority for placing building in specific zone type"""
        props = self.get_building_properties(building_name)
        if not props:
            return 0.0
        
        zone_priorities = {
            "economic": {
                BuildingCategory.ECONOMIC: 1.0,
                BuildingCategory.INFRASTRUCTURE: 0.7,
                BuildingCategory.COMMAND: 0.3,
                BuildingCategory.MILITARY_PRODUCTION: 0.2,
                BuildingCategory.UPGRADE: 0.4,
                BuildingCategory.DEFENSIVE: 0.1,
            },
            "military": {
                BuildingCategory.MILITARY_PRODUCTION: 1.0,
                BuildingCategory.COMMAND: 0.8,
                BuildingCategory.DEFENSIVE: 0.9,
                BuildingCategory.UPGRADE: 0.6,
                BuildingCategory.INFRASTRUCTURE: 0.3,
                BuildingCategory.ECONOMIC: 0.2,
            },
            "defensive": {
                BuildingCategory.DEFENSIVE: 1.0,
                BuildingCategory.MILITARY_PRODUCTION: 0.7,
                BuildingCategory.COMMAND: 0.5,
                BuildingCategory.UPGRADE: 0.3,
                BuildingCategory.INFRASTRUCTURE: 0.2,
                BuildingCategory.ECONOMIC: 0.1,
            },
            "central": {
                BuildingCategory.COMMAND: 1.0,
                BuildingCategory.UPGRADE: 0.9,
                BuildingCategory.MILITARY_PRODUCTION: 0.6,
                BuildingCategory.INFRASTRUCTURE: 0.5,
                BuildingCategory.ECONOMIC: 0.4,
                BuildingCategory.DEFENSIVE: 0.3,
            }
        }
        
        return zone_priorities.get(zone_type, {}).get(props.category, 0.5)