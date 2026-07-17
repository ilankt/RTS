import math
from core.config import DEBUG_MOVEMENT
from entities.unit import STANCE_AGGRESSIVE, STANCE_DEFENSIVE, STANCE_NO_ATTACK, STANCE_STAND_GROUND
from systems.combat_rules import (
    calculate_damage as calculate_combat_damage,
    effective_attack_range,
    has_bonus_against,
    is_building_target,
    is_resisted_by,
    is_valid_attack_target,
    type_effectiveness,
)


class CombatSystem:
    # §8.12 battlefield awareness: how far a unit NOTICES enemies (world px).
    # Acquisition used to be capped at weapon range, so melee units were
    # blind beyond 48 px — even idle armies let enemies stroll past. Stances
    # still gate the response (stand-ground never chases, defensive leashes).
    AGGRO_RANGE = 200
    # §9 blind-march fix: MARCHING aggressive AI units scan wider than idle
    # ones — at 200 px (~3 tiles) armies whose routes ran 250-400 px apart
    # passed each other in mutual blindness (measured). Idle defenders keep
    # the tighter radius so they aren't pulled off their posts.
    MOVE_AGGRO_RANGE = 300

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
    
    def evaluate_combat_targets(self, unit, search_range=None, units_only=False):
        """Evaluate potential combat targets for a unit (spatial-index query).

        units_only skips the static-index sweep for callers that discard
        buildings anyway (the on-the-move §8.12 scan)."""
        potential_targets = []
        if search_range is None:
            search_range = max(unit.get_effective_attack_range("search"), self.AGGRO_RANGE)
        collision = self.game.collision_system

        for other_unit in collision.query_nearby_units(unit.x, unit.y, search_range, exclude=unit):
            if other_unit.player != unit.player and other_unit.hp > 0:
                distance = unit.get_distance_to(other_unit)
                if distance <= search_range and is_valid_attack_target(unit, other_unit):
                    potential_targets.append((other_unit, distance))

        for building in [] if units_only else collision.query_nearby_static(
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

    def _marching_past_gate(self, unit):
        """Should the on-the-move scan be allowed to (re)target this unit?
        Yes when it has no target, is marching on a building, or — §9
        blind-march fix — is chasing a UNIT farther than the scan radius:
        focus-fire squads used to march through enemy armies at 41-156 px
        without retargeting because any unit-target blocked the rescan."""
        target = unit.current_target
        if target is None or is_building_target(target):
            return True
        return ((target.x - unit.x) ** 2 + (target.y - unit.y) ** 2
                > self.MOVE_AGGRO_RANGE ** 2)

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
                    # Counter hits pop emphasized ("N!"), resisted hits gray - §8.4
                    is_counter = has_bonus_against(unit, unit.current_target)
                    resisted = is_resisted_by(unit, unit.current_target)
                    damage_events.append((unit.current_target, damage_dealt, is_counter, resisted))
                    # §8.11: victims remember their attacker (retaliation,
                    # emergency defense) — also makes the kill-XP path live
                    unit.current_target.last_attacker = unit
                    unit.current_target._last_damage_frame = self.game.frame_counter
                    if hasattr(self.game, 'notify_human_combat'):
                        self.game.notify_human_combat(unit, unit.current_target)
                    # §8.5 juice: ram blows rattle the camera a little
                    if unit.name == 'ram' and getattr(self.game, 'camera', None):
                        self.game.camera.add_shake(2.5)
                
                # Auto-engage nearby enemies if idle. Acquisition scans are
                # throttled per unit (~0.25-0.5s, jittered) — C2.
                # can_attack_flag gate (§8.12): workers/healers must never
                # acquire targets — the old weapon-range-sized search only
                # hid that (range 0 found nothing); AGGRO_RANGE would let an
                # idle worker "attack" at attack_speed 0 and divide by zero.
                if (unit.status == "idle" and not unit.current_target
                        and getattr(unit, "can_attack_flag", False)):
                    if unit.stance == STANCE_NO_ATTACK:
                        pass  # Never auto-attack
                    elif (getattr(unit, "flow_slot_target", None) is not None
                            and getattr(unit, "flow_field", None) is None):
                        # §9: parked waiter for a flow-field build — the
                        # player's group move owns this unit for the few
                        # build frames; _attach re-stamps it. Without this,
                        # waiters idle-acquired adjacent enemies and fell
                        # out of the ordered move.
                        pass
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
                
                # §8.11/§8.12 retaliation + battlefield awareness for units
                # ON THE MOVE (the idle block above owns the idle case).
                elif (
                    unit.status == "run"
                    and not unit.in_combat
                    and getattr(unit, "can_attack_flag", False)
                    and unit.stance in (STANCE_AGGRESSIVE, STANCE_DEFENSIVE)
                    # §8.9: retreating units run — they don't turn and fight
                    and self.game.frame_counter >= getattr(unit, "_retreating_until", 0)
                ):
                    engaged = False
                    # (1) Hit while moving -> turn on the attacker (§8.11)
                    if getattr(unit, "_last_damage_frame", -1_000_000) >= self.game.frame_counter - 45:
                        attacker = getattr(unit, "last_attacker", None)
                        if (
                            attacker is not None
                            and getattr(attacker, "hp", 0) > 0
                            and getattr(attacker, "in_world", True)
                            and unit.current_target is not attacker
                            # rams only ever answer buildings (can't hit units)
                            and not (getattr(unit, "building_only_attack", False)
                                     and not is_building_target(attacker))
                        ):
                            dist_sq = (attacker.x - unit.x) ** 2 + (attacker.y - unit.y) ** 2
                            if dist_sq <= unit.stance_chase_distance ** 2:
                                unit.divert_to_target(attacker)
                                engaged = True
                    # (2) §8.12 battlefield awareness: AI units on the move
                    # engage enemy UNITS that come within reach — armies no
                    # longer pass each other blindly. Human orders stay
                    # literal (nobody wants hijacked move commands), and
                    # marches don't get distracted by mere buildings.
                    if (
                        not engaged
                        and unit.stance == STANCE_AGGRESSIVE
                        and not getattr(unit.player, "human", True)
                        and not getattr(unit, "building_only_attack", False)
                        # frame throttle BEFORE the gate helper — this chain
                        # runs per frame per marching unit; the helper does
                        # attribute loads + a distance compute
                        and self.game.frame_counter >= getattr(unit, "_next_target_scan_frame", 0)
                        and self._marching_past_gate(unit)
                    ):
                        unit._next_target_scan_frame = self.game.frame_counter + 15 + (id(unit) % 16)
                        for target, _distance in self.evaluate_combat_targets(
                                unit, self.MOVE_AGGRO_RANGE, units_only=True):
                            unit.divert_to_target(target)
                            break  # nearest unit decides

                # §8.12 no tunnel vision: a unit hammering a BUILDING while a
                # live enemy UNIT hits it switches to the guard — the building
                # can wait; dying to the last man against masonry cannot.
                # Rams keep ramming (their escorts handle the guards).
                elif (
                    unit.in_combat
                    and unit.current_target is not None
                    and is_building_target(unit.current_target)
                    and getattr(unit, "can_attack_flag", False)
                    and not getattr(unit, "building_only_attack", False)
                    and unit.stance != STANCE_NO_ATTACK
                    and getattr(unit, "_last_damage_frame", -1_000_000)
                        >= self.game.frame_counter - 45
                ):
                    attacker = getattr(unit, "last_attacker", None)
                    if (
                        attacker is not None
                        and getattr(attacker, "hp", 0) > 0
                        and getattr(attacker, "in_world", True)
                        and not is_building_target(attacker)
                    ):
                        dist_sq = (attacker.x - unit.x) ** 2 + (attacker.y - unit.y) ** 2
                        if dist_sq <= unit.stance_chase_distance ** 2:
                            unit.current_target = attacker
                            unit.in_combat = False
                            unit.is_engaging = True

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
                        # §9: retaliation reads _retreating_until, not the scan
                        # frame — with only the scan gate, a unit under fire at
                        # the leash boundary re-acquired its attacker every
                        # frame and dithered in place forever (measured: 918
                        # walk-home orders in 30 s from one unit).
                        frame = self.game.frame_counter
                        unit._next_target_scan_frame = frame + 60
                        unit._retreating_until = max(getattr(unit, "_retreating_until", 0), frame + 60)

                # Handle ongoing engagements
                if unit.is_engaging and unit.current_target:
                    self.handle_combat_engagement(unit, unit.current_target)

                # Healers mend the most-wounded nearby ally (§9)
                if unit.name == "healer":
                    self._update_healer(unit, delta_time)
        
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
                        damage_events.append((
                            building.current_target,
                            damage_dealt,
                            has_bonus_against(building, building.current_target),
                            is_resisted_by(building, building.current_target),
                        ))
                        building.current_target.last_attacker = building
                        building.current_target._last_damage_frame = self.game.frame_counter
                        if hasattr(self.game, 'notify_human_combat'):
                            self.game.notify_human_combat(building, building.current_target)
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
                        potential_targets = []
                        collision = self.game.collision_system

                        # Check enemy units (reach = range + target radius,
                        # matching can_attack_target — an archer plinking
                        # from max reach must be acquirable)
                        for unit in collision.query_nearby_units(building.x, building.y, attack_range + 24):
                            if unit.player != building.player and unit.hp > 0:
                                dist_sq = (building.x - unit.x) ** 2 + (building.y - unit.y) ** 2
                                reach = attack_range + getattr(unit, 'radius', 0)
                                if dist_sq <= reach * reach:
                                    potential_targets.append((unit, dist_sq))

                        # Check enemy buildings
                        for other_building in collision.query_nearby_static(
                            building.x,
                            building.y,
                            attack_range + 96,
                            include_construction_sites=False,
                            include_resources=False,
                        ):
                            if other_building.player != building.player and other_building.hp > 0:
                                dist_sq = (building.x - other_building.x) ** 2 + (building.y - other_building.y) ** 2
                                reach = attack_range + getattr(other_building, 'radius', 0)
                                if dist_sq <= reach * reach:
                                    potential_targets.append((other_building, dist_sq))

                        # Sort by distance and engage closest
                        if potential_targets:
                            potential_targets.sort(key=lambda x: x[1])
                            target, _ = potential_targets[0]
                            building.start_attack(target)
        
        # Spawn damage notifications and particles
        if hasattr(self.game, 'floating_ui') and self.game.floating_ui:
            for target, damage, is_counter, is_resisted in damage_events:
                self.game.floating_ui.add_damage_notification(
                    target, damage, is_critical=is_counter, is_resisted=is_resisted
                )
                # Spawn attack particles at target position
                if hasattr(self.game, 'particles') and self.game.particles:
                    self.game.particles.spawn_attack_particles(target.x, target.y, count=2)
                # Play hit sound
                if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
                    self.game.sound_manager.play_hit()

        # Under-attack alert for the human player (§7.4): sound + minimap ping,
        # rate-limited so a battle doesn't spam.
        for target, _damage, _is_counter, _is_resisted in damage_events:
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
            if getattr(self.game, 'ui_manager', None):
                self.game.ui_manager.add_alert("Under attack!", (target.x, target.y))
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
    
    def _unit_max_hp(self, unit):
        template = self.game.game_data["units"].get(unit.name) if hasattr(self.game, "game_data") else None
        return template.hp if template else unit.hp

    def _update_healer(self, healer, delta_time):
        """Heal the most-wounded friendly unit in range (game-time cadence)."""
        from core.config import HEALER_HEAL_AMOUNT, HEALER_HEAL_INTERVAL, HEALER_HEAL_RANGE

        healer._heal_cooldown = getattr(healer, "_heal_cooldown", 0.0) - delta_time
        if healer._heal_cooldown > 0:
            return

        range_sq = HEALER_HEAL_RANGE * HEALER_HEAL_RANGE
        best = None
        best_missing = 0
        for ally in self.game.collision_system.query_nearby_units(healer.x, healer.y, HEALER_HEAL_RANGE, exclude=healer):
            if ally.player is not healer.player or ally.hp <= 0:
                continue
            if (ally.x - healer.x) ** 2 + (ally.y - healer.y) ** 2 > range_sq:
                continue
            missing = self._unit_max_hp(ally) - ally.hp
            if missing > best_missing:
                best_missing = missing
                best = ally

        if best is not None:
            healed = min(self._unit_max_hp(best), best.hp + HEALER_HEAL_AMOUNT) - best.hp
            best.hp += healed
            healer._heal_cooldown = HEALER_HEAL_INTERVAL
            healer.status = "attack"  # plays the healer's cast animation
            if getattr(self.game, "particles", None):
                self.game.particles.spawn_attack_particles(best.x, best.y, count=1)
            # §7.4 readability: green "+N" float so heals are legible
            if getattr(self.game, "floating_ui", None):
                self.game.floating_ui.add_heal_notification(best, healed)
        elif healer.status == "attack" and not healer.in_combat:
            # No one to heal: drop the cast pose or the healer sits in its
            # attack animation forever (§8.11 frozen-animation family)
            healer.status = "idle"
        # (no target in range: cooldown stays expired so the next tick can heal)

    def handle_unit_death(self, unit):
        """Handle cleanup when a unit dies"""
        # Spawn death particles and sound
        if hasattr(self.game, 'particles') and self.game.particles:
            self.game.particles.spawn_death_particles(unit.x, unit.y, count=6)
        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
            self.game.sound_manager.play_death()
        # §8.5 death fade: the unit's last frame ghosts out in place
        renderer = getattr(self.game, 'rendering_system', None)
        if renderer is not None and hasattr(unit, 'get_current_sprite'):
            try:
                renderer.add_death_fade(unit, unit.get_current_sprite())
            except Exception:
                pass
        
        # Clear any units targeting this one. Also reset status: units left
        # in status="attack"/"run" with no target froze in their attack
        # animation forever AND stopped acquiring targets (the auto-engage
        # gate requires status=="idle") — user-reported §8.11.
        for other_unit in self.game.units:
            if hasattr(other_unit, 'current_target') and other_unit.current_target == unit:
                other_unit.current_target = None
                other_unit.is_engaging = False
                if hasattr(other_unit, 'in_combat'):
                    other_unit.in_combat = False
                if other_unit.status in ("attack", "run") and not getattr(other_unit, 'destination', None):
                    other_unit.status = "idle"

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
        # §8.9 garrison: survivors are ejected unharmed before the rubble
        if getattr(building, "garrison", None):
            from systems import garrison
            garrison.eject_all(self.game, building)
        # Spawn death particles and sound
        if hasattr(self.game, 'particles') and self.game.particles:
            count = 12 if building.name == "castle" else 8
            self.game.particles.spawn_death_particles(building.x, building.y, count=count)
        if hasattr(self.game, 'sound_manager') and self.game.sound_manager:
            self.game.sound_manager.play_death()
        # §8.5 death fade for the building sprite
        renderer = getattr(self.game, 'rendering_system', None)
        if renderer is not None:
            try:
                player_index = self.game.players.index(building.player)
                sprite = renderer.sprite_manager.get_building_sprite(building.name, player_index)
                renderer.add_death_fade(building, sprite)
            except Exception:
                pass
        
        # Screen shake on major building destruction
        if building.name == "castle":
            self.game.camera.add_shake(15.0)
        elif building.name in ("barracks", "watchtower", "stable"):
            self.game.camera.add_shake(5.0)
        
        # Clear any units targeting this building (incl. the frozen-attack-
        # animation reset — see handle_unit_death)
        for unit in self.game.units:
            if hasattr(unit, 'current_target') and unit.current_target == building:
                unit.current_target = None
                unit.is_engaging = False
                if hasattr(unit, 'in_combat'):
                    unit.in_combat = False
                if unit.status in ("attack", "run") and not getattr(unit, 'destination', None):
                    unit.status = "idle"
        
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
            # §8.5 muzzle flash where ranged shots leave the attacker
            if (getattr(self.game, 'particles', None)
                    and getattr(attacker, 'name', None) in ("archer", "watchtower")):
                self.game.particles.spawn_muzzle_flash(attacker.x, attacker.y - 12)
    
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
