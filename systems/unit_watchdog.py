import pygame
import random
import math
from core.config import GHOST_DURATION

class UnitWatchdog:
    def __init__(self, game):
        self.game = game
        self.last_check = pygame.time.get_ticks()
        self.check_interval = 2000  # Check every 2 seconds
        self.unit_positions = {}

    def update(self):
        now = pygame.time.get_ticks()
        if now - self.last_check > self.check_interval:
            self.last_check = now
            self.check_units()
        self.check_ghost_timers()

    def check_ghost_timers(self):
        """Checks and updates ghost timers for all units."""
        now = pygame.time.get_ticks()
        for unit in self.game.units:
            if unit.ghost_timer is not None:
                if now - unit.ghost_timer > GHOST_DURATION:
                    unit.collision = True
                    unit.ghost_timer = None

    def check_units(self):
        for unit in self.game.units:
            if unit.status == "run":
                if unit in self.unit_positions and self.unit_positions[unit] == (unit.x, unit.y):
                    # Unit is stuck, activate ghosting and move it
                    self.activate_ghost_and_nudge(unit)
                else:
                    self.unit_positions[unit] = (unit.x, unit.y)

    def activate_ghost_and_nudge(self, unit):
        """Activates ghost mode for a unit and nudges it to a safe location."""
        # 1. Turn ghosting on for the unit
        unit.collision = False
        unit.ghost_timer = pygame.time.get_ticks()

        # 2. Find a safe nudge position
        nudge_pos = self._find_random_nearby_walkable_tile(unit)
        if nudge_pos:
            # 3. Immediately move the unit to the nudge position
            unit.x, unit.y = nudge_pos[0], nudge_pos[1]
            unit.destination = nudge_pos
            unit.path = None # Clear the old path
            unit.path_index = 0

    def _find_random_nearby_walkable_tile(self, unit, max_radius=30):
        """Find a random walkable tile within a certain radius of a given world position."""
        for _ in range(20):  # Try 20 times to find a valid spot
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(10, max_radius)
            
            check_x = unit.x + radius * math.cos(angle)
            check_y = unit.y + radius * math.sin(angle)
            
            grid_pos = self.game.game_map.world_to_grid(check_x, check_y)
            if grid_pos:
                if self.game.pathfinder._is_walkable(check_x, check_y, unit.radius):
                    return (check_x, check_y)
        return None
