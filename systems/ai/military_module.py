"""Military AI module for combat and unit production"""
import math
import random
import pygame
from typing import Dict, List, Tuple, Optional, Any
from .base_module import AIModule
from .formation_system import FormationManager, FormationType
from entities.objects import Unit, Building


class MilitaryModule(AIModule):
    """Handles military decisions: unit production, combat tactics, defense"""
    
    def __init__(self, ai_system, player):
        super().__init__(ai_system, player)
        self.priority = 0.6  # Medium-high priority
        self.update_interval = 2.0  # Balanced for performance and responsiveness
        
        # Initialize formation manager
        self.formation_manager = FormationManager(ai_system, player)
        
        # Combat state tracking
        self.in_combat = False
        self.last_combat_time = 0
        self.retreat_threshold = 0.3  # Retreat when force strength below 30%
        
        # Unit composition targets
        self.unit_ratios = {
            "warrior": 0.6,  # 60% warriors
            "archer": 0.4    # 40% archers
        }
        
        # Tactical settings
        self.attack_force_min = 3
        self.defense_radius = 350
        self.patrol_radius = 200
        
        # Formation tactics
        self.use_formations = True
        self.last_formation_update = 0
        self.formation_update_interval = 5.0
        
    def update(self, delta_time: float) -> None:
        """Update module and formation manager"""
        super().update(delta_time)
        self.formation_manager.update(delta_time)
        
        # Update formations periodically
        self.last_formation_update += delta_time
        if self.last_formation_update >= self.formation_update_interval:
            self._update_formations()
            self.last_formation_update = 0
    
    def get_tasks(self) -> List[Dict[str, Any]]:
        """Generate military tasks based on a clear, state-driven logic."""
        tasks = []
        memory = self.ai_system.player_memory[self.player]

        # 1. Defend the base if it's under attack.
        threat_level = self._assess_threat_level()
        if threat_level > 0.5:
            tasks.append({"action": "defend_base", "priority": 1.0, "target": None, "params": {"threat_level": threat_level}})

        # 2. Build a barracks if one doesn't exist and the economy can support it.
        if not memory["buildings"]["barracks"] and self._can_afford("barracks"):
            if len(memory["gathering_workers"]) + len(memory["idle_workers"]) > 3: # Require a stable economy
                tasks.append({"action": "build_barracks", "priority": 0.8, "target": None, "params": {}})

        # 3. Train military units if a barracks exists.
        if memory["buildings"]["barracks"]:
            unit_type = self._get_unit_to_train()
            if unit_type and self._can_afford(unit_type):
                tasks.append({"action": "train_military", "priority": 0.7, "target": memory["buildings"]["barracks"][0], "params": {"unit_type": unit_type}})

        # 4. Organize and attack with military units.
        military_strength = self._calculate_military_strength()
        enemy_strength = self._estimate_enemy_strength()
        if military_strength > enemy_strength * 1.5 and len(memory["military_units"]) >= self.attack_force_min:
            target = self._find_attack_target()
            if target:
                tasks.append({"action": "attack_enemy", "priority": 0.8, "target": target, "params": {"use_formations": self.use_formations}})

        return tasks
    
    def execute_task(self, task: Dict[str, Any]) -> bool:
        """Execute military task"""
        action = task["action"]
        
        if action == "defend_base":
            return self._execute_defend_base(task)
        elif action == "build_barracks":
            return self._execute_build_barracks(task)
        elif action == "train_military":
            return self._execute_train_military(task)
        elif action == "form_units":
            return self._execute_form_units(task)
        elif action == "attack_enemy":
            return self._execute_attack_enemy(task)
        elif action == "patrol":
            return self._execute_patrol(task)
        elif action == "retreat":
            return self._execute_retreat(task)
        
        return False
    
    def _assess_threat_level(self) -> float:
        """Assess current threat level (0-1)"""
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return 0.0
        
        threat_score = 0.0
        enemy_count = 0
        
        # Check for nearby enemy units
        for unit in self.game.units:
            if unit.player != self.player:
                distance = math.sqrt((unit.x - castle.x)**2 + (unit.y - castle.y)**2)
                if distance < self.defense_radius:
                    # Closer enemies are more threatening
                    threat_contribution = 1.0 - (distance / self.defense_radius)
                    threat_score += threat_contribution
                    enemy_count += 1
        
        # Normalize threat score
        if enemy_count > 0:
            threat_score = min(1.0, threat_score / 3)  # Cap at 3 nearby enemies for max threat
            self.in_combat = True
            self.last_combat_time = pygame.time.get_ticks() / 1000.0
        else:
            # Decay combat state after 10 seconds
            current_time = pygame.time.get_ticks() / 1000.0
            if current_time - self.last_combat_time > 10:
                self.in_combat = False
        
        return threat_score
    
    def _calculate_military_strength(self) -> float:
        """Calculate our military strength"""
        memory = self.ai_system.player_memory[self.player]
        strength = 0.0
        
        for unit in memory["military_units"]:
            if hasattr(unit, 'hp') and hasattr(unit, 'max_hp'):
                # Weight by unit type and health
                base_strength = 1.0 if unit.name == "warrior" else 0.8  # Warriors slightly stronger
                health_ratio = unit.hp / unit.max_hp
                strength += base_strength * health_ratio
        
        return strength
    
    def _estimate_enemy_strength(self) -> float:
        """Estimate enemy military strength"""
        enemy_strength = 0.0
        
        for unit in self.game.units:
            if unit.player != self.player and hasattr(unit, 'name'):
                if unit.name in ["warrior", "archer"]:
                    enemy_strength += 1.0
        
        return enemy_strength
    
    def _get_unit_to_train(self) -> Optional[str]:
        """Determine which unit type to train - balanced but warrior-focused early"""
        memory = self.ai_system.player_memory[self.player]
        
        # Count current units
        warrior_count = sum(1 for u in memory["military_units"] if u.name == "warrior")
        archer_count = sum(1 for u in memory["military_units"] if u.name == "archer")
        total_military = warrior_count + archer_count
        
        # Early game: focus on warriors first (stronger melee units)
        if total_military < 3:
            return "warrior"
        
        # Mid game: balance with archers
        if total_military < 6:
            if warrior_count >= archer_count:
                return "archer"
            else:
                return "warrior"
        
        # Late game: maintain ratio
        warrior_ratio = warrior_count / total_military if total_military > 0 else 0
        
        # Train unit type we're lacking (60% warrior, 40% archer target)
        if warrior_ratio < 0.6:
            return "warrior"
        else:
            return "archer"
    
    def _find_attack_target(self) -> Optional[Any]:
        """Find best target to attack"""
        targets = []
        
        # Prioritize enemy buildings
        for building in self.game.buildings:
            if building.player != self.player:
                priority = 2.0 if building.name == "castle" else 1.0
                targets.append((building, priority))
        
        # Add enemy units as secondary targets
        for unit in self.game.units:
            if unit.player != self.player:
                priority = 0.5
                targets.append((unit, priority))
        
        if not targets:
            return None
        
        # Sort by priority and return highest
        targets.sort(key=lambda x: x[1], reverse=True)
        return targets[0][0]
    
    def _is_unit_idle(self, unit: Unit) -> bool:
        """Check if unit is idle"""
        if hasattr(unit, 'status'):
            return unit.status == "idle"
        return True
    
    def _execute_defend_base(self, task: Dict[str, Any]) -> bool:
        """Rally units to defend base"""
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return False
        
        if self.use_formations:
            # Use formations for defense
            defensive_formations = [f for f in self.formation_manager.formations 
                                  if f.formation_type in [FormationType.BOX, FormationType.LINE]]
            
            if defensive_formations:
                # Move formations to defensive positions
                for formation in defensive_formations:
                    angle = random.uniform(0, 2 * math.pi)
                    defense_x = castle.x + self.patrol_radius * 0.7 * math.cos(angle)
                    defense_y = castle.y + self.patrol_radius * 0.7 * math.sin(angle)
                    
                    nearest_enemy = self._find_nearest_enemy_to_point(castle.x, castle.y)
                    if nearest_enemy:
                        self.formation_manager.attack_target_with_formation(formation, nearest_enemy)
                    else:
                        self.formation_manager.move_formation_to(formation, defense_x, defense_y)
                    
                    # Execute formation orders
                    self._execute_formation_orders(formation)
            else:
                # Create defensive formation
                unformed_units = self._get_unformed_military_units(memory)
                if len(unformed_units) >= 3:
                    center_x = castle.x + 100
                    center_y = castle.y + 100
                    self.formation_manager.create_formation(
                        unformed_units, FormationType.BOX, center_x, center_y
                    )
        else:
            # Individual unit commands
            for unit in memory["military_units"]:
                nearest_enemy = self._find_nearest_enemy_to_point(castle.x, castle.y)
                if nearest_enemy:
                    self.ai_system._command_unit_attack(unit, nearest_enemy)
                else:
                    # Move to defensive position near castle
                    angle = random.uniform(0, 2 * math.pi)
                    defense_x = castle.x + self.patrol_radius * 0.5 * math.cos(angle)
                    defense_y = castle.y + self.patrol_radius * 0.5 * math.sin(angle)
                    self.ai_system._command_unit_move(unit, (defense_x, defense_y))
        
        return True
    
    def _execute_build_barracks(self, task: Dict[str, Any]) -> bool:
        """Build a barracks"""
        self.ai_system._build_structure(self.player, "barracks")
        return True
    
    def _execute_train_military(self, task: Dict[str, Any]) -> bool:
        """Train military unit"""
        unit_type = task["params"]["unit_type"]
        self.ai_system._train_unit(self.player, unit_type)
        return True
    
    def _execute_attack_enemy(self, task: Dict[str, Any]) -> bool:
        """Coordinate attack on enemy target"""
        target = task["target"]
        memory = self.ai_system.player_memory[self.player]
        use_formations = task["params"].get("use_formations", False)
        
        if use_formations and self.formation_manager.formations:
            # Use formations for attack
            for formation in self.formation_manager.formations:
                self.formation_manager.attack_target_with_formation(formation, target)
                self._execute_formation_orders(formation)
        else:
            # Individual unit commands
            for unit in memory["military_units"]:
                self.ai_system._command_unit_attack(unit, target)
        
        return True
    
    def _execute_patrol(self, task: Dict[str, Any]) -> bool:
        """Set units to patrol around base"""
        units = task["target"]
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return False
        
        for i, unit in enumerate(units):
            # Spread units around base perimeter
            angle = (i / len(units)) * 2 * math.pi
            patrol_x = castle.x + self.patrol_radius * math.cos(angle)
            patrol_y = castle.y + self.patrol_radius * math.sin(angle)
            self.ai_system._command_unit_move(unit, (patrol_x, patrol_y))
        
        return True
    
    def _execute_retreat(self, task: Dict[str, Any]) -> bool:
        """Retreat units to castle"""
        units = task["target"]
        memory = self.ai_system.player_memory[self.player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return False
        
        for unit in units:
            # Move to castle with some spread
            angle = random.uniform(0, 2 * math.pi)
            retreat_x = castle.x + 50 * math.cos(angle)
            retreat_y = castle.y + 50 * math.sin(angle)
            self.ai_system._command_unit_move(unit, (retreat_x, retreat_y))
        
        return True
    
    def _find_nearest_enemy_to_point(self, x: float, y: float) -> Optional[Any]:
        """Find nearest enemy to a specific point"""
        nearest = None
        min_distance = float('inf')
        
        for unit in self.game.units:
            if unit.player != self.player:
                distance = math.sqrt((unit.x - x)**2 + (unit.y - y)**2)
                if distance < min_distance:
                    min_distance = distance
                    nearest = unit
        
        return nearest
    
    def _can_afford(self, item_type: str) -> bool:
        """Check if player can afford item"""
        costs = self.ai_system.cost_data.get(item_type, {})
        for resource, amount in costs.items():
            if self.player.resources.get(resource, 0) < amount:
                return False
        return True
    
    # Formation-related helper methods
    
    def _execute_form_units(self, task: Dict[str, Any]) -> bool:
        """Form units into formations"""
        units = task["target"]
        situation = task["params"].get("situation", "attack")
        
        formations = self.formation_manager.auto_form_units(units, situation)
        if formations:
            print(f"AI {self.player.name}: Created {len(formations)} formation(s) for {situation}")
            return True
        return False
    
    def _execute_formation_orders(self, formation) -> None:
        """Execute movement orders for formation"""
        orders = self.formation_manager.get_formation_orders(formation)
        for unit, target_pos in orders:
            self.ai_system._command_unit_move(unit, target_pos)
    
    def _get_unformed_military_units(self, memory: Dict) -> List:
        """Get military units not in formations"""
        unformed = []
        for unit in memory["military_units"]:
            if not self.formation_manager.is_unit_in_formation(unit):
                unformed.append(unit)
        return unformed
    
    def _update_formations(self) -> None:
        """Update and optimize formations"""
        memory = self.ai_system.player_memory[self.player]
        
        # Remove formations with too few units
        for formation in self.formation_manager.formations[:]:
            if len(formation.units) < self.formation_manager.min_formation_size:
                self.formation_manager.dissolve_formation(formation)
        
        # Create formations for unformed units
        unformed_units = self._get_unformed_military_units(memory)
        if len(unformed_units) >= self.formation_manager.min_formation_size:
            threat_level = self._assess_threat_level()
            situation = "defend" if threat_level > 0.5 else "attack"
            self.formation_manager.auto_form_units(unformed_units, situation)