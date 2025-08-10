import math
import pygame
from systems.pathfinding import Pathfinding
from systems.gathering_manager import get_gathering_distance, get_drop_off_distance
from core.config import DEBUG_MOVEMENT, DEBUG_PATHFINDING
from utils.debug_logger import debug_log


class MovementSystem:
    """Handles all unit movement, pathfinding, and navigation logic"""
    
    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        
    def update_unit_movement(self, unit, delta_time):
        """Main movement update for a single unit"""
        # Update animation with delta_time
        unit.update_animation(delta_time)
        
        # Update combat if applicable
        if hasattr(unit, 'update_combat'):
            unit.update_combat(delta_time)
            self._handle_combat_movement(unit)
        
        # Handle target checking during movement
        if unit.path or unit.destination or unit.is_dropping_off:
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
                # Debug: Unit attacking target
                pass
                unit.start_attack(unit.current_target)
        
        # Handle engaging state - continuously track and pursue target
        if unit.is_engaging and unit.current_target:
            # Check if target still exists and is valid
            pass
            if unit.current_target.hp <= 0:
                unit.current_target = None
                unit.is_engaging = False
                unit.status = "idle"
                return
            
            # Check if we can attack now
            distance = unit.get_distance_to(unit.current_target)
            
            # Debug engaging state only when stuck
            if (unit.status == "idle" and self.game.frame_counter % 120 == 0 and DEBUG_MOVEMENT):
                # Debug: Unit stuck while engaging
                pass
                pass
            
            # Handle combat units attacking
            if unit.current_target and unit.can_attack(unit.current_target):
                # Debug: Unit attacking target
                pass
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
            pass
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
                pass
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
            pass
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
            # Debug: Unit requesting repath due to collision
            pass
            return True
        
        return False
    
    def _reevaluate_movement_strategy(self, unit, force_strategy_change):
        """Re-evaluate and update movement strategy"""
        # Check line of sight
        obstacles = (self.game.buildings + 
                    [u for u in self.game.units if u != unit and u != unit.current_target] +
                    self.game.resources)
        has_los = unit.has_line_of_sight(unit.current_target, self.game_map, obstacles)
        
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
                if DEBUG_MOVEMENT:
                    # Debug: Unit stuck analysis
                    pass
                    pass
        
        if debug_this_eval and detector['stuck_timer'] == 0 and DEBUG_MOVEMENT:
            distance = unit.get_distance_to(unit.current_target)
            # Debug: Unit strategy
        
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
            obstacles = (self.game.buildings + 
                        [u for u in self.game.units if u != unit and u != unit.current_target] +
                        self.game.resources)
            current_los = unit.has_line_of_sight(unit.current_target, self.game_map, obstacles)
            
            if not current_los:
                if debug_this_eval and DEBUG_MOVEMENT:
                    # Debug: LOS no longer valid while stuck
                    pass
                    pass
                # Force pathfinding strategy
                self._use_pathfinding_strategy(unit, True, debug_this_eval)
                return
        
        # Check for multiple units attacking same target
        attacking_same_target = [u for u in self.game.units 
                               if u != unit and u.current_target == unit.current_target and u.is_engaging]
        
        if len(attacking_same_target) >= 2:
            # Multi-unit attack positioning
            pass
            optimal_position = self.game._find_optimal_attack_position(unit, unit.current_target, attacking_same_target)
            
            if optimal_position:
                if debug_this_eval:
                    # Debug: Multi-unit attack - using optimal position
                    pass
                    pass
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
                if debug_this_eval:
                    # Debug: Switching to direct LOS movement
                    pass
                    pass
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
            if debug_this_eval:
                # Debug: Path exists - continuing current path
                pass
                pass
            return
        
        if debug_this_eval and DEBUG_PATHFINDING:
            # Debug: No LOS - attempting pathfinding
        
            pass
        pathfinder = Pathfinding(self.game_map, self.game)
        path = None
        
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
            if debug_this_eval and DEBUG_PATHFINDING:
                # Debug: Pathfinding successful
                pass
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
                if debug_this_eval and DEBUG_PATHFINDING:
                    # Debug: Pathfinding to range
                    pass
                return
        
        # Option 3: Fallback to direct movement
        if debug_this_eval and DEBUG_PATHFINDING:
            # Debug: Pathfinding failed - using direct fallback
            pass
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
            required_distance = unit.radius + unit.building_target.radius - 5
            
            # Log current state every few frames for debugging
            frame_counter = getattr(unit, '_build_log_counter', 0)
            if frame_counter % 60 == 0:  # Log every 60 frames
                debug_log.log(f"BUILD_TRACKING: Worker at ({unit.x:.0f}, {unit.y:.0f}) -> Construction at ({unit.building_target.x:.0f}, {unit.building_target.y:.0f})", "BUILD_TRACK")
                debug_log.log(f"  Distance: {build_distance:.1f}, Required: {required_distance:.1f}, Has path: {unit.path is not None}, Has dest: {unit.destination is not None}", "BUILD_TRACK")
                debug_log.log(f"  Status: {unit.status}, is_building: {unit.is_building}, is_engaging: {getattr(unit, 'is_engaging', False)}", "BUILD_TRACK")
                
                # Extra debug when very close but not close enough
                if build_distance < required_distance + 20 and build_distance > required_distance:
                    debug_log.log(f"  CLOSE BUT NOT CLOSE ENOUGH: Gap of {build_distance - required_distance:.1f} pixels", "BUILD_TRACK")
                    if unit.destination:
                        debug_log.log(f"  Destination: ({unit.destination[0]:.0f}, {unit.destination[1]:.0f})", "BUILD_TRACK")
                    if hasattr(unit, '_stuck_detector'):
                        debug_log.log(f"  Stuck timer: {unit._stuck_detector.get('stuck_timer', 0)}", "BUILD_TRACK")
            unit._build_log_counter = frame_counter + 1
            
            # Add tolerance for stuck units
            if hasattr(unit, '_stuck_detector') and unit._stuck_detector['stuck_timer'] >= 60:
                tolerance = unit.get_target_tolerance("movement")
                required_distance += tolerance
                debug_log.log(f"Worker stuck approaching construction - increased tolerance to {required_distance:.1f}", "MOVEMENT")
            
            # Debug stuck workers with building targets
            if not unit.path and not unit.destination and unit.status == "idle":
                debug_log.log(f"Worker at ({unit.x:.0f}, {unit.y:.0f}) has building_target but no movement!", "CONSTRUCTION")
                debug_log.log(f"  - Target: Construction at ({unit.building_target.x:.0f}, {unit.building_target.y:.0f})", "CONSTRUCTION")
                debug_log.log(f"  - Distance: {build_distance:.1f}, Required: {required_distance:.1f}", "CONSTRUCTION")
                
                # Recovery: Re-path to building target
                if build_distance > required_distance + 5:
                    debug_log.log(f"  - Recovery: Re-pathing to construction site", "MOVEMENT")
                    from systems.pathfinding import Pathfinding
                    pathfinder = Pathfinding(self.game_map, self.game)
                    pathfinder.current_unit = unit
                    pathfinder.building_target = unit.building_target  # Allow pathfinding to target
                    
                    path = pathfinder.find_path((unit.x, unit.y), 
                                              (unit.building_target.x, unit.building_target.y), 
                                              unit.radius, unit)
                    if path:
                        unit.path = path
                        unit.path_index = 0
                        unit.destination = path[0] if path else None
                        unit.status = "run"
                        debug_log.log(f"  - Recovery: Path found to construction site", "MOVEMENT")
                    else:
                        debug_log.log(f"  - Recovery: No path to construction site!", "MOVEMENT")
            
            # Check if worker is close enough to start building
            # Add a small tolerance (10 pixels) to account for pathfinding/collision precision
            if build_distance <= required_distance + 10:
                # Start building
                debug_log.log(f"Worker reached construction site at distance {build_distance:.1f} (required: {required_distance:.1f})", "CONSTRUCTION")
                debug_log.log(f"  Worker status: {unit.status}, is_building: {unit.is_building}", "CONSTRUCTION")
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                unit.is_building = True
                unit.status = "build"
                debug_log.log(f"  Updated worker - status: {unit.status}, is_building: {unit.is_building}", "CONSTRUCTION")
                
                # Link worker to construction site
                if hasattr(unit.building_target, 'builder'):
                    if unit.building_target.builder is None:
                        unit.building_target.builder = unit
                        debug_log.log(f"  Linked worker to construction site", "CONSTRUCTION")
                    else:
                        debug_log.log(f"  Construction site already has a builder: {unit.building_target.builder}", "CONSTRUCTION")
                else:
                    debug_log.log(f"  ERROR: Construction site has no 'builder' attribute!", "CONSTRUCTION")
                return
        
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
            
            if drop_distance <= required_distance or unit.is_dropping_off or reached_destination:
                # Drop off resources
                pass
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = None
                
                building_name = unit.drop_off_target.name
                building_x = unit.drop_off_target.x  # Store building position before it's cleared
                building_y = unit.drop_off_target.y
                resource_type = unit.resource_type
                if self.game.gathering_manager.drop_off_resources(unit, unit.drop_off_target, delta_time):
                    # Debug: Worker dropped off resources
                    pass
                    # Move away from building
                    if hasattr(unit, 'gathering_target') and unit.gathering_target:
                        unit.destination = (unit.gathering_target.x, unit.gathering_target.y)
                        unit.status = "run"
                        unit.is_engaging = True  # Resume gathering after drop-off
                    else:
                        away_x = unit.x + (unit.x - building_x) * 0.5
                        away_y = unit.y + (unit.y - building_y) * 0.5
                        unit.destination = (away_x, away_y)
                        unit.status = "run"
                return
        
        # Check gathering target
        elif (unit.name == "worker" and hasattr(unit, 'gathering_target') and 
              unit.gathering_target and hasattr(unit, 'is_engaging') and unit.is_engaging):
            
            from systems.gathering_manager import get_gathering_distance
            target_distance = math.sqrt((unit.x - unit.gathering_target.x)**2 + 
                                      (unit.y - unit.gathering_target.y)**2)
            gathering_distance = get_gathering_distance(unit, unit.gathering_target)
            
            # Debug and recover stuck workers with gathering targets
            if not unit.path and not unit.destination and unit.status == "idle":
                debug_log.log(f"DEBUG: Worker at ({unit.x:.0f}, {unit.y:.0f}) has gathering_target but no movement!", "MOVEMENT")
                debug_log.log(f"  - Target: {unit.gathering_target.name} at ({unit.gathering_target.x:.0f}, {unit.gathering_target.y:.0f})", "MOVEMENT")
                debug_log.log(f"  - Distance: {target_distance:.1f}, Required: {gathering_distance:.1f}", "MOVEMENT")
                debug_log.log(f"  - Resource remaining: {getattr(unit.gathering_target, 'amount_remaining', 'N/A')}", "MOVEMENT")
                
                # Recovery: If too far from target, clear the stuck state and re-path
                if target_distance > gathering_distance + 5:  # Small tolerance
                    debug_log.log(f"  - Recovery: Re-pathing to distant gathering target", "MOVEMENT")
                    from systems.pathfinding import Pathfinding
                    pathfinder = Pathfinding(self.game_map, self.game)
                    pathfinder.gathering_target = unit.gathering_target
                    pathfinder.current_unit = unit
                    
                    path = pathfinder.find_path((unit.x, unit.y), 
                                              (unit.gathering_target.x, unit.gathering_target.y), 
                                              unit.radius, unit)
                    if path:
                        unit.path = path
                        unit.path_index = 0
                        unit.destination = path[0] if path else None
                        unit.status = "run"
                        debug_log.log(f"  - Recovery: Path found, worker moving again", "MOVEMENT")
                    else:
                        # Can't reach target - clear it
                        debug_log.log(f"  - Recovery: No path to target, clearing gathering target", "MOVEMENT")
                        unit.gathering_target = None
                        unit.is_engaging = False
            
            if target_distance <= gathering_distance:
                debug_log.log(f"Worker at distance {target_distance:.1f} from {unit.gathering_target.name} (required: {gathering_distance:.1f})", "MOVEMENT")
                # Attempt to start gathering. If successful, the gathering manager will handle state changes.
                if self.game.gathering_manager.start_gathering(unit, unit.gathering_target):
                    debug_log.log(f"  Started gathering successfully", "MOVEMENT")
                    # Now that gathering has officially started, clear the movement state.
                    unit.path = None
                    unit.path_index = 0
                    unit.path_target = None
                    unit.destination = None
                    unit.is_engaging = False
                else:
                    # Failed to start gathering - resource might be depleted
                    debug_log.log(f"  Failed to start gathering - resource might be depleted", "MOVEMENT")
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
            if DEBUG_MOVEMENT:
                # Debug: Unit stuck in path processing
                pass
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
            pass
            unit.path_index += 1
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = max(0, unit._stuck_detector['stuck_timer'] - 20)
            
            if unit.path_index >= len(unit.path):
                # Path complete
                pass
                self._handle_path_completion(unit)
        else:
            # Move toward waypoint
            pass
            self._move_unit_toward_destination(unit, pos, direction, delta_time)
    
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
            obstacles = (self.game.buildings + 
                        [u for u in self.game.units if u != unit and u != target_object] +
                        self.game.resources)
            has_los = unit.has_line_of_sight(target_object, self.game_map, obstacles)
            
            if has_los:
                # Debug: Target moved - switching to direct LOS
                pass
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = (target_object.x, target_object.y)
                unit.has_los = True
                unit.is_fallback_movement = False
                return
        
        # Re-pathfind
        target_type = "combat" if unit.is_engaging else "movement"
        if DEBUG_PATHFINDING:
            # Debug: Target moved - re-pathfinding
        
            pass
        pathfinder = Pathfinding(self.game_map, self.game)
        
        # Set pathfinder targets
        if hasattr(unit, 'drop_off_target') and unit.drop_off_target == target_object:
            pathfinder.drop_off_target = unit.drop_off_target
        
        new_path = pathfinder.find_path(
            (unit.x, unit.y),
            (target_object.x, target_object.y),
            unit.radius,
            unit
        )
        
        if new_path:
            unit.path = new_path
            unit.path_index = 0
            unit.path_target = (target_object.x, target_object.y)
            unit.destination = new_path[0]
            # Debug: New path found
        else:
            # Fallback for combat units
            pass
            if unit.is_engaging:
                if DEBUG_PATHFINDING:
                    # Debug: Re-pathfinding failed - using direct fallback
                    pass
                unit.path = None
                unit.path_index = 0
                unit.path_target = None
                unit.destination = (target_object.x, target_object.y)
                unit.has_los = False
                unit.is_fallback_movement = True
            else:
                if DEBUG_PATHFINDING:
                    # Debug: Re-pathfinding failed - clearing path
                    pass
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
            
            # Check garrison target
            if hasattr(unit, 'garrison_target') and unit.garrison_target:
                self.game.gathering_manager.garrison_worker_to_farm(unit, unit.garrison_target)
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
            pass
            if unit.is_fallback_movement:
                self._move_unit_toward_destination_with_avoidance(unit, pos, direction, delta_time)
            else:
                self._move_unit_toward_destination(unit, pos, direction, delta_time)
    
    def _move_unit_toward_destination_with_avoidance(self, unit, pos, direction, delta_time):
        """Move unit toward destination with basic obstacle avoidance"""
        direction.normalize_ip()
        new_pos = pos + direction * unit.movement_speed * delta_time
        
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
    
    def _move_unit_toward_destination(self, unit, pos, direction, delta_time):
        """Move unit toward its destination with collision handling"""
        direction.normalize_ip()
        new_pos = pos + direction * unit.movement_speed * delta_time
        
        # Check collisions
        adjusted_pos = self.game._check_unit_collision_and_adjust(unit, new_pos, direction)
        
        # Check terrain and update position
        self._check_terrain_and_update(unit, adjusted_pos)
    
    def _check_terrain_and_update(self, unit, adjusted_pos):
        """Check terrain and update unit position"""
        # Check with full radius to ensure unit doesn't overlap water
        check_points = [
            (adjusted_pos.x, adjusted_pos.y),  # Center
            (adjusted_pos.x + unit.radius, adjusted_pos.y),  # Right
            (adjusted_pos.x - unit.radius, adjusted_pos.y),  # Left
            (adjusted_pos.x, adjusted_pos.y + unit.radius),  # Bottom
            (adjusted_pos.x, adjusted_pos.y - unit.radius),  # Top
            (adjusted_pos.x + unit.radius * 0.7, adjusted_pos.y + unit.radius * 0.7),  # Bottom-right
            (adjusted_pos.x - unit.radius * 0.7, adjusted_pos.y + unit.radius * 0.7),  # Bottom-left
            (adjusted_pos.x + unit.radius * 0.7, adjusted_pos.y - unit.radius * 0.7),  # Top-right
            (adjusted_pos.x - unit.radius * 0.7, adjusted_pos.y - unit.radius * 0.7),  # Top-left
        ]
        
        can_move = True
        for check_x, check_y in check_points:
            hex_coord = self.game_map.world_to_grid(check_x, check_y)
            if hex_coord:
                col, row = hex_coord
                if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                    tile_type = self.game_map.grid[row][col]
                    if tile_type in {"water", "lava"}:
                        can_move = False
                        break
        
        if can_move:
            self._update_unit_position(unit, adjusted_pos)
        else:
            # Stop at unwalkable terrain and request new path
            if unit.path:
                unit.path = None
                unit.path_index = 0
            unit.destination = None
            unit.status = "idle"
            unit._needs_repath = True  # Request new path next update
    
    def _update_unit_position(self, unit, new_pos):
        """Update unit position and handle blocked movement more robustly"""
        actually_moved = abs(new_pos.x - unit.x) > 0.1 or abs(new_pos.y - unit.y) > 0.1
        
        if actually_moved:
            unit.x, unit.y = new_pos.x, new_pos.y
            unit.status = "run"
            if hasattr(unit, '_movement_blocked_timer'):
                unit._movement_blocked_timer = 0
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
        
        if DEBUG_MOVEMENT:
            # Debug: Unit stuck - forcing complete re-pathfinding
            pass
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