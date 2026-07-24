import pygame
from entities.game_object import GameObject
from systems.combat_rules import (
    calculate_damage as calculate_combat_damage,
    effective_attack_range,
    effective_stat,
)


class Building(GameObject):
    """Building entity class"""
    def __init__(self, name, size, hp, sprite, build_duration, x=0, y=0, radius=0, player=None, costs=None, 
                 armor_type="light", armor_value=0, can_attack=False, min_damage=0, max_damage=0, 
                 attack_type="slash", attack_speed=1.0, attack_range=0,
                 display_name=None, role="", requires=None, buildable=True, strong_against=None, weak_against=None):
        super().__init__(name, size, hp, sprite, x, y, radius, player)
        self.display_name = display_name or name.replace("_", " ").title()
        self.role = role
        self.requires = requires or []
        self.buildable = buildable
        self.strong_against = strong_against or []
        self.weak_against = weak_against or []
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
        self.last_attack_time = 0  # wall-clock stamp, used only for projectile-spawn detection
        self._attack_cooldown = 0.0  # game-time seconds until the next attack
        self.in_combat = False
        
        # Unit production system
        self.production_queue = []  # Queue of units to produce
        self.current_production = None  # Currently producing unit: {"unit_type": str, "progress": float, "total_time": float}
        self.can_produce = self._get_production_capabilities()
        
        # Tech research system
        self.research_queue = []  # Queue of techs to research
        self.current_research = None  # Currently researching tech: {"tech_name": str, "progress": float, "total_time": float}

        # Rally point (§7.4): newly produced units path here; if the rally was
        # set on a resource, rallied workers start gathering it.
        self.rally_point = None
        self.rally_resource = None

        # Walls/gates were removed; `passable` is kept as a generic inert flag
        # (shared nav/collision code reads it) that no building sets True now.
        self.passable = False

    def _get_production_capabilities(self):
        """Get list of units this building can produce"""
        production_map = {
            "castle": ["worker"],
            "barracks": ["warrior", "archer", "spearman"],
            "stable": ["cavalry"],
            "siege_workshop": ["ram"],
            "temple": ["healer"],
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
        
        # Check range — same radius courtesy units get (unit.can_attack adds
        # the TARGET's radius): without it an archer plinking a fat tower
        # out-reached the tower by the tower's own radius (user-reported;
        # reach vs a big building = range + its radius, both directions)
        distance = ((self.x - target.x) ** 2 + (self.y - target.y) ** 2) ** 0.5
        return distance <= effective_attack_range(self) + getattr(target, 'radius', 0)
    
    def calculate_damage(self, target):
        """Calculate damage dealt to target based on attack and armor types"""
        return calculate_combat_damage(self, target)

    def get_effective_min_damage(self):
        return int(effective_stat(self, "min_damage"))

    def get_effective_max_damage(self):
        return int(effective_stat(self, "max_damage"))

    def get_effective_attack_range(self):
        return effective_attack_range(self)

    def get_effective_armor_value(self):
        return int(effective_stat(self, "armor_value"))
    
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
        
        # Attack cadence runs on GAME time (see Unit.update_combat) so tower
        # DPS keeps pace with the rest of the sim at any game speed.
        self._attack_cooldown = getattr(self, "_attack_cooldown", 0.0) - delta_time
        if self._attack_cooldown <= 0:
            # Perform attack
            damage = self.calculate_damage(self.current_target)
            self.current_target.hp -= damage
            self.last_attack_time = pygame.time.get_ticks() / 1000.0
            # §8.9 garrison: each sheltered unit speeds tower fire +15%
            speed = self.attack_speed * (1.0 + 0.15 * len(getattr(self, "garrison", ())))
            self._attack_cooldown = 1.0 / speed
            
            # Check if target is destroyed
            if self.current_target.hp <= 0:
                self.current_target = None
                self.in_combat = False
