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
        
        # If already producing, add to queue
        if building.current_production:
            building.production_queue.append(unit_type)
            # Debug: Added unit to production queue
            return True, f"Added {unit_type} to queue"
        
        # Start production immediately
        return self._start_immediate_production(building, unit_type, unit_data, costs)
    
    def _start_immediate_production(self, building, unit_type, unit_data, costs):
        """Start production immediately (no queue)"""
        # Deduct resources
        for resource, amount in costs.items():
            building.player.resources[resource] -= amount
        
        # Start production
        building.current_production = {
            "unit_type": unit_type,
            "progress": 0.0,
            "total_time": unit_data.get('build_time', 10),
            "unit_data": unit_data
        }
        
        # Debug: Started producing unit
        return True, f"Started producing {unit_type}"
    
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
            attack_range=unit_data.get('attack_range', 32)
        )
        
        # Set up animations using sprite manager
        self._setup_unit_animations(new_unit, unit_data)
        
        # Add to game
        self.game.units.append(new_unit)
        
        # Debug: Completed production of unit
        
        # Invalidate AI memory cache for immediate detection of new unit
        if hasattr(self.game, 'ai_system') and self.game.ai_system:
            self.game.ai_system.invalidate_memory_cache(building.player)
            debug_log.log(f"AI: Invalidated memory cache for {building.player.name} after producing {unit_type}", "PRODUCTION")
        
        # Clear current production
        building.current_production = None
        
        # Start next in queue if any
        if building.production_queue:
            next_unit_type = building.production_queue.pop(0)
            if next_unit_type in self.units_data:
                next_unit_data = self.units_data[next_unit_type]
                costs = next_unit_data.get('costs', {})
                if self._can_afford(building.player, costs):
                    self._start_immediate_production(building, next_unit_type, next_unit_data, costs)
                else:
                    # Debug: Cannot afford next unit in queue
                    pass
    
    def _find_spawn_position(self, building):
        """Find a valid spawn position near the building"""
        # Try positions in a circle around the building
        spawn_distance = building.radius + 40  # Spawn a bit away from building
        
        for angle in range(0, 360, 45):  # Try 8 directions
            angle_rad = math.radians(angle)
            spawn_x = building.x + math.cos(angle_rad) * spawn_distance
            spawn_y = building.y + math.sin(angle_rad) * spawn_distance
            
            # Check if position is valid (not colliding with other objects)
            if self._is_valid_spawn_position(spawn_x, spawn_y):
                return (spawn_x, spawn_y)
        
        # Fallback: spawn at building position (not ideal but prevents crashes)
        return (building.x, building.y)
    
    def _is_valid_spawn_position(self, x, y):
        """Check if a spawn position is valid (no collisions)"""
        spawn_radius = 16  # Radius for unit being spawned
        
        # Check terrain
        hex_coord = self.game.game_map.world_to_grid(x, y)
        if hex_coord:
            tile_type = self.game.game_map.grid[hex_coord[1]][hex_coord[0]]
            if tile_type in {"water", "lava"}:
                return False
        
        # Check collision with existing objects
        all_objects = self.game.buildings + self.game.units + self.game.resources + self.game.construction_sites
        for obj in all_objects:
            distance = math.sqrt((x - obj.x)**2 + (y - obj.y)**2)
            min_distance = spawn_radius + obj.radius
            if distance < min_distance:
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
        
        # Debug: Cancelled production
        building.current_production = None
        
        # Start next in queue if any
        if building.production_queue:
            next_unit_type = building.production_queue.pop(0)
            if next_unit_type in self.units_data:
                next_unit_data = self.units_data[next_unit_type]
                next_costs = next_unit_data.get('costs', {})
                if self._can_afford(building.player, next_costs):
                    self._start_immediate_production(building, next_unit_type, next_unit_data, next_costs)
        
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