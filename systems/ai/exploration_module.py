"""Exploration AI module for scouting and map control"""
import math
import random
from typing import Dict, List, Tuple, Optional, Any, Set
from .base_module import AIModule
from core.config import TILE_WIDTH, TILE_HEIGHT
from utils.debug_logger import debug_log


class ExplorationModule(AIModule):
    """Handles exploration: scouting, resource discovery, enemy detection"""
    
    def __init__(self, ai_system, player):
        super().__init__(ai_system, player)
        self.priority = 0.4  # Lower priority unless resources are scarce
        self.update_interval = 5.0
        
        # Track explored areas
        self.explored_tiles = set()  # Set of (grid_x, grid_y) tuples
        self.last_scout_positions = {}  # Track scout movement
        self.scout_stuck_timers = {}  # Detect stuck scouts
        
        # Exploration parameters
        self.min_scouts = 1
        self.max_scouts = 2
        self.exploration_radius = 800  # How far from base to explore
        self.fog_reveal_radius = 200  # Radius around scout that gets revealed
        
    def get_tasks(self) -> List[Dict[str, Any]]:
        """Generate exploration tasks"""
        tasks = []
        memory = self.ai_system.player_memory[self.player]
        
        # Check if we need more exploration
        exploration_need = self._calculate_exploration_need()
        
        if exploration_need > 0.3:
            # Increase priority when exploration is needed
            self.priority = 0.7
        else:
            self.priority = 0.4
        
        # Task 1: Assign scouts
        current_scouts = self._get_current_scouts()
        if len(current_scouts) < self.min_scouts:
            available_units = self._get_available_scouts(memory)
            if available_units:
                tasks.append({
                    "action": "assign_scout",
                    "priority": 0.8,
                    "target": available_units[0],
                    "params": {}
                })
        
        # Task 2: Direct scouts to unexplored areas
        for scout in current_scouts:
            if self._is_scout_idle(scout):
                target_pos = self._find_exploration_target(scout)
                if target_pos:
                    tasks.append({
                        "action": "explore_area",
                        "priority": 0.7,
                        "target": scout,
                        "params": {"position": target_pos}
                    })
        
        # Task 3: Replace stuck scouts
        stuck_scouts = self._find_stuck_scouts()
        for scout in stuck_scouts:
            tasks.append({
                "action": "unstuck_scout",
                "priority": 0.6,
                "target": scout,
                "params": {}
            })
        
        return tasks
    
    def execute_task(self, task: Dict[str, Any]) -> bool:
        """Execute exploration task"""
        action = task["action"]
        
        if action == "assign_scout":
            return self._execute_assign_scout(task)
        elif action == "explore_area":
            return self._execute_explore_area(task)
        elif action == "unstuck_scout":
            return self._execute_unstuck_scout(task)
        
        return False
    
    def update(self, delta_time: float) -> None:
        """Update exploration state"""
        super().update(delta_time)
        
        # Update explored areas based on unit positions
        self._update_explored_areas()
        
        # Update scout tracking
        self._update_scout_tracking(delta_time)
    
    def _calculate_exploration_need(self) -> float:
        """Calculate how much we need to explore (0-1)"""
        memory = self.ai_system.player_memory[self.player]
        
        # Factor 1: Resource scarcity
        total_resources = sum(len(locs) for locs in memory["resource_locations"].values())
        resource_factor = max(0, 1.0 - (total_resources / 10))  # Need exploration if < 10 resources found
        
        # Factor 2: Map coverage
        map_tiles = self.game.game_map.width * self.game.game_map.height
        explored_ratio = len(self.explored_tiles) / map_tiles
        coverage_factor = max(0, 1.0 - (explored_ratio * 2))  # Need exploration if < 50% explored
        
        # Factor 3: Enemy intel
        enemies_found = len(memory["enemy_locations"])
        enemy_factor = 0.3 if enemies_found == 0 else 0.0  # Some need if no enemies found
        
        # Combine factors
        return (resource_factor * 0.5 + coverage_factor * 0.3 + enemy_factor * 0.2)
    
    def _get_current_scouts(self) -> List[Any]:
        """Get units currently assigned as scouts"""
        scouts = []
        for unit in self.game.units:
            if unit.player == self.player and unit in self.scout_stuck_timers:
                scouts.append(unit)
        return scouts
    
    def _get_available_scouts(self, memory: Dict) -> List[Any]:
        """Get units that can be used as scouts"""
        available = []
        
        # Prefer idle military units
        for unit in memory["military_units"]:
            if self._is_unit_idle(unit) and unit not in self.scout_stuck_timers:
                available.append(unit)
        
        # Use idle workers if no military available
        if not available and len(memory["idle_workers"]) > 2:  # Keep some workers for economy
            available.append(memory["idle_workers"][0])
        
        return available
    
    def _is_scout_idle(self, scout: Any) -> bool:
        """Check if scout needs new orders"""
        if hasattr(scout, 'status') and scout.status == "idle":
            return True
        
        # Check if scout reached destination
        if hasattr(scout, 'destination') and scout.destination:
            distance = math.sqrt((scout.x - scout.destination[0])**2 + 
                               (scout.y - scout.destination[1])**2)
            return distance < 50
        
        return False
    
    def _find_exploration_target(self, scout: Any) -> Optional[Tuple[float, float]]:
        """Find unexplored area to send scout to"""
        castle = self.ai_system.player_memory[self.player]["buildings"]["castle"]
        if not castle:
            return None
        
        # Generate candidate positions
        candidates = []
        for _ in range(20):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(200, self.exploration_radius)
            
            x = castle.x + distance * math.cos(angle)
            y = castle.y + distance * math.sin(angle)
            
            # Check if within map bounds
            if (0 < x < self.game.game_map.width * TILE_WIDTH and 
                0 < y < self.game.game_map.height * TILE_HEIGHT):
                
                grid_x = int(x / TILE_WIDTH)
                grid_y = int(y / TILE_HEIGHT)
                
                # Prefer unexplored tiles
                if (grid_x, grid_y) not in self.explored_tiles:
                    candidates.append((x, y, 1.0))  # High priority
                else:
                    # Lower priority for already explored
                    candidates.append((x, y, 0.3))
        
        if not candidates:
            return None
        
        # Sort by priority and pick from top candidates
        candidates.sort(key=lambda c: c[2], reverse=True)
        top_candidates = candidates[:5]
        chosen = random.choice(top_candidates)
        
        return (chosen[0], chosen[1])
    
    def _find_stuck_scouts(self) -> List[Any]:
        """Find scouts that are stuck"""
        stuck = []
        for scout, timer in self.scout_stuck_timers.items():
            if timer > 5.0:  # Stuck for more than 5 seconds
                stuck.append(scout)
        return stuck
    
    def _update_explored_areas(self) -> None:
        """Update which tiles have been explored"""
        for unit in self.game.units:
            if unit.player == self.player:
                # Mark tiles around unit as explored
                center_x = int(unit.x / TILE_WIDTH)
                center_y = int(unit.y / TILE_HEIGHT)
                
                reveal_tiles = int(self.fog_reveal_radius / TILE_WIDTH)
                for dx in range(-reveal_tiles, reveal_tiles + 1):
                    for dy in range(-reveal_tiles, reveal_tiles + 1):
                        grid_x = center_x + dx
                        grid_y = center_y + dy
                        
                        if (0 <= grid_x < self.game.game_map.width and 
                            0 <= grid_y < self.game.game_map.height):
                            self.explored_tiles.add((grid_x, grid_y))
    
    def _update_scout_tracking(self, delta_time: float) -> None:
        """Track scout movement to detect stuck units"""
        current_scouts = self._get_current_scouts()
        
        for scout in current_scouts:
            current_pos = (scout.x, scout.y)
            
            if scout in self.last_scout_positions:
                last_pos = self.last_scout_positions[scout]
                distance_moved = math.sqrt((current_pos[0] - last_pos[0])**2 + 
                                         (current_pos[1] - last_pos[1])**2)
                
                if distance_moved < 10:  # Barely moved
                    self.scout_stuck_timers[scout] += delta_time
                else:
                    self.scout_stuck_timers[scout] = 0
            else:
                self.scout_stuck_timers[scout] = 0
            
            self.last_scout_positions[scout] = current_pos
        
        # Clean up old scouts
        for scout in list(self.scout_stuck_timers.keys()):
            if scout not in current_scouts:
                del self.scout_stuck_timers[scout]
                if scout in self.last_scout_positions:
                    del self.last_scout_positions[scout]
    
    def _is_unit_idle(self, unit: Any) -> bool:
        """Check if unit is idle"""
        if hasattr(unit, 'status'):
            return unit.status == "idle"
        return True
    
    def _execute_assign_scout(self, task: Dict[str, Any]) -> bool:
        """Assign unit as scout"""
        scout = task["target"]
        self.scout_stuck_timers[scout] = 0.0
        self.last_scout_positions[scout] = (scout.x, scout.y)
        debug_log.log(f"AI {self.player.name}: Assigned {scout.name} as scout", "AI_EXPLORE")
        return True
    
    def _execute_explore_area(self, task: Dict[str, Any]) -> bool:
        """Send scout to explore area"""
        scout = task["target"]
        position = task["params"]["position"]
        self.ai_system._command_unit_move(scout, position)
        return True
    
    def _execute_unstuck_scout(self, task: Dict[str, Any]) -> bool:
        """Handle stuck scout"""
        scout = task["target"]
        
        # Find new random position nearby
        angle = random.uniform(0, 2 * math.pi)
        distance = 100
        new_x = scout.x + distance * math.cos(angle)
        new_y = scout.y + distance * math.sin(angle)
        
        # Reset stuck timer
        self.scout_stuck_timers[scout] = 0
        
        # Move to new position
        self.ai_system._command_unit_move(scout, (new_x, new_y))
        return True