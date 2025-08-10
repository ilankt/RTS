"""Economy AI module for resource gathering and management"""
import math
import random
import pygame
from typing import Dict, List, Tuple, Optional, Any
from .base_module import AIModule
from .resource_manager import ResourceManager
from entities.objects import Unit, Building, Resource
from utils.debug_logger import debug_log


class EconomyModule(AIModule):
    """Handles economic decisions: gathering, worker production, resource buildings"""
    
    def __init__(self, ai_system, player):
        super().__init__(ai_system, player)
        self.priority = 0.8  # High priority for economy
        self.update_interval = 1.5  # Fixed timing: must be less than AI task_cooldown (2.0s)
        self.force_initial_update = True  # Force first update regardless of timing
        self.force_next_update = False  # Force update when new units are produced
        
        # Initialize smart resource manager
        self.resource_manager = ResourceManager(ai_system, player)
        
        # Resource targets based on game phase
        self.resource_targets = {
            "early": {"gold": 100, "wood": 150, "stone": 50, "food": 100},
            "mid": {"gold": 300, "wood": 400, "stone": 200, "food": 300},
            "late": {"gold": 1000, "wood": 1000, "stone": 500, "food": 500}
        }
        
        # Track resource income rates
        self.resource_income = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        self.last_resource_check = {k: 0 for k in self.resource_income}
        
        # Worker assignment stability
        self.worker_assignments = {}  # worker_id -> (resource_type, assignment_time)
        self.min_assignment_duration = 5.0  # Reduced to 5 seconds for more responsiveness
        self.last_rebalance_time = 0
        self.rebalance_cooldown = 15.0  # Only rebalance every 15 seconds
        self.last_worker_count = 0  # Track worker count changes
        self.same_resource_timer = 0  # Track how long all workers on same resource
        self.force_diversity_threshold = 10.0  # Force diversity after 10 seconds
        
        # Worker stuck detection
        self.worker_positions = {}  # worker_id -> (last_pos, last_time, stuck_time)
        self.stuck_detection_threshold = 5.0  # Consider stuck after 5 seconds
        self.position_tolerance = 5.0  # Pixels - if worker hasn't moved this much, consider stuck
        
        # Track resources that need buildings
        self.far_resources_need_buildings = set()  # Set of resource types that need buildings
        
    def update(self, delta_time: float) -> None:
        """Update module and resource manager"""
        super().update(delta_time)
        self.resource_manager.update(delta_time)
        
        # Check for resource diversity
        self._check_resource_diversity(delta_time)
    
    def should_update(self) -> bool:
        """Check if module needs to generate new tasks - prioritize idle workers"""
        # Check base class timing first
        should_update = super().should_update()
        
        # Force update if we have idle workers (more responsive)
        memory = self.ai_system.player_memory[self.player]
        idle_workers = memory.get("idle_workers", [])
        
        # Also check for disconnected gathering workers
        gathering_workers = memory.get("gathering_workers", [])
        disconnected_workers = [w for w in gathering_workers if hasattr(w, 'status') and w.status == "idle"]
        
        if idle_workers or disconnected_workers or self.force_next_update:
            if idle_workers or disconnected_workers:
                debug_log.log(f"AI {self.player.name}: Forcing update - {len(idle_workers)} idle workers, {len(disconnected_workers)} disconnected", "AI_ECONOMY")
            if self.force_next_update:
                debug_log.log(f"AI {self.player.name}: Forcing update due to force_next_update flag", "AI_ECONOMY")
                self.force_next_update = False
            should_update = True
        
        return should_update
    
    def get_tasks(self) -> List[Dict[str, Any]]:
        """Generate economic tasks based on a unified scoring system."""
        tasks = []
        memory = self.ai_system.player_memory[self.player]

        # 1. Handle workers who need to drop off resources first
        workers_to_drop_off = []
        all_idle_workers = list(memory["idle_workers"])
        for worker in memory["gathering_workers"]:
            if hasattr(worker, 'status') and worker.status == "idle":
                all_idle_workers.append(worker)
        
        for worker in all_idle_workers:
            if hasattr(worker, 'resource_amount') and worker.resource_amount > 0:
                tasks.append({"action": "drop_off_resources", "priority": 1.0, "target": worker, "params": {}})
                workers_to_drop_off.append(worker)
        
        all_idle_workers = [w for w in all_idle_workers if w not in workers_to_drop_off]

        # 2. Score and prioritize all possible economic actions
        possible_actions = []
        game_phase = self._determine_game_phase()
        resource_needs = self._calculate_resource_needs(game_phase)
        
        # Log current resources
        current_resources = {k: int(v) for k, v in self.player.resources.items()}
        debug_log.log(f"AI {self.player.name}: Current resources: {current_resources}", "AI_ECONOMY")
        debug_log.log(f"AI {self.player.name}: Game phase: {game_phase}, Resource needs: {resource_needs}", "AI_ECONOMY")

        # Action: Train Worker
        worker_count = len(memory["idle_workers"]) + len(memory["gathering_workers"]) + len(memory["building_workers"])
        ideal_workers = self._calculate_ideal_workers(game_phase)
        if worker_count < ideal_workers and self._can_afford("worker"):
            possible_actions.append({"action": "train_worker", "score": 80})

        # Action: Build House
        current_pop = len([u for u in self.game.units if u.player == self.player])
        pop_limit = self._get_population_limit()
        if current_pop >= pop_limit - 2 and self._can_afford("house"):
            possible_actions.append({"action": "build_house", "score": 90})

        # Action: Build Resource Buildings
        building_scores = self._score_resource_buildings(resource_needs)
        debug_log.log(f"AI {self.player.name}: Resource building scores: {building_scores}", "AI_ECONOMY")
        debug_log.log(f"AI {self.player.name}: Far resources needing buildings: {self.far_resources_need_buildings}", "AI_ECONOMY")
        for building_type, score in building_scores.items():
            costs = self.ai_system.cost_data.get(building_type, {})
            can_afford = self._can_afford(building_type)
            debug_log.log(f"AI {self.player.name}: {building_type} - score: {score}, costs: {costs}, can afford: {can_afford}", "AI_ECONOMY")
            if can_afford:
                # Adjust score based on affordability - affordable buildings get priority boost
                adjusted_score = score
                possible_actions.append({"action": "build_resource_building", "score": adjusted_score, "params": {"building_type": building_type}})
            else:
                # Log why we're skipping unaffordable buildings
                debug_log.log(f"AI {self.player.name}: Skipping {building_type} - cannot afford (score was {score})", "AI_ECONOMY")

        # Action: Build Barracks
        # Build barracks when we have at least 3 workers and no barracks yet
        barracks_count = len(memory["buildings"].get("barracks", []))
        # Check barracks cost details
        if barracks_count == 0:
            barracks_costs = self.ai_system.cost_data.get("barracks", {})
            player_resources = {k: int(v) for k, v in self.player.resources.items()}
            can_afford = self._can_afford("barracks")
            debug_log.log(f"AI {self.player.name}: Barracks check - workers: {worker_count}, barracks: {barracks_count}", "AI_ECONOMY")
            debug_log.log(f"  Resources: {player_resources}", "AI_ECONOMY")
            debug_log.log(f"  Barracks costs: {barracks_costs}", "AI_ECONOMY")
            debug_log.log(f"  Can afford: {can_afford}", "AI_ECONOMY")
        if worker_count >= 2 and barracks_count == 0 and self._can_afford("barracks"):  # Reduced from 3 to 2 workers
            # Scale barracks priority with worker count - more workers = higher priority
            # Base score 90, +10 per worker above 2 (max +30 at 5 workers)
            worker_bonus = min((worker_count - 2) * 10, 30)
            barracks_score = 90 + worker_bonus  # Increased base priority
            possible_actions.append({"action": "build_barracks", "score": barracks_score})
            debug_log.log(f"AI {self.player.name}: Added barracks to possible actions with score {barracks_score} (base 85 + worker bonus {worker_bonus})", "AI_ECONOMY")

        # 3. Check for far resources before assigning workers
        # First, identify which resources are too far and need buildings
        self._check_far_resources(memory)
        
        # 4. Assign idle workers to gather resources (but not from far resources that need buildings)
        if all_idle_workers:
            assignments = self.resource_manager.get_optimal_worker_assignment(all_idle_workers)
            for resource_type, workers in assignments.items():
                # Check if this is a critical resource (we have 0 of it)
                is_critical = self.player.resources.get(resource_type, 0) == 0
                
                # Skip assignment if this resource type needs a building - UNLESS it's critical
                if resource_type in self.far_resources_need_buildings and not is_critical:
                    debug_log.log(f"AI {self.player.name}: Skipping {resource_type} gathering - needs building first", "AI_ECONOMY")
                    continue
                    
                for worker in workers:
                    # Critical resources get higher priority
                    priority = 0.99 if is_critical else 0.95
                    tasks.append({"action": "gather_resource", "priority": priority, "target": worker, "params": {"resource_type": resource_type}})

        # 4. Select the best economic action and create a task for it
        if possible_actions:
            # Debug: Log all possible actions and their scores
            debug_log.log(f"AI {self.player.name}: Possible actions:", "AI_ECONOMY")
            for action in possible_actions:
                action_desc = f"{action['action']}"
                if 'params' in action and 'building_type' in action['params']:
                    action_desc += f" ({action['params']['building_type']})"
                debug_log.log(f"  - {action_desc}: score {action['score']}", "AI_ECONOMY")
            
            # Final affordability check before selecting action
            affordable_actions = []
            for action in possible_actions:
                if action["action"] == "build_resource_building":
                    building_type = action["params"]["building_type"]
                    if self._can_afford(building_type):
                        affordable_actions.append(action)
                    else:
                        debug_log.log(f"AI {self.player.name}: Removing {building_type} from selection - no longer affordable", "AI_ECONOMY")
                else:
                    affordable_actions.append(action)
            
            if not affordable_actions:
                debug_log.log(f"AI {self.player.name}: No affordable actions available", "AI_ECONOMY")
                return tasks
            
            best_action = max(affordable_actions, key=lambda x: x["score"])
            action_type = best_action["action"]
            action_desc = f"{action_type}"
            if 'params' in best_action and 'building_type' in best_action['params']:
                action_desc += f" ({best_action['params']['building_type']})"
            debug_log.log(f"AI {self.player.name}: Selected action: {action_desc} (score: {best_action['score']})", "AI_ECONOMY")

            if action_type == "train_worker":
                tasks.append({"action": "train_worker", "priority": 0.8, "target": memory["buildings"]["castle"], "params": {}})
            elif action_type == "build_house":
                tasks.append({"action": "build_house", "priority": 0.85, "target": None, "params": {}})
            elif action_type == "build_barracks":
                tasks.append({"action": "build_barracks", "priority": 0.85, "target": None, "params": {"building_type": "barracks"}})
            elif action_type == "build_resource_building":
                # Boost priority if this building is needed for far resources
                building_type = best_action["params"]["building_type"]
                building_to_resource = {"mine": "gold", "lumbermill": "wood", "quarry": "stone"}
                resource_type = building_to_resource.get(building_type)
                
                if resource_type and resource_type in self.far_resources_need_buildings:
                    # Very high priority for buildings needed for far resources
                    priority = 0.98
                    debug_log.log(f"AI {self.player.name}: Boosting {building_type} priority to {priority} - needed for far {resource_type}", "AI_ECONOMY")
                else:
                    priority = 0.7
                    
                tasks.append({"action": "build_resource_building", "priority": priority, "target": None, "params": best_action["params"]})

        return tasks
    
    def execute_task(self, task: Dict[str, Any]) -> bool:
        """Execute economic task"""
        action = task["action"]
        
        if action == "gather_resource":
            result = self._execute_gather_resource(task)
            if not result:
                # If gather failed (likely due to distance), force immediate update
                self.force_next_update = True
                debug_log.log(f"AI {self.player.name}: Gather task failed, forcing immediate update", "AI_ECONOMY")
            return result
        elif action == "train_worker":
            return self._execute_train_worker(task)
        elif action == "plan_worker_training":
            return True  # Just planning, no immediate action
        elif action == "build_house":
            return self._execute_build_house(task)
        elif action == "build_barracks":
            return self._execute_build_barracks(task)
        elif action == "build_resource_building":
            return self._execute_build_resource_building(task)
        elif action == "rebalance_workers":
            return self._execute_rebalance_workers(task)
        elif action == "drop_off_resources":
            return self._execute_drop_off_resources(task)
        
        return False
    
    def _determine_game_phase(self) -> str:
        """Determine current game phase based on various factors"""
        memory = self.ai_system.player_memory[self.player]
        
        # Simple phase detection based on buildings and units
        building_count = sum(len(buildings) for buildings in memory["buildings"].values() if isinstance(buildings, list))
        if memory["buildings"]["castle"]:
            building_count += 1
            
        unit_count = len([u for u in self.game.units if u.player == self.player])
        
        # More lenient thresholds: 2 buildings OR 3 units for mid-game
        if building_count < 2 and unit_count < 3:
            return "early"
        elif building_count < 8 or unit_count < 15:
            return "mid"
        else:
            return "late"
    
    def _calculate_resource_needs(self, game_phase: str) -> Dict[str, float]:
        """Calculate resource needs based on current vs target amounts"""
        targets = self.resource_targets[game_phase]
        needs = {}
        
        for resource, target in targets.items():
            current = self.player.resources.get(resource, 0)
            # Need is higher when we have less of the resource
            needs[resource] = max(0, (target - current) / target)
            
        return needs
    
    def _get_priority_resource(self, resource_needs: Dict[str, float]) -> Optional[str]:
        """Get highest priority resource to gather"""
        memory = self.ai_system.player_memory[self.player]
        available_resources = []
        
        for res_type, need in resource_needs.items():
            if res_type in memory["resource_locations"] and memory["resource_locations"][res_type]:
                # Weight by need and availability
                weight = need * len(memory["resource_locations"][res_type])
                available_resources.append((res_type, weight))
        
        if not available_resources:
            return None
            
        # Sort by weight and return highest priority
        available_resources.sort(key=lambda x: x[1], reverse=True)
        return available_resources[0][0]
    
    def _calculate_ideal_workers(self, game_phase: str) -> int:
        """Calculate ideal number of workers for current game phase - limited for military focus"""
        # Increased early game workers to 5 to ensure barracks can be built
        phase_workers = {"early": 5, "mid": 6, "late": 7}
        return phase_workers.get(game_phase, 5)
    
    def _should_build_resource_building(self, resource_needs: Dict[str, float]) -> bool:
        """Determine if we should build a resource building"""
        memory = self.ai_system.player_memory[self.player]
        
        # Check if we're already building one
        resource_buildings_constructing = len([
            s for s in self.game.construction_sites 
            if s.player == self.player and s.building_name in ["mine", "quarry", "lumbermill", "farm"]
        ])
        
        if resource_buildings_constructing > 0:
            return False
            
        # Check if we have enough workers
        worker_count = len(memory["idle_workers"]) + len(memory["gathering_workers"])
        if worker_count < 3:
            return False
            
        # Check if any resource has high need
        return any(need > 0.4 for need in resource_needs.values())
    
    def _get_priority_resource_building(self, resource_needs: Dict[str, float]) -> Optional[str]:
        """Determine which resource building is the highest priority to build."""
        memory = self.ai_system.player_memory[self.player]
        if not memory["buildings"]["castle"]:
            return None

        resource_to_building = {
            "gold": "mine", "stone": "quarry", "wood": "lumbermill", "food": "farm"
        }

        # Count existing and in-progress resource buildings
        existing_buildings = {"mine": 0, "quarry": 0, "lumbermill": 0, "farm": 0}
        for b in memory["buildings"]["resource_buildings"]:
            if b.name in existing_buildings:
                existing_buildings[b.name] += 1
        for s in self.game.construction_sites:
            if s.player == self.player and s.building_name in existing_buildings:
                existing_buildings[s.building_name] += 1

        # Find resource clusters to determine how many deposit-based buildings are needed
        # Note: This uses a method from the building placement manager
        resource_clusters = self.ai_system.building_placement_managers[self.player]._find_resource_clusters()
        cluster_counts = {"gold": 0, "wood": 0, "stone": 0}
        for _, _, resources in resource_clusters:
            if not resources:
                continue
            res_types = [r[2] for r in resources]
            # Find the most common resource type in the cluster
            dominant_type = max(set(res_types), key=res_types.count)
            if dominant_type in cluster_counts:
                cluster_counts[dominant_type] += 1

        # Score potential buildings based on need and availability
        building_scores = {}
        for res_type, need in resource_needs.items():
            if need < 0.4:  # Minimum need threshold to consider building
                continue

            building_type = resource_to_building.get(res_type)
            if not building_type:
                continue

            # Logic for deposit-based buildings (mine, lumbermill, quarry)
            if res_type in cluster_counts:
                # Allow building if we have fewer buildings than resource clusters
                if existing_buildings[building_type] < cluster_counts[res_type]:
                    # Score is weighted by need and the number of clusters (opportunity)
                    building_scores[building_type] = need * (1 + cluster_counts[res_type])
            
            # Logic for farms (not dependent on deposits)
            elif res_type == "food":
                # Allow up to 2 farms for a stable food supply
                if existing_buildings["farm"] < 2:
                    # Farm score is just based on need, with a boost to make it competitive
                    building_scores["farm"] = need * 1.5

        if not building_scores:
            return None

        # Return the building with the highest score
        best_building = max(building_scores, key=building_scores.get)
        return best_building
    
    def _should_rebalance_workers(self) -> bool:
        """Check if workers need rebalancing across resources"""
        memory = self.ai_system.player_memory[self.player]
        
        # Count workers per resource type
        resource_workers = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        
        for worker in memory["gathering_workers"]:
            if hasattr(worker, 'gathering_target') and worker.gathering_target:
                res_type = getattr(worker.gathering_target, 'name', None)
                if res_type in resource_workers:
                    resource_workers[res_type] += 1
        
        # Check if distribution is very uneven
        worker_counts = list(resource_workers.values())
        if worker_counts:
            max_workers = max(worker_counts)
            min_workers = min(worker_counts)
            return max_workers - min_workers > 2
        
        return False
    
    def _execute_gather_resource(self, task: Dict[str, Any]) -> bool:
        """Execute gather resource task"""
        worker = task["target"]
        resource_type = task["params"]["resource_type"]
        memory = self.ai_system.player_memory[self.player]
        
        # Check if this is a critical resource (we have 0 of it)
        is_critical = self.player.resources.get(resource_type, 0) == 0
        if is_critical:
            debug_log.log(f"AI {self.player.name}: {resource_type} is CRITICAL (amount=0)", "AI_ECONOMY")
        
        # Skip far resources UNLESS they're critical
        if resource_type in self.far_resources_need_buildings and not is_critical:
            debug_log.log(f"AI {self.player.name}: Skipping gather execution for {resource_type} - building needed", "AI_ECONOMY")
            return False
        
        if resource_type in memory["resource_locations"]:
            resources = memory["resource_locations"][resource_type]
            
            if resources:
                # Find closest resource
                closest = min(resources, key=lambda r: math.sqrt((r.x - worker.x)**2 + (r.y - worker.y)**2))
                
                # Command worker to gather
                self.ai_system._command_worker_gather(worker, closest)
                
                return True
        
        return False
    
    def _execute_train_worker(self, task: Dict[str, Any]) -> bool:
        """Execute train worker task"""
        castle = task["target"]
        if castle:
            self.ai_system._train_unit(self.player, "worker")
            # Release reservation if we had one
            if task["params"].get("reserved"):
                self.resource_manager.release_reservation("worker")
            return True
        return False
    
    def _execute_build_house(self, task: Dict[str, Any]) -> bool:
        """Execute build house task"""
        self.ai_system._build_structure(self.player, "house")
        return True
    
    def _execute_build_barracks(self, task: Dict[str, Any]) -> bool:
        """Execute build barracks task"""
        building_type = task["params"]["building_type"]
        self.ai_system._build_structure(self.player, building_type)
        debug_log.log(f"AI {self.player.name}: Building barracks for military production", "AI_ECONOMY")
        return True
    
    def _execute_build_resource_building(self, task: Dict[str, Any]) -> bool:
        """Execute build resource building task"""
        building_type = task["params"]["building_type"]
        self.ai_system._build_structure(self.player, building_type)
        return True
    
    def _execute_rebalance_workers(self, task: Dict[str, Any]) -> bool:
        """Rebalance workers across resources"""
        memory = self.ai_system.player_memory[self.player]
        force_diversity = task["params"].get("force_diversity", False)
        
        if force_diversity:
            # Stop ALL workers except one to force redistribution
            debug_log.log(f"AI {self.player.name}: Forcing resource diversity - stopping most workers", "AI_ECONOMY")
            workers_to_reassign = []
            kept_one = False
            for worker in memory["gathering_workers"]:
                if hasattr(worker, 'gathering_target'):
                    if not kept_one:
                        kept_one = True  # Keep first worker gathering
                    else:
                        worker.gathering_target = None
                        worker.status = "idle"
                        workers_to_reassign.append(worker)
        else:
            # Normal rebalancing - stop some workers to reassign them
            workers_to_reassign = []
            for worker in memory["gathering_workers"][:3]:  # Reassign up to 3 workers
                if hasattr(worker, 'gathering_target'):
                    worker.gathering_target = None
                    worker.status = "idle"
                    workers_to_reassign.append(worker)
        
        # Clear worker assignments to allow fresh assignment
        if workers_to_reassign:
            for worker in workers_to_reassign:
                worker_id = id(worker)
                if worker_id in self.worker_assignments:
                    del self.worker_assignments[worker_id]
        
        # They'll be reassigned next update with diversity in mind
        return len(workers_to_reassign) > 0
    
    def _execute_drop_off_resources(self, task: Dict[str, Any]) -> bool:
        """Command a worker to drop off carried resources"""
        worker = task["target"]
        if hasattr(worker, 'resource_amount') and worker.resource_amount > 0:
            # The gathering manager has the logic to find the nearest drop-off
            self.ai_system.game.gathering_manager._find_drop_off_location(worker)
            return True
        return False
    
    def _get_truly_idle_workers(self, idle_workers, current_time: float):
        """Filter idle workers to only include those not recently assigned"""
        truly_idle = []
        
        for worker in idle_workers:
            worker_id = id(worker)
            
            # Check if worker was recently assigned
            if worker_id in self.worker_assignments:
                resource_type, assignment_time = self.worker_assignments[worker_id]
                time_since_assignment = current_time - assignment_time
                
                if time_since_assignment < self.min_assignment_duration:
                    # Worker was recently assigned, skip for stability
                    continue
            
            # Worker is truly idle and available for assignment
            truly_idle.append(worker)
        
        return truly_idle
    
    def _can_afford(self, item_type: str) -> bool:
        """Check if player can afford item"""
        costs = self.ai_system.cost_data.get(item_type, {})
        can_afford = True
        
        # Enhanced debug logging for all building types
        if item_type in ["mine", "quarry", "lumbermill", "farm", "barracks", "house"]:
            debug_log.log(f"AI {self.player.name}: Checking {item_type} affordability:", "AI_ECONOMY")
            debug_log.log(f"  Costs from cost_data: {costs}", "AI_ECONOMY")
        
        for resource, amount in costs.items():
            player_amount = self.player.resources.get(resource, 0)
            if player_amount < amount:
                can_afford = False
                if item_type in ["mine", "quarry", "lumbermill", "farm", "barracks", "house"]:
                    debug_log.log(f"  Cannot afford - need {amount} {resource}, have {player_amount}", "AI_ECONOMY")
            else:
                if item_type in ["mine", "quarry", "lumbermill", "farm", "barracks", "house"]:
                    debug_log.log(f"  Can afford - need {amount} {resource}, have {player_amount}", "AI_ECONOMY")
        
        if item_type in ["mine", "quarry", "lumbermill", "farm", "barracks", "house"]:
            debug_log.log(f"  Final result: can_afford = {can_afford}", "AI_ECONOMY")
        
        return can_afford
    
    def _get_population_limit(self) -> int:
        """Get current population limit"""
        memory = self.ai_system.player_memory[self.player]
        base_limit = 5
        house_bonus = len(memory["buildings"]["houses"]) * 5
        return base_limit + house_bonus
    
    def _check_resource_diversity(self, delta_time: float) -> None:
        """Check if all workers are gathering the same resource and force diversity - simplified"""
        memory = self.ai_system.player_memory[self.player]
        gathering_workers = memory.get("gathering_workers", [])
        
        if len(gathering_workers) < 2:
            self.same_resource_timer = 0
            return
        
        # Simple check - if more than 3 workers on same resource, force diversity
        resource_counts = {}
        for worker in gathering_workers:
            if hasattr(worker, 'gathering_target') and worker.gathering_target:
                res_type = getattr(worker.gathering_target, 'name', None)
                if res_type:
                    resource_counts[res_type] = resource_counts.get(res_type, 0) + 1
        
        max_on_same_resource = max(resource_counts.values()) if resource_counts else 0
        if max_on_same_resource >= 3:
            self.force_next_update = True

    def _score_resource_buildings(self, resource_needs):
        """Scores all possible resource buildings based on needs and game state."""
        memory = self.ai_system.player_memory[self.player]
        scores = {}

        # Count existing and in-progress buildings
        existing_buildings = {b_type: 0 for b_type in ["mine", "lumbermill", "quarry", "farm"]}
        for b in memory["buildings"]["resource_buildings"]:
            if b.name in existing_buildings: existing_buildings[b.name] += 1
        for s in self.game.construction_sites:
            if s.player == self.player and s.building_name in existing_buildings: existing_buildings[s.building_name] += 1

        # Check distance to nearest resources for distance bonus
        castle = memory["buildings"]["castle"]
        distance_bonuses = {}
        if castle:
            resource_to_building = {"gold": "mine", "wood": "lumbermill", "stone": "quarry"}
            for res_type, building_type in resource_to_building.items():
                if res_type in memory["resource_locations"] and memory["resource_locations"][res_type]:
                    nearest_dist = min(math.sqrt((r.x - castle.x)**2 + (r.y - castle.y)**2) 
                                     for r in memory["resource_locations"][res_type])
                    # Add significant distance bonus if resources are far
                    if nearest_dist > 400:
                        distance_bonuses[building_type] = 70  # Very high priority
                    elif nearest_dist > 200:
                        distance_bonuses[building_type] = 50  # High priority
                        # Also mark this resource as needing a building
                        if res_type not in self.far_resources_need_buildings:
                            debug_log.log(f"AI {self.player.name}: Adding distance bonus for {building_type} - {res_type} is {nearest_dist:.0f} units away", "AI_ECONOMY")

        # Score Farm - always consider building at least one farm for food sustainability
        if existing_buildings["farm"] < 2:
            # First farm is high priority, second farm based on need
            if existing_buildings["farm"] == 0:
                scores["farm"] = 80  # High priority for first farm
                debug_log.log(f"AI {self.player.name}: First farm priority score: 80", "AI_ECONOMY")
            elif resource_needs.get("food", 0) > 0.2:  # Lower threshold for second farm
                scores["farm"] = 60 + resource_needs["food"] * 20  
                debug_log.log(f"AI {self.player.name}: Second farm score: {scores['farm']}", "AI_ECONOMY")

        # Score deposit-based buildings with higher base scores
        resource_to_building = {"gold": "mine", "wood": "lumbermill", "stone": "quarry"}
        for res_type, building_type in resource_to_building.items():
            # Check if this resource type has far deposits that need buildings
            if res_type in self.far_resources_need_buildings and existing_buildings[building_type] < 2:
                # CRITICAL priority - we can't gather without this building
                base_score = 150  # Very high base when needed for far resources
                scores[building_type] = base_score + distance_bonuses.get(building_type, 0)
                debug_log.log(f"AI {self.player.name}: CRITICAL - {building_type} needed for far {res_type}, score: {scores[building_type]}", "AI_ECONOMY")
            # Normal scoring for optional buildings
            elif resource_needs.get(res_type, 0) > 0.2 and existing_buildings[building_type] < 2:
                base_score = 70  # Normal base score
                need_bonus = resource_needs[res_type] * 30
                distance_bonus = distance_bonuses.get(building_type, 0)
                scores[building_type] = base_score + need_bonus + distance_bonus

        return scores
    
    def _check_far_resources(self, memory: Dict[str, Any]) -> None:
        """Check which resource types are too far and need buildings"""
        self.far_resources_need_buildings.clear()
        
        # Only check if we have a castle
        castle = memory["buildings"]["castle"]
        if not castle:
            return
            
        # Mapping of resources to buildings
        resource_to_building = {"gold": "mine", "wood": "lumbermill", "stone": "quarry"}
        
        # Check each resource type
        for res_type, building_type in resource_to_building.items():
            if res_type not in memory["resource_locations"]:
                continue
                
            resources = memory["resource_locations"][res_type]
            if not resources:
                continue
                
            # Find nearest resource distance
            nearest_dist = min(math.sqrt((r.x - castle.x)**2 + (r.y - castle.y)**2) 
                             for r in resources)
            
            # Check if we need a building for this resource
            if nearest_dist > 200:
                # Count existing buildings of this type
                existing = sum(1 for b in memory["buildings"]["resource_buildings"] if b.name == building_type)
                existing += sum(1 for s in self.game.construction_sites 
                              if s.player == self.player and s.building_name == building_type)
                
                # If we have less than 2 buildings for this far resource, mark it as needing a building
                if existing < 2:
                    self.far_resources_need_buildings.add(res_type)
                    debug_log.log(f"AI {self.player.name}: {res_type} resources are far ({nearest_dist:.0f} units), need {building_type}", "AI_ECONOMY")
    
