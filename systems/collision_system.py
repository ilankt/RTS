import math
import pygame
from core.config import DEBUG_MOVEMENT, DEBUG_PATHFINDING


class CollisionSystem:
    """Handles collision detection, resolution, and unit separation"""
    
    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        
    def check_unit_collision_and_adjust(self, unit, new_pos, direction):
        """Smart collision detection with sliding behavior"""
        if not unit.collision:
            return new_pos

        original_pos = pygame.math.Vector2(unit.x, unit.y)
        final_pos = new_pos
        
        # First, check for collisions with static objects (buildings, resources)
        for building in self.game.buildings:
            # Skip drop-off targets when unit is dropping off
            pass
            if (hasattr(unit, 'drop_off_target') and unit.drop_off_target == building and
                hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
                continue
                
            dx = final_pos.x - building.x
            dy = final_pos.y - building.y
            distance = math.sqrt(dx * dx + dy * dy)
            min_distance = unit.radius + building.radius + 2
            
            if distance < min_distance:
                # Calculate overlap amount
                pass
                overlap = min_distance - distance
                # Try sliding along the obstacle
                final_pos = self._calculate_slide_position(original_pos, final_pos, 
                                                         pygame.math.Vector2(building.x, building.y), 
                                                         building.radius + unit.radius + 2,
                                                         unit, overlap)
        
        # Check resources
        for resource in self.game.resources:
            dx = final_pos.x - resource.x
            dy = final_pos.y - resource.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            # For gathering targets, allow closer approach but prevent complete overlap
            if (hasattr(unit, 'gathering_target') and unit.gathering_target == resource):
                # Allow gathering distance but prevent overlap beyond gathering range
                pass
                from systems.gathering_manager import get_gathering_distance
                gathering_distance = get_gathering_distance(unit, resource)
                min_distance = max(gathering_distance * 0.8, unit.radius + resource.radius - 5)  # Allow closer but not overlapping
            else:
                # Normal collision distance for non-gathering targets
                pass
                min_distance = unit.radius + resource.radius + 2
            
            if distance < min_distance:
                # Calculate overlap amount
                pass
                overlap = min_distance - distance
                # Try sliding along the obstacle
                final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                         pygame.math.Vector2(resource.x, resource.y),
                                                         min_distance,
                                                         unit, overlap)
        
        # Then check other units with special handling
        for other_unit in self.game.units:
            if other_unit == unit:
                continue
            
            # Calculate distances
            current_distance = math.sqrt((unit.x - other_unit.x)**2 + (unit.y - other_unit.y)**2)
            new_distance = math.sqrt((final_pos.x - other_unit.x)**2 + (final_pos.y - other_unit.y)**2)
            min_distance = unit.radius + other_unit.radius + 2
            
            # If already overlapping, prioritize separation
            if current_distance < min_distance:
                if new_distance > current_distance:
                    continue  # Allow movement that separates
                else:
                    # For LOS movement that's causing overlapping, temporarily disable it
                    pass
                    if (hasattr(unit, 'has_los') and unit.has_los and 
                        hasattr(unit, 'current_target') and unit.current_target and
                        current_distance < (unit.radius + other_unit.radius) * 0.8):  # Significantly overlapping
                        
                        # Mark unit as needing separation instead of target pursuit
                        if not hasattr(unit, '_needs_separation'):
                            unit._needs_separation = 0
                        unit._needs_separation += 1
                        
                        # After 30 frames (0.5s) of overlapping, force pathfinding
                        if unit._needs_separation >= 30:
                            if DEBUG_MOVEMENT:
                                # Debug: Unit overlapping - disabling LOS temporarily
                                pass
                                pass
                            unit.has_los = False  # Force pathfinding on next strategy evaluation
                            unit._needs_separation = 0
                    
                    # Try to find a perpendicular escape direction
                    escape_dir = self._find_escape_direction(original_pos, 
                                                           pygame.math.Vector2(other_unit.x, other_unit.y),
                                                           direction)
                    if escape_dir:
                        escape_move = escape_dir * (unit.movement_speed * (1/60))
                        test_pos = original_pos + escape_move
                        # Check if escape position is valid
                        if not self._would_collide_with_static(unit, test_pos):
                            final_pos = test_pos
                    else:
                        final_pos = original_pos  # Can't move
            else:
                # Reset separation counter when not overlapping
                pass
                if hasattr(unit, '_needs_separation'):
                    unit._needs_separation = 0
                
                # Normal collision avoidance
                if new_distance < min_distance:
                    # Calculate overlap amount
                    pass
                    overlap = min_distance - new_distance
                    # Try sliding along the unit
                    final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                             pygame.math.Vector2(other_unit.x, other_unit.y),
                                                             other_unit.radius + unit.radius + 2,
                                                             unit, overlap)
        
        return final_pos
    
    def _calculate_slide_position(self, start_pos, desired_pos, obstacle_pos, min_distance, unit=None, overlap_amount=0):
        """Calculate a sliding position along an obstacle"""
        # Vector from start to desired position
        move_vector = desired_pos - start_pos
        move_distance = move_vector.length()
        
        if move_distance < 0.1:
            return start_pos
        
        # Reduce sliding when unit is near target (combat or gathering)
        if unit and hasattr(unit, 'is_engaging') and unit.is_engaging:
            target = None
            range_check = None
            
            # Check for combat target
            if hasattr(unit, 'current_target') and unit.current_target:
                target = unit.current_target
                if hasattr(unit, 'get_effective_attack_range'):
                    range_check = unit.get_effective_attack_range("exact")
            
            # Check for gathering target
            elif hasattr(unit, 'gathering_target') and unit.gathering_target:
                target = unit.gathering_target
                # For gathering, use a reasonable range check (gathering distance is typically smaller)
                from systems.gathering_manager import get_gathering_distance
                try:
                    range_check = get_gathering_distance(unit, target)
                except:
                    range_check = 50  # Fallback range
            
            # Apply sliding reduction if target and range are available
            if target and range_check:
                dist_to_target = math.sqrt((target.x - start_pos.x)**2 + (target.y - start_pos.y)**2)
                # If within 2x range, reduce sliding to allow more direct approach
                if dist_to_target < range_check * 2:
                    return start_pos  # Don't slide when close to target
        
        # Vector from obstacle to start position
        to_start = start_pos - obstacle_pos
        
        if to_start.length() < 0.1:
            return start_pos  # Too close to obstacle center
        
        # Project movement onto the tangent of the obstacle
        # This gives us the sliding direction
        to_start_normalized = to_start.normalize()
        dot = move_vector.dot(to_start_normalized)
        slide_vector = move_vector - to_start_normalized * dot
        
        if slide_vector.length() > 0.1:
            # Smooth sliding transitions based on overlap severity
            pass
            if overlap_amount > 0:
                # More overlap = slower movement (0.3 to 0.8 based on overlap)
                pass
                slide_factor = max(0.3, min(0.8, 1.0 - overlap_amount / 50))
            else:
                slide_factor = 0.7  # Default for non-overlap collisions
            
            # Apply sliding movement with smooth factor
            slide_pos = start_pos + slide_vector.normalize() * move_distance * slide_factor
            
            # Ensure we're not getting closer to the obstacle
            if (slide_pos - obstacle_pos).length() >= min_distance - 1:
                return slide_pos
        
        return start_pos  # Can't slide, stay in place
    
    def _find_escape_direction(self, unit_pos, obstacle_pos, preferred_dir):
        """Find a perpendicular direction to escape from an overlapping obstacle"""
        to_obstacle = obstacle_pos - unit_pos
        
        if to_obstacle.length() < 0.1:
            # Units are on top of each other, use preferred direction
            pass
            return preferred_dir
        
        # Get perpendicular directions
        perpendicular1 = pygame.math.Vector2(-to_obstacle.y, to_obstacle.x).normalize()
        perpendicular2 = pygame.math.Vector2(to_obstacle.y, -to_obstacle.x).normalize()
        
        # Choose the perpendicular that aligns better with preferred direction
        if preferred_dir.dot(perpendicular1) > preferred_dir.dot(perpendicular2):
            return perpendicular1
        else:
            return perpendicular2
    
    def _would_collide_with_static(self, unit, test_pos):
        """Check if a position would collide with static obstacles"""
        # Check buildings
        for building in self.game.buildings:
            dist = math.sqrt((test_pos.x - building.x)**2 + (test_pos.y - building.y)**2)
            if dist < building.radius + unit.radius + 2:
                return True
        
        # Check resources
        for resource in self.game.resources:
            dist = math.sqrt((test_pos.x - resource.x)**2 + (test_pos.y - resource.y)**2)
            if dist < resource.radius + unit.radius + 2:
                return True
        
        # Check terrain with unit radius consideration
        # Check multiple points around the unit's edge
        check_points = [
            (test_pos.x, test_pos.y),  # Center
            (test_pos.x + unit.radius, test_pos.y),  # Right
            (test_pos.x - unit.radius, test_pos.y),  # Left
            (test_pos.x, test_pos.y + unit.radius),  # Bottom
            (test_pos.x, test_pos.y - unit.radius),  # Top
        ]
        
        for check_x, check_y in check_points:
            hex_coord = self.game_map.world_to_grid(check_x, check_y)
            if hex_coord:
                col, row = hex_coord
                if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                    if self.game_map.grid[row][col] in {"water", "lava"}:
                        return True
        
        return False
    
    def separate_overlapping_units(self):
        """Push apart units that are overlapping with priority for drop-off workers"""
        base_separation_force = 0.8  # Increased base separation force
        
        for i, unit1 in enumerate(self.game.units):
            if not unit1.collision:
                continue
            for unit2 in self.game.units[i + 1:]:
                if not unit2.collision:
                    continue
                # Calculate distance between units
                pass
                dx = unit2.x - unit1.x
                dy = unit2.y - unit1.y
                distance = math.sqrt(dx * dx + dy * dy)
                
                # Check if they're overlapping
                min_distance = unit1.radius + unit2.radius + 2
                if distance < min_distance and distance > 0:
                    # Calculate overlap amount
                    pass
                    overlap = min_distance - distance
                    
                    # Increase separation force if either unit is dropping off
                    separation_force = base_separation_force
                    if ((hasattr(unit1, 'is_dropping_off') and unit1.is_dropping_off) or 
                        (hasattr(unit1, 'drop_off_target') and unit1.drop_off_target and 
                         hasattr(unit1, 'resource_amount') and unit1.resource_amount > 0) or
                        (hasattr(unit2, 'is_dropping_off') and unit2.is_dropping_off) or 
                        (hasattr(unit2, 'drop_off_target') and unit2.drop_off_target and 
                         hasattr(unit2, 'resource_amount') and unit2.resource_amount > 0)):
                        separation_force = 1.5  # Stronger separation for drop-off workers
                    
                    # Normalize direction vector
                    dx_norm = dx / distance
                    dy_norm = dy / distance
                    
                    # Calculate separation distance for each unit
                    separation_per_unit = overlap * separation_force / 2
                    
                    # Push units apart (each moves half the distance)
                    unit1.x -= dx_norm * separation_per_unit
                    unit1.y -= dy_norm * separation_per_unit
                    unit2.x += dx_norm * separation_per_unit
                    unit2.y += dy_norm * separation_per_unit
                    
                    # Ensure units don't go into unwalkable terrain
                    self._ensure_unit_on_walkable_terrain(unit1)
                    self._ensure_unit_on_walkable_terrain(unit2)
    
    def _ensure_unit_on_walkable_terrain(self, unit):
        """Make sure unit stays on walkable terrain after separation"""
        hex_coord = self.game_map.world_to_grid(unit.x, unit.y)
        if hex_coord:
            col, row = hex_coord
            if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                tile_type = self.game_map.grid[row][col]
                if tile_type in {"water", "lava"}:
                    # Find nearest walkable position
                    pass
                    for radius in range(5, 30, 5):
                        for angle in range(0, 360, 45):
                            test_x = unit.x + radius * math.cos(math.radians(angle))
                            test_y = unit.y + radius * math.sin(math.radians(angle))
                            test_hex = self.game_map.world_to_grid(test_x, test_y)
                            if test_hex:
                                test_col, test_row = test_hex
                                if 0 <= test_row < self.game_map.height and 0 <= test_col < self.game_map.width:
                                    test_tile = self.game_map.grid[test_row][test_col]
                                    if test_tile not in {"water", "lava"}:
                                        unit.x = test_x
                                        unit.y = test_y
                                        return
    
    def apply_separation_to_unit(self, unit):
        """Apply separation force to a specific unit if it's overlapping with others"""
        separation_applied = False
        max_separation_force = 2.0  # Stronger force for individual separation
        
        for other_unit in self.game.units:
            if other_unit == unit:
                continue
                
            # Calculate distance between units
            dx = unit.x - other_unit.x
            dy = unit.y - other_unit.y
            distance = math.sqrt(dx * dx + dy * dy)
            
            # Check if they're overlapping
            min_distance = unit.radius + other_unit.radius + 2
            if distance < min_distance and distance > 0:
                # Calculate overlap amount
                pass
                overlap = min_distance - distance
                
                # Normalize direction vector (direction to push this unit)
                dx_norm = dx / distance
                dy_norm = dy / distance
                
                # Calculate separation force based on overlap severity
                # More overlap = stronger force, up to max_separation_force
                separation_force = min(max_separation_force, overlap * 0.8)
                
                # Apply separation to this unit only
                unit.x += dx_norm * separation_force
                unit.y += dy_norm * separation_force
                separation_applied = True
                
                # Ensure unit doesn't go into unwalkable terrain
                self._ensure_unit_on_walkable_terrain(unit)
                
                # For workers dropping off, prioritize separation over pathfinding
                if (hasattr(unit, 'is_dropping_off') and unit.is_dropping_off) or \
                   (hasattr(unit, 'drop_off_target') and unit.drop_off_target and unit.resource_amount > 0):
                    # Clear destination temporarily to allow separation to take effect
                    if overlap > 5:  # Only for significant overlaps
                        unit.destination = None
                        # Don't clear path completely, just pause movement
                        if hasattr(unit, '_separation_pause_timer'):
                            unit._separation_pause_timer += 1
                        else:
                            unit._separation_pause_timer = 1
                        
                        # Resume movement after separation
                        if unit._separation_pause_timer > 10:  # About 1/6 second
                            unit._separation_pause_timer = 0
                            # Restore destination if we have drop-off target
                            if hasattr(unit, 'drop_off_target') and unit.drop_off_target:
                                unit.destination = (unit.drop_off_target.x, unit.drop_off_target.y)
        
        return separation_applied
    
    def handle_blocked_unit(self, unit):
        """Handle a unit that has been blocked for too long"""
        # Reset the blocked timer
        unit._movement_blocked_timer = 0
        
        # Different strategies based on what the unit is doing
        if (hasattr(unit, 'drop_off_target') and unit.drop_off_target and 
            hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
            # Worker trying to drop off resources
            if DEBUG_MOVEMENT:
                # Debug: Worker blocked while trying to drop off resources
                pass
                pass
            
            # Try to use pathfinding if not already using it
            if not unit.path:
                from systems.pathfinding import Pathfinding
                pathfinder = Pathfinding(self.game_map, self.game)
                pathfinder.drop_off_target = unit.drop_off_target
                pathfinder.current_unit = unit
                
                path = pathfinder.find_path((unit.x, unit.y), 
                                          (unit.drop_off_target.x, unit.drop_off_target.y), 
                                          unit.radius, unit)
                if path:
                    unit.path = path
                    unit.path_index = 0
                    unit.destination = path[0] if path else None
                    if DEBUG_PATHFINDING:
                        # Debug: Found alternate path
                        pass
                        pass
            else:
                # Already has path but still stuck - skip current waypoint
                pass
                if unit.path_index < len(unit.path) - 1:
                    unit.path_index += 1
                    unit.destination = unit.path[unit.path_index]
                    if DEBUG_MOVEMENT:
                        # Debug: Skipping to next waypoint
                        pass
                        pass
                else:
                    # At last waypoint but stuck - clear path and try direct movement
                    pass
                    unit.path = None
                    unit.path_index = 0
                    unit.destination = (unit.drop_off_target.x, unit.drop_off_target.y)
                    if DEBUG_MOVEMENT:
                        # Debug: Clearing path, trying direct movement
        
                        pass
        elif hasattr(unit, 'gathering_target') and unit.gathering_target:
            # Worker trying to gather resources
            pass
            if DEBUG_MOVEMENT:
                # Debug: Worker blocked while trying to gather
            
                pass
            # Similar logic for gathering
            if not unit.path:
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
                    if DEBUG_PATHFINDING:
                        # Debug: Found alternate path
        
                        pass
        elif hasattr(unit, 'current_target') and unit.current_target and hasattr(unit, 'is_engaging') and unit.is_engaging:
            # Combat unit trying to reach target
            pass
            if DEBUG_MOVEMENT:
                # Debug: Unit blocked while engaging target
            
                pass
            # Force re-pathfinding
            unit._needs_repath = True
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = 100  # Trigger immediate re-evaluation
        
        else:
            # Generic movement - try to find alternate route
            pass
            if unit.destination:
                if DEBUG_MOVEMENT:
                    # Debug: Unit blocked during generic movement
                
                    pass
                # If using direct movement, try pathfinding
                if not unit.path:
                    from systems.pathfinding import Pathfinding
                    pathfinder = Pathfinding(self.game_map, self.game)
                    pathfinder.current_unit = unit
                    
                    path = pathfinder.find_path((unit.x, unit.y), unit.destination, unit.radius, unit)
                    if path:
                        unit.path = path
                        unit.path_index = 0
                        unit.destination = path[0] if path else None
                        if DEBUG_PATHFINDING:
                            # Debug: Switching to pathfinding
                            pass
                else:
                    # Has path but stuck - try skipping waypoint
                    pass
                    if unit.path_index < len(unit.path) - 1:
                        unit.path_index += 1
                        unit.destination = unit.path[unit.path_index]
                        if DEBUG_MOVEMENT:
                            # Debug: Skipping to next waypoint
    
                            pass
    def find_blocking_object(self, start, end, radius, unit=None):
        """Find the first object blocking a path between two points"""
        # Sample points along the line
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance == 0:
            return None
        
        steps = int(distance / 10) + 1  # Check every 10 units
        
        for i in range(1, steps + 1):
            t = i / steps
            check_x = start[0] + dx * t
            check_y = start[1] + dy * t
            
            # Check collision with buildings
            for building in self.game.buildings:
                dist = math.sqrt((building.x - check_x)**2 + (building.y - check_y)**2)
                if dist < building.radius + radius + 2:
                    return building
            
            # Check collision with other units
            for other_unit in self.game.units:
                if unit and other_unit == unit:
                    continue  # Skip self
                dist = math.sqrt((other_unit.x - check_x)**2 + (other_unit.y - check_y)**2)
                if dist < other_unit.radius + radius + 2:
                    return other_unit
            
            # Check collision with resources
            for resource in self.game.resources:
                dist = math.sqrt((resource.x - check_x)**2 + (resource.y - check_y)**2)
                if dist < resource.radius + radius + 2:
                    return resource
        
        return None
    
    def calculate_detour_point(self, start, end, obstacle, unit_radius):
        """Calculate a detour point to go around an obstacle"""
        # Calculate direction from start to obstacle
        dx = obstacle.x - start[0]
        dy = obstacle.y - start[1]
        dist_to_obstacle = math.sqrt(dx * dx + dy * dy)
        
        if dist_to_obstacle == 0:
            return None
        
        # Normalize direction
        dx /= dist_to_obstacle
        dy /= dist_to_obstacle
        
        # Calculate perpendicular directions (left and right)
        left_x, left_y = -dy, dx
        right_x, right_y = dy, -dx
        
        # Calculate detour distance (obstacle radius + unit radius + buffer)
        detour_distance = obstacle.radius + unit_radius + 20
        
        # Try both left and right detours
        for perpendicular in [(left_x, left_y), (right_x, right_y)]:
            detour_x = obstacle.x + perpendicular[0] * detour_distance
            detour_y = obstacle.y + perpendicular[1] * detour_distance
            
            # Check if detour point is walkable
            hex_coord = self.game_map.world_to_grid(detour_x, detour_y)
            if hex_coord:
                tile_type = self.game_map.grid[hex_coord[1]][hex_coord[0]]
                if tile_type not in {"water", "lava"}:
                    # Check if detour point is clear of obstacles
                    pass
                    is_clear = True
                    for obj in self.game.buildings + self.game.units + self.game.resources:
                        dist = math.sqrt((obj.x - detour_x)**2 + (obj.y - detour_y)**2)
                        if dist < obj.radius + unit_radius + 5:
                            is_clear = False
                            break
                    
                    if is_clear:
                        return (detour_x, detour_y)
        
        return None
    
    def position_is_free(self, unit, position, buffer):
        """Check if a position is free of collisions for the given unit"""
        # Get all potential obstacles (units, buildings, resources)
        obstacles = []
        
        # Add other units
        for other_unit in self.game.units:
            if other_unit == unit:
                continue
            obstacles.append(other_unit)
        
        # Add buildings (unless it's the unit's drop-off target)
        for building in self.game.buildings:
            if hasattr(unit, 'drop_off_target') and building == unit.drop_off_target:
                continue
            obstacles.append(building)
        
        # Add resources (unless it's the unit's gathering target)
        for resource in self.game.resources:
            if hasattr(unit, 'gathering_target') and resource == unit.gathering_target:
                continue
            obstacles.append(resource)
        
        # Check collision with all obstacles
        for obstacle in obstacles:
            distance = math.sqrt((position.x - obstacle.x)**2 + (position.y - obstacle.y)**2)
            min_distance = unit.radius + obstacle.radius + buffer
            
            if distance < min_distance:
                return False
        
        return True

    def get_safe_position(self, unit, target_pos):
        """Checks if a target position is valid and returns a safe position if not."""
        # Check for collisions at the target position
        for obstacle in self.game.buildings + self.game.resources + self.game.units:
            if obstacle == unit:
                continue

            distance = math.sqrt((target_pos[0] - obstacle.x)**2 + (target_pos[1] - obstacle.y)**2)
            min_distance = unit.radius + obstacle.radius

            if distance < min_distance:
                # Collision detected, calculate a safe "nudge" position
                direction_x = target_pos[0] - obstacle.x
                direction_y = target_pos[1] - obstacle.y
                dist = math.sqrt(direction_x**2 + direction_y**2)

                if dist == 0:
                    direction_x, direction_y = 1, 0
                else:
                    direction_x /= dist
                    direction_y /= dist

                nudge_distance = min_distance + 2 # Add a small buffer
                safe_x = obstacle.x + direction_x * nudge_distance
                safe_y = obstacle.y + direction_y * nudge_distance
                return (safe_x, safe_y)

        # Position is safe
        return target_pos