import json
import math
from entities import Unit
from systems.animation import Animation
from core.config import TILE_WIDTH
from utils.debug_logger import debug_log

class ProductionManager:
    """Manages unit production for buildings"""
    
    def __init__(self, game):
        self.game = game
        self.units_data = self._load_units_data()
    
    def _load_units_data(self):
        """Load unit data from JSON file"""
        try:
            with open('data/units.json', 'r') as f:
                units_list = json.load(f)
            # Convert to dict for easier lookup
            units_dict = {}
            for unit in units_list:
                units_dict[unit['name']] = unit
            return units_dict
        except:
            return {}
    
    def start_production(self, building, unit_type):
        """Start producing a unit in a building"""
        if not building.can_produce or unit_type not in building.can_produce:
            return False, f"Building {building.name} cannot produce {unit_type}"
        
        if unit_type not in self.units_data:
            return False, f"Unit type {unit_type} not found"
        
        unit_data = self.units_data[unit_type]
        costs = unit_data.get('costs', {})
        
        # Check if player can afford the unit
        if not self._can_afford(building.player, costs):
            return False, "Cannot afford unit"
        
        # If already producing, add to queue — paid up front, like the
        # immediate start, so the queue can't order units for free (§7.4)
        if building.current_production:
            if len(building.production_queue) >= self.MAX_QUEUE:
                return False, "Queue is full"
            for resource, amount in costs.items():
                building.player.resources[resource] -= amount
            building.production_queue.append(unit_type)
            return True, f"Added {unit_type} to queue"

        # Start production immediately
        return self._start_immediate_production(building, unit_type, unit_data, costs)

    MAX_QUEUE = 5  # queued entries beyond the one in progress

    def _start_immediate_production(self, building, unit_type, unit_data, costs, charge=True):
        """Start production now. charge=False for queue pops (paid on queue)."""
        if charge:
            for resource, amount in costs.items():
                building.player.resources[resource] -= amount

        # Start production
        building.current_production = {
            "unit_type": unit_type,
            "progress": 0.0,
            "total_time": unit_data.get('build_time', 10),
            "unit_data": unit_data
        }

        return True, f"Started producing {unit_type}"

    def _start_next_queued(self, building):
        """Pop the queue into production. Queued units were already paid for."""
        while building.production_queue:
            next_unit_type = building.production_queue.pop(0)
            unit_data = self.units_data.get(next_unit_type)
            if unit_data is None:
                continue
            self._start_immediate_production(
                building, next_unit_type, unit_data, unit_data.get('costs', {}), charge=False
            )
            return

    def cancel_queued(self, building, unit_type):
        """Remove the last queued unit of a type, refunding its full cost."""
        for i in range(len(building.production_queue) - 1, -1, -1):
            if building.production_queue[i] != unit_type:
                continue
            building.production_queue.pop(i)
            costs = self.units_data.get(unit_type, {}).get('costs', {})
            for resource, amount in costs.items():
                building.player.resources[resource] += amount
            return True, f"Removed {unit_type} from queue"
        return False, f"No {unit_type} queued"
    
    def _can_afford(self, player, costs):
        """Check if player can afford the costs"""
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False
        return True
    
    def update(self, delta_time):
        """Update production progress for all buildings"""
        for building in self.game.buildings:
            if building.current_production:
                self._update_building_production(building, delta_time)
    
    def _update_building_production(self, building, delta_time):
        """Update production for a single building"""
        production = building.current_production
        production["progress"] += delta_time
        
        # Check if production is complete
        if production["progress"] >= production["total_time"]:
            self._complete_production(building)
    
    def _complete_production(self, building):
        """Complete unit production and spawn the unit"""
        production = building.current_production
        unit_type = production["unit_type"]
        unit_data = production["unit_data"]
        
        # Find spawn position near building
        spawn_pos = self._find_spawn_position(building)
        
        # Create the unit
        new_unit = Unit(
            name=unit_type,
            size=unit_data['size'],
            hp=unit_data['hp'],
            movement_speed=unit_data['movement_speed'],
            attack=unit_data.get('attack'),
            animations={},  # Will be set up by sprite manager
            x=spawn_pos[0],
            y=spawn_pos[1],
            radius=unit_data['size'][0] * TILE_WIDTH / 8,  # TILE_WIDTH / 8 for smaller units
            player=building.player,
            can_build=unit_data.get('can_build', False),
            can_attack=unit_data.get('can_attack', False),
            min_damage=unit_data.get('min_damage', 0),
            max_damage=unit_data.get('max_damage', 0),
            attack_type=unit_data.get('attack_type', 'slash'),
            armor_type=unit_data.get('armor_type', 'light'),
            armor_value=unit_data.get('armor_value', 0),
            attack_speed=unit_data.get('attack_speed', 1.0),
            attack_range=unit_data.get('attack_range', 32),
            display_name=unit_data.get('display_name'),
            role=unit_data.get('role', ''),
            requires=unit_data.get('requires', []),
            buildable=unit_data.get('buildable', True),
            strong_against=unit_data.get('strong_against', []),
            weak_against=unit_data.get('weak_against', []),
            building_only_attack=unit_data.get('building_only_attack', False),
        )
        
        # Set up animations using sprite manager
        self._setup_unit_animations(new_unit, unit_data)

        # Add to game
        self.game.units.append(new_unit)

        # Match statistics (§8.8)
        stats = getattr(self.game, "stats_units_trained", None)
        if stats is not None:
            key = (building.player.name, unit_type)
            stats[key] = stats.get(key, 0) + 1

        # Rally point (§7.4): send the fresh unit on its way
        self._apply_rally(building, new_unit)
        
        # Invalidate AI memory cache for immediate detection of new unit
        if hasattr(self.game, 'ai_system') and self.game.ai_system:
            self.game.ai_system.invalidate_memory_cache(building.player)
            debug_log.log(f"AI: Invalidated memory cache for {building.player.name} after producing {unit_type}", "PRODUCTION")
        
        # Clear current production
        building.current_production = None

        # Start next in queue if any (already paid for)
        self._start_next_queued(building)
    
    def _apply_rally(self, building, unit):
        """Path a newly produced unit to its building's rally point, if any.

        Workers rallied onto a resource start gathering it directly."""
        resource = getattr(building, "rally_resource", None)
        if resource is not None and (
            not getattr(resource, "in_world", True) or getattr(resource, "amount_remaining", 0) <= 0
        ):
            building.rally_resource = resource = None  # depleted since it was set
        if resource is not None and unit.name == "worker":
            worker_tasks = getattr(self.game, "worker_task_system", None)
            if worker_tasks and worker_tasks.assign_gather(unit, resource):
                return
        point = getattr(building, "rally_point", None)
        if point:
            self.game.pathfinder.issue_move(unit, point)

    def _find_spawn_position(self, building):
        """Find a valid spawn position near the building.

        BUG FIX (user-reported): the old version tried 8 points on ONE ring
        and then fell back to the BUILDING CENTER — when produced units
        crowded the barracks (common now that armies mass at home), every
        point failed and new units spawned INSIDE the building, stuck.
        Now: widen the search over several rings; if still crowded, allow
        overlapping UNITS (the separation pass shoves them apart) but never
        statics; the building center is never returned."""
        rings = (40, 72, 104, 136)
        for ring in rings:
            distance = building.radius + ring
            for angle in range(0, 360, 30):
                angle_rad = math.radians(angle)
                spawn_x = building.x + math.cos(angle_rad) * distance
                spawn_y = building.y + math.sin(angle_rad) * distance
                if self._is_valid_spawn_position(spawn_x, spawn_y):
                    return (spawn_x, spawn_y)
        # Crowded by friendly units: overlap is fine, statics are not
        for ring in rings[:3]:
            distance = building.radius + ring
            for angle in range(0, 360, 30):
                angle_rad = math.radians(angle)
                spawn_x = building.x + math.cos(angle_rad) * distance
                spawn_y = building.y + math.sin(angle_rad) * distance
                if self._is_valid_spawn_position(spawn_x, spawn_y, ignore_units=True):
                    return (spawn_x, spawn_y)
        # Walled in on every side: at least spawn OUTSIDE the building's own
        # footprint so separation + the watchdog can recover the unit
        map_cx = self.game.game_map.width * TILE_WIDTH / 2
        map_cy = self.game.game_map.height * TILE_WIDTH / 2
        angle_rad = math.atan2(map_cy - building.y, map_cx - building.x)
        edge = building.radius + 24
        return (building.x + math.cos(angle_rad) * edge,
                building.y + math.sin(angle_rad) * edge)

    def _is_valid_spawn_position(self, x, y, ignore_units=False):
        """Check if a spawn position is valid (no collisions)"""
        spawn_radius = 16  # Radius for unit being spawned

        # Check terrain
        terrain_probe = getattr(self.game.game_map, "nav_terrain_walkable", None)
        if terrain_probe is not None:
            if not terrain_probe(x, y):
                return False
        else:
            hex_coord = self.game.game_map.world_to_grid(x, y)
            if hex_coord:
                tile_type = self.game.game_map.grid[hex_coord[1]][hex_coord[0]]
                if tile_type in {"water", "lava"}:
                    return False

        # Check collision with existing objects via the shared spatial index
        collision = self.game.collision_system
        nearby = list(collision.query_nearby_static(x, y, spawn_radius))
        if not ignore_units:
            nearby.extend(collision.query_nearby_units(x, y, spawn_radius))
        for obj in nearby:
            min_distance = spawn_radius + obj.radius
            if (x - obj.x) ** 2 + (y - obj.y) ** 2 < min_distance * min_distance:
                return False

        return True
    
    def _setup_unit_animations(self, unit, unit_data):
        """Set up animations for a newly created unit"""
        unit.animations = {}
        player_index = self.game.players.index(unit.player)
        
        for anim_name, anim_path in unit_data['animations'].items():
            # Get tinted sprite sheet from sprite manager
            sprite_sheet = self.game.sprite_manager.get_unit_animation_sheet(
                unit.name, anim_name, player_index
            )
            
            # Create animation with proper parameters (frame_width, frame_height, animation_speed)
            unit.animations[anim_name] = Animation(sprite_sheet, 192, 192, 100)
        
        # Set default status
        unit.status = "idle"
    
    def cancel_production(self, building):
        """Cancel current production and refund partial resources"""
        if not building.current_production:
            return False, "No production to cancel"
        
        production = building.current_production
        unit_data = self.units_data.get(production["unit_type"], {})
        costs = unit_data.get('costs', {})
        
        # Refund half the resources (based on progress)
        refund_percentage = 0.5  # Always refund 50%
        
        for resource, amount in costs.items():
            refund_amount = int(amount * refund_percentage)
            building.player.resources[resource] += refund_amount
        
        building.current_production = None

        # Start next in queue if any (already paid for)
        self._start_next_queued(building)

        return True, "Production cancelled"
    
    def get_production_info(self, building):
        """Get production information for UI display"""
        if not building.current_production:
            return None
        
        production = building.current_production
        progress_percentage = production["progress"] / production["total_time"]
        progress_percentage = min(1.0, progress_percentage)  # Cap at 100%
        
        return {
            "unit_type": production["unit_type"],
            "progress": progress_percentage,
            "time_remaining": production["total_time"] - production["progress"],
            "queue_length": len(building.production_queue)
        }
    
    def get_unit_count_in_production(self, building, unit_type):
        """Get count of specific unit type in production + queue"""
        count = 0
        
        # Check current production
        if building.current_production and building.current_production["unit_type"] == unit_type:
            count += 1
        
        # Check queue
        for queued_unit in building.production_queue:
            if queued_unit == unit_type:
                count += 1
        
        return count
