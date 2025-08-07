"""Military formation system for coordinated unit movement and combat"""
import math
import random
from typing import Dict, List, Tuple, Optional, Set
from enum import Enum
from dataclasses import dataclass


class FormationType(Enum):
    """Types of military formations"""
    LINE = "line"                 # Units in a straight line
    WEDGE = "wedge"              # V-shaped formation for breakthrough
    BOX = "box"                  # Square/rectangular formation for defense
    COLUMN = "column"            # Single file for movement through narrow areas
    SCATTER = "scatter"          # Spread formation to avoid area damage
    ARCHER_SCREEN = "archer_screen"  # Archers behind melee units


@dataclass
class FormationPosition:
    """Position within a formation"""
    x_offset: float
    y_offset: float
    priority: int  # 0 = leader, higher = further from center
    role: str      # "leader", "melee", "ranged", "support"


class Formation:
    """Represents a military formation with unit positions"""
    
    def __init__(self, formation_type: FormationType, center_x: float, center_y: float, 
                 facing_angle: float = 0.0, spacing: float = 60.0):
        self.formation_type = formation_type
        self.center_x = center_x
        self.center_y = center_y
        self.facing_angle = facing_angle  # Radians
        self.spacing = spacing
        
        # Unit assignments
        self.units = []
        self.unit_positions = {}  # unit -> FormationPosition
        self.leader = None
        
        # Formation state
        self.is_moving = False
        self.target_x = center_x
        self.target_y = center_y
        self.in_combat = False
        
        # Generate formation positions
        self._generate_positions()
    
    def _generate_positions(self) -> None:
        """Generate formation positions based on type"""
        positions = []
        
        if self.formation_type == FormationType.LINE:
            # Horizontal line formation
            for i in range(10):  # Support up to 10 units
                x_offset = (i - 4.5) * self.spacing
                y_offset = 0
                priority = abs(i - 4.5)  # Center units have priority
                role = "melee" if i < 5 else "ranged"
                positions.append(FormationPosition(x_offset, y_offset, priority, role))
        
        elif self.formation_type == FormationType.WEDGE:
            # V-shaped formation for attack
            positions.append(FormationPosition(0, 0, 0, "leader"))  # Point of wedge
            
            for i in range(1, 10):
                side = 1 if i % 2 == 1 else -1
                row = (i + 1) // 2
                x_offset = side * row * self.spacing * 0.7
                y_offset = -row * self.spacing * 0.5
                priority = row
                role = "melee" if row <= 2 else "ranged"
                positions.append(FormationPosition(x_offset, y_offset, priority, role))
        
        elif self.formation_type == FormationType.BOX:
            # Square formation for defense
            side_length = 3  # 3x3 formation
            for row in range(side_length):
                for col in range(side_length):
                    x_offset = (col - 1) * self.spacing
                    y_offset = (row - 1) * self.spacing
                    priority = max(abs(col - 1), abs(row - 1))
                    
                    # Outer ring is melee, inner is ranged
                    if row == 0 or row == side_length - 1 or col == 0 or col == side_length - 1:
                        role = "melee"
                    else:
                        role = "ranged"
                    
                    positions.append(FormationPosition(x_offset, y_offset, priority, role))
        
        elif self.formation_type == FormationType.COLUMN:
            # Single file formation
            for i in range(10):
                x_offset = 0
                y_offset = i * self.spacing * 0.8
                priority = i
                role = "leader" if i == 0 else ("melee" if i < 5 else "ranged")
                positions.append(FormationPosition(x_offset, y_offset, priority, role))
        
        elif self.formation_type == FormationType.SCATTER:
            # Random scattered positions
            for i in range(10):
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(self.spacing * 0.5, self.spacing * 1.5)
                x_offset = distance * math.cos(angle)
                y_offset = distance * math.sin(angle)
                priority = random.randint(1, 5)
                role = "melee" if random.random() < 0.6 else "ranged"
                positions.append(FormationPosition(x_offset, y_offset, priority, role))
        
        elif self.formation_type == FormationType.ARCHER_SCREEN:
            # Archers behind melee screen
            # Front row - melee units
            for i in range(5):
                x_offset = (i - 2) * self.spacing
                y_offset = 0
                priority = abs(i - 2)
                positions.append(FormationPosition(x_offset, y_offset, priority, "melee"))
            
            # Back row - archers
            for i in range(5):
                x_offset = (i - 2) * self.spacing * 0.8
                y_offset = -self.spacing * 1.2
                priority = abs(i - 2) + 3
                positions.append(FormationPosition(x_offset, y_offset, priority, "ranged"))
        
        self.positions = positions
    
    def add_unit(self, unit) -> bool:
        """Add unit to formation"""
        if len(self.units) >= len(self.positions):
            return False
        
        # Find best position for unit type
        unit_type = getattr(unit, 'name', 'unknown')
        preferred_role = "ranged" if unit_type == "archer" else "melee"
        
        # Find best available position
        best_position = None
        best_score = float('inf')
        
        for position in self.positions:
            if position not in self.unit_positions.values():
                # Score based on role match and priority
                role_score = 0 if position.role == preferred_role else 1
                total_score = position.priority + role_score
                
                if total_score < best_score:
                    best_score = total_score
                    best_position = position
        
        if best_position:
            self.units.append(unit)
            self.unit_positions[unit] = best_position
            
            if not self.leader or best_position.priority == 0:
                self.leader = unit
            
            return True
        
        return False
    
    def remove_unit(self, unit) -> bool:
        """Remove unit from formation"""
        if unit in self.units:
            self.units.remove(unit)
            del self.unit_positions[unit]
            
            if self.leader == unit and self.units:
                # Find new leader (lowest priority)
                self.leader = min(self.units, 
                    key=lambda u: self.unit_positions[u].priority)
            
            return True
        return False
    
    def get_unit_target_position(self, unit) -> Optional[Tuple[float, float]]:
        """Get target position for unit in formation"""
        if unit not in self.unit_positions:
            return None
        
        position = self.unit_positions[unit]
        
        # Rotate position based on formation facing
        cos_angle = math.cos(self.facing_angle)
        sin_angle = math.sin(self.facing_angle)
        
        rotated_x = position.x_offset * cos_angle - position.y_offset * sin_angle
        rotated_y = position.x_offset * sin_angle + position.y_offset * cos_angle
        
        target_x = self.center_x + rotated_x
        target_y = self.center_y + rotated_y
        
        return (target_x, target_y)
    
    def move_to(self, target_x: float, target_y: float) -> None:
        """Move formation to target position"""
        self.target_x = target_x
        self.target_y = target_y
        self.is_moving = True
    
    def face_towards(self, target_x: float, target_y: float) -> None:
        """Orient formation to face target"""
        dx = target_x - self.center_x
        dy = target_y - self.center_y
        self.facing_angle = math.atan2(dy, dx)
    
    def update_center(self) -> None:
        """Update formation center based on unit positions"""
        if not self.units:
            return
        
        total_x = sum(getattr(unit, 'x', 0) for unit in self.units)
        total_y = sum(getattr(unit, 'y', 0) for unit in self.units)
        
        self.center_x = total_x / len(self.units)
        self.center_y = total_y / len(self.units)
    
    def is_in_position(self, tolerance: float = 30.0) -> bool:
        """Check if all units are in formation positions"""
        for unit in self.units:
            target_pos = self.get_unit_target_position(unit)
            if target_pos:
                distance = math.sqrt((unit.x - target_pos[0])**2 + 
                                   (unit.y - target_pos[1])**2)
                if distance > tolerance:
                    return False
        return True
    
    def get_formation_strength(self) -> float:
        """Calculate formation combat strength"""
        strength = 0.0
        for unit in self.units:
            # Base strength based on unit type
            if hasattr(unit, 'name'):
                if unit.name == "warrior":
                    strength += 1.0
                elif unit.name == "archer":
                    strength += 0.8
            
            # Health modifier
            if hasattr(unit, 'hp') and hasattr(unit, 'max_hp'):
                health_ratio = unit.hp / unit.max_hp
                strength *= health_ratio
        
        # Formation bonus
        formation_bonus = {
            FormationType.LINE: 1.1,
            FormationType.WEDGE: 1.2,
            FormationType.BOX: 1.0,
            FormationType.COLUMN: 0.9,
            FormationType.SCATTER: 0.8,
            FormationType.ARCHER_SCREEN: 1.15
        }
        
        return strength * formation_bonus.get(self.formation_type, 1.0)


class FormationManager:
    """Manages military formations for AI player"""
    
    def __init__(self, ai_system, player):
        self.ai_system = ai_system
        self.player = player
        self.game = ai_system.game
        
        # Active formations
        self.formations = []
        self.unit_formations = {}  # unit -> formation
        
        # Formation preferences
        self.formation_preferences = {
            "attack": [FormationType.WEDGE, FormationType.ARCHER_SCREEN],
            "defend": [FormationType.BOX, FormationType.LINE],
            "move": [FormationType.COLUMN, FormationType.LINE],
            "scout": [FormationType.SCATTER]
        }
        
        # Formation settings
        self.min_formation_size = 3
        self.max_formation_size = 8
        self.formation_spacing = 60.0
        
    def update(self, delta_time: float) -> None:
        """Update all formations"""
        # Update formation centers
        for formation in self.formations:
            formation.update_center()
        
        # Clean up empty formations
        self.formations = [f for f in self.formations if f.units]
        
        # Update unit_formations mapping
        self.unit_formations = {}
        for formation in self.formations:
            for unit in formation.units:
                self.unit_formations[unit] = formation
    
    def create_formation(self, units: List, formation_type: FormationType, 
                        center_x: float, center_y: float) -> Optional[Formation]:
        """Create new formation with units"""
        if len(units) < self.min_formation_size:
            return None
        
        formation = Formation(formation_type, center_x, center_y, 
                            spacing=self.formation_spacing)
        
        # Add units to formation
        added_units = []
        for unit in units[:self.max_formation_size]:
            if formation.add_unit(unit):
                added_units.append(unit)
        
        if len(added_units) >= self.min_formation_size:
            self.formations.append(formation)
            return formation
        
        return None
    
    def auto_form_units(self, units: List, situation: str = "attack") -> List[Formation]:
        """Automatically create formations for units"""
        if len(units) < self.min_formation_size:
            return []
        
        formations_created = []
        remaining_units = units.copy()
        
        # Choose formation type based on situation
        preferred_types = self.formation_preferences.get(situation, [FormationType.LINE])
        
        while len(remaining_units) >= self.min_formation_size:
            # Group units by type for formation
            melee_units = [u for u in remaining_units if getattr(u, 'name', '') == 'warrior']
            ranged_units = [u for u in remaining_units if getattr(u, 'name', '') == 'archer']
            
            # Determine formation type and composition
            if len(melee_units) >= 3 and len(ranged_units) >= 2 and FormationType.ARCHER_SCREEN in preferred_types:
                formation_type = FormationType.ARCHER_SCREEN
                formation_units = melee_units[:3] + ranged_units[:2]
            else:
                formation_type = preferred_types[0] if preferred_types else FormationType.LINE
                formation_units = remaining_units[:self.max_formation_size]
            
            # Calculate formation center
            center_x = sum(getattr(u, 'x', 0) for u in formation_units) / len(formation_units)
            center_y = sum(getattr(u, 'y', 0) for u in formation_units) / len(formation_units)
            
            # Create formation
            formation = self.create_formation(formation_units, formation_type, center_x, center_y)
            if formation:
                formations_created.append(formation)
                for unit in formation_units:
                    if unit in remaining_units:
                        remaining_units.remove(unit)
            else:
                break
        
        return formations_created
    
    def move_formation_to(self, formation: Formation, target_x: float, target_y: float) -> None:
        """Move formation to target position"""
        formation.move_to(target_x, target_y)
        formation.center_x = target_x
        formation.center_y = target_y
    
    def attack_target_with_formation(self, formation: Formation, target) -> None:
        """Command formation to attack target"""
        if not target or not formation.units:
            return
        
        target_x = getattr(target, 'x', 0)
        target_y = getattr(target, 'y', 0)
        
        # Face formation towards target
        formation.face_towards(target_x, target_y)
        formation.in_combat = True
        
        # Position formation for optimal attack
        # Move formation to engagement range
        distance_to_target = 100  # Stay back a bit for ranged units
        dx = target_x - formation.center_x
        dy = target_y - formation.center_y
        distance = math.sqrt(dx**2 + dy**2)
        
        if distance > distance_to_target:
            # Move closer
            ratio = (distance - distance_to_target) / distance
            new_x = formation.center_x + dx * ratio
            new_y = formation.center_y + dy * ratio
            formation.move_to(new_x, new_y)
    
    def get_formation_orders(self, formation: Formation) -> List[Tuple]:
        """Get movement orders for all units in formation"""
        orders = []
        
        for unit in formation.units:
            target_pos = formation.get_unit_target_position(unit)
            if target_pos:
                orders.append((unit, target_pos))
        
        return orders
    
    def dissolve_formation(self, formation: Formation) -> None:
        """Dissolve formation and free units"""
        if formation in self.formations:
            self.formations.remove(formation)
        
        for unit in formation.units:
            if unit in self.unit_formations:
                del self.unit_formations[unit]
    
    def get_unit_formation(self, unit) -> Optional[Formation]:
        """Get formation that unit belongs to"""
        return self.unit_formations.get(unit)
    
    def is_unit_in_formation(self, unit) -> bool:
        """Check if unit is part of a formation"""
        return unit in self.unit_formations
    
    def get_optimal_formation_type(self, situation: str, unit_composition: Dict[str, int]) -> FormationType:
        """Get optimal formation type for situation and units"""
        melee_count = unit_composition.get('warrior', 0)
        ranged_count = unit_composition.get('archer', 0)
        
        if situation == "attack":
            if melee_count >= 3 and ranged_count >= 2:
                return FormationType.ARCHER_SCREEN
            elif melee_count > ranged_count:
                return FormationType.WEDGE
            else:
                return FormationType.LINE
        
        elif situation == "defend":
            if melee_count + ranged_count >= 6:
                return FormationType.BOX
            else:
                return FormationType.LINE
        
        elif situation == "move":
            return FormationType.COLUMN
        
        else:  # scout or default
            return FormationType.SCATTER if melee_count + ranged_count <= 3 else FormationType.LINE