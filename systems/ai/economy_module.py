"""Economy AI module for resource gathering and management"""
import math
import random
import pygame
from typing import Dict, List, Tuple, Optional, Any
from .base_module import AIModule
from .resource_manager import ResourceManager
from entities.objects import Unit, Building, Resource


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
                print(f"AI {self.player.name}: Forcing update - {len(idle_workers)} idle workers, {len(disconnected_workers)} disconnected")
            if self.force_next_update:
                print(f"AI {self.player.name}: Forcing update due to force_next_update flag")
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
        print(f"AI {self.player.name}: Game phase: {game_phase}, Resource needs: {resource_needs}")

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
        print(f"AI {self.player.name}: Resource building scores: {building_scores}")
        for building_type, score in building_scores.items():
            if self._can_afford(building_type):
                possible_actions.append({"action": "build_resource_building", "score": score, "params": {"building_type": building_type}})

        # Action: Build Barracks
        # Build barracks when we have at least 3 workers and no barracks yet
        barracks_count = len(memory["buildings"].get("barracks", []))
        # Check barracks cost details
        if barracks_count == 0:
            barracks_costs = self.ai_system.cost_data.get("barracks", {})
            player_resources = {k: int(v) for k, v in self.player.resources.items()}
            can_afford = self._can_afford("barracks")
            print(f"AI {self.player.name}: Barracks check - workers: {worker_count}, barracks: {barracks_count}")
            print(f"  Resources: {player_resources}")
            print(f"  Barracks costs: {barracks_costs}")
            print(f"  Can afford: {can_afford}")
        if worker_count >= 3 and barracks_count == 0 and self._can_afford("barracks"):
            # Scale barracks priority with worker count - more workers = higher priority
            # Base score 85, +5 per worker above 3 (max +25 at 8 workers)
            worker_bonus = min((worker_count - 3) * 5, 25)
            barracks_score = 85 + worker_bonus
            possible_actions.append({"action": "build_barracks", "score": barracks_score})
            print(f"AI {self.player.name}: Added barracks to possible actions with score {barracks_score} (base 85 + worker bonus {worker_bonus})")

        # 3. Assign idle workers to gather resources
        if all_idle_workers:
            assignments = self.resource_manager.get_optimal_worker_assignment(all_idle_workers)
            for resource_type, workers in assignments.items():
                for worker in workers:
                    tasks.append({"action": "gather_resource", "priority": 0.95, "target": worker, "params": {"resource_type": resource_type}})

        # 4. Select the best economic action and create a task for it
        if possible_actions:
            # Debug: Log all possible actions and their scores
            print(f"AI {self.player.name}: Possible actions:")
            for action in possible_actions:
                print(f"  - {action['action']}: score {action['score']}")
            
            best_action = max(possible_actions, key=lambda x: x["score"])
            action_type = best_action["action"]
            print(f"AI {self.player.name}: Selected action: {action_type} (score: {best_action['score']})")

            if action_type == "train_worker":
                tasks.append({"action": "train_worker", "priority": 0.8, "target": memory["buildings"]["castle"], "params": {}})
            elif action_type == "build_house":
                tasks.append({"action": "build_house", "priority": 0.85, "target": None, "params": {}})
            elif action_type == "build_barracks":
                tasks.append({"action": "build_barracks", "priority": 0.85, "target": None, "params": {"building_type": "barracks"}})
            elif action_type == "build_resource_building":
                tasks.append({"action": "build_resource_building", "priority": 0.7, "target": None, "params": best_action["params"]})

        return tasks
    
    def execute_task(self, task: Dict[str, Any]) -> bool:
        """Execute economic task"""
        action = task["action"]
        
        if action == "gather_resource":
            return self._execute_gather_resource(task)
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
        
        if resource_type in memory["resource_locations"]:
            resources = memory["resource_locations"][resource_type]
            
            if resources:
                # Find closest resource
                closest = min(resources, key=lambda r: math.sqrt((r.x - worker.x)**2 + (r.y - worker.y)**2))
                distance = math.sqrt((closest.x - worker.x)**2 + (closest.y - worker.y)**2)
                
                # Check if resource is too far (>200 units) and we should build a resource building
                if distance > 200:
                    resource_to_building = {"gold": "mine", "wood": "lumbermill", "stone": "quarry"}
                    building_type = resource_to_building.get(resource_type)
                    
                    if building_type:
                        # Count existing buildings
                        existing = sum(1 for b in memory["buildings"]["resource_buildings"] if b.name == building_type)
                        existing += sum(1 for s in self.game.construction_sites 
                                      if s.player == self.player and s.building_name == building_type)
                        
                        # If we have less than 2 of this building type, prioritize building
                        if existing < 2:
                            # Don't gather from far resources - force building instead
                            print(f"AI {self.player.name}: Resource {resource_type} too far ({distance:.0f} units), refusing to gather - need {building_type}")
                            # Mark this as a high priority need
                            self.force_next_update = True
                            return False
                        # If we already have 2 buildings but resource still far, warn but continue
                        elif distance > 400:
                            print(f"AI {self.player.name}: Warning - gathering {resource_type} from very far ({distance:.0f} units)")
                
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
        print(f"AI {self.player.name}: Building barracks for military production")
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
            print(f"AI {self.player.name}: Forcing resource diversity - stopping most workers")
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
        for resource, amount in costs.items():
            if self.player.resources.get(resource, 0) < amount:
                can_afford = False
        
        # Debug logging for barracks
        if item_type == "barracks":
            print(f"AI {self.player.name}: Checking barracks affordability:")
            print(f"  Costs: {costs}")
            print(f"  Current resources: gold={self.player.resources.get('gold', 0)}, wood={self.player.resources.get('wood', 0)}, stone={self.player.resources.get('stone', 0)}")
            print(f"  Can afford: {can_afford}")
        
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
                        distance_bonuses[building_type] = 50  # Very high priority
                    elif nearest_dist > 200:
                        distance_bonuses[building_type] = 35  # High priority

        # Score Farm with higher base and lower threshold
        if resource_needs.get("food", 0) > 0.3 and existing_buildings["farm"] < 2:
            scores["farm"] = 70 + resource_needs["food"] * 20  # Reduced from 85 to make barracks more competitive

        # Score deposit-based buildings with higher base scores
        resource_to_building = {"gold": "mine", "wood": "lumbermill", "stone": "quarry"}
        for res_type, building_type in resource_to_building.items():
            # Lower threshold (0.2) and allow up to 2 of each type
            if resource_needs.get(res_type, 0) > 0.2 and existing_buildings[building_type] < 2:
                base_score = 70  # Reduced from 85 to make barracks more competitive
                need_bonus = resource_needs[res_type] * 30
                distance_bonus = distance_bonuses.get(building_type, 0)
                scores[building_type] = base_score + need_bonus + distance_bonus

        return scores
    
