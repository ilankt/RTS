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
            tuple(id(obj) for obj in getattr(self.game, "fountains", ())),
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
        # §8.9 fountains: indexed as "resource" on purpose — they block
        # movement and placement, and every combat-targeting query filters
        # resources out, so nothing ever tries to shoot the fountain.
        for obj in getattr(self.game, "fountains", ()):
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
            # Open gates are passable (§8.10)
            if getattr(building, "passable", False):
                continue
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
                    if debug_log.enabled("COLLISION"):
                        debug_log.log(f"GATHERING: Pushed overlapping worker away from resource to distance {min_distance}", "COLLISION")
                else:
                    # Try sliding along the obstacle
                    final_pos = self._calculate_slide_position(original_pos, final_pos,
                                                             pygame.math.Vector2(resource.x, resource.y),
                                                             min_distance,
                                                             unit, overlap)
        
        # Then check other units: right-of-way rules (B4) - the higher-priority
        # unit proceeds and parts the crowd, the lower-priority one yields.
        # Context steering already avoids most of these contacts proactively.
        for other_unit in self._nearby_units(final_pos.x, final_pos.y, unit.radius, exclude=unit):
            if not getattr(other_unit, "collision", True):
                continue
            self._record_collision_check()
            min_distance = unit.radius + other_unit.radius + 2
            new_distance = math.hypot(final_pos.x - other_unit.x, final_pos.y - other_unit.y)
            if new_distance >= min_distance:
                continue
            current_distance = math.hypot(unit.x - other_unit.x, unit.y - other_unit.y)
            if current_distance < min_distance and new_distance > current_distance:
                continue  # Already overlapping - always allow separating moves

            # Ignore units pressing on our back: a convoy leader must not
            # yield to its own followers or the whole column freezes.
            rel_x = other_unit.x - unit.x
            rel_y = other_unit.y - unit.y
            if (
                direction.x * rel_x + direction.y * rel_y <= 0
                and current_distance >= (unit.radius + other_unit.radius) * 0.9
            ):
                continue

            if self._has_right_of_way(unit, other_unit):
                # Part the crowd: nudge the other unit sideways a bit.
                self._nudge_aside(other_unit, unit, direction)
                if new_distance < (unit.radius + other_unit.radius) * 0.75:
                    # Too deep to push through this frame - hold position and
                    # let the nudge open space.
                    final_pos = original_pos
            else:
                # Yield - but creep sideways instead of freezing so crowded
                # piles drain instead of deadlocking.
                sidestep = self._yield_sidestep(unit, other_unit, original_pos, direction)
                final_pos = sidestep if sidestep is not None else original_pos

        return final_pos

    def _yield_sidestep(self, unit, other_unit, original_pos, direction):
        """Small perpendicular step away from the conflict, if safe."""
        offset_x = unit.x - other_unit.x
        offset_y = unit.y - other_unit.y
        norm = math.hypot(offset_x, offset_y)
        if norm < 1e-6:
            return None
        perp_x = -offset_y / norm
        perp_y = offset_x / norm
        # Prefer the side that still makes progress toward our goal.
        if perp_x * direction.x + perp_y * direction.y < 0:
            perp_x = -perp_x
            perp_y = -perp_y
        cand_x = original_pos.x + perp_x * 1.5
        cand_y = original_pos.y + perp_y * 1.5
        if self._is_on_unwalkable_terrain(cand_x, cand_y, unit.radius):
            return None
        candidate = pygame.math.Vector2(cand_x, cand_y)
        if self._would_collide_with_static(unit, candidate):
            return None
        return candidate

    @staticmethod
    def _unit_priority(unit):
        """Right-of-way class: carrier > mover > idle (B4)."""
        if getattr(unit, "resource_amount", 0) > 0:
            return 2
        if getattr(unit, "path", None) or getattr(unit, "destination", None):
            return 1
        return 0

    def _has_right_of_way(self, unit, other_unit):
        return (self._unit_priority(unit), id(unit)) > (self._unit_priority(other_unit), id(other_unit))

    def _nudge_aside(self, other_unit, mover, mover_direction):
        """Push a lower-priority unit perpendicular to the mover's direction."""
        if mover_direction.length_squared() < 1e-9:
            return
        perp_x = -mover_direction.y
        perp_y = mover_direction.x
        offset_x = other_unit.x - mover.x
        offset_y = other_unit.y - mover.y
        if offset_x * perp_x + offset_y * perp_y < 0:
            perp_x = -perp_x
            perp_y = -perp_y
        push = 2.5
        cand_x = other_unit.x + perp_x * push
        cand_y = other_unit.y + perp_y * push
        if self._is_on_unwalkable_terrain(cand_x, cand_y, other_unit.radius):
            return
        candidate = pygame.math.Vector2(cand_x, cand_y)
        if self._would_collide_with_static(other_unit, candidate):
            return
        other_unit.x = cand_x
        other_unit.y = cand_y
    
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
            if getattr(building, "passable", False):
                continue  # open gate (§8.10)
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

    # Separation acts only on *deep* overlaps (movement holds at 0.75x radii
    # sum) with a small capped push, so it can't fight steering or make an
    # arrived crowd churn.
    SEPARATION_TRIGGER_FACTOR = 0.9
    SEPARATION_MAX_PUSH = 1.5

    def separate_overlapping_units(self):
        """Gently push apart units that are deeply overlapping."""
        self.begin_frame()
        for i, unit1 in enumerate(self.game.units):
            if not unit1.collision:
                continue
            nearby_units = {id(unit) for unit in self._nearby_units(unit1.x, unit1.y, unit1.radius, exclude=unit1)}
            for unit2 in self.game.units[i + 1:]:
                if id(unit2) not in nearby_units:
                    continue
                if not unit2.collision:
                    continue
                dx = unit2.x - unit1.x
                dy = unit2.y - unit1.y
                self._record_collision_check()
                distance = math.sqrt(dx * dx + dy * dy)

                trigger_distance = (unit1.radius + unit2.radius) * self.SEPARATION_TRIGGER_FACTOR
                if distance >= trigger_distance or distance <= 0:
                    continue

                overlap = trigger_distance - distance
                push = min(self.SEPARATION_MAX_PUSH, overlap * 0.5)

                dx_norm = dx / distance
                dy_norm = dy / distance

                cand1_x = unit1.x - dx_norm * push
                cand1_y = unit1.y - dy_norm * push
                cand2_x = unit2.x + dx_norm * push
                cand2_y = unit2.y + dy_norm * push

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
                    # Has path but stuck - try skipping waypoint. §8.13.3:
                    # never skip onto a leg that crosses blocked terrain —
                    # waypoints are sparse (greedy smoothing), so skipping
                    # one around a lake discards the whole detour and aims
                    # the unit straight across the bay.
                    skipped = False
                    if unit.path_index < len(unit.path) - 1:
                        next_point = unit.path[unit.path_index + 1]
                        if self.game.pathfinder.grid.segment_clear(
                                (unit.x, unit.y), next_point, unit.radius):
                            unit.path_index += 1
                            unit.destination = next_point
                            skipped = True
                    if not skipped:
                        # Out of skippable waypoints (or the skip would cross
                        # water): re-plan the remaining leg from here. The old
                        # code did NOTHING in this state, so a unit whose last
                        # leg crossed a lake re-blocked every 0.5 s forever.
                        goal = unit.path_target or unit.path[-1]
                        fresh = self.game.pathfinder.find_path(
                            (unit.x, unit.y), goal, unit.radius, unit)
                        if fresh:
                            unit.path = fresh
                            unit.path_index = 0
                            unit.destination = fresh[0]
                            unit.path_target = goal
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
