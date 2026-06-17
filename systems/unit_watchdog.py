"""Unit watchdog - detects stuck units and recovers them."""
import pygame
import math
from utils.debug_logger import debug_log


class UnitWatchdog:
    """Monitors all units for stuck conditions and performs recovery."""

    CHECK_INTERVAL = 1000       # Check every 1 second (ms)
    STUCK_THRESHOLD = 3.0       # Seconds without meaningful movement
    MOVE_EPSILON = 3.0          # Pixels - must move at least this much to count

    def __init__(self, game):
        self.game = game
        self.last_check = pygame.time.get_ticks()
        # Per-unit tracking: {unit: {"x": float, "y": float, "timer": float}}
        self.tracking = {}

    def update(self):
        now = pygame.time.get_ticks()
        if now - self.last_check < self.CHECK_INTERVAL:
            return
        elapsed = (now - self.last_check) / 1000.0
        self.last_check = now

        # Clean up tracking for dead units
        alive = set(self.game.units)
        self.tracking = {u: v for u, v in self.tracking.items() if u in alive}

        for unit in self.game.units:
            self._check_unit(unit, elapsed)

    def _check_unit(self, unit, elapsed):
        """Check if a unit is stuck and needs recovery."""
        # Only care about units that SHOULD be moving
        if not self._should_be_moving(unit):
            # Not supposed to move - reset tracking
            self.tracking.pop(unit, None)
            return

        if unit not in self.tracking:
            self.tracking[unit] = {"x": unit.x, "y": unit.y, "timer": 0.0}
            return

        info = self.tracking[unit]
        dx = unit.x - info["x"]
        dy = unit.y - info["y"]
        moved = math.hypot(dx, dy)

        if moved < self.MOVE_EPSILON:
            # Hasn't moved meaningfully
            info["timer"] += elapsed
        else:
            # Made progress - reset
            info["x"] = unit.x
            info["y"] = unit.y
            info["timer"] = 0.0
            return

        if info["timer"] >= self.STUCK_THRESHOLD:
            self._recover_unit(unit)
            self.tracking.pop(unit, None)

    def _should_be_moving(self, unit) -> bool:
        """Return True if this unit has a reason to be moving."""
        # Actively building at a site - stationary is fine
        if unit.is_building:
            return False
        # Actively gathering in range - stationary is fine
        if unit.is_gathering and unit.status == "gather":
            return False
        # Idle with no targets - nothing to do
        if unit.status == "idle" and not unit.destination and not unit.path:
            if not unit.building_target and not unit.is_engaging and not unit.current_target:
                return False
        # Drop-off delay is brief but stationary
        if getattr(unit, "is_dropping_off", False):
            return False
        # In combat and attacking - stationary is fine
        if unit.in_combat and unit.status == "attack":
            return False
        # Everything else: has a path, destination, target, or is_engaging -> should move
        return True

    def _recover_unit(self, unit):
        """Recover a stuck unit by clearing state and nudging position."""
        debug_log.log(
            f"WATCHDOG: {unit.name} stuck at ({unit.x:.0f}, {unit.y:.0f}) "
            f"status={unit.status} for {self.STUCK_THRESHOLD}s - recovering",
            "WATCHDOG",
        )

        # Full state wipe
        worker_tasks = getattr(self.game, "worker_task_system", None)
        if worker_tasks and worker_tasks.active_task(unit):
            worker_tasks.cancel(unit)
        unit.clear_all_movement_state()

        # Nudge to nearest safe position if overlapping something
        safe = self._find_nearby_safe_position(unit)
        if safe and math.hypot(safe[0] - unit.x, safe[1] - unit.y) > 1:
            unit.x, unit.y = safe
            debug_log.log(f"  Nudged to ({unit.x:.0f}, {unit.y:.0f})", "WATCHDOG")

    def _find_nearby_safe_position(self, unit):
        """Find nearest walkable, non-colliding position."""
        # Check if current position is already fine
        if self._is_safe(unit.x, unit.y, unit.radius):
            return (unit.x, unit.y)

        for radius in range(10, 160, 10):
            for angle_deg in range(0, 360, 30):
                angle = math.radians(angle_deg)
                tx = unit.x + radius * math.cos(angle)
                ty = unit.y + radius * math.sin(angle)
                if self._is_safe(tx, ty, unit.radius):
                    return (tx, ty)

        # Fallback: teleport near castle
        return self._find_castle_position(unit)

    def _is_safe(self, x, y, radius):
        """Position is walkable terrain and not overlapping buildings/resources."""
        grid_pos = self.game.game_map.world_to_grid(x, y)
        if not grid_pos:
            return False
        col, row = grid_pos
        if row < 0 or row >= self.game.game_map.height or col < 0 or col >= self.game.game_map.width:
            return False
        if self.game.game_map.grid[row][col] in ("water", "lava"):
            return False

        min_dist = radius + 5
        for obj in self.game.buildings + self.game.resources + self.game.construction_sites:
            if math.hypot(obj.x - x, obj.y - y) < min_dist + obj.radius:
                return False
        return True

    def _find_castle_position(self, unit):
        """Find safe position near player's castle as last resort."""
        if not unit.player:
            return None
        for building in self.game.buildings:
            if building.player == unit.player and building.name == "castle":
                for radius in range(50, 200, 20):
                    for angle_deg in range(0, 360, 45):
                        angle = math.radians(angle_deg)
                        tx = building.x + radius * math.cos(angle)
                        ty = building.y + radius * math.sin(angle)
                        if self._is_safe(tx, ty, unit.radius):
                            return (tx, ty)
        return None
