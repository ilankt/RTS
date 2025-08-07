"""Base module for AI behavior system"""
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Any


class AIModule(ABC):
    """Base class for all AI behavior modules"""
    
    def __init__(self, ai_system, player):
        self.ai_system = ai_system
        self.player = player
        self.game = ai_system.game
        self.priority = 1.0  # Base priority, can be adjusted
        self.last_update = 0
        self.update_interval = 1.0  # Update frequency in seconds
        
    @abstractmethod
    def get_tasks(self) -> List[Dict[str, Any]]:
        """
        Generate list of possible tasks with priorities
        Returns list of task dictionaries with:
        - action: string identifier
        - priority: float (0-1)
        - target: optional target object
        - params: additional parameters
        """
        pass
        
    @abstractmethod
    def execute_task(self, task: Dict[str, Any]) -> bool:
        """Execute a specific task, return True if successful"""
        pass
        
    def update(self, delta_time: float) -> None:
        """Update module state if needed"""
        self.last_update += delta_time
        
    def should_update(self) -> bool:
        """Check if module needs to generate new tasks"""
        # Force initial update if module supports it
        if hasattr(self, 'force_initial_update') and self.force_initial_update:
            print(f"Module {self.__class__.__name__}: Forcing initial update")
            self.force_initial_update = False
            return True
        
        should_update = self.last_update >= self.update_interval
        if should_update:
            print(f"Module {self.__class__.__name__}: Update due (last_update: {self.last_update:.1f}s >= interval: {self.update_interval:.1f}s)")
        return should_update
        
    def reset_update_timer(self) -> None:
        """Reset the update timer"""
        self.last_update = 0
        
    def get_priority(self) -> float:
        """Get current module priority"""
        return self.priority
        
    def set_priority(self, priority: float) -> None:
        """Set module priority"""
        self.priority = max(0.0, min(1.0, priority))