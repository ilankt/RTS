import pygame
import random
from entities.game_object import GameObject


class Building(GameObject):
    """Building entity class"""
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