import pygame
import json
import random
import math
from systems.animation import Animation
from core.config import TILE_WIDTH, TILE_HEIGHT, RESOURCE_LIMITS, WORKER_CAPACITY, DEBUG_MOVEMENT # Import TILE_WIDTH and TILE_HEIGHT
from entities.player import Player

class GameObject:
    def __init__(self, name, size, hp, sprite, x, y, radius, player=None):
        self.name = name
        self.size = size # Keep size for now, might be useful for other things
        self.hp = hp
        self.sprite = sprite
        self.x = x
        self.y = y
        self.radius = radius
        self.selected = False
        self.player = player

class Building(GameObject):
    def __init__(self, name, size, hp, sprite, build_duration, x=0, y=0, radius=0, player=None, costs=None, 
                 armor_type="light", armor_value=0, can_attack=False, min_damage=0, max_damage=0, 
                 attack_type="slash", attack_speed=1.0, attack_range=0):
        super().__init__(name, size, hp, sprite, x, y, radius, player)
        self.build_duration = build_duration
        self.costs = costs or {}
        
        # Armor properties
        self.armor_type = armor_type
        self.armor_value = armor_value
        
        # Combat properties (for defensive buildings like watchtowers)
        self.can_attack = can_attack
        self.min_damage = min_damage
        self.max_damage = max_damage
        self.attack_type = attack_type
        self.attack_speed = attack_speed
        self.attack_range = attack_range
        
        # Combat state
        self.current_target = None
        self.last_attack_time = 0
        self.in_combat = False
        
        # Unit production system
        self.production_queue = []  # Queue of units to produce
        self.current_production = None  # Currently producing unit: {"unit_type": str, "progress": float, "total_time": float}
        self.can_produce = self._get_production_capabilities()
    
    def _get_production_capabilities(self):
        """Get list of units this building can produce"""
        production_map = {
            "castle": ["worker"],
            "barracks": ["warrior", "archer"]
        }
        return production_map.get(self.name, [])
    
    def can_attack_target(self, target):
        """Check if this building can attack the target"""
        if not self.can_attack:
            return False
        
        # Check if target is valid and alive
        if not target or target.hp <= 0:
            return False
        
        # Check if target belongs to enemy
        if target.player == self.player:
            return False
        
        # Check range
        distance = ((self.x - target.x) ** 2 + (self.y - target.y) ** 2) ** 0.5
        return distance <= self.attack_range
    
    def calculate_damage(self, target):
        """Calculate damage dealt to target based on attack and armor types"""
        # Base damage (random between min and max)
        base_damage = random.randint(self.min_damage, self.max_damage)
        
        # Get target armor
        target_armor_type = getattr(target, 'armor_type', 'light')
        target_armor_value = getattr(target, 'armor_value', 0)
        
        # Attack type effectiveness matrix
        effectiveness = {
            "slash": {"light": 1.5, "heavy": 1.0, "fortified": 0.5},
            "pierce": {"light": 1.0, "heavy": 1.5, "fortified": 0.5},
            "siege": {"light": 0.75, "heavy": 1.0, "fortified": 2.0}
        }
        
        # Apply type effectiveness
        multiplier = effectiveness.get(self.attack_type, {}).get(target_armor_type, 1.0)
        damage = base_damage * multiplier
        
        # Apply armor reduction
        damage = max(1, damage - target_armor_value)  # Minimum 1 damage
        
        return int(damage)
    
    def start_attack(self, target):
        """Begin attacking a target"""
        self.current_target = target
        self.in_combat = True
    
    def update_combat(self, delta_time):
        """Handle attack timing and execution for defensive buildings"""
        if not hasattr(self, 'can_attack') or not self.can_attack or not self.in_combat or not self.current_target:
            return
        
        # Check if target is still valid and in range
        if not self.can_attack_target(self.current_target):
            # Target moved out of range or died
            self.current_target = None
            self.in_combat = False
            return
        
        # Check if enough time has passed to attack again
        current_time = pygame.time.get_ticks() / 1000.0
        time_between_attacks = 1.0 / self.attack_speed
        
        if current_time - self.last_attack_time >= time_between_attacks:
            # Perform attack
            damage = self.calculate_damage(self.current_target)
            self.current_target.hp -= damage
            self.last_attack_time = current_time
            
            # Check if target is destroyed
            if self.current_target.hp <= 0:
                self.current_target = None
                self.in_combat = False

class Unit(GameObject):
    def __init__(self, name, size, hp, movement_speed, attack, animations, x=0, y=0, radius=0, player=None, can_build=False, can_attack=False,
                 min_damage=0, max_damage=0, attack_type="slash", armor_type="light", armor_value=0, attack_speed=1.0, attack_range=32):
        super().__init__(name, size, hp, None, x, y, radius, player) # Units don't have a single sprite
        self.movement_speed = movement_speed
        self.attack = attack  # Keep for backward compatibility
        self.animations = animations
        self.status = "idle"
        self.destination = None # This will be a Vector2(x,y)
        self.path = None  # List of waypoints [(x,y), ...]
        self.path_index = 0  # Current waypoint index
        self.path_target = None  # Final destination for pathfinding
        
        # Combat properties
        self.min_damage = min_damage
        self.max_damage = max_damage
        self.attack_type = attack_type  # "slash", "pierce", "siege"
        self.armor_type = armor_type    # "light", "heavy", "fortified"
        self.armor_value = armor_value
        self.attack_speed = attack_speed  # Attacks per second
        self.attack_range = attack_range  # Range in pixels
        
        # Combat state
        self.current_target = None
        self.last_attack_time = 0
        self.in_combat = False
        self.is_engaging = False  # Moving to attack target
        self.has_los = False  # Line of sight to target
        self.los_range = 150  # Range to switch from pathfinding to direct LOS
        self.is_fallback_movement = False  # Flag for when using direct movement as fallback
        
        # Gathering state
        self.is_gathering = False
        self.gathering_target = None  # Resource being gathered
        self.resource_type = None  # Type of resource being carried
        self.resource_amount = 0  # Amount being carried
        self.max_capacity = WORKER_CAPACITY  # Max carrying capacity per resource type
        self.gathering_timer = 0  # Time accumulator for gathering
        self.drop_off_target = None  # Building to drop resources at
        self.is_dropping_off = False  # Whether unit is currently dropping off
        self.drop_off_timer = 0.0  # Timer for drop-off delay
        self.garrison_target = None  # Farm to garrison into
        
        # Building state
        self.can_build = can_build
        self.is_building = False
        self.building_target = None  # ConstructionSite being built
        
        # Attack capability
        self.can_attack_flag = can_attack
        self.last_task = None
        self.collision = True
        self.ghost_timer = None

    def set_animations(self, animations):
        self.animations = animations

    def update_animation(self, delta_time=None):
        # Use build animation if building, otherwise use current status
        animation_status = "build" if self.is_building and "build" in self.animations else self.status
        
        # Special case for archer - use "shoot" instead of "attack"
        if animation_status == "attack" and self.name == "archer" and "shoot" in self.animations:
            animation_status = "shoot"
        
        if animation_status in self.animations:
            # Use attack speed for combat animations
            if animation_status in ["attack", "shoot"] and self.attack_speed > 0:
                # Convert attack speed (attacks per second) to animation speed (ms per frame)
                # Distribute the attack time across the animation frames
                num_frames = len(self.animations[animation_status].frames)
                time_per_attack = 1000.0 / self.attack_speed  # Total time for one attack in ms
                time_per_frame = time_per_attack / num_frames  # Time per animation frame
                self.animations[animation_status].update(custom_speed=time_per_frame, delta_time=delta_time)
            else:
                # Use default animation speed for non-combat animations
                self.animations[animation_status].update(delta_time=delta_time)

    def get_current_sprite(self):
        # Use build animation if building, otherwise use current status
        animation_status = "build" if self.is_building and "build" in self.animations else self.status
        
        # Special case for archer - use "shoot" instead of "attack"
        if animation_status == "attack" and self.name == "archer" and "shoot" in self.animations:
            animation_status = "shoot"
        
        if animation_status in self.animations:
            return self.animations[animation_status].get_current_frame()
        return None
    
    def stop(self):
        """Stop the unit from moving or performing actions"""
        self.destination = None
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.status = "idle"
        self.is_gathering = False
        self.is_building = False
        self.is_dropping_off = False
        self.drop_off_timer = 0.0
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        # Don't clear targets - unit might want to resume later
    
    def clear_all_movement_state(self):
        """Completely clear all movement and task-related state - used when transitioning between major tasks"""
        # Movement state
        self.destination = None
        self.path = None
        self.path_index = 0
        self.path_target = None
        self.status = "idle"
        
        # Gathering state
        self.is_gathering = False
        self.gathering_target = None
        self.resource_type = None
        self.resource_amount = 0
        self.gathering_timer = 0
        self.is_dropping_off = False
        self.drop_off_timer = 0.0
        self.drop_off_target = None
        self.previous_gathering_target = None
        if hasattr(self, 'gathering_position'):
            delattr(self, 'gathering_position')
        
        # Building state
        self.is_building = False
        self.building_target = None
        
        # Combat state
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        self.has_los = False
        self.is_fallback_movement = False
        
        # Clear from any resource gatherer lists
        if hasattr(self, 'gathering_target') and self.gathering_target:
            if hasattr(self.gathering_target, 'gatherers') and self in self.gathering_target.gatherers:
                self.gathering_target.gatherers.remove(self)
        
        # Reset any stuck detection state
        if hasattr(self, '_stuck_detector'):
            delattr(self, '_stuck_detector')
    
    def get_effective_attack_range(self, buffer_type="exact"):
        """Get effective attack range with standardized buffers"""
        if buffer_type == "exact":
            return self.attack_range
        elif buffer_type == "approach":
            # For pathfinding approach - stay slightly within range
            return self.attack_range * 0.9
        elif buffer_type == "positioning":
            # For positioning around targets - more conservative
            return max(self.attack_range - 5, self.attack_range * 0.85)
        else:
            return self.attack_range
    
    def get_distance_to(self, target):
        """Standardized distance calculation"""
        if not target:
            return float('inf')
        return ((self.x - target.x) ** 2 + (self.y - target.y) ** 2) ** 0.5
    
    def get_target_tolerance(self, target_type="movement"):
        """Get dynamic tolerance based on how long unit has been stuck"""
        base_tolerance = 5  # Base tolerance in units
        
        # Check for dance loop detection
        if hasattr(self, '_stuck_detector'):
            stuck_time = self._stuck_detector['stuck_timer']
            
            if stuck_time >= 60:  # 1 second of being stuck
                # Increase tolerance based on how long stuck
                tolerance_multiplier = min(stuck_time / 60, 6)  # Cap at 6x tolerance
                adaptive_tolerance = base_tolerance * tolerance_multiplier
                
                if target_type == "combat":
                    # For combat, be more generous - allow attack if reasonably close
                    return min(adaptive_tolerance, self.get_effective_attack_range("exact") * 0.3)
                else:
                    # For movement, allow larger tolerance
                    return adaptive_tolerance
        
        return base_tolerance

    def can_attack(self, target, use_tolerance=False):
        """Check if target is in range and valid for attack"""
        if not target or target == self:
            return False
        
        # Check if target has different player (can't attack own units)
        if hasattr(target, 'player') and hasattr(self, 'player'):
            if target.player == self.player:
                return False
        
        # Check range using standardized calculation
        distance = self.get_distance_to(target)
        attack_range = self.get_effective_attack_range("exact")
        
        # Apply tolerance if requested (for stuck units)
        if use_tolerance:
            tolerance = self.get_target_tolerance("combat")
            attack_range += tolerance
        
        # Attack range checking happens silently
        
        return distance <= attack_range
    
    def has_line_of_sight(self, target, game_map, obstacles=None):
        """Check if there's a clear line of sight to target with improved accuracy"""
        if not target:
            return False
        
        dx = target.x - self.x
        dy = target.y - self.y
        distance = (dx * dx + dy * dy) ** 0.5
        
        if distance == 0:
            return True
        
        # Normalize direction
        dx_norm = dx / distance
        dy_norm = dy / distance
        
        # More accurate sampling - every 16 pixels instead of 32
        sample_distance = 16
        samples = int(distance / sample_distance) + 1
        
        # Consider unit width for path checking
        path_width = self.radius * 1.2  # Slightly wider than unit for comfortable movement
        
        for i in range(1, samples):  # Skip start and end points
            sample_x = self.x + (dx_norm * sample_distance * i)
            sample_y = self.y + (dy_norm * sample_distance * i)
            
            # Check terrain at center and edges of unit path
            check_points = [
                (sample_x, sample_y),  # Center
                (sample_x + dy_norm * path_width * 0.5, sample_y - dx_norm * path_width * 0.5),  # Left edge
                (sample_x - dy_norm * path_width * 0.5, sample_y + dx_norm * path_width * 0.5),  # Right edge
            ]
            
            for check_x, check_y in check_points:
                # Check terrain
                hex_coord = game_map.world_to_grid(check_x, check_y)
                if hex_coord and 0 <= hex_coord[1] < len(game_map.grid) and 0 <= hex_coord[0] < len(game_map.grid[0]):
                    tile_type = game_map.grid[hex_coord[1]][hex_coord[0]]
                    if tile_type in {"water", "lava"}:
                        return False
                
                # Check obstacles with improved collision detection
                if obstacles:
                    for obstacle in obstacles:
                        if obstacle == self or obstacle == target:
                            continue
                        
                        # Check if any part of unit's path would collide with obstacle
                        obs_distance = ((check_x - obstacle.x) ** 2 + (check_y - obstacle.y) ** 2) ** 0.5
                        
                        # Use same collision distance as movement system for consistency
                        collision_distance = obstacle.radius + self.radius + 2  # Same as collision system
                        
                        if obs_distance < collision_distance:
                            return False
        
        return True
    
    def calculate_damage(self, target):
        """Calculate damage dealt to target based on attack and armor types"""
        # Base damage (random between min and max)
        base_damage = random.randint(self.min_damage, self.max_damage)
        
        # Get target armor
        target_armor_type = getattr(target, 'armor_type', 'light')
        target_armor_value = getattr(target, 'armor_value', 0)
        
        # Attack type effectiveness matrix
        effectiveness = {
            "slash": {"light": 1.5, "heavy": 1.0, "fortified": 0.5},
            "pierce": {"light": 1.0, "heavy": 1.5, "fortified": 0.5},
            "siege": {"light": 0.75, "heavy": 1.0, "fortified": 2.0}
        }
        
        # Apply type effectiveness
        multiplier = effectiveness.get(self.attack_type, {}).get(target_armor_type, 1.0)
        damage = base_damage * multiplier
        
        # Apply armor reduction
        damage = max(1, damage - target_armor_value)  # Minimum 1 damage
        
        return int(damage)
    
    def start_attack(self, target):
        """Begin attacking a target"""
        self.current_target = target
        self.in_combat = True
        self.is_engaging = False  # No longer pursuing, now attacking
        self.status = "attack"
        
        # Stop movement when attacking
        self.destination = None
        self.path = None
        self.path_index = 0
        self.path_target = None
    
    def update_combat(self, delta_time):
        """Handle attack timing and execution"""
        if not self.in_combat or not self.current_target:
            return
        
        # Combat update happens silently unless there are issues
        
        # Check if target is still valid and in range
        if not self.can_attack(self.current_target):
            # Target moved out of range, switch to engaging
            self.in_combat = False
            self.is_engaging = True
            self.status = "run"
            if DEBUG_MOVEMENT:
                print(f"{self.name} target out of range, re-engaging {self.current_target.name}")
            return
        
        # Check if enough time has passed to attack again
        current_time = pygame.time.get_ticks() / 1000.0
        time_between_attacks = 1.0 / self.attack_speed
        
        if current_time - self.last_attack_time >= time_between_attacks:
            # Perform attack
            damage = self.calculate_damage(self.current_target)
            self.current_target.hp -= damage
            self.last_attack_time = current_time
            
            if DEBUG_MOVEMENT:
                print(f"{self.name} attacks {self.current_target.name} for {damage} damage!")
            
            # Check if target is destroyed
            if self.current_target.hp <= 0:
                if DEBUG_MOVEMENT:
                    print(f"{self.current_target.name} destroyed!")
                self.current_target = None
                self.in_combat = False
                self.is_engaging = False
                self.status = "idle"

class Resource(GameObject):
    def __init__(self, name, sprite, x=0, y=0, radius=0):
        super().__init__(name, [1,1], 0, sprite, x, y, radius)
        # Initialize resource amount based on resource type
        self.amount_remaining = RESOURCE_LIMITS.get(name, 100)  # Default to 100 if not specified
        self.gatherers = []  # Track units gathering from this resource

class ConstructionSite(GameObject):
    def __init__(self, building_name, building_data, x, y, radius, player=None):
        # Use construction sprite and temporary HP
        super().__init__(f"{building_name}_construction", building_data['size'], 100, 
                         "assets/sprites/Buildings/Construction.png", x, y, radius, player)
        self.building_name = building_name
        self.building_data = building_data
        self.construction_progress = 0
        self.construction_duration = building_data['build_duration']
        self.builder = None  # The unit currently building this
        self.costs = building_data.get('costs', {})  # Resources spent on this construction

def load_game_data():
    with open('data/buildings.json', 'r') as f:
        buildings_data = json.load(f)
    with open('data/units.json', 'r') as f:
        units_data = json.load(f)
    with open('data/resources.json', 'r') as f:
        resources_data = json.load(f)

    game_data = {"buildings": {}, "units": {}, "resources": {}}

    for b in buildings_data:
        # Calculate radius based on size[0] and TILE_WIDTH
        radius = b['size'][0] * TILE_WIDTH / 2
        game_data["buildings"][b['name']] = Building(
            name=b['name'],
            size=b['size'],
            hp=b['hp'],
            sprite=b['sprite'],
            build_duration=b['build_duration'],
            x=0, 
            y=0, 
            radius=radius,
            costs=b.get('costs', {}),
            armor_type=b.get('armor_type', 'fortified'),
            armor_value=b.get('armor_value', 0),
            can_attack=b.get('can_attack', False),
            min_damage=b.get('min_damage', 0),
            max_damage=b.get('max_damage', 0),
            attack_type=b.get('attack_type', 'slash'),
            attack_speed=b.get('attack_speed', 1.0),
            attack_range=b.get('attack_range', 0)
        )

    for u in units_data:
        # Calculate radius based on size[0] and TILE_WIDTH
        # Units should be smaller than tiles - use 1/8 tile width for radius
        # This gives workers/warriors/archers a 16-pixel diameter (8 radius)
        radius = u['size'][0] * TILE_WIDTH / 8
        game_data["units"][u['name']] = Unit(
            x=0, y=0, radius=radius, 
            name=u['name'], 
            size=u['size'], 
            hp=u['hp'], 
            movement_speed=u['movement_speed'], 
            attack=u.get('attack'), 
            animations=u['animations'], 
            can_build=u.get('can_build', False),
            can_attack=u.get('can_attack', False),
            min_damage=u.get('min_damage', 0),
            max_damage=u.get('max_damage', 0),
            attack_type=u.get('attack_type', 'slash'),
            armor_type=u.get('armor_type', 'light'),
            armor_value=u.get('armor_value', 0),
            attack_speed=u.get('attack_speed', 1.0),
            attack_range=u.get('attack_range', 32)
        )

    for r in resources_data:
        # Resources have a fixed size of [1,1] in the current Resource class, so radius will be TILE_WIDTH / 4 (reduced for better pathfinding)
        radius = TILE_WIDTH / 4
        game_data["resources"][r['name']] = Resource(x=0, y=0, radius=radius, **r)

    return game_data
