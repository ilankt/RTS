import math
from core.config import DEBUG_MOVEMENT


class CombatSystem:
    """Handles combat targeting, attack positioning, and combat logic"""
    
    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        self.projectile_system = None  # Will be set after projectile system is created
        self.attack_trackers = {}  # Track last attack time for each attacker
        
    def find_optimal_attack_position(self, unit, target, other_attackers):
        """Find optimal attack position for unit when multiple units are attacking the same target"""
        target_x, target_y = target.x, target.y
        attack_range = unit.get_effective_attack_range("positioning")  # Use standardized positioning range
        
        # Generate potential attack positions in a circle around the target
        num_positions = 8  # Check 8 positions around the target
        best_position = None
        best_score = float('-inf')
        
        for i in range(num_positions):
            angle = (i / num_positions) * 2 * math.pi
            pos_x = target_x + math.cos(angle) * attack_range
            pos_y = target_y + math.sin(angle) * attack_range
            
            # Check if position is valid (not in water/lava, not blocked by buildings)
            hex_coord = self.game_map.world_to_grid(pos_x, pos_y)
            if not hex_coord:
                continue
            col, row = hex_coord
            if row < 0 or row >= self.game_map.height or col < 0 or col >= self.game_map.width:
                continue
            tile_type = self.game_map.grid[row][col]
            if tile_type in {"water", "lava"}:
                continue
            
            # Check for collision with buildings
            blocked_by_building = False
            for building in self.game.buildings:
                dist_to_building = math.sqrt((building.x - pos_x)**2 + (building.y - pos_y)**2)
                if dist_to_building < (building.radius + unit.radius):
                    blocked_by_building = True
                    break
            if blocked_by_building:
                continue
            
            # Score this position based on:
            # 1. Distance to other attacking units (farther is better)
            # 2. Distance to current unit position (closer is better)
            # 3. Line of sight to target
            
            score = 0
            
            # Distance to other attackers (farther is better)
            min_dist_to_attacker = float('inf')
            for other in other_attackers:
                dist = math.sqrt((other.x - pos_x)**2 + (other.y - pos_y)**2)
                min_dist_to_attacker = min(min_dist_to_attacker, dist)
            
            if min_dist_to_attacker < unit.radius * 3:  # Too close to other units
                score -= 100
            else:
                score += min(min_dist_to_attacker, unit.radius * 6)  # Cap the benefit
            
            # Distance to current position (closer is better)
            dist_to_current = math.sqrt((unit.x - pos_x)**2 + (unit.y - pos_y)**2)
            score += max(0, 200 - dist_to_current)  # Prefer closer positions
            
            # Check line of sight to target
            obstacles = (self.game.buildings + 
                        [u for u in self.game.units if u != unit and u != target] + 
                        self.game.resources)
            
            # Create temporary unit at this position to check LOS
            temp_unit = type('TempUnit', (), {
                'x': pos_x, 'y': pos_y, 'radius': unit.radius,
                'has_line_of_sight': unit.has_line_of_sight
            })()
            
            if temp_unit.has_line_of_sight(target, self.game_map, obstacles):
                score += 50  # Bonus for clear LOS
            
            if score > best_score:
                best_score = score
                best_position = (pos_x, pos_y)
        
        return best_position
    
    def evaluate_combat_targets(self, unit):
        """Evaluate potential combat targets for a unit"""
        # Find all enemy units and buildings in range
        potential_targets = []
        
        for other_unit in self.game.units:
            if other_unit.player != unit.player:
                distance = unit.get_distance_to(other_unit)
                if distance <= unit.get_effective_attack_range("search"):
                    potential_targets.append((other_unit, distance))
        
        for building in self.game.buildings:
            if building.player != unit.player:
                distance = unit.get_distance_to(building)
                if distance <= unit.get_effective_attack_range("search"):
                    potential_targets.append((building, distance))
        
        # Sort by distance
        potential_targets.sort(key=lambda x: x[1])
        
        return potential_targets
    
    def handle_combat_engagement(self, unit, target):
        """Handle a unit engaging a target in combat"""
        # Check if target is still valid
        if target.hp <= 0:
            unit.current_target = None
            unit.is_engaging = False
            unit.status = "idle"
            return False
        
        # Check if we can attack
        if unit.can_attack(target):
            # Unit attacking target
            unit.start_attack(target)
            return True
        
        # Need to move closer
        unit.is_engaging = True
        return False
    
    def check_for_attacks_and_spawn_projectiles(self):
        """Check all units and buildings for recent attacks and spawn projectiles"""
        if not self.projectile_system:
            return
            
        # Check all units
        for unit in self.game.units:
            if hasattr(unit, 'in_combat') and unit.in_combat and hasattr(unit, 'last_attack_time'):
                # Check if this is a new attack
                unit_id = id(unit)
                if unit_id not in self.attack_trackers or self.attack_trackers[unit_id] < unit.last_attack_time:
                    # New attack detected!
                    self.attack_trackers[unit_id] = unit.last_attack_time
                    if unit.current_target and unit.current_target.hp > 0:
                        # Calculate damage for the projectile
                        damage = unit.calculate_damage(unit.current_target) if hasattr(unit, 'calculate_damage') else 10
                        self.create_attack_projectile(unit, unit.current_target, damage)
        
        # Check all buildings
        for building in self.game.buildings:
            if hasattr(building, 'can_attack') and building.can_attack and hasattr(building, 'in_combat') and building.in_combat and hasattr(building, 'last_attack_time'):
                # Check if this is a new attack
                building_id = id(building)
                if building_id not in self.attack_trackers or self.attack_trackers[building_id] < building.last_attack_time:
                    # New attack detected!
                    self.attack_trackers[building_id] = building.last_attack_time
                    if building.current_target and building.current_target.hp > 0:
                        # Calculate damage for the projectile
                        damage = building.calculate_damage(building.current_target) if hasattr(building, 'calculate_damage') else 10
                        self.create_attack_projectile(building, building.current_target, damage)
    
    def update_combat_units(self, delta_time):
        """Update all combat-capable units and buildings"""
        # Track damage dealt this frame for notifications
        damage_events = []
        
        # Update units
        for unit in self.game.units:
            if hasattr(unit, 'update_combat'):
                # Hook into combat to capture damage
                old_target_hp = getattr(unit.current_target, 'hp', 0) if unit.current_target else 0
                unit.update_combat(delta_time)
                new_target_hp = getattr(unit.current_target, 'hp', 0) if unit.current_target else 0
                if old_target_hp > new_target_hp and unit.current_target:
                    damage_dealt = old_target_hp - new_target_hp
                    damage_events.append((unit.current_target, damage_dealt))
                
                # Auto-engage nearby enemies if idle
                if unit.status == "idle" and not unit.current_target:
                    from entities.unit import STANCE_NO_ATTACK, STANCE_STAND_GROUND, STANCE_DEFENSIVE
                    
                    if unit.stance == STANCE_NO_ATTACK:
                        pass  # Never auto-attack
                    else:
                        targets = self.evaluate_combat_targets(unit)
                        if targets and getattr(unit.player, 'auto_attack', True):
                            target, distance = targets[0]
                            
                            # Check stance restrictions
                            should_engange = True
                            if unit.stance == STANCE_STAND_GROUND:
                                # Only attack if already in range, never move
                                if not unit.can_attack(target):
                                    should_engange = False
                            elif unit.stance == STANCE_DEFENSIVE:
                                # Only chase within limited distance from home position
                                if unit.stance_home_position:
                                    home_dist = math.sqrt((target.x - unit.stance_home_position[0])**2 + (target.y - unit.stance_home_position[1])**2)
                                    if home_dist > unit.stance_chase_distance:
                                        should_engange = False
                                else:
                                    unit.stance_home_position = (unit.x, unit.y)
                            
                            if should_engange:
                                unit.current_target = target
                                unit.is_engaging = True
                                if DEBUG_MOVEMENT:
                                    # Auto-engaging target
                                    pass
                
                # Handle ongoing engagements
                if unit.is_engaging and unit.current_target:
                    self.handle_combat_engagement(unit, unit.current_target)
        
        # Update defensive buildings (watchtowers, etc.)
        for building in self.game.buildings:
            if hasattr(building, 'can_attack') and building.can_attack:
                # Update building combat
                if hasattr(building, 'update_combat'):
                    old_target_hp = getattr(building.current_target, 'hp', 0) if building.current_target else 0
                    building.update_combat(delta_time)
                    new_target_hp = getattr(building.current_target, 'hp', 0) if building.current_target else 0
                    if old_target_hp > new_target_hp and building.current_target:
                        damage_dealt = old_target_hp - new_target_hp
                        damage_events.append((building.current_target, damage_dealt))
                
                # Auto-target enemies if not already attacking
                if not building.current_target or building.current_target.hp <= 0:
                    # Find enemies in range
                    potential_targets = []
                    
                    # Check enemy units
                    for unit in self.game.units:
                        if unit.player != building.player:
                            distance = ((building.x - unit.x) ** 2 + (building.y - unit.y) ** 2) ** 0.5
                            if distance <= building.attack_range:
                                potential_targets.append((unit, distance))
                    
                    # Check enemy buildings
                    for other_building in self.game.buildings:
                        if other_building.player != building.player:
                            distance = ((building.x - other_building.x) ** 2 + (building.y - other_building.y) ** 2) ** 0.5
                            if distance <= building.attack_range:
                                potential_targets.append((other_building, distance))
                    
                    # Sort by distance and engage closest
                    if potential_targets:
                        potential_targets.sort(key=lambda x: x[1])
                        target, _ = potential_targets[0]
                        building.start_attack(target)
        
        # Spawn damage notifications and particles
        if hasattr(self.game, 'floating_ui') and self.game.floating_ui:
            for target, damage in damage_events:
                self.game.floating_ui.add_damage_notification(target, damage)
                # Spawn attack particles at target position
                if hasattr(self.game, 'particles') and self.game.particles:
                    self.game.particles.spawn_attack_particles(target.x, target.y, count=2)
                # Play hit sound
                if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                    self.game.sound_manager.play_hit()
        
        # Check for new attacks and spawn projectiles
        self.check_for_attacks_and_spawn_projectiles()
    
    def calculate_damage(self, attacker, target):
        """Calculate damage dealt from attacker to target"""
        # Base damage
        base_damage = attacker.get_attack_damage()
        
        # Apply type effectiveness
        effectiveness = self.get_type_effectiveness(attacker.attack_type, target.armor_type)
        
        # Apply armor reduction
        armor_reduction = 1.0 - (target.armor * 0.05)  # 5% reduction per armor point
        armor_reduction = max(0.1, armor_reduction)  # Minimum 10% damage
        
        # Calculate final damage
        final_damage = base_damage * effectiveness * armor_reduction
        
        return int(final_damage)
    
    def get_type_effectiveness(self, attack_type, armor_type):
        """Get damage effectiveness multiplier based on attack and armor types"""
        effectiveness_table = {
            ("slash", "light"): 1.5,
            ("pierce", "heavy"): 1.5,
            ("siege", "fortified"): 2.0,
            ("slash", "heavy"): 0.75,
            ("pierce", "fortified"): 0.5,
            ("siege", "light"): 0.5,
        }
        
        return effectiveness_table.get((attack_type, armor_type), 1.0)
    
    def handle_unit_death(self, unit):
        """Handle cleanup when a unit dies"""
        # Spawn death particles and sound
        if hasattr(self.game, 'particles') and self.game.particles:
            self.game.particles.spawn_death_particles(unit.x, unit.y, count=6)
        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
            self.game.sound_manager.play_death()
        
        # Clear any units targeting this one
        for other_unit in self.game.units:
            if hasattr(other_unit, 'current_target') and other_unit.current_target == unit:
                other_unit.current_target = None
                other_unit.is_engaging = False
                if hasattr(other_unit, 'in_combat'):
                    other_unit.in_combat = False
        
        # Remove from game lists
        if unit in self.game.units:
            self.game.units.remove(unit)
        
        # Award experience to killer if applicable
        if hasattr(unit, 'last_attacker') and unit.last_attacker:
            if hasattr(unit.last_attacker, 'gain_experience'):
                exp_value = getattr(unit, 'exp_value', 10)
                unit.last_attacker.gain_experience(exp_value)
    
    def handle_building_destruction(self, building):
        """Handle cleanup when a building is destroyed"""
        # Spawn death particles and sound
        if hasattr(self.game, 'particles') and self.game.particles:
            count = 12 if building.name == "castle" else 8
            self.game.particles.spawn_death_particles(building.x, building.y, count=count)
        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
            self.game.sound_manager.play_death()
        
        # Screen shake on major building destruction
        if building.name == "castle":
            self.game.camera.add_shake(15.0)
        elif building.name in ("barracks", "watchtower", "stable"):
            self.game.camera.add_shake(5.0)
        
        # Clear any units targeting this building
        for unit in self.game.units:
            if hasattr(unit, 'current_target') and unit.current_target == building:
                unit.current_target = None
                unit.is_engaging = False
                if hasattr(unit, 'in_combat'):
                    unit.in_combat = False
        
        # Remove from game lists
        if building in self.game.buildings:
            self.game.buildings.remove(building)
        
        # Cancel any production queues
        if hasattr(building, 'production_queue'):
            building.production_queue.clear()
    
    def create_attack_projectile(self, attacker, target, damage):
        """Create a projectile for an attack"""
        if self.projectile_system:
            self.projectile_system.create_projectile(attacker, target, damage)
    
    def get_units_in_combat(self):
        """Get all units currently in combat"""
        combat_units = []
        for unit in self.game.units:
            if hasattr(unit, 'in_combat') and unit.in_combat:
                combat_units.append(unit)
            elif hasattr(unit, 'is_engaging') and unit.is_engaging:
                combat_units.append(unit)
        return combat_units
    
    def get_combat_statistics(self, player):
        """Get combat statistics for a player"""
        stats = {
            'units_in_combat': 0,
            'enemies_killed': 0,
            'buildings_destroyed': 0,
            'damage_dealt': 0,
            'damage_taken': 0
        }
        
        for unit in self.game.units:
            if unit.player == player:
                if hasattr(unit, 'in_combat') and unit.in_combat:
                    stats['units_in_combat'] += 1
                if hasattr(unit, 'kills'):
                    stats['enemies_killed'] += unit.kills
                if hasattr(unit, 'damage_dealt'):
                    stats['damage_dealt'] += unit.damage_dealt
                if hasattr(unit, 'damage_taken'):
                    stats['damage_taken'] += unit.damage_taken
        
        return stats