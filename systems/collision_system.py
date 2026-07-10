import math
import pygame
from utils.debug_logger import debug_log
from utils.perf_stats import perf_stats


SPATIAL_BUCKET_SIZE = 96


class CollisionSystem:
    """Handles collision detection, resolution, and unit separation"""
    
    def __init__(self, game):
        self.game = game
        self.game_map = game.game_map
        self.bucket_size = SPATIAL_BUCKET_SIZE
        self._static_buckets = {}
        self._static_kinds = {}
        self._unit_buckets = {}
        self._static_signature = None
        self._static_signature_frame = None
        self._unit_bucket_frame = None

    def begin_frame(self):
        """Prepare collision acceleration structures for the current frame."""
        self._ensure_static_index()
        frame = getattr(self.game, "frame_counter", 0)
        if self._unit_bucket_frame != frame:
            self._rebuild_unit_index()
            self._unit_bucket_frame = frame

    def _cell_for(self, x, y):
        return (int(x // self.bucket_size), int(y // self.bucket_size))

    def _cells_for_bounds(self, x, y, radius):
        min_cell = self._cell_for(x - radius, y - radius)
        max_cell = self._cell_for(x + radius, y + radius)
        for cell_x in range(min_cell[0], max_cell[0] + 1):
            for cell_y in range(min_cell[1], max_cell[1] + 1):
                yield (cell_x, cell_y)

    def _index_object(self, buckets, obj, padding=2):
        radius = getattr(obj, "radius", 0) + padding
        for cell in self._cells_for_bounds(obj.x, obj.y, radius):
            buckets.setdefault(cell, []).append(obj)

    def _make_static_signature(self):
        return (
            tuple(id(obj) for obj in self.game.buildings),
            tuple(id(obj) for obj in self.game.construction_sites),
            tuple(id(obj) for obj in self.game.resources),
        )

    def _ensure_static_index(self):
        # The signature itself is O(objects); compute it at most once per frame.
        frame = getattr(self.game, "frame_counter", 0)
        if self._static_signature_frame == frame and self._static_signature is not None:
            return
        self._static_signature_frame = frame
        signature = self._make_static_signature()
        if signature == self._static_signature:
            return
        self._static_buckets = {}
        self._static_kinds = {}
        for obj in self.game.buildings:
            self._index_object(self._static_buckets, obj)
            self._static_kinds[id(obj)] = "building"
        for obj in self.game.construction_sites:
            self._index_object(self._static_buckets, obj)
            self._static_kinds[id(obj)] = "site"
        for obj in self.game.resources:
            self._index_object(self._static_buckets, obj)
            self._static_kinds[id(obj)] = "resource"
        self._static_signature = signature

    def invalidate_static_index(self):
        """Force a signature re-check on the next query (world just changed)."""
        self._static_signature_frame = None

    def _rebuild_unit_index(self):
        self._unit_buckets = {}
        for unit in self.game.units:
            self._index_object(self._unit_buckets, unit)

    def _iter_bucket_objects(self, buckets, x, y, radius):
        seen = set()
        for cell in self._cells_for_bounds(x, y, radius):
            for obj in buckets.get(cell, ()):
                obj_id = id(obj)
                if obj_id in seen:
                    continue
                seen.add(obj_id)
                yield obj

    def _nearby_static(
        self,
        x,
        y,
        radius,
        *,
        include_buildings=True,
        include_construction_sites=True,
        include_resources=True,
    ):
        self._ensure_static_index()
        kinds = self._static_kinds
        for obj in self._iter_bucket_objects(self._static_buckets, x, y, radius + 2):
            kind = kinds.get(id(obj))
            if kind == "building":
                if include_buildings:
                    yield obj
            elif kind == "site":
                if include_construction_sites:
                    yield obj
            elif include_resources:
                yield obj

    def _nearby_units(self, x, y, radius, exclude=None):
        self.begin_frame()
        for unit in self._iter_bucket_objects(self._unit_buckets, x, y, radius + 2):
            if unit is not exclude:
                yield unit

    # ------------------------------------------------------------------
    # Shared spatial queries (Phase 1): the single index other systems use
    # instead of rescanning game.units / game.buildings.
    # ------------------------------------------------------------------
    def query_nearby_units(self, x, y, radius, exclude=None):
        """Units whose padded bounds may overlap the circle at (x, y)."""
        return list(self._nearby_units(x, y, radius, exclude=exclude))

    def query_nearby_static(
        self,
        x,
        y,
        radius,
        *,
        include_buildings=True,
        include_construction_sites=True,
        include_resources=True,
    ):
        """Static objects whose padded bounds may overlap the circle at (x, y)."""
        return list(
            self._nearby_static(
                x,
                y,
                radius,
                include_buildings=include_buildings,
                include_construction_sites=include_construction_sites,
                include_resources=include_resources,
            )
        )

    def query_obstacles_along(self, start, end, *, include_construction_sites=False, pad=80):
        """Obstacles (units + buildings + resources) near the segment start-end.

        Used to feed has_line_of_sight instead of rebuilding full world lists."""
        mid_x = (start[0] + end[0]) * 0.5
        mid_y = (start[1] + end[1]) * 0.5
        radius = math.hypot(end[0] - start[0], end[1] - start[1]) * 0.5 + pad
        obstacles = self.query_nearby_static(
            mid_x, mid_y, radius, include_construction_sites=include_construction_sites
        )
        obstacles.extend(self._nearby_units(mid_x, mid_y, radius))
        return obstacles

    def _record_collision_check(self):
        perf_stats.increment("collision_checks")
        
    def check_unit_collision_and_adjust(self, unit, new_pos, direction):
        """Smart collision detection with sliding behavior"""
        if not unit.collision:
            return new_pos
        self.begin_frame()

        original_pos = pygame.math.Vector2(unit.x, unit.y)
        final_pos = new_pos
        
        # First, check for collisions with static objects (buildings, construction sites)
        for building in self._nearby_static(
            final_pos.x,
            final_pos.y,
            unit.radius,
            include_resources=False,
        ):
            # Skip drop-off targets when unit is dropping off
            if (hasattr(unit, 'drop_off_target') and unit.drop_off_target == building and
                hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
                continue
            
            # Special handling for workers approaching their building target
            if (hasattr(unit, 'building_target') and unit.building_target == building):
                # Allow workers to get close to their construction site, but not too close
                min_distance = unit.radius + building.radius - 5  # Slight overlap allowed
            else:
                min_distance = unit.radius + building.radius + 2
                
            dx = final_pos.x - building.x
            dy = final_pos.y - building.y
            self._record_collision_check()
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < min_distance:
                # Calculate overlap amount
                overlap = min_distance - distance
                # Try sliding along the obstacle
                final_pos = self._calculate_slide_position(original_pos, final_pos, 
                                                         pygame.math.Vector2(building.x, building.y), 
                                                         min_distance,
                                                         unit, overlap)
        
        # Check resources
        for resource in self._nearby_static(
            final_pos.x,
            final_pos.y,
            unit.radius,
            include_buildings=False,
            include_construction_sites=False,
        ):
            dx = final_pos.x - resource.x
            dy = final_pos.y - resource.y
            self._record_collision_check()
            distance = math.sqrt(dx * dx + dy * dy)
            
            # For gathering targets, allow closer approach but prevent complete overlap
            if (hasattr(unit, 'gathering_target') and unit.gathering_target == resource):
                # Allow workers to get close enough to gather, but prevent them from overlapping
                pass
                # Minimum distance is just enough to prevent overlap
                # Workers can get as close as their radii allow without overlapping
                min_distance = unit.radius + resource.radius  # Prevent overlap but allow gathering
            else:
                # Normal collision distance for non-gathering targets
                pass
                min_distance = unit.radius + resource.radius + 2
            
            if distance < min_distance:
                # Calculate overlap amount
                pass
                overlap = min_distance - distance
                
                # If unit is gathering and severely overlapping, push it out immediately
                if (hasattr(unit, 'is_gathering') and unit.is_gathering and 
                    hasattr(unit, 'gathering_target') and unit.gathering_target == resource and
                    distance < unit.radius + resource.radius):
                    # Push unit directly away from resource to gathering distance
                    if distance > 0:
                        push_x = (unit.x - resource.x) / distance
                        push_y = (unit.y - resource.y) / distance
                    else:
                        # If exactly on center, push in random direction
                        import random
                        angle = random.random() * 2 * math.pi
                        push_x = math.cos(angle)
                        push_y = math.sin(angle)
                    
                    # Validate push direction against terrain, try alternate angles if needed
                    cand_x = resource.x + push_x * min_distance
                    cand_y = resource.y + push_y * min_distance
                    if not self._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
                        final_pos.x = cand_x
                        final_pos.y = cand_y
                    else:
                        # Try 7 alternate angles (45° increments)
                        base_angle = math.atan2(push_y, push_x)
                        found_safe = False
                        for i in range(1, 8):
                            alt_angle = base_angle + i * (math.pi / 4)
                            alt_x = resource.x + math.cos(alt_angle) * min_distance
                            alt_y = resource.y + math.sin(alt_angle) * min_distance
                            if not self._is_on_unwalkable_terrain(alt_x, alt_y, unit.radius):
                                final_pos.x = alt_x
                                final_pos.y = alt_y
                                found_safe = True
                                break
                        if not found_safe:
                            pass  # Stay put rather than push into water
                    debug_log.log(f"GATHERING: Pushed overlapping worker away from resource to distance {min_distance}", "COLLISION")
                else:
                    # Try sliding along the obstacle
                    final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                             pygame.math.Vector2(resource.x, resource.y),
                                                             min_distance,
                                                             unit, overlap)
        
        # Then check other units with special handling
        for other_unit in self._nearby_units(final_pos.x, final_pos.y, unit.radius, exclude=unit):
            # --- Drop-off right-of-way ---
            # Workers approaching a resource yield to workers carrying resources
            unit_is_carrier = getattr(unit, 'resource_amount', 0) > 0
            other_is_carrier = getattr(other_unit, 'resource_amount', 0) > 0
            unit_approaching = (getattr(unit, 'is_engaging', False) and getattr(unit, 'gathering_target', None) and not unit_is_carrier)

            if unit_approaching and other_is_carrier:
                # This unit is approaching a resource; other is carrying — yield
                self._record_collision_check()
                approach_dist = math.sqrt((final_pos.x - other_unit.x)**2 + (final_pos.y - other_unit.y)**2)
                if approach_dist < unit.radius + other_unit.radius + 2:
                    final_pos = original_pos
                    continue

            # Calculate distances
            self._record_collision_check()
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
                unit_radius = unit.radius if unit else 8
                # Validate terrain before accepting slide
                if not self._is_on_unwalkable_terrain(slide_pos.x, slide_pos.y, unit_radius):
                    return slide_pos
                # Try half-distance slide
                half_slide = start_pos + slide_vector.normalize() * move_distance * slide_factor * 0.5
                if (half_slide - obstacle_pos).length() >= min_distance - 1:
                    if not self._is_on_unwalkable_terrain(half_slide.x, half_slide.y, unit_radius):
                        return half_slide

        return start_pos  # Can't slide safely, stay in place
    
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
        for building in self._nearby_static(
            test_pos.x,
            test_pos.y,
            unit.radius,
            include_construction_sites=False,
            include_resources=False,
        ):
            self._record_collision_check()
            dist = math.sqrt((test_pos.x - building.x)**2 + (test_pos.y - building.y)**2)
            if dist < building.radius + unit.radius + 2:
                return True
        
        # Check resources
        for resource in self._nearby_static(
            test_pos.x,
            test_pos.y,
            unit.radius,
            include_buildings=False,
            include_construction_sites=False,
        ):
            self._record_collision_check()
            dist = math.sqrt((test_pos.x - resource.x)**2 + (test_pos.y - resource.y)**2)
            if dist < resource.radius + unit.radius + 2:
                return True
        
        # Check terrain with full radius to ensure unit doesn't overlap water
        return self._is_on_unwalkable_terrain(test_pos.x, test_pos.y, unit.radius)

    def _is_on_unwalkable_terrain(self, x, y, radius):
        """Lightweight 9-point terrain check. Returns True if any point is on water/lava."""
        probe = getattr(self.game_map, "nav_terrain_walkable", None)
        diag = radius * 0.7
        check_points = (
            (x, y),
            (x + radius, y), (x - radius, y),
            (x, y + radius), (x, y - radius),
            (x + diag, y + diag), (x - diag, y + diag),
            (x + diag, y - diag), (x - diag, y - diag),
        )
        if probe is not None:
            return any(not probe(cx, cy) for cx, cy in check_points)
        for cx, cy in check_points:
            hex_coord = self.game_map.world_to_grid(cx, cy)
            if hex_coord:
                col, row = hex_coord
                if 0 <= row < self.game_map.height and 0 <= col < self.game_map.width:
                    if self.game_map.grid[row][col] in {"water", "lava"}:
                        return True
        return False

    def separate_overlapping_units(self):
        """Push apart units that are overlapping with priority for drop-off workers"""
        self.begin_frame()
        base_separation_force = 0.8  # Increased base separation force
        
        for i, unit1 in enumerate(self.game.units):
            if not unit1.collision:
                continue
            nearby_units = {id(unit) for unit in self._nearby_units(unit1.x, unit1.y, unit1.radius, exclude=unit1)}
            for unit2 in self.game.units[i + 1:]:
                if id(unit2) not in nearby_units:
                    continue
                if not unit2.collision:
                    continue
                # Calculate distance between units
                pass
                dx = unit2.x - unit1.x
                dy = unit2.y - unit1.y
                self._record_collision_check()
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
                    
                    # Compute candidate positions, only apply if terrain is safe
                    cand1_x = unit1.x - dx_norm * separation_per_unit
                    cand1_y = unit1.y - dy_norm * separation_per_unit
                    cand2_x = unit2.x + dx_norm * separation_per_unit
                    cand2_y = unit2.y + dy_norm * separation_per_unit

                    if not self._is_on_unwalkable_terrain(cand1_x, cand1_y, unit1.radius):
                        unit1.x = cand1_x
                        unit1.y = cand1_y
                    if not self._is_on_unwalkable_terrain(cand2_x, cand2_y, unit2.radius):
                        unit2.x = cand2_x
                        unit2.y = cand2_y
    
    def _ensure_unit_on_walkable_terrain(self, unit):
        """Safety net: move unit out of unwalkable terrain using 9-point check"""
        if not self._is_on_unwalkable_terrain(unit.x, unit.y, unit.radius):
            return
        # Spiral search: 12 directions, up to 80px
        for search_radius in range(5, 85, 5):
            for angle_deg in range(0, 360, 30):
                test_x = unit.x + search_radius * math.cos(math.radians(angle_deg))
                test_y = unit.y + search_radius * math.sin(math.radians(angle_deg))
                if not self._is_on_unwalkable_terrain(test_x, test_y, unit.radius):
                    unit.x = test_x
                    unit.y = test_y
                    return
    
    def apply_separation_to_unit(self, unit):
        """Apply separation force to a specific unit if it's overlapping with others"""
        separation_applied = False
        max_separation_force = 2.0  # Stronger force for individual separation
        
        for other_unit in self._nearby_units(unit.x, unit.y, unit.radius, exclude=unit):
            # Calculate distance between units
            dx = unit.x - other_unit.x
            dy = unit.y - other_unit.y
            self._record_collision_check()
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
                
                # Validate before applying separation
                cand_x = unit.x + dx_norm * separation_force
                cand_y = unit.y + dy_norm * separation_force
                if not self._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
                    unit.x = cand_x
                    unit.y = cand_y
                    separation_applied = True
                # else: skip push to avoid water
                
                # For workers dropping off, prioritize separation over pathfinding
                if (hasattr(unit, 'is_dropping_off') and unit.is_dropping_off) or \
                   (hasattr(unit, 'drop_off_target') and unit.drop_off_target and unit.resource_amount > 0):
                    worker_tasks = getattr(self.game, "worker_task_system", None)
                    if worker_tasks and worker_tasks.owns(unit):
                        continue
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

        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks and worker_tasks.owns(unit):
            worker_tasks.request_repath(unit)
            return
        
        # Different strategies based on what the unit is doing
        if (hasattr(unit, 'drop_off_target') and unit.drop_off_target and 
            hasattr(unit, 'resource_amount') and unit.resource_amount > 0):
            # Worker trying to drop off resources
            # Try to use pathfinding if not already using it
            if not unit.path:
                self.game.pathfinder.issue_interact(unit, unit.drop_off_target, "dropoff")
            else:
                # Already has path but still stuck - skip current waypoint
                if unit.path_index < len(unit.path) - 1:
                    unit.path_index += 1
                    unit.destination = unit.path[unit.path_index]
                else:
                    # At last waypoint but stuck - clear path and try direct movement
                    unit.path = None
                    unit.path_index = 0
                    unit.destination = (unit.drop_off_target.x, unit.drop_off_target.y)
        elif hasattr(unit, 'gathering_target') and unit.gathering_target:
            # Worker trying to gather resources
            # Similar logic for gathering
            if not unit.path:
                self.game.pathfinder.issue_interact(unit, unit.gathering_target, "gather")
        elif hasattr(unit, 'current_target') and unit.current_target and hasattr(unit, 'is_engaging') and unit.is_engaging:
            # Combat unit trying to reach target
            # Force re-pathfinding
            unit._needs_repath = True
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = 100  # Trigger immediate re-evaluation
        
        else:
            # Generic movement - try to find alternate route
            if unit.destination:
                # If using direct movement, try pathfinding
                if not unit.path:
                    path = self.game.pathfinder.find_path(
                        (unit.x, unit.y), unit.destination, unit.radius, unit)
                    if path:
                        unit.path = path
                        unit.path_index = 0
                        unit.destination = path[0] if path else None
                else:
                    # Has path but stuck - try skipping waypoint
                    if unit.path_index < len(unit.path) - 1:
                        unit.path_index += 1
                        unit.destination = unit.path[unit.path_index]
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
            for building in self._nearby_static(
                check_x,
                check_y,
                radius,
                include_construction_sites=False,
                include_resources=False,
            ):
                self._record_collision_check()
                dist = math.sqrt((building.x - check_x)**2 + (building.y - check_y)**2)
                if dist < building.radius + radius + 2:
                    return building
            
            # Check collision with other units
            for other_unit in self._nearby_units(check_x, check_y, radius, exclude=unit):
                self._record_collision_check()
                dist = math.sqrt((other_unit.x - check_x)**2 + (other_unit.y - check_y)**2)
                if dist < other_unit.radius + radius + 2:
                    return other_unit
            
            # Check collision with resources
            for resource in self._nearby_static(
                check_x,
                check_y,
                radius,
                include_buildings=False,
                include_construction_sites=False,
            ):
                self._record_collision_check()
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
                    obstacles = list(self._nearby_static(detour_x, detour_y, unit_radius, include_construction_sites=False))
                    obstacles.extend(self._nearby_units(detour_x, detour_y, unit_radius))
                    for obj in obstacles:
                        self._record_collision_check()
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
        for other_unit in self._nearby_units(position.x, position.y, unit.radius + buffer, exclude=unit):
            obstacles.append(other_unit)
        
        # Add buildings (unless it's the unit's drop-off target)
        for building in self._nearby_static(
            position.x,
            position.y,
            unit.radius + buffer,
            include_construction_sites=False,
            include_resources=False,
        ):
            if hasattr(unit, 'drop_off_target') and building == unit.drop_off_target:
                continue
            obstacles.append(building)
        
        # Add resources (unless it's the unit's gathering target)
        for resource in self._nearby_static(
            position.x,
            position.y,
            unit.radius + buffer,
            include_buildings=False,
            include_construction_sites=False,
        ):
            if hasattr(unit, 'gathering_target') and resource == unit.gathering_target:
                continue
            obstacles.append(resource)
        
        # Check collision with all obstacles
        for obstacle in obstacles:
            self._record_collision_check()
            distance = math.sqrt((position.x - obstacle.x)**2 + (position.y - obstacle.y)**2)
            min_distance = unit.radius + obstacle.radius + buffer
            
            if distance < min_distance:
                return False
        
        return True

    def get_safe_position(self, unit, target_pos):
        """Checks if a target position is valid and returns a safe position if not."""
        # Check for collisions at the target position
        obstacles = list(self._nearby_static(target_pos[0], target_pos[1], unit.radius, include_construction_sites=False))
        obstacles.extend(self._nearby_units(target_pos[0], target_pos[1], unit.radius, exclude=unit))
        for obstacle in obstacles:
            self._record_collision_check()
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

                # Validate nudge position against terrain
                if not self._is_on_unwalkable_terrain(safe_x, safe_y, unit.radius):
                    return (safe_x, safe_y)
                # Try 7 alternate angles
                base_angle = math.atan2(direction_y, direction_x)
                for i in range(1, 8):
                    alt_angle = base_angle + i * (math.pi / 4)
                    alt_x = obstacle.x + math.cos(alt_angle) * nudge_distance
                    alt_y = obstacle.y + math.sin(alt_angle) * nudge_distance
                    if not self._is_on_unwalkable_terrain(alt_x, alt_y, unit.radius):
                        return (alt_x, alt_y)
                # All directions unsafe, return original target rather than push into water
                return target_pos

        # Position is safe
        return target_pos
