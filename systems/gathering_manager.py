import math
from core.config import GATHERING_DISTANCE_MULTIPLIER, GATHERING_RATES, DROP_OFF_BUILDINGS, DROP_OFF_DELAY, FARM_FOOD_AMOUNT, FARM_FOOD_INTERVAL
from utils.debug_logger import debug_log

def get_gathering_distance(worker, resource):
    """Calculate the gathering distance between a worker and resource"""
    # Treat resources like other game objects - keep proper distance
    combined_radius = worker.radius + resource.radius
    buffer = combined_radius * 0.1  # 10% buffer as requested
    return combined_radius + buffer + 5  # Additional 5px safety margin

def get_drop_off_distance(worker, building):
    """Calculate the drop-off distance between a worker and building"""
    # Use same logic as gathering distance for consistency
    combined_radius = worker.radius + building.radius
    buffer = combined_radius * 0.1  # 10% buffer as requested
    return combined_radius + buffer + 5  # Additional 5px safety margin

class GatheringManager:
    def __init__(self, game):
        self.game = game
        
    def update(self, delta_time):
        """Update all gathering workers, farms, and tree regrowth"""
        for unit in self.game.units:
            if unit.name == "worker" and unit.is_gathering:
                self._update_gathering_worker(unit, delta_time)
        
        # Update farms - automatic food generation (10 food every 10 seconds)
        for building in self.game.buildings:
            if building.name == "farm" and building.hp > 0:
                # Initialize farm timer if not exists
                pass
                if not hasattr(building, 'food_timer'):
                    building.food_timer = 0.0
                    
                building.food_timer += delta_time
                
                # Generate food based on config values
                if building.food_timer >= FARM_FOOD_INTERVAL:
                    food_amount = FARM_FOOD_AMOUNT
                    if building.player:
                        building.player.resources["food"] += int(food_amount)
                        
                    # Add floating notification
                    if hasattr(self.game, 'floating_ui') and self.game.floating_ui:
                        self.game.floating_ui.add_resource_notification(building, "food", food_amount)
                    
                    building.food_timer = 0.0  # Reset timer
                    # Debug: Farm produced food
        
        # Tree regrowth: track depleted tree positions and regrow after timer
        self._update_tree_regrowth(delta_time)
        
    
    def _update_gathering_worker(self, worker, delta_time):
        """Update a single gathering worker"""
        if worker.gathering_target and worker.gathering_target.amount_remaining > 0:
            # Track gathering progress to detect stuck workers
            if not hasattr(worker, '_last_resource_amount'):
                worker._last_resource_amount = worker.resource_amount
                worker._gathering_no_progress_timer = 0
            
            # Check if still in range
            pass
            distance = self._get_distance(worker, worker.gathering_target)
            gathering_distance = get_gathering_distance(worker, worker.gathering_target)
            if distance <= gathering_distance:
                # Gather resources
                pass
                resource_type = worker.gathering_target.name
                
                # Apply player's gathering rate multiplier
                base_rate = GATHERING_RATES.get(resource_type, 1)
                player_multiplier = 1.0
                if hasattr(worker, 'player') and worker.player:
                    player_multiplier = worker.player.gathering_rates.get(resource_type, 1.0)
                    # Apply tech gathering multiplier
                    tech_multiplier = getattr(worker.player, 'tech_gathering_multiplier', 1.0)
                    player_multiplier *= tech_multiplier
                gather_rate = base_rate * player_multiplier
                amount_to_gather = gather_rate * delta_time
                
                # Check capacity
                current_capacity = worker.max_capacity.get(worker.gathering_target.name, 20)
                space_left = current_capacity - worker.resource_amount
                
                if space_left > 0:
                    # Gather resources
                    pass
                    actual_gathered = min(amount_to_gather, space_left, worker.gathering_target.amount_remaining)
                    worker.resource_amount += actual_gathered
                    worker.resource_type = resource_type
                    worker.gathering_target.amount_remaining -= actual_gathered
                    
                    # Update animation
                    worker.status = "gather"
                    worker.gathering_timer += delta_time
                    
                    # Reset progress timer if actually gathering
                    if actual_gathered > 0:
                        worker._gathering_no_progress_timer = 0
                    else:
                        # Not making progress
                        worker._gathering_no_progress_timer += delta_time
                        
                        if worker._gathering_no_progress_timer > 2.0:
                            debug_log.log(f"WARNING: Worker not gathering despite being in range for {worker._gathering_no_progress_timer:.1f}s", "GATHERING")
                            debug_log.log(f"  - Distance: {distance:.1f}, Required: {gathering_distance:.1f}", "GATHERING")
                            debug_log.log(f"  - Worker radius: {worker.radius}, Resource radius: {worker.gathering_target.radius}", "GATHERING")
                            
                            # Force stop gathering to trigger re-approach
                            worker.is_gathering = False
                            worker.status = "idle"
                            worker._gathering_no_progress_timer = 0
                    
                    worker._last_resource_amount = worker.resource_amount
                else:
                    # Worker is full, needs to drop off
                    pass
                    worker.is_gathering = False
                    # Keep gathering_target for now - will be cleared after drop-off path is set
                    self._find_drop_off_location(worker)
            else:
                # Out of range, stop gathering
                pass
                worker.is_gathering = False
                worker.gathering_target = None
        else:
            # Resource depleted or invalid
            debug_log.log(f"Worker at ({worker.x:.0f}, {worker.y:.0f}) stopped gathering - resource depleted or invalid", "GATHERING")
            
            # Clear gathering state
            worker.is_gathering = False
            worker.gathering_target = None
            worker.status = "idle"
            
            # Clear any movement state
            worker.destination = None
            worker.path = None
            worker.path_index = 0
            worker.path_target = None
            worker.is_engaging = False
            
            # Remove worker from resource's gatherer list if resource still exists
            if hasattr(worker, 'gathering_target') and worker.gathering_target and hasattr(worker.gathering_target, 'gatherers'):
                if worker in worker.gathering_target.gatherers:
                    worker.gathering_target.gatherers.remove(worker)
    
    def reserve_gathering_position(self, worker, resource):
        """Reserve a unique gathering position around a resource for a worker.

        Call this BEFORE pathfinding so the worker paths to its own slot
        instead of the resource center.  Adds the worker to
        ``resource.gatherers`` and returns ``(x, y)``.
        """
        if not hasattr(resource, 'gatherers'):
            resource.gatherers = []

        # Clean up invalid gatherers
        resource.gatherers = [
            g for g in resource.gatherers
            if g and hasattr(g, 'hp') and g.hp > 0
            and (getattr(g, 'gathering_target', None) == resource
                 or getattr(g, 'previous_gathering_target', None) == resource)
        ]

        # Register this worker
        if worker not in resource.gatherers:
            resource.gatherers.append(worker)

        # Compute a unique angle slot for this worker
        worker_index = resource.gatherers.index(worker)
        gatherer_count = len(resource.gatherers)
        gathering_radius = get_gathering_distance(worker, resource)

        # Evenly distribute around the resource (minimum 8 slots)
        num_slots = max(8, gatherer_count * 2)
        angle = worker_index * (2 * math.pi / num_slots)

        gx = resource.x + math.cos(angle) * gathering_radius
        gy = resource.y + math.sin(angle) * gathering_radius

        if self._is_valid_gathering_position(gx, gy, worker):
            return (gx, gy)

        # Try nearby angles if primary is blocked
        angle_step = 2 * math.pi / num_slots
        for offset in [0.5, -0.5, 1.0, -1.0]:
            alt_angle = angle + offset * angle_step
            ax = resource.x + math.cos(alt_angle) * gathering_radius
            ay = resource.y + math.sin(alt_angle) * gathering_radius
            if self._is_valid_gathering_position(ax, ay, worker):
                return (ax, ay)

        # Fallback: resource center (original behaviour)
        return (resource.x, resource.y)

    def start_gathering(self, worker, resource):
        """Start a worker gathering from a resource"""
        if worker.name != "worker":
            return False
            
        # Check if resource has any remaining
        if resource.amount_remaining <= 0:
            return False
            
        # Check distance
        distance = self._get_distance(worker, resource)
        gathering_distance = get_gathering_distance(worker, resource)
        if distance > gathering_distance:
            return False
            
        # Clear engagement state only if worker is actually starting to gather
        # This prevents breaking the movement system's tracking
        if hasattr(worker, 'is_engaging'):
            worker.is_engaging = False
        
        # Start gathering
        worker.is_gathering = True
        worker.gathering_target = resource
        worker.status = "gather"
        
        # Add worker to resource's gatherer list with positioning
        if worker not in resource.gatherers:
            resource.gatherers.append(worker)
            
        # Calculate and assign gathering position for this worker
        try:
            gathering_pos = self._calculate_gathering_position(worker, resource)
            if gathering_pos:
                worker.gathering_position = gathering_pos
        except Exception as e:
            # Fallback: use resource position
            worker.gathering_position = (resource.x, resource.y)
        
        return True
    
    def drop_off_resources(self, worker, building, delta_time=0.016):
        """Drop off resources at a building"""
        if not worker.resource_amount or not worker.resource_type:
            return False
            
        # Check if this is a valid drop-off building
        valid_buildings = DROP_OFF_BUILDINGS.get(worker.resource_type, [])
        if building.name not in valid_buildings:
            return False
            
        # Check distance using same logic as gathering
        distance = self._get_distance(worker, building)
        required_distance = get_drop_off_distance(worker, building)
        if distance > required_distance:
            return False
            
        # Start drop-off process with delay
        if not worker.is_dropping_off:
            worker.drop_off_timer = 0.0
            worker.is_dropping_off = True
            worker.status = "idle"  # Use idle animation during drop-off
            # Debug: Worker starting drop-off
            return False  # Not finished yet
        
        # Update drop-off timer
        worker.drop_off_timer += delta_time
        
        if worker.drop_off_timer >= DROP_OFF_DELAY:
            # Drop off resources
            pass
            dropped_amount = worker.resource_amount
            dropped_type = worker.resource_type
            
            if worker.player:
                worker.player.resources[worker.resource_type] += int(worker.resource_amount)
                
            # Debug: Worker dropped off resources
            
            # Add floating notification
            if hasattr(self.game, 'floating_ui') and self.game.floating_ui:
                self.game.floating_ui.add_resource_notification(building, dropped_type, dropped_amount)
            
            # Clear worker's inventory and timer
            worker.resource_amount = 0
            worker.resource_type = None
            worker.drop_off_target = None
            worker.drop_off_timer = 0.0
            worker.is_dropping_off = False
            worker.status = "idle"  # Ensure worker returns to idle state
            
            # Restore gathering target if it still exists and has resources
            if (hasattr(worker, 'previous_gathering_target') and 
                worker.previous_gathering_target and 
                worker.previous_gathering_target.amount_remaining > 0):
                worker.gathering_target = worker.previous_gathering_target
                worker.previous_gathering_target = None
                # Debug: Worker will return to gather
            else:
                worker.previous_gathering_target = None
            
        return True
    
    def _update_tree_regrowth(self, delta_time):
        """Handle tree regrowth from depleted tree positions"""
        # Initialize regrowth tracker on game if not present
        if not hasattr(self.game, '_tree_regrowth'):
            self.game._tree_regrowth = []  # List of (x, y, timer)
        
        # Update timers
        regrown = []
        for i, (x, y, timer) in enumerate(self.game._tree_regrowth):
            self.game._tree_regrowth[i] = (x, y, timer - delta_time)
            if timer - delta_time <= 0:
                regrown.append((x, y))
        
        # Remove regrown entries and spawn new trees
        self.game._tree_regrowth = [t for t in self.game._tree_regrowth if t[2] > 0]
        
        for x, y in regrown:
            # Check position is still valid (not blocked by buildings)
            blocked = False
            for building in self.game.buildings:
                dist = math.sqrt((x - building.x)**2 + (y - building.y)**2)
                if dist < building.radius + 20:
                    blocked = True
                    break
            
            if not blocked:
                from entities import Resource
                template = self.game.game_data["resources"].get("wood")
                if template:
                    tree = Resource(
                        name=template.name,
                        sprite=template.sprite,
                        radius=template.radius,
                    )
                    tree.x = x
                    tree.y = y
                    self.game.resources.append(tree)
                    self.game.pathfinder.mark_dirty()
        
        return False  # Still dropping off
    
    
    def _find_drop_off_location(self, worker):
        """Find the nearest drop-off location for a worker"""
        if not worker.resource_type:
            return
            
        valid_buildings = DROP_OFF_BUILDINGS.get(worker.resource_type, [])
        nearest_building = None
        nearest_distance = float('inf')
        
        # Check all buildings
        for building in self.game.buildings:
            if building.name in valid_buildings and building.player == worker.player:
                distance = self._get_distance(worker, building)
                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_building = building
        
        if nearest_building:
            worker.drop_off_target = nearest_building
            
            # Pathfind to drop-off building (excluded from collision)
            path = self.game.pathfinder.find_path(
                (worker.x, worker.y),
                (nearest_building.x, nearest_building.y),
                worker.radius,
                worker,
                drop_off_target=nearest_building
            )
            
            if path:
                worker.path = path
                worker.path_index = 0
                # Use the actual reachable position as target (may be different from building center)
                worker.path_target = path[-1] if path else (nearest_building.x, nearest_building.y)
                worker.destination = path[0] if path else None
                worker.status = "run"
                
                # Preserve gathering target for return after drop-off
                worker.previous_gathering_target = worker.gathering_target
                worker.gathering_target = None
                
                # Check if we had to redirect to a reachable position
                final_pos = path[-1]
                distance_to_building = ((final_pos[0] - nearest_building.x)**2 + (final_pos[1] - nearest_building.y)**2) ** 0.5
                if distance_to_building > nearest_building.radius + worker.radius + 10:
                    # Debug: Worker moving to drop off from reachable position
                    pass
                    pass
                else:
                    # Debug: Worker moving to drop off
                    pass
                    pass
            else:
                # Fallback: try to find a reachable position manually
                pass
                closest_reachable = pathfinder._find_closest_reachable_position(
                    (worker.x, worker.y), (nearest_building.x, nearest_building.y), worker.radius)
                
                if closest_reachable:
                    # Debug: No path found, moving to closest reachable position
                    pass
                    worker.destination = closest_reachable
                    worker.path = None
                    worker.path_index = 0
                    worker.path_target = closest_reachable
                    worker.status = "run"
                else:
                    # Complete fallback: try direct movement to building center (original behavior)
                    pass
                    # Debug: No reachable position found, trying direct movement
                    worker.destination = (nearest_building.x, nearest_building.y)
                    worker.path = None
                    worker.path_index = 0
                    worker.path_target = (nearest_building.x, nearest_building.y)
                    worker.status = "run"
    
    def _get_distance(self, obj1, obj2):
        """Calculate distance between two objects"""
        dx = obj1.x - obj2.x
        dy = obj1.y - obj2.y
        return math.sqrt(dx * dx + dy * dy)
    
    def _calculate_gathering_position(self, worker, resource):
        """Calculate optimal gathering position around resource to avoid crowding"""
        if not hasattr(resource, 'gatherers'):
            resource.gatherers = []
            
        # Clean up any invalid gatherers (dead, None, or no longer gathering this resource)
        resource.gatherers = [g for g in resource.gatherers 
                             if g and hasattr(g, 'hp') and g.hp > 0 
                             and hasattr(g, 'gathering_target') 
                             and g.gathering_target == resource]
            
        # Ensure worker is in gatherers list
        if worker not in resource.gatherers:
            resource.gatherers.append(worker)
            
        # Get stable snapshot of gatherer list to prevent issues during iteration
        gatherers_snapshot = list(resource.gatherers)  # Create copy to prevent modification issues
        gatherer_count = len(gatherers_snapshot)
        
        # Safely find worker index
        try:
            worker_index = gatherers_snapshot.index(worker)
        except ValueError:
            # This should not happen now, but keep as safety
            debug_log.log(f"Warning: Worker still not found after adding to gatherers list", "GATHERING")
            worker_index = 0  # Use first position as fallback
        
        # Define gathering radius around resource - use the official gathering distance
        gathering_radius = get_gathering_distance(worker, resource)
        
        # Calculate angle for this worker (evenly distribute around circle)
        angle_per_worker = (2 * math.pi) / max(8, gatherer_count * 2)  # At least 8 positions, more if needed
        worker_angle = worker_index * angle_per_worker
        
        # Calculate position
        gather_x = resource.x + math.cos(worker_angle) * gathering_radius
        gather_y = resource.y + math.sin(worker_angle) * gathering_radius
        
        # Validate position (check if it's accessible)
        if self._is_valid_gathering_position(gather_x, gather_y, worker):
            return (gather_x, gather_y)
        
        # If primary position is blocked, try alternative positions
        for offset in [0.5, -0.5, 1.0, -1.0]:
            alt_angle = worker_angle + (offset * angle_per_worker)
            alt_x = resource.x + math.cos(alt_angle) * gathering_radius
            alt_y = resource.y + math.sin(alt_angle) * gathering_radius
            
            if self._is_valid_gathering_position(alt_x, alt_y, worker):
                return (alt_x, alt_y)
        
        # Fallback: return resource position
        return (resource.x, resource.y)
    
    def _is_valid_gathering_position(self, x, y, worker):
        """Check if a gathering position is valid (no terrain/collision issues)"""
        # Check terrain
        hex_coord = self.game.game_map.world_to_grid(x, y)
        if hex_coord:
            row, col = hex_coord
            if (0 <= row < len(self.game.game_map.grid) and 
                0 <= col < len(self.game.game_map.grid[row])):
                tile_type = self.game.game_map.grid[row][col]
                if tile_type in {"water", "lava"}:
                    return False
        
        # Check collision with buildings (allow some overlap with resources and units)
        for building in self.game.buildings:
            distance = math.sqrt((x - building.x)**2 + (y - building.y)**2)
            if distance < building.radius + worker.radius + 5:
                return False
        
        return True