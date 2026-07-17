import math
import pygame
from systems.gathering_manager import get_gathering_distance, get_drop_off_distance
from core.config import DEBUG_MOVEMENT
from utils.debug_logger import debug_log
from utils.perf_stats import perf_stats


NUM_STEER_SLOTS = 16
STEER_SLOT_DIRS = tuple(
    (math.cos(2 * math.pi * i / NUM_STEER_SLOTS), math.sin(2 * math.pi * i / NUM_STEER_SLOTS))
    for i in range(NUM_STEER_SLOTS)
)


class MovementSystem:
    """Handles all unit movement, pathfinding, and navigation logic"""

    # Arrival behavior (B3): decelerate inside this radius of the final
    # destination and never step past it - removes overshoot/oscillation.
    ARRIVAL_SLOWING_RADIUS = 40.0
    ARRIVAL_MIN_SPEED_FACTOR = 0.4

    # Context steering (B1/B4): don't steer in the last stretch - the arrival
    # logic and right-of-way handle close-range resolution.
    STEER_MIN_GOAL_DISTANCE = 24.0

    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        
    def update_unit_movement(self, unit, delta_time):
        """Main movement update for a single unit"""
        # Update animation with delta_time
        unit.update_animation(delta_time)
        worker_task_system = getattr(self.game, "worker_task_system", None)
        worker_task_owned = bool(worker_task_system and worker_task_system.owns(unit))
        
        # Update combat if applicable
        if hasattr(unit, 'update_combat'):
            unit.update_combat(delta_time)
            self._handle_combat_movement(unit)
        
        # Flow-field followers: shared field until the personal-slot handoff
        if getattr(unit, "flow_field", None) is not None:
            self._follow_flow_field(unit, delta_time)
            return

        # Handle target checking during movement
        if (not worker_task_owned and
                (unit.path or unit.destination or unit.is_dropping_off or
                (hasattr(unit, 'building_target') and unit.building_target) or
                (hasattr(unit, 'gathering_target') and unit.gathering_target) or
                (hasattr(unit, 'drop_off_target') and unit.drop_off_target))):
            self._check_movement_targets(unit, delta_time)
        
        # Handle path following
        if unit.path and unit.path_index < len(unit.path):
            self._follow_path(unit, delta_time)
        elif unit.destination and not unit.path:
            self._move_direct(unit, delta_time)
        
        
    
    def _handle_combat_movement(self, unit):
        """Handle movement for combat units engaging targets"""
        # Auto-attack when reaching target during movement
        if unit.current_target and not unit.in_combat and unit.status == "run":
            if unit.can_attack(unit.current_target):
                unit.start_attack(unit.current_target)
        
        # Handle engaging state - continuously track and pursue target
        if unit.is_engaging and unit.current_target:
            # Check if target still exists and is valid
            if unit.current_target.hp <= 0:
                unit.current_target = None
                unit.is_engaging = False
                unit.status = "idle"
                return
            
            # Handle combat units attacking
            if unit.current_target and unit.can_attack(unit.current_target):
                unit.start_attack(unit.current_target)
                return
            
            # Re-evaluate movement strategy
            self._evaluate_combat_movement_strategy(unit)
    
    def _evaluate_combat_movement_strategy(self, unit):
        """Evaluate and update combat movement strategy"""
        # For gathering workers, use simpler logic
        if (unit.name == "worker" and hasattr(unit, 'gathering_target') and 
            unit.gathering_target and unit.is_engaging):
            # Don't apply complex combat movement to gathering workers
            return
            
        # Initialize unified stuck detection if needed
        if not hasattr(unit, '_stuck_detector'):
            unit._stuck_detector = {
                'last_position': (unit.x, unit.y),
                'stuck_timer': 0,
                'check_interval': 30,  # Check every 0.5 seconds
                'frames_since_check': 0,
                'strategy_timer': 0
            }
        
        detector = unit._stuck_detector
        detector['frames_since_check'] += 1
        detector['strategy_timer'] += 1
        
        # Periodic stuck check
        if detector['frames_since_check'] >= detector['check_interval']:
            # Calculate movement since last check
            movement = math.sqrt(
                (unit.x - detector['last_position'][0])**2 + 
                (unit.y - detector['last_position'][1])**2
            )
            
            # Expected movement in this time period
            expected_movement = unit.movement_speed * (detector['check_interval'] / 60.0)
            
            # If moved less than 25% of expected, increment stuck timer
            if movement < expected_movement * 0.25:
                detector['stuck_timer'] += detector['check_interval']
            else:
                # Reduce stuck timer if making progress
                detector['stuck_timer'] = max(0, detector['stuck_timer'] - detector['check_interval'] // 2)
            
            detector['last_position'] = (unit.x, unit.y)
            detector['frames_since_check'] = 0
        
        # Determine stuck state
        is_stuck = detector['stuck_timer'] >= 60  # 1 second
        is_very_stuck = detector['stuck_timer'] >= 120  # 2 seconds
        is_strategy_timeout = detector['strategy_timer'] >= 300  # 5 seconds
        
        # Handle stuck conditions
        if is_stuck and unit.path and not is_very_stuck:
            # Try path adjustment first
            if self._adjust_stuck_unit_path(unit):
                detector['stuck_timer'] = max(0, detector['stuck_timer'] - 30)
                return
        
        # Re-evaluate strategy if needed
        force_change = is_very_stuck or is_strategy_timeout
        should_reevaluate = self._should_reevaluate_strategy(unit, force_change)
        
        if should_reevaluate:
            self._reevaluate_movement_strategy(unit, force_change)
            # Reset timers on strategy change
            if force_change:
                detector['stuck_timer'] = 0
                detector['strategy_timer'] = 0
    
    def _should_reevaluate_strategy(self, unit, force_strategy_change):
        """Determine if movement strategy should be re-evaluated"""
        # Clear repath flags
        if hasattr(unit, '_needs_repath'):
            needs_repath = unit._needs_repath
            unit._needs_repath = False
            if needs_repath:
                return True
        
        # Target moved significantly
        if unit.path_target and unit.current_target:
            if (abs(unit.path_target[0] - unit.current_target.x) > 60 or 
                abs(unit.path_target[1] - unit.current_target.y) > 60):
                return True
        
        # No path or destination
        if not unit.destination and not unit.path:
            return True
        
        # Idle with no path
        if unit.status == "idle" and unit.is_engaging and not unit.path:
            return True
        
        # Periodic check when stuck
        if (self.game.frame_counter % 300 == 0 and force_strategy_change and unit.path):
            return True
        
        return False
    
    LOS_CACHE_FRAMES = 8  # combat LOS re-checked at most every N frames per unit

    def _cached_los(self, unit, target):
        """has_line_of_sight with a short-lived per-unit cache (profiler: LOS
        sampling dominates war-scale frames when re-checked every frame)."""
        frame = self.game.frame_counter
        cached = getattr(unit, "_los_cache", None)
        if cached is not None:
            cached_frame, cached_target_id, cached_result = cached
            if cached_target_id == id(target) and frame - cached_frame < self.LOS_CACHE_FRAMES:
                return cached_result
        obstacles = self.game.collision_system.query_obstacles_along(
            (unit.x, unit.y), (target.x, target.y)
        )
        result = unit.has_line_of_sight(target, self.game_map, obstacles)
        unit._los_cache = (frame, id(target), result)
        return result

    def _reevaluate_movement_strategy(self, unit, force_strategy_change):
        """Re-evaluate and update movement strategy"""
        # Check line of sight (obstacles from the shared spatial index)
        has_los = self._cached_los(unit, unit.current_target)
        
        # Debug output
        if not hasattr(unit, '_last_strategy_state'):
            unit._last_strategy_state = None
            unit._stuck_counter = 0
        
        detector = unit._stuck_detector if hasattr(unit, '_stuck_detector') else {'stuck_timer': 0, 'strategy_timer': 0}
        current_strategy = "LOS" if has_los else ("FALLBACK" if getattr(unit, 'is_fallback_movement', False) else "PATH")
        current_state = f"{current_strategy}_{unit.status}_{unit.path is not None}_{unit.destination is not None}"
        
        debug_this_eval = False
        if unit._last_strategy_state != current_state:
            debug_this_eval = True
            unit._last_strategy_state = current_state
            unit._stuck_counter = 0
            detector['strategy_timer'] = 0
        elif force_strategy_change:
            unit._stuck_counter += 1
            if unit._stuck_counter >= 60:
                debug_this_eval = DEBUG_MOVEMENT
        
        # Strategy 1: Line of sight available
        if has_los and not detector['strategy_timer'] >= 300:  # Avoid LOS if timed out
            self._use_los_strategy(unit, debug_this_eval)
        # Strategy 2: No LOS - use pathfinding
        else:
            self._use_pathfinding_strategy(unit, force_strategy_change, debug_this_eval)
        
        # Update destination for moving targets
        if (unit.has_los or unit.is_fallback_movement) and unit.destination:
            unit.destination = (unit.current_target.x, unit.current_target.y)
    
    def _use_los_strategy(self, unit, debug_this_eval):
        """Use line of sight movement strategy"""
        # Check if unit has been stuck with LOS for too long - re-evaluate LOS
        if (unit.has_los and hasattr(unit, '_stuck_detector') and 
            unit._stuck_detector['stuck_timer'] >= 60):  # 1 second of being stuck
            
            # Re-check LOS to see if it's still valid
            current_los = self._cached_los(unit, unit.current_target)
            
            if not current_los:
                # Force pathfinding strategy
                self._use_pathfinding_strategy(unit, True, debug_this_eval)
                return
        
        # Check for multiple units attacking same target (only nearby attackers
        # matter for positioning; query the shared index instead of all units)
        target = unit.current_target
        attacking_same_target = [
            u
            for u in self.game.collision_system.query_nearby_units(target.x, target.y, 300, exclude=unit)
            if u.current_target == target and u.is_engaging
        ]
        
        if len(attacking_same_target) >= 2:
            # Multi-unit attack positioning
            optimal_position = self.game._find_optimal_attack_position(unit, unit.current_target, attacking_same_target)
            
            if optimal_position:
                unit.destination = optimal_position
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.has_los = True
                unit.is_fallback_movement = False
                return
        
        # Single unit attack
        if unit.status != "idle" or not hasattr(unit, '_blocked_by_collision'):
            if not unit.has_los:  # Switching to LOS
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
            unit.destination = (unit.current_target.x, unit.current_target.y)
            unit.has_los = True
            unit.is_fallback_movement = False
    
    def _use_pathfinding_strategy(self, unit, force_strategy_change, debug_this_eval):
        """Use pathfinding movement strategy"""
        # Don't interrupt existing working paths
        if unit.path and not force_strategy_change:
            return
        
        pathfinder = self.game.pathfinder
        path = None

        if unit.current_target and pathfinder.issue_interact(unit, unit.current_target, "attack"):
            return
        
        # Option 1: Direct to target
        path = pathfinder.find_path((unit.x, unit.y), 
                                  (unit.current_target.x, unit.current_target.y), 
                                  unit.radius, unit)
        
        if path:
            unit.path = path
            unit.path_index = 0
            unit.path_target = (unit.current_target.x, unit.current_target.y)
            unit.destination = path[0]
            unit.has_los = False
            unit.is_fallback_movement = False
            return
        
        # Option 2: Approach to attack range
        distance = unit.get_distance_to(unit.current_target)
        if distance > unit.get_effective_attack_range("exact"):
            approach_distance = unit.get_effective_attack_range("approach")
            dx = unit.current_target.x - unit.x
            dy = unit.current_target.y - unit.y
            target_x = unit.current_target.x - (dx / distance) * approach_distance
            target_y = unit.current_target.y - (dy / distance) * approach_distance
            
            path = pathfinder.find_path((unit.x, unit.y), (target_x, target_y), unit.radius, unit)
            if path:
                unit.path = path
                unit.path_index = 0
                unit.path_target = (target_x, target_y)
                unit.destination = path[0]
                unit.has_los = False
                unit.is_fallback_movement = False
                return
        
        # Option 3: Fallback to direct movement
        unit.destination = (unit.current_target.x, unit.current_target.y)
        unit.path = None
        unit.path_index = 0
        unit.path_target = None
        unit.status = "run"
        unit.has_los = False
        unit.is_fallback_movement = True
    
    def _check_movement_targets(self, unit, delta_time):
        """Check if unit has reached various movement targets"""
        # Check building target
        if (hasattr(unit, 'building_target') and unit.building_target and not unit.is_building):
            build_distance = math.sqrt((unit.x - unit.building_target.x)**2 +
                                     (unit.y - unit.building_target.y)**2)
            if hasattr(self.game, "pathfinder"):
                required_distance = self.game.pathfinder.get_interaction_distance(
                    unit, unit.building_target, "build"
                )
            else:
                required_distance = unit.radius + unit.building_target.radius + 4

            # Add tolerance for stuck units
            if hasattr(unit, '_stuck_detector') and unit._stuck_detector.get('stuck_timer', 0) >= 60:
                tolerance = unit.get_target_tolerance("movement")
                required_distance += tolerance

            # Recovery: worker has building_target but no movement
            if not unit.path and not unit.destination and unit.status == "idle":
                if build_distance > required_distance + 5:
                    debug_log.log("Recovery: Re-pathing worker to construction site", "CONSTRUCTION")
                    self.game.pathfinder.issue_interact(unit, unit.building_target, "build")

            # Check if worker is close enough to start building
            if build_distance <= required_distance + 8:
                debug_log.log(f"Worker reached construction site at dist {build_distance:.0f}", "CONSTRUCTION")

                # Clear movement, start building
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                unit.is_building = True
                unit.status = "build"

                # Link worker to construction site
                if hasattr(unit.building_target, 'builder'):
                    unit.building_target.builder = unit

                # Clear conflicting states
                unit.is_gathering = False
                unit.gathering_target = None
                unit.is_dropping_off = False
                unit.drop_off_target = None
                unit.current_target = None
                unit.is_engaging = False
        
        # Check drop-off target
        elif (hasattr(unit, 'drop_off_target') and unit.drop_off_target and 
              (unit.resource_amount > 0 or unit.is_dropping_off)):
            
            drop_distance = math.sqrt((unit.x - unit.drop_off_target.x)**2 + 
                                    (unit.y - unit.drop_off_target.y)**2)
            required_distance = get_drop_off_distance(unit, unit.drop_off_target)
            
            # Add tolerance for stuck units
            if hasattr(unit, '_stuck_detector') and unit._stuck_detector['stuck_timer'] >= 60:
                tolerance = unit.get_target_tolerance("movement")
                required_distance += tolerance
            
            # Check if reached destination
            reached_destination = False
            if unit.path_target:
                dest_distance = math.sqrt((unit.x - unit.path_target[0])**2 + 
                                        (unit.y - unit.path_target[1])**2)
                dest_tolerance = 15
                if hasattr(unit, '_stuck_detector') and unit._stuck_detector['stuck_timer'] >= 60:
                    dest_tolerance = unit.get_target_tolerance("movement")
                reached_destination = dest_distance <= dest_tolerance
            
            interaction_tolerance = max(24, unit.radius * 6)
            if drop_distance <= required_distance + interaction_tolerance or unit.is_dropping_off or reached_destination:
                # Drop off resources
                pass
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                
                building_x = unit.drop_off_target.x  # Store building position before it's cleared
                building_y = unit.drop_off_target.y
                if self.game.gathering_manager.drop_off_resources(unit, unit.drop_off_target, delta_time):
                    # Move away from building
                    if hasattr(unit, 'gathering_target') and unit.gathering_target:
                        self.game.pathfinder.issue_interact(unit, unit.gathering_target, "gather")
                    else:
                        away_x = unit.x + (unit.x - building_x) * 0.5
                        away_y = unit.y + (unit.y - building_y) * 0.5
                        unit.destination = (away_x, away_y)
                        unit.status = "run"
                return
            elif not unit.path and not unit.destination and not unit.is_dropping_off:
                self.game.pathfinder.issue_interact(unit, unit.drop_off_target, "dropoff")
                return
        
        # Check gathering target
        elif (unit.name == "worker" and hasattr(unit, 'gathering_target') and 
              unit.gathering_target):
            
            target_distance = math.sqrt((unit.x - unit.gathering_target.x)**2 + 
                                      (unit.y - unit.gathering_target.y)**2)
            gathering_distance = get_gathering_distance(unit, unit.gathering_target)
            
            # Track stuck state for gathering workers
            if not hasattr(unit, '_gathering_stuck_timer'):
                unit._gathering_stuck_timer = 0
                unit._last_gathering_distance = target_distance
            
            # Check if worker is making progress
            distance_change = abs(unit._last_gathering_distance - target_distance)
            if unit.is_gathering and distance_change < 0.1:  # Not moving while gathering
                unit._gathering_stuck_timer += delta_time
            else:
                unit._gathering_stuck_timer = 0
            unit._last_gathering_distance = target_distance
            
            # Check if worker is overlapping with resource (stuck inside)
            if target_distance < unit.radius + unit.gathering_target.radius:
                debug_log.log(f"WARNING: Worker overlapping with resource! Distance: {target_distance:.1f}, Min safe: {unit.radius + unit.gathering_target.radius:.1f}", "MOVEMENT")
                # Push worker to proper gathering distance
                if target_distance > 0:
                    push_x = (unit.x - unit.gathering_target.x) / target_distance
                    push_y = (unit.y - unit.gathering_target.y) / target_distance
                else:
                    # If exactly on center, push in random direction
                    import random
                    angle = random.random() * 2 * math.pi
                    push_x = math.cos(angle)
                    push_y = math.sin(angle)
                
                # Move to gathering distance — validate terrain first
                cand_x = unit.gathering_target.x + push_x * gathering_distance
                cand_y = unit.gathering_target.y + push_y * gathering_distance
                if not self.game.collision_system._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
                    unit.x = cand_x
                    unit.y = cand_y
                else:
                    # Try alternate angles
                    base_angle = math.atan2(push_y, push_x)
                    for i in range(1, 8):
                        alt_angle = base_angle + i * (math.pi / 4)
                        alt_x = unit.gathering_target.x + math.cos(alt_angle) * gathering_distance
                        alt_y = unit.gathering_target.y + math.sin(alt_angle) * gathering_distance
                        if not self.game.collision_system._is_on_unwalkable_terrain(alt_x, alt_y, unit.radius):
                            unit.x = alt_x
                            unit.y = alt_y
                            break
                unit.destination = None
                unit.path = None
                unit._gathering_stuck_timer = 0  # Reset stuck timer
                debug_log.log(f"  - Pushed worker to safe distance: ({unit.x:.0f}, {unit.y:.0f})", "MOVEMENT")
            
            # Additional recovery: If stuck gathering for too long, force a reset
            elif unit._gathering_stuck_timer > 3.0:  # Stuck for 3 seconds
                debug_log.log(f"RECOVERY: Worker stuck gathering for {unit._gathering_stuck_timer:.1f}s - forcing reset", "MOVEMENT")
                
                # Option 1: Try different gathering position
                if unit._gathering_stuck_timer < 6.0:
                    # Calculate a different angle — try up to 8 angles for safe terrain
                    import random
                    base_angle = random.random() * 2 * math.pi
                    moved = False
                    for attempt in range(8):
                        angle = base_angle + attempt * (math.pi / 4)
                        new_x = unit.gathering_target.x + math.cos(angle) * gathering_distance
                        new_y = unit.gathering_target.y + math.sin(angle) * gathering_distance
                        if not self.game.collision_system._is_on_unwalkable_terrain(new_x, new_y, unit.radius):
                            unit.x = new_x
                            unit.y = new_y
                            moved = True
                            debug_log.log(f"  - Moved to new gathering position: ({new_x:.0f}, {new_y:.0f})", "MOVEMENT")
                            break
                    unit._gathering_stuck_timer = 0
                    if not moved:
                        debug_log.log("  - All gathering positions on water, staying put", "MOVEMENT")
                
                # Option 2: More drastic - temporarily stop gathering
                else:
                    debug_log.log("  - Drastic recovery: Stopping gathering temporarily", "MOVEMENT")
                    unit.is_gathering = False
                    unit.status = "idle"
                    unit.destination = None
                    unit.path = None
                    unit._gathering_stuck_timer = 0
                    
                    # Move away from resource
                    if target_distance > 0:
                        push_x = (unit.x - unit.gathering_target.x) / target_distance
                        push_y = (unit.y - unit.gathering_target.y) / target_distance
                    else:
                        import random
                        angle = random.random() * 2 * math.pi
                        push_x = math.cos(angle)
                        push_y = math.sin(angle)
                    
                    cand_x = unit.gathering_target.x + push_x * (gathering_distance + 20)
                    cand_y = unit.gathering_target.y + push_y * (gathering_distance + 20)
                    if not self.game.collision_system._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
                        unit.x = cand_x
                        unit.y = cand_y
                    else:
                        base_angle = math.atan2(push_y, push_x)
                        for i in range(1, 8):
                            alt_angle = base_angle + i * (math.pi / 4)
                            alt_x = unit.gathering_target.x + math.cos(alt_angle) * (gathering_distance + 20)
                            alt_y = unit.gathering_target.y + math.sin(alt_angle) * (gathering_distance + 20)
                            if not self.game.collision_system._is_on_unwalkable_terrain(alt_x, alt_y, unit.radius):
                                unit.x = alt_x
                                unit.y = alt_y
                                break
                    
                    # Will re-engage next frame
                    unit.is_engaging = True
            
            # Debug and recover stuck workers with gathering targets
            elif not unit.path and not unit.destination and unit.status == "idle":
                if debug_log.enabled("MOVEMENT"):
                    debug_log.log(f"DEBUG: Worker at ({unit.x:.0f}, {unit.y:.0f}) has gathering_target but no movement!", "MOVEMENT")
                    debug_log.log(f"  - Target: {unit.gathering_target.name} at ({unit.gathering_target.x:.0f}, {unit.gathering_target.y:.0f})", "MOVEMENT")
                    debug_log.log(f"  - Distance: {target_distance:.1f}, Required: {gathering_distance:.1f}", "MOVEMENT")
                    debug_log.log(f"  - Resource remaining: {getattr(unit.gathering_target, 'amount_remaining', 'N/A')}", "MOVEMENT")
                
                # Recovery: If too far from target, clear the stuck state and re-path
                if target_distance > gathering_distance + 5:  # Small tolerance
                    debug_log.log("  - Recovery: Re-pathing to distant gathering target", "MOVEMENT")
                    if self.game.pathfinder.issue_interact(unit, unit.gathering_target, "gather"):
                        debug_log.log("  - Recovery: Path found, worker moving again", "MOVEMENT")
                    else:
                        # Can't reach target - clear it
                        debug_log.log("  - Recovery: No path to target, clearing gathering target", "MOVEMENT")
                        unit.gathering_target = None
                        unit.is_engaging = False
            
            interaction_tolerance = max(24, unit.radius * 6)
            if target_distance <= gathering_distance + interaction_tolerance:
                if debug_log.enabled("MOVEMENT"):
                    debug_log.log(f"Worker at distance {target_distance:.1f} from {unit.gathering_target.name} (required: {gathering_distance:.1f})", "MOVEMENT")
                # Attempt to start gathering. If successful, the gathering manager will handle state changes.
                if self.game.gathering_manager.start_gathering(unit, unit.gathering_target):
                    debug_log.log("  Started gathering successfully", "MOVEMENT")
                    # Now that gathering has officially started, clear the movement state.
                    unit.path = None
                    unit.path_index = 0
                    unit.path_target = None
                    unit.destination = None
                    unit.is_engaging = False
                else:
                    # Failed to start gathering - resource might be depleted
                    debug_log.log("  Failed to start gathering - resource might be depleted", "MOVEMENT")
                    unit.gathering_target = None
                    unit.is_engaging = False
                    unit.status = "idle"
    
    def _follow_path(self, unit, delta_time):
        """Follow a pathfinding path"""
        # Safety check - ensure path exists
        if not unit.path:
            return
            
        # Force re-pathfinding if stuck
        if (unit.is_engaging and unit.current_target and 
            hasattr(unit, '_stuck_detector') and unit._stuck_detector['stuck_timer'] >= 120):
            unit.path = None
            unit.path_index = 0
            unit.path_target = None
            unit.destination = None
            unit.status = "idle"
            unit._stuck_detector['stuck_timer'] = 0
            unit._stuck_detector['strategy_timer'] = 0
            unit._needs_repath = True
            return
        
        # Check if target moved significantly
        self._check_target_movement(unit)
        
        # Get current waypoint - check again after target movement check
        if not unit.path or unit.path_index >= len(unit.path):
            return
        
        waypoint = unit.path[unit.path_index]
        unit.destination = waypoint
        
        # Move toward waypoint
        pos = pygame.math.Vector2(unit.x, unit.y)
        dest_vec = pygame.math.Vector2(unit.destination)
        direction = dest_vec - pos
        distance = direction.length()
        
        # Waypoint tolerance
        waypoint_tolerance = 4
        if hasattr(unit, '_position_stuck_timer') and unit._position_stuck_timer >= 60:
            tolerance = unit.get_target_tolerance("movement")
            waypoint_tolerance = max(4, min(tolerance, 8))
        
        if distance < waypoint_tolerance:
            # Reached waypoint
            unit.path_index += 1
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = max(0, unit._stuck_detector['stuck_timer'] - 20)

            if unit.path_index >= len(unit.path):
                # Path complete
                self._handle_path_completion(unit)
        else:
            # Move toward waypoint; decelerate only into the last one
            is_final_waypoint = unit.path_index == len(unit.path) - 1 and not unit.is_engaging
            self._move_unit_toward_destination(unit, pos, direction, delta_time, final_approach=is_final_waypoint)
    
    def _check_target_movement(self, unit):
        """Check if movement target has moved significantly"""
        target_object = None
        if unit.is_engaging and unit.current_target:
            target_object = unit.current_target
        elif hasattr(unit, 'gathering_target') and unit.gathering_target:
            target_object = unit.gathering_target
        elif hasattr(unit, 'building_target') and unit.building_target:
            target_object = unit.building_target
        elif hasattr(unit, 'drop_off_target') and unit.drop_off_target:
            target_object = unit.drop_off_target
        
        if target_object and unit.path_target:
            original_target_pos = getattr(unit, 'path_target_object_pos', None)
            if original_target_pos:
                target_displacement = math.sqrt(
                    (target_object.x - original_target_pos[0])**2 +
                    (target_object.y - original_target_pos[1])**2
                )
            else:
                target_displacement = math.sqrt(
                    (target_object.x - unit.path_target[0])**2 +
                    (target_object.y - unit.path_target[1])**2
                )
            
            # Skip for drop-off targets
            is_drop_off = (hasattr(unit, 'drop_off_target') and 
                          unit.drop_off_target and target_object == unit.drop_off_target)
            
            if target_displacement > unit.radius * 2 and not is_drop_off:
                self._repath_to_moved_target(unit, target_object, target_displacement)
    
    def _repath_to_moved_target(self, unit, target_object, target_displacement):
        """Re-pathfind to a target that has moved"""
        # Check LOS for combat units
        if unit.is_engaging and unit.current_target:
            has_los = self._cached_los(unit, target_object)
            
            if has_los:
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = (target_object.x, target_object.y)
                unit.has_los = True
                unit.is_fallback_movement = False
                return
        
        # Re-pathfind
        target_mode = getattr(unit, 'path_target_mode', None)
        if target_mode in ("gather", "build", "dropoff", "attack"):
            if self.game.pathfinder.issue_interact(unit, target_object, target_mode):
                return

        drop_off = unit.drop_off_target if (hasattr(unit, 'drop_off_target') and unit.drop_off_target == target_object) else None
        new_path = self.game.pathfinder.find_path(
            (unit.x, unit.y),
            (target_object.x, target_object.y),
            unit.radius,
            unit,
            drop_off_target=drop_off
        )
        
        if new_path:
            unit.path = new_path
            unit.path_index = 0
            unit.path_target = (target_object.x, target_object.y)
            unit.destination = new_path[0]
        else:
            # Fallback for combat units
            if unit.is_engaging:
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = (target_object.x, target_object.y)
                unit.has_los = False
                unit.is_fallback_movement = True
            else:
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                unit.status = "idle"
    
    def _handle_path_completion(self, unit):
        """Handle when a unit completes its path, with a final position check."""
        if unit.path_target:
            # Proactive collision check before finalizing position
            final_pos = self.game.collision_system.get_safe_position(unit, unit.path_target)
            unit.x, unit.y = final_pos[0], final_pos[1]

            # Stop all movement
            unit.destination = None
            unit.path = None
            unit.path_index = 0
            unit.path_target = None
            unit.status = "idle"

            if not unit.collision:
                unit.collision = True
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = 0
            
            # Check garrison target (§8.9: shelter in castle/watchtower —
            # the old farm-garrison call pointed at a method that never
            # existed and would have crashed on arrival)
            if hasattr(unit, 'garrison_target') and unit.garrison_target:
                from systems import garrison
                garrison.try_enter(self.game, unit, unit.garrison_target)
        else:
            unit.destination = None
            unit.path = None
            unit.path_index = 0
            unit.status = "idle"
    
    def _move_direct(self, unit, delta_time):
        """Direct movement without pathfinding"""
        pos = pygame.math.Vector2(unit.x, unit.y)
        
        # Update destination for moving targets
        if unit.is_engaging and unit.current_target and (unit.has_los or unit.is_fallback_movement):
            unit.destination = (unit.current_target.x, unit.current_target.y)
        
        dest_vec = pygame.math.Vector2(unit.destination)
        direction = dest_vec - pos
        distance = direction.length()
        
        # Arrival tolerance
        arrival_tolerance = 2
        if hasattr(unit, '_stuck_detector') and unit._stuck_detector['stuck_timer'] >= 60:
            tolerance = unit.get_target_tolerance("movement")
            arrival_tolerance = max(2, min(tolerance * 0.7, 5))
        
        if distance < arrival_tolerance:
            # Reached destination
            pass
            unit.destination = None
            unit.status = "idle"
            if not unit.collision:
                unit.collision = True
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = 0
        else:
            # Move toward destination with avoidance for fallback movement
            if unit.is_fallback_movement:
                self._move_unit_toward_destination_with_avoidance(unit, pos, direction, delta_time)
            else:
                # Direct moves decelerate into the goal unless chasing a target
                final_approach = not (unit.is_engaging and unit.current_target)
                self._move_unit_toward_destination(unit, pos, direction, delta_time, final_approach=final_approach)
    
    def _step_length(self, unit, distance, delta_time, final_approach):
        """Step length with arrival deceleration and no overshoot."""
        speed = unit.movement_speed
        if final_approach and distance < self.ARRIVAL_SLOWING_RADIUS:
            speed *= max(self.ARRIVAL_MIN_SPEED_FACTOR, distance / self.ARRIVAL_SLOWING_RADIUS)
        return min(speed * delta_time, distance)

    def _move_unit_toward_destination_with_avoidance(self, unit, pos, direction, delta_time):
        """Move unit toward destination with basic obstacle avoidance"""
        distance = direction.length()
        if distance < 1e-6:
            return
        direction = direction / distance
        step = self._step_length(unit, distance, delta_time, final_approach=False)
        new_pos = pos + direction * step
        
        # Check collisions
        adjusted_pos = self.game._check_unit_collision_and_adjust(unit, new_pos, direction)
        
        # If we're stuck and using fallback movement, try basic avoidance
        if (hasattr(unit, '_stuck_detector') and 
            unit._stuck_detector['stuck_timer'] >= 30 and
            adjusted_pos.distance_to(pos) < 0.1):
            
            # Try perpendicular directions
            perpendicular1 = pygame.math.Vector2(-direction.y, direction.x)
            perpendicular2 = pygame.math.Vector2(direction.y, -direction.x)
            
            # Test both perpendicular directions
            for perp_dir in [perpendicular1, perpendicular2]:
                test_pos = pos + perp_dir * unit.movement_speed * delta_time * 2  # Move sideways
                test_adjusted = self.game._check_unit_collision_and_adjust(unit, test_pos, perp_dir)
                
                # Check if this direction is clearer
                if test_adjusted.distance_to(pos) > adjusted_pos.distance_to(pos):
                    # Also check if it doesn't take us too far from target
                    pass
                    if unit.destination:
                        dest_vec = pygame.math.Vector2(unit.destination)
                        if test_adjusted.distance_to(dest_vec) < pos.distance_to(dest_vec) * 1.5:
                            adjusted_pos = test_adjusted
                            break
        
        # Check terrain and update position
        self._check_terrain_and_update(unit, adjusted_pos)
    
    def _move_unit_toward_destination(self, unit, pos, direction, delta_time, final_approach=False):
        """Move unit toward its destination with collision handling"""
        distance = direction.length()
        if distance < 1e-6:
            return
        direction = direction / distance
        step = self._step_length(unit, distance, delta_time, final_approach)

        # Context steering: pick the least-obstructed direction near the
        # desired one instead of walking into neighbors and sliding.
        if distance > self.STEER_MIN_GOAL_DISTANCE:
            direction = self._context_steer_direction(unit, pos, direction)

        new_pos = pos + direction * step

        # Check collisions
        adjusted_pos = self.game._check_unit_collision_and_adjust(unit, new_pos, direction)

        # Check terrain and update position
        self._check_terrain_and_update(unit, adjusted_pos)

    def _follow_flow_field(self, unit, delta_time):
        """Drive a unit along its group flow field (Phase 5, A7)."""
        from systems.flow_field import HANDOFF_DISTANCE

        pathfinder = self.game.pathfinder
        field = unit.flow_field
        slot = unit.flow_slot_target or field.goal_point
        dx = slot[0] - unit.x
        dy = slot[1] - unit.y
        dist_sq = dx * dx + dy * dy

        # Handoff: near the slot (or field went stale) -> personal short path.
        if field.revision != pathfinder.flow_fields.revision or dist_sq <= HANDOFF_DISTANCE * HANDOFF_DISTANCE:
            unit.flow_field = None
            unit.flow_slot_target = None
            pathfinder.issue_move(unit, slot)
            return

        cell = pathfinder.grid.world_to_cell((unit.x, unit.y))
        direction = field.direction_at(cell)
        if direction is None:
            if cell == field.goal_cell:
                norm = math.sqrt(dist_sq)
                direction = (dx / norm, dy / norm)
            else:
                # Cell the field never reached (disconnected pocket) - fall
                # back to an individual path.
                unit.flow_field = None
                unit.flow_slot_target = None
                pathfinder.issue_move(unit, slot)
                return

        pos = pygame.math.Vector2(unit.x, unit.y)
        desired = pygame.math.Vector2(direction)
        steered = self._context_steer_direction(unit, pos, desired)
        step = unit.movement_speed * delta_time
        new_pos = pos + steered * step
        unit.status = "run"
        unit.destination = slot  # keeps watchdog/HUD semantics sane
        adjusted_pos = self.game._check_unit_collision_and_adjust(unit, new_pos, steered)
        self._check_terrain_and_update(unit, adjusted_pos)

    def _context_steer_direction(self, unit, pos, desired_dir):
        """16-slot interest/danger steering against nearby units (B1/B4).

        Neighbors come from the one shared spatial hash; interaction targets
        never register as danger so approaches stay possible."""
        lookahead = unit.radius * 4 + 16
        collision = getattr(self.game, "collision_system", None)
        if collision is None or not hasattr(collision, "query_nearby_units"):
            return desired_dir
        neighbors = collision.query_nearby_units(pos.x, pos.y, lookahead, exclude=unit)
        if not neighbors:
            unit._steer_last_slot = None
            return desired_dir

        excluded = (
            unit.current_target,
            getattr(unit, "gathering_target", None),
            getattr(unit, "drop_off_target", None),
            getattr(unit, "building_target", None),
        )
        desired_x = desired_dir.x
        desired_y = desired_dir.y
        danger = [0.0] * NUM_STEER_SLOTS
        any_danger = False
        for other in neighbors:
            if other in excluded or not getattr(other, "collision", True):
                continue
            offset_x = other.x - pos.x
            offset_y = other.y - pos.y
            dist = math.hypot(offset_x, offset_y)
            if dist < 1e-6:
                continue
            clearance = dist - unit.radius - other.radius
            if clearance > lookahead:
                continue
            toward_x = offset_x / dist
            toward_y = offset_y / dist
            # Ignore neighbors clearly behind us unless already touching.
            if toward_x * desired_x + toward_y * desired_y < -0.3 and clearance > 0:
                continue
            weight = 1.0 - max(0.0, clearance) / lookahead
            any_danger = True
            for i, (slot_x, slot_y) in enumerate(STEER_SLOT_DIRS):
                alignment = slot_x * toward_x + slot_y * toward_y
                if alignment > 0.6:
                    value = weight * alignment
                    if value > danger[i]:
                        danger[i] = value
        if not any_danger:
            unit._steer_last_slot = None
            return desired_dir

        last_slot = getattr(unit, "_steer_last_slot", None)
        terrain_probe = getattr(self.game_map, "nav_terrain_walkable", None)
        # §8.13.3: probe with the SAME full-radius test the mover gates on —
        # the old single center-point probe kept selecting shoreline slots the
        # mover then rejected at ±radius, livelocking crowds at water.
        terrain_check = getattr(collision, "_is_on_unwalkable_terrain", None)
        probe_distance = unit.radius * 2 + 12
        scored = []
        for i, (slot_x, slot_y) in enumerate(STEER_SLOT_DIRS):
            interest = slot_x * desired_x + slot_y * desired_y
            if interest < -0.2:
                continue  # never reverse
            score = interest - danger[i] * 1.6
            if i == last_slot:
                score += 0.08  # hysteresis against slot flip-flop
            scored.append((score, i, slot_x, slot_y))
        scored.sort(reverse=True)
        for score, i, slot_x, slot_y in scored:
            # Never steer into blocked terrain: a wiped-out move order is far
            # worse than a slightly more crowded slot.
            probe_x = pos.x + slot_x * probe_distance
            probe_y = pos.y + slot_y * probe_distance
            if terrain_check is not None:
                if terrain_check(probe_x, probe_y, unit.radius):
                    continue
            elif terrain_probe is not None and not terrain_probe(probe_x, probe_y):
                continue
            unit._steer_last_slot = i
            return pygame.math.Vector2((slot_x, slot_y))
        return desired_dir
    
    def _check_terrain_and_update(self, unit, adjusted_pos):
        """Terrain-gate a step; slide along shorelines instead of stalling."""
        collision = self.game.collision_system
        if not collision._is_on_unwalkable_terrain(adjusted_pos.x, adjusted_pos.y, unit.radius):
            self._update_unit_position(unit, adjusted_pos)
            return

        # §8.13.3: already overlapping water (bad spawn, legacy push)? Snap to
        # the nearest clear spot via the spiral rescue. The old escape hatch
        # let such a unit move ANYWHERE — including deeper into the water.
        if collision._is_on_unwalkable_terrain(unit.x, unit.y, unit.radius):
            collision._ensure_unit_on_walkable_terrain(unit)
            perf_stats.increment("terrain_rescues")
            return

        # §8.13.3 shoreline sliding: the full step enters water — keep the
        # along-shore axis instead of killing the whole move (the atomic
        # reject starved lakeside crowds into a steering livelock: nobody
        # moved -> same danger field -> same rejected slot). Slide the FULL
        # step length along the surviving axis: the raw projected component
        # can be sub-epsilon (a near-horizontal path leg grazing the shore),
        # which _update_unit_position would read as "blocked" and freeze.
        dx = adjusted_pos.x - unit.x
        dy = adjusted_pos.y - unit.y
        step = math.hypot(dx, dy)
        candidates = []
        if dx:
            candidates.append((unit.x + math.copysign(step, dx), unit.y))
        if dy:
            candidates.append((unit.x, unit.y + math.copysign(step, dy)))
        if abs(dy) > abs(dx):
            candidates.reverse()
        for cand_x, cand_y in candidates:
            if not collision._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
                self._update_unit_position(unit, pygame.math.Vector2(cand_x, cand_y))
                return

        # Blocked outright: keep the move order (path and destination), but
        # drop the steering hysteresis so the +0.08 bonus can't re-pick the
        # slot the mover just rejected (§8.13.3 livelock fuel).
        unit._steer_last_slot = None
        unit._needs_repath = True
        if not hasattr(unit, '_movement_blocked_timer'):
            unit._movement_blocked_timer = 0
        unit._movement_blocked_timer += 1
        if unit._movement_blocked_timer > 30:
            self.game._handle_blocked_unit(unit)
    
    def _update_unit_position(self, unit, new_pos):
        """Update unit position and handle blocked movement more robustly"""
        actually_moved = abs(new_pos.x - unit.x) > 0.1 or abs(new_pos.y - unit.y) > 0.1
        
        if actually_moved:
            # Face the direction of real horizontal travel (sheets face
            # right; the renderer mirrors when facing_left). The threshold
            # keeps steering jitter from flip-flopping the sprite.
            dx = new_pos.x - unit.x
            if dx > 0.1:
                unit.facing_left = False
            elif dx < -0.1:
                unit.facing_left = True
            unit.x, unit.y = new_pos.x, new_pos.y
            unit.status = "run"
            if hasattr(unit, '_movement_blocked_timer'):
                unit._movement_blocked_timer = 0
            # Real progress resets the watchdog's resume allowance - the cap
            # is per stuck incident, not per unit lifetime.
            if getattr(unit, '_watchdog_resume_count', 0):
                unit._watchdog_resume_count = 0
        else:
            # Movement blocked
            if not hasattr(unit, '_movement_blocked_timer'):
                unit._movement_blocked_timer = 0
            unit._movement_blocked_timer += 1
            
            # Only set to idle if blocked for a short time and not on a critical task.
            # This prevents the status from flipping immediately.
            if unit._movement_blocked_timer > 15: # Wait for ~1/4 second
                if not unit.is_engaging and not unit.building_target and not unit.is_dropping_off:
                    unit.status = "idle"
            
            # Handle if blocked too long (existing logic)
            if unit._movement_blocked_timer > 30:  # 0.5 seconds
                self.game._handle_blocked_unit(unit)
    
    def _adjust_stuck_unit_path(self, unit):
        """Force re-pathfinding when stuck"""
        if not unit.path or not unit.current_target:
            return False
        
        unit.path = None
        unit.path_index = 0
        unit.path_target = None
        unit.destination = None
        unit._path_adjustment_count = 0
        
        # Clear stuck timers
        if hasattr(unit, '_stuck_detector'):
            unit._stuck_detector['stuck_timer'] = 0
            unit._stuck_detector['strategy_timer'] = 0
        
        return True
