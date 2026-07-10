import pygame
from entities.game_object import GameObject
from core.config import WORKER_CAPACITY, DEBUG_MOVEMENT
from systems.combat_rules import (
    calculate_damage as calculate_combat_damage,
    effective_attack_range,
    effective_stat,
    is_valid_attack_target,
)
from utils.debug_logger import debug_log


# Unit stance constants
STANCE_AGGRESSIVE = "aggressive"
STANCE_DEFENSIVE = "defensive"
STANCE_STAND_GROUND = "stand_ground"
STANCE_NO_ATTACK = "no_attack"

class Unit(GameObject):
    """Unit entity class"""
    def __init__(self, name, size, hp, movement_speed, attack, animations, x=0, y=0, radius=0, player=None, can_build=False, can_attack=False,
                 min_damage=0, max_damage=0, attack_type="slash", armor_type="light", armor_value=0, attack_speed=1.0, attack_range=32,
                 display_name=None, role="", requires=None, buildable=True, strong_against=None, weak_against=None,
                 building_only_attack=False):
        super().__init__(name, size, hp, None, x, y, radius, player)  # Units don't have a single sprite
        self.display_name = display_name or name.replace("_", " ").title()
        self.role = role
        self.requires = requires or []
        self.buildable = buildable
        self.strong_against = strong_against or []
        self.weak_against = weak_against or []
        self.movement_speed = movement_speed
        self.attack = attack  # Keep for backward compatibility
        self.animations = animations
        self.status = "idle"
        self.destination = None  # This will be a Vector2(x,y)
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
        self.building_only_attack = building_only_attack
        
        # Stance system
        self.stance = STANCE_AGGRESSIVE  # Default stance
        self.stance_chase_distance = 300  # How far DEFENSIVE units will chase
        self.stance_home_position = None  # Position to return to for STAND_GROUND
        
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
        self._clear_navigation_metadata()
        self.status = "idle"
        self.is_gathering = False
        # Don't clear is_building if we have a building_target - we might be at the construction site
        if not self.building_target:
            self.is_building = False
        self.is_dropping_off = False
        self.drop_off_timer = 0.0
        self.current_target = None
        self.in_combat = False
        self.is_engaging = False
        # Don't clear targets - unit might want to resume later
    
    def clear_all_movement_state(self):
        """Completely clear all movement and task-related state - used when transitioning between major tasks"""
        # Clear from any resource gatherer lists BEFORE clearing gathering_target
        if self.gathering_target:
            if hasattr(self.gathering_target, 'gatherers') and self in self.gathering_target.gatherers:
                self.gathering_target.gatherers.remove(self)

        # Movement state
        self.destination = None
        self.path = None
        self.path_index = 0
        self.path_target = None
        self._clear_navigation_metadata()
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

        # Reset any stuck detection state
        if hasattr(self, '_stuck_detector'):
            delattr(self, '_stuck_detector')

    def _clear_navigation_metadata(self):
        for attr in ("path_target_object", "path_target_object_pos", "path_target_mode"):
            if hasattr(self, attr):
                delattr(self, attr)
    
    def get_effective_attack_range(self, buffer_type="exact"):
        """Get effective attack range with standardized buffers"""
        attack_range = effective_attack_range(self)
        if buffer_type == "exact":
            return attack_range
        elif buffer_type == "approach":
            # For pathfinding approach - stay slightly within range
            return attack_range * 0.9
        elif buffer_type == "positioning":
            # For positioning around targets - more conservative
            return max(attack_range - 5, attack_range * 0.85)
        else:
            return attack_range
    
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
        if not is_valid_attack_target(self, target):
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
        
        target_radius = getattr(target, 'radius', 0)
        return distance <= attack_range + target_radius
    
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

        terrain_probe = getattr(game_map, "nav_terrain_walkable", None)

        for i in range(1, samples):  # Skip start and end points
            sample_x = self.x + (dx_norm * sample_distance * i)
            sample_y = self.y + (dy_norm * sample_distance * i)

            # Check terrain at center and edges of unit path
            check_points = (
                (sample_x, sample_y),  # Center
                (sample_x + dy_norm * path_width * 0.5, sample_y - dx_norm * path_width * 0.5),  # Left edge
                (sample_x - dy_norm * path_width * 0.5, sample_y + dx_norm * path_width * 0.5),  # Right edge
            )

            for check_x, check_y in check_points:
                # Check terrain
                if terrain_probe is not None:
                    if not terrain_probe(check_x, check_y):
                        return False
                else:
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
                        obs_dist_sq = (check_x - obstacle.x) ** 2 + (check_y - obstacle.y) ** 2

                        # Use same collision distance as movement system for consistency
                        collision_distance = obstacle.radius + self.radius + 2  # Same as collision system

                        if obs_dist_sq < collision_distance * collision_distance:
                            return False

        return True
    
    def calculate_damage(self, target):
        """Calculate damage dealt to target based on attack and armor types"""
        return calculate_combat_damage(self, target)

    def get_effective_min_damage(self):
        return int(effective_stat(self, "min_damage"))

    def get_effective_max_damage(self):
        return int(effective_stat(self, "max_damage"))

    def get_effective_armor_value(self):
        return int(effective_stat(self, "armor_value"))
    
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
                debug_log.log(f"{self.name} target out of range, re-engaging {self.current_target.name}", "GENERAL")
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
                debug_log.log(f"{self.name} attacks {self.current_target.name} for {damage} damage!", "GENERAL")
            
            # Check if target is destroyed
            if self.current_target.hp <= 0:
                if DEBUG_MOVEMENT:
                    debug_log.log(f"{self.current_target.name} destroyed!", "GENERAL")
                self.current_target = None
                self.in_combat = False
                self.is_engaging = False
                self.status = "idle"
