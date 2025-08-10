import pygame
import math
from core.config import TILE_WIDTH, TILE_HEIGHT

class UnitWatchdog:
    """Simplified unit recovery system for severely stuck units"""
    def __init__(self, game):
        self.game = game
        self.last_check = pygame.time.get_ticks()
        self.check_interval = 3000  # Check every 3 seconds
        self.stuck_units = {}  # Track units that have been stuck for a long time

    def update(self):
        now = pygame.time.get_ticks()
        if now - self.last_check > self.check_interval:
            self.last_check = now
            self.check_severely_stuck_units()

    def check_severely_stuck_units(self):
        """Check for units that have been stuck for a very long time"""
        for unit in self.game.units:
            # Skip units that are supposed to be stationary
            if unit.status == "idle" or unit.is_building or unit.is_gathering:
                if unit in self.stuck_units:
                    del self.stuck_units[unit]
                continue
                
            # Check if unit has stuck detector from movement system
            if hasattr(unit, '_stuck_detector') and unit._stuck_detector.get('stuck_timer', 0) >= 300:  # 5 seconds
                # Track how long this unit has been severely stuck
                if unit not in self.stuck_units:
                    self.stuck_units[unit] = 1
                else:
                    self.stuck_units[unit] += 1
                    
                # If stuck for multiple check cycles, perform emergency recovery
                if self.stuck_units[unit] >= 5:  # 15+ seconds total  (increased for construction)
                    self.perform_emergency_recovery(unit)
                    del self.stuck_units[unit]
            else:
                # Unit is not stuck, remove from tracking
                if unit in self.stuck_units:
                    del self.stuck_units[unit]

    def perform_emergency_recovery(self, unit):
        """Perform emergency recovery for severely stuck units"""
        print(f"EMERGENCY RECOVERY: {unit.name} at ({unit.x:.0f}, {unit.y:.0f}) has been stuck for 6+ seconds")
        
        # Find nearest valid position
        safe_pos = self._find_nearest_safe_position(unit)
        if safe_pos:
            # Teleport unit to safe position
            unit.x, unit.y = safe_pos
            
            # Clear all movement state
            unit.destination = None
            unit.path = None
            unit.path_index = 0
            unit.path_target = None
            unit.status = "idle"
            unit.is_engaging = False
            unit.is_fallback_movement = False
            
            # Reset stuck detector
            if hasattr(unit, '_stuck_detector'):
                unit._stuck_detector['stuck_timer'] = 0
                unit._stuck_detector['last_position'] = (unit.x, unit.y)
                
            print(f"  -> Teleported to ({unit.x:.0f}, {unit.y:.0f})")

    def _find_nearest_safe_position(self, unit):
        """Find the nearest walkable position to the unit"""
        # Search in expanding circles
        for radius in range(20, 200, 20):
            # Check 8 directions at this radius
            for angle in range(0, 360, 45):
                rad = math.radians(angle)
                test_x = unit.x + radius * math.cos(rad)
                test_y = unit.y + radius * math.sin(rad)
                
                # Check if position is walkable
                if self._is_position_safe(test_x, test_y, unit.radius):
                    return (test_x, test_y)
                    
        # If no safe position found nearby, try to find spawn position
        return self._find_spawn_position(unit)
        
    def _is_position_safe(self, x, y, radius):
        """Check if a position is safe for a unit"""
        # Check terrain
        hex_coord = self.game.game_map.world_to_grid(x, y)
        if not hex_coord:
            return False
            
        col, row = hex_coord
        if row < 0 or row >= self.game.game_map.height or col < 0 or col >= self.game.game_map.width:
            return False
            
        tile_type = self.game.game_map.grid[row][col]
        if tile_type in {"water", "lava"}:
            return False
            
        # Check for collisions with buildings and resources
        for obj in self.game.buildings + self.game.resources:
            dist = math.sqrt((obj.x - x)**2 + (obj.y - y)**2)
            if dist < (obj.radius + radius + 10):  # Extra margin
                return False
                
        return True
        
    def _find_spawn_position(self, unit):
        """Find a spawn position near the unit's base"""
        if unit.player:
            # Find player's castle
            for building in self.game.buildings:
                if building.player == unit.player and building.name == "castle":
                    # Find safe position near castle
                    return self.game.game_map.find_safe_spawn_position(
                        unit.radius, 
                        center_pos=(building.x, building.y),
                        search_range=(50, 200)
                    )
        return None
