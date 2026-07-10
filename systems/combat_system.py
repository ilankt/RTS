import math
from core.config import DEBUG_MOVEMENT
from entities.unit import STANCE_DEFENSIVE, STANCE_NO_ATTACK, STANCE_STAND_GROUND
from systems.combat_rules import (
    calculate_damage as calculate_combat_damage,
    effective_attack_range,
    has_bonus_against,
    is_valid_attack_target,
    type_effectiveness,
)


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

        terrain_probe = getattr(self.game_map, "nav_terrain_walkable", None)
        # One spatial query around the target covers every candidate position.
        nearby_buildings = self.game.collision_system.query_nearby_static(
            target_x,
            target_y,
            attack_range + unit.radius + 8,
            include_construction_sites=False,
            include_resources=False,
        )

        # Generate potential attack positions in a circle around the target
        num_positions = 8  # Check 8 positions around the target
        best_position = None
        best_score = float('-inf')

        for i in range(num_positions):
            angle = (i / num_positions) * 2 * math.pi
            pos_x = target_x + math.cos(angle) * attack_range
            pos_y = target_y + math.sin(angle) * attack_range

            # Check if position is valid (not in water/lava, not blocked by buildings)
            if terrain_probe is not None:
                if not terrain_probe(pos_x, pos_y):
                    continue
            else:
                hex_coord = self.game_map.world_to_grid(pos_x, pos_y)
                if not hex_coord:
                    continue
                col, row = hex_coord
                if row < 0 or row >= self.game_map.height or col < 0 or col >= self.game_map.width:
                    continue
                if self.game_map.grid[row][col] in {"water", "lava"}:
                    continue

            # Check for collision with buildings
            blocked_by_building = False
            for building in nearby_buildings:
                min_dist = building.radius + unit.radius
                if (building.x - pos_x) ** 2 + (building.y - pos_y) ** 2 < min_dist * min_dist:
                    blocked_by_building = True
                    break
            if blocked_by_building:
                continue

            # Score this position based on:
            # 1. Distance to other attacking units (farther is better)
            # 2. Distance to current unit position (closer is better)

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

            if score > best_score:
                best_score = score
                best_position = (pos_x, pos_y)

        return best_position
    
    def evaluate_combat_targets(self, unit):
        """Evaluate potential combat targets for a unit (spatial-index query)"""
        potential_targets = []
        search_range = unit.get_effective_attack_range("search")
        collision = self.game.collision_system

        for other_unit in collision.query_nearby_units(unit.x, unit.y, search_range, exclude=unit):
            if other_unit.player != unit.player and other_unit.hp > 0:
                distance = unit.get_distance_to(other_unit)
                if distance <= search_range and is_valid_attack_target(unit, other_unit):
                    potential_targets.append((other_unit, distance))

        for building in collision.query_nearby_static(
            unit.x, unit.y, search_range, include_construction_sites=False, include_resources=False
        ):
            if building.player != unit.player and building.hp > 0:
                distance = unit.get_distance_to(building)
                if distance <= search_range and is_valid_attack_target(unit, building):
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
                    # Counter hits pop emphasized ("N!") - §8.4 legibility
                    is_counter = has_bonus_against(unit, unit.current_target)
                    damage_events.append((unit.current_target, damage_dealt, is_counter))
                
                # Auto-engage nearby enemies if idle. Acquisition scans are
                # throttled per unit (~0.25-0.5s, jittered) — C2.
                if unit.status == "idle" and not unit.current_target:
                    if unit.stance == STANCE_NO_ATTACK:
                        pass  # Never auto-attack
                    elif self.game.frame_counter < getattr(unit, "_next_target_scan_frame", 0):
                        pass  # Recently scanned and found nothing
                    else:
                        unit._next_target_scan_frame = self.game.frame_counter + 15 + (id(unit) % 16)
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
                
                # Defensive leash (§9 backlog fix): a DEFENSIVE unit that chased
                # its target beyond stance_chase_distance drops the chase and
                # walks back to its home position instead of freezing in the
                # field wherever the pursuit ended.
                if (
                    unit.stance == STANCE_DEFENSIVE
                    and unit.stance_home_position
                    and (unit.is_engaging or unit.in_combat)
                ):
                    home_x, home_y = unit.stance_home_position
                    leash = unit.stance_chase_distance
                    if (unit.x - home_x) ** 2 + (unit.y - home_y) ** 2 > leash * leash:
                        self.game.pathfinder.issue_move(unit, unit.stance_home_position)
                        # Suppress instant re-acquisition so the walk home wins.
                        unit._next_target_scan_frame = self.game.frame_counter + 60

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
                        damage_events.append(
                            (building.current_target, damage_dealt, has_bonus_against(building, building.current_target))
                        )
                        # §8.10 tower-value metric for the balance sim
                        if building.name == "watchtower" and building.player:
                            stats = getattr(self.game, "stats_tower_damage", None)
                            if stats is not None:
                                name = building.player.name
                                stats[name] = stats.get(name, 0) + damage_dealt
                
                # Auto-target enemies if not already attacking. Re-scan is
                # throttled per building (~0.25-0.5s, jittered) — C2.
                if not building.current_target or building.current_target.hp <= 0:
                    frame = self.game.frame_counter
                    next_scan = getattr(building, "_next_target_scan_frame", 0)
                    if frame >= next_scan:
                        building._next_target_scan_frame = frame + 15 + (id(building) % 16)
                        attack_range = effective_attack_range(building)
                        range_sq = attack_range * attack_range
                        potential_targets = []
                        collision = self.game.collision_system

                        # Check enemy units
                        for unit in collision.query_nearby_units(building.x, building.y, attack_range):
                            if unit.player != building.player and unit.hp > 0:
                                dist_sq = (building.x - unit.x) ** 2 + (building.y - unit.y) ** 2
                                if dist_sq <= range_sq:
                                    potential_targets.append((unit, dist_sq))

                        # Check enemy buildings
                        for other_building in collision.query_nearby_static(
                            building.x,
                            building.y,
                            attack_range,
                            include_construction_sites=False,
                            include_resources=False,
                        ):
                            if other_building.player != building.player and other_building.hp > 0:
                                dist_sq = (building.x - other_building.x) ** 2 + (building.y - other_building.y) ** 2
                                if dist_sq <= range_sq:
                                    potential_targets.append((other_building, dist_sq))

                        # Sort by distance and engage closest
                        if potential_targets:
                            potential_targets.sort(key=lambda x: x[1])
                            target, _ = potential_targets[0]
                            building.start_attack(target)
        
        # Spawn damage notifications and particles
        if hasattr(self.game, 'floating_ui') and self.game.floating_ui:
            for target, damage, is_counter in damage_events:
                self.game.floating_ui.add_damage_notification(target, damage, is_critical=is_counter)
                # Spawn attack particles at target position
                if hasattr(self.game, 'particles') and self.game.particles:
                    self.game.particles.spawn_attack_particles(target.x, target.y, count=2)
                # Play hit sound
                if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                    self.game.sound_manager.play_hit()

        # Under-attack alert for the human player (§7.4): sound + minimap ping,
        # rate-limited so a battle doesn't spam.
        for target, _damage, _is_counter in damage_events:
            player = getattr(target, 'player', None)
            if player is None or not getattr(player, 'human', False):
                continue
            import pygame as _pygame

            now = _pygame.time.get_ticks()
            if now - getattr(self, '_last_under_attack_alert', -99999) < 10000:
                break
            self._last_under_attack_alert = now
            if getattr(self.game, 'sound_manager', None):
                self.game.sound_manager.play_alert()
            if getattr(self.game, 'minimap', None):
                self.game.minimap.add_ping(target.x, target.y)
            break
        
        # Check for new attacks and spawn projectiles
        self.check_for_attacks_and_spawn_projectiles()
    
    def calculate_damage(self, attacker, target):
        """Calculate damage dealt from attacker to target"""
        # Base damage
        return calculate_combat_damage(attacker, target)
    
    def get_type_effectiveness(self, attack_type, armor_type):
        """Get damage effectiveness multiplier based on attack and armor types"""
        return type_effectiveness(attack_type, armor_type)
    
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
        unit.in_world = False
        if unit in self.game.units:
            self.game.units.remove(unit)
        # Drop the attack tracker so id() reuse can't suppress a new unit's first shot
        self.attack_trackers.pop(id(unit), None)

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
        building.in_world = False
        if building in self.game.buildings:
            self.game.buildings.remove(building)
        self.attack_trackers.pop(id(building), None)

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
