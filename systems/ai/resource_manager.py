"""Smart resource management system for AI"""
import math
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import time


class ResourceManager:
    """Manages resource allocation and predicts future needs"""
    
    def __init__(self, ai_system, player):
        self.ai_system = ai_system
        self.player = player
        self.game = ai_system.game
        
        # Resource tracking
        self.resource_history = defaultdict(list)  # Track resource amounts over time
        self.income_rates = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        self.consumption_rates = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        
        # Early game resource rotation
        self.early_game_resource_index = 0
        self.resources_being_gathered = set()  # Track which resources have workers
        
        # Priority resource stability
        self.current_priority_resource = None
        self.priority_set_time = 0
        self.priority_change_interval = 30.0  # Change priority every 30 seconds max
        
        # Game time tracking
        self.game_start_time = 0
        self.game_time = 0
        
        # Prediction settings - Reduced frequency for performance
        self.history_window = 10.0  # Track last 10 seconds
        self.prediction_horizon = 30.0  # Predict 30 seconds ahead
        self.update_interval = 3.0  # Update rates every 3 seconds (reduced from 1.0)
        self.last_update = 0
        
        # Caching for expensive operations
        self.cached_assignments = None
        self.cache_timestamp = 0
        self.cache_duration = 5.0  # Cache worker assignments for 5 seconds
        
        # Resource allocation
        self.resource_reservations = defaultdict(int)  # Reserved for future builds
        self.build_queue_costs = defaultdict(int)  # Costs of planned builds
        
        # Worker efficiency tracking
        self.worker_efficiency = {}  # Worker ID -> efficiency score
        self.resource_saturation = {}  # Resource ID -> worker count
        
    def update(self, delta_time: float) -> None:
        """Update resource tracking and predictions"""
        self.last_update += delta_time
        
        # Track game time
        if self.game_start_time == 0:
            self.game_start_time = time.time()
        self.game_time = time.time() - self.game_start_time
        
        if self.last_update >= self.update_interval:
            self._update_resource_history()
            self._calculate_income_rates()
            self._update_worker_efficiency()
            self.last_update = 0
    
    def get_available_resources(self) -> Dict[str, int]:
        """Get resources available after reservations"""
        available = {}
        for resource in ["gold", "wood", "stone", "food"]:
            current = self.player.resources.get(resource, 0)
            reserved = self.resource_reservations.get(resource, 0)
            available[resource] = max(0, current - reserved)
        return available
    
    def can_afford_with_prediction(self, item_type: str, time_horizon: float = 10.0) -> Tuple[bool, float]:
        """Check if we can afford item now or within time horizon"""
        costs = self.ai_system.cost_data.get(item_type, {})
        available = self.get_available_resources()
        
        # Check immediate affordability
        can_afford_now = all(available.get(res, 0) >= amount for res, amount in costs.items())
        if can_afford_now:
            return True, 0.0
        
        # Predict when we can afford
        max_wait_time = 0.0
        for resource, needed in costs.items():
            current = available.get(resource, 0)
            if current < needed:
                deficit = needed - current
                income_rate = self.income_rates.get(resource, 0)
                
                if income_rate > 0:
                    wait_time = deficit / income_rate
                    max_wait_time = max(max_wait_time, wait_time)
                else:
                    return False, float('inf')  # Can't afford without income
        
        return max_wait_time <= time_horizon, max_wait_time
    
    def reserve_resources(self, item_type: str) -> bool:
        """Reserve resources for future purchase"""
        costs = self.ai_system.cost_data.get(item_type, {})
        available = self.get_available_resources()
        
        # Check if we can reserve
        for resource, amount in costs.items():
            if available.get(resource, 0) < amount:
                return False
        
        # Make reservation
        for resource, amount in costs.items():
            self.resource_reservations[resource] += amount
        
        return True
    
    def release_reservation(self, item_type: str) -> None:
        """Release reserved resources"""
        costs = self.ai_system.cost_data.get(item_type, {})
        for resource, amount in costs.items():
            self.resource_reservations[resource] = max(0, 
                self.resource_reservations[resource] - amount)
    
    def get_priority_resource(self, time_horizon: float = 30.0) -> Optional[str]:
        """Determine which resource to prioritize gathering with stable early game strategy"""
        memory = self.ai_system.player_memory[self.player]
        current_time = time.time()
        
        # Get available resources (exclude stone for first 10 minutes)
        available_resources = []
        early_game_resources = ["gold", "wood", "food"]  # Core early game resources
        if self.game_time > 600:  # After 10 minutes, include stone
            early_game_resources.append("stone")
            
        for resource in early_game_resources:
            if resource in memory.get("resource_locations", {}):
                resources = memory["resource_locations"][resource]
                if resources and any(r.amount_remaining > 0 for r in resources):
                    available_resources.append(resource)
        
        if not available_resources:
            print(f"AI {self.player.name}: No available resources")
            return None
        
        # Early game strategy (first 5 minutes): Stable 33% distribution
        if self.game_time < 300:  # First 5 minutes
            # Check if we need to update priority (or set initial)
            if (self.current_priority_resource is None or 
                self.current_priority_resource not in available_resources or
                current_time - self.priority_set_time > self.priority_change_interval):
                
                # Calculate current worker distribution
                resource_worker_counts = {"gold": 0, "wood": 0, "food": 0, "stone": 0}
                for worker in memory.get("gathering_workers", []):
                    if hasattr(worker, 'gathering_target') and worker.gathering_target:
                        res_type = getattr(worker.gathering_target, 'name', None)
                        if res_type in resource_worker_counts:
                            resource_worker_counts[res_type] += 1
                
                # Find resource with least workers (for balanced distribution)
                total_workers = sum(resource_worker_counts.values())
                if total_workers == 0:
                    # First worker - start with gold
                    self.current_priority_resource = "gold"
                else:
                    # Find resource with least workers among available resources
                    min_workers = float('inf')
                    best_resource = None
                    for res in available_resources:
                        worker_count = resource_worker_counts.get(res, 0)
                        if worker_count < min_workers:
                            min_workers = worker_count
                            best_resource = res
                    
                    # If we found a resource with no workers, prioritize it
                    if best_resource and min_workers == 0:
                        self.current_priority_resource = best_resource
                    else:
                        # Otherwise, use deficit calculation
                        target_per_resource = max(1, total_workers / len(available_resources))
                        deficits = {}
                        for res in available_resources:
                            current_workers = resource_worker_counts.get(res, 0)
                            deficit = target_per_resource - current_workers
                            deficits[res] = deficit
                        
                        # Choose resource with highest deficit
                        self.current_priority_resource = max(deficits.items(), key=lambda x: x[1])[0]
                
                self.priority_set_time = current_time
                print(f"AI {self.player.name}: Early game priority set to {self.current_priority_resource} (game time: {self.game_time:.1f}s)")
                
                # Log worker distribution for debugging
                dist_str = ", ".join([f"{res}: {count}" for res, count in resource_worker_counts.items() if res in available_resources])
                print(f"AI {self.player.name}: Current worker distribution: {dist_str}")
            
            return self.current_priority_resource
        
        # Mid/late game: Use more complex needs-based strategy
        total_income = sum(self.income_rates.values())
        if total_income > 0:
            # Calculate future needs and deficits
            future_needs = self._predict_resource_needs(time_horizon)
            deficits = {}
            
            for resource in available_resources:
                current = self.player.resources.get(resource, 0)
                predicted_income = self.income_rates[resource] * time_horizon
                predicted_consumption = self.consumption_rates[resource] * time_horizon
                predicted_amount = current + predicted_income - predicted_consumption
                
                deficit = future_needs[resource] - predicted_amount
                if deficit > 0:
                    deficits[resource] = deficit
            
            if deficits:
                # Update priority only if significant change needed or time elapsed
                if (self.current_priority_resource is None or
                    current_time - self.priority_set_time > self.priority_change_interval):
                    
                    self.current_priority_resource = max(deficits.items(), key=lambda x: x[1])[0]
                    self.priority_set_time = current_time
                    print(f"AI {self.player.name}: Mid-game priority updated to {self.current_priority_resource}")
                
                return self.current_priority_resource
        
        # Fallback: Return current priority or first available
        if self.current_priority_resource and self.current_priority_resource in available_resources:
            return self.current_priority_resource
        else:
            self.current_priority_resource = available_resources[0]
            self.priority_set_time = current_time
            return self.current_priority_resource
    
    def _find_closest_resource_to_position(self, resource_type: str, x: float, y: float, memory: dict) -> Optional[Tuple[Any, float]]:
        """Find the closest resource of given type to a position"""
        if resource_type not in memory["resource_locations"]:
            return None
            
        resources = memory["resource_locations"][resource_type]
        if not resources:
            return None
            
        closest = None
        min_distance = float('inf')
        
        for resource in resources:
            if hasattr(resource, 'amount_remaining') and resource.amount_remaining <= 0:
                continue
            distance = math.sqrt((resource.x - x)**2 + (resource.y - y)**2)
            if distance < min_distance:
                min_distance = distance
                closest = resource
                
        return (closest, min_distance) if closest else None

    def get_optimal_worker_assignment(self, workers: List) -> Dict:
        """Calculate optimal worker distribution across resources with caching"""
        current_time = time.time()
        
        # Use cached result if still valid and same workers
        if (self.cached_assignments is not None and 
            current_time - self.cache_timestamp < self.cache_duration and
            len(workers) == len(self.cached_assignments.get('workers', []))):
            # Return cached assignments adapted to current workers
            return self._adapt_cached_assignments(workers)
        
        assignments = defaultdict(list)
        memory = self.ai_system.player_memory[self.player]
        
        # Get available resources (respect early game stone exclusion)
        early_game_resources = ["gold", "wood", "food"]  # Core early game resources
        if self.game_time > 600:  # After 10 minutes, include stone
            early_game_resources.append("stone")
        
        # Check if economy module has far resources marked
        far_resources = set()
        economy_module = self.ai_system.player_modules.get(self.player, {}).get("economy")
        if economy_module and hasattr(economy_module, 'far_resources_need_buildings'):
            far_resources = economy_module.far_resources_need_buildings
            
        available_resources = [r for r in early_game_resources
                             if r in memory["resource_locations"] and memory["resource_locations"][r]
                             and r not in far_resources]  # Exclude far resources that need buildings
        
        if far_resources:
            print(f"AI {self.player.name}: Excluding far resources from assignment: {far_resources}")
        
        if not available_resources:
            print(f"AI {self.player.name}: No available resources for worker assignment (far resources excluded: {far_resources})")
            return assignments
        
        # New strategy: Consider distance when assigning workers
        if len(workers) <= 4:
            # For 4 or fewer workers, prioritize having at least one worker on each available resource
            # Check current distribution to see which resources need workers
            resource_worker_counts = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
            for worker in memory.get("gathering_workers", []):
                if hasattr(worker, 'gathering_target') and worker.gathering_target:
                    res_type = getattr(worker.gathering_target, 'name', None)
                    if res_type in resource_worker_counts:
                        resource_worker_counts[res_type] += 1
            
            # Find resources with no workers first
            unassigned_resources = [res for res in available_resources if resource_worker_counts.get(res, 0) == 0]
            
            # For each worker, find the closest available resource type
            # But ensure diversity by tracking assignments
            assigned_counts = {res: 0 for res in available_resources}
            
            for worker in workers:
                best_resource = None
                best_distance = float('inf')
                
                # First pass: check unassigned resource types
                for res_type in unassigned_resources:
                    if assigned_counts[res_type] == 0:  # No one assigned yet this round
                        result = self._find_closest_resource_to_position(res_type, worker.x, worker.y, memory)
                        if result:
                            _, distance = result
                            # Penalize very distant resources
                            if distance < 200 or (distance < best_distance and distance < 400):
                                best_distance = distance
                                best_resource = res_type
                
                # Second pass: if all unassigned types are far, check all types
                if best_resource is None:
                    for res_type in available_resources:
                        result = self._find_closest_resource_to_position(res_type, worker.x, worker.y, memory)
                        if result:
                            _, distance = result
                            # Add penalty for already assigned resources to encourage diversity
                            effective_distance = distance + (assigned_counts[res_type] * 100)
                            if effective_distance < best_distance:
                                best_distance = effective_distance
                                best_resource = res_type
                
                if best_resource:
                    assignments[best_resource].append(worker)
                    assigned_counts[best_resource] += 1
                    # Remove from unassigned if someone got assigned
                    if best_resource in unassigned_resources and assigned_counts[best_resource] > 0:
                        unassigned_resources.remove(best_resource)
                
            print(f"AI {self.player.name}: Distance-aware diversity assignment - distributed {len(workers)} workers")
            print(f"AI {self.player.name}: Assignment counts: {assigned_counts}")
        else:
            # For more workers, use priority-based assignment
            priority_resource = self.get_priority_resource(15.0)  # Shorter horizon for performance
            
            if priority_resource and priority_resource in available_resources:
                # First ensure each resource has at least one worker
                worker_index = 0
                for resource in available_resources:
                    if worker_index < len(workers):
                        assignments[resource].append(workers[worker_index])
                        worker_index += 1
                
                # Assign remaining workers based on priority
                remaining_workers = workers[worker_index:]
                if remaining_workers and priority_resource:
                    # Assign 60% of remaining to priority, rest distributed
                    priority_count = max(1, int(len(remaining_workers) * 0.6))
                    for i in range(priority_count):
                        if worker_index < len(workers):
                            assignments[priority_resource].append(workers[worker_index])
                            worker_index += 1
                    
                    # Distribute any remaining workers
                    while worker_index < len(workers):
                        for resource in available_resources:
                            if worker_index < len(workers):
                                assignments[resource].append(workers[worker_index])
                                worker_index += 1
                                
                print(f"AI {self.player.name}: Priority assignment with diversity - {priority_resource} priority")
            else:
                # Fallback: Simple round-robin
                for i, worker in enumerate(workers):
                    res_type = available_resources[i % len(available_resources)]
                    assignments[res_type].append(worker)
                    
                print(f"AI {self.player.name}: Round-robin assigned {len(workers)} workers")
        
        # Update tracking of which resources are being gathered
        self.resources_being_gathered = set(assignments.keys())
        
        # Verify all workers got assigned
        total_assigned = sum(len(worker_list) for worker_list in assignments.values())
        if total_assigned != len(workers):
            print(f"AI {self.player.name}: WARNING - Only {total_assigned}/{len(workers)} workers assigned!")
        
        # Cache the result
        self.cached_assignments = {'assignments': dict(assignments), 'workers': workers[:]}
        self.cache_timestamp = current_time
        
        # Debug output
        assignment_summary = {res_type: len(worker_list) for res_type, worker_list in assignments.items()}
        print(f"AI {self.player.name}: Final assignments: {assignment_summary}")
        
        return assignments
    
    def _update_resource_history(self) -> None:
        """Update resource amount history"""
        current_time = time.time()
        
        for resource in ["gold", "wood", "stone", "food"]:
            amount = self.player.resources.get(resource, 0)
            history = self.resource_history[resource]
            
            # Add new entry
            history.append((current_time, amount))
            
            # Remove old entries
            cutoff_time = current_time - self.history_window
            self.resource_history[resource] = [
                (t, a) for t, a in history if t > cutoff_time
            ]
    
    def _calculate_income_rates(self) -> None:
        """Calculate resource income rates from history"""
        current_time = time.time()
        
        for resource in ["gold", "wood", "stone", "food"]:
            history = self.resource_history[resource]
            
            if len(history) < 2:
                self.income_rates[resource] = 0
                continue
            
            # Use linear regression for rate calculation
            time_span = history[-1][0] - history[0][0]
            if time_span > 0:
                amount_change = history[-1][1] - history[0][1]
                self.income_rates[resource] = max(0, amount_change / time_span)
    
    def _update_worker_efficiency(self) -> None:
        """Track worker gathering efficiency"""
        memory = self.ai_system.player_memory[self.player]
        
        # Reset saturation counts
        self.resource_saturation.clear()
        
        # Update which resources are actually being gathered
        self.resources_being_gathered.clear()
        
        # Count workers per resource
        for worker in memory["gathering_workers"]:
            if hasattr(worker, 'gathering_target') and worker.gathering_target:
                target = worker.gathering_target
                self.resource_saturation[id(target)] = self.resource_saturation.get(id(target), 0) + 1
                
                # Track resource types being gathered
                if hasattr(target, 'name'):
                    self.resources_being_gathered.add(target.name)
                
                # Simple efficiency based on travel distance
                if hasattr(worker, 'gathering_start_time'):
                    efficiency = 1.0  # Base efficiency
                    # Could add more factors here
                    self.worker_efficiency[id(worker)] = efficiency
    
    def _predict_resource_needs(self, time_horizon: float) -> Dict[str, int]:
        """Predict resource needs for the next time period"""
        needs = {"gold": 0, "wood": 0, "stone": 0, "food": 0}
        memory = self.ai_system.player_memory[self.player]
        
        # Base needs by game phase
        phase_multipliers = {
            "early": {"gold": 1.0, "wood": 1.5, "stone": 0.5, "food": 1.0},
            "mid": {"gold": 1.5, "wood": 2.0, "stone": 1.0, "food": 1.5},
            "late": {"gold": 2.0, "wood": 2.0, "stone": 1.5, "food": 2.0}
        }
        
        phase = memory.get("game_phase", "early")
        multipliers = phase_multipliers.get(phase, phase_multipliers["early"])
        
        # Calculate base needs
        base_needs = {
            "gold": 50 * multipliers["gold"],
            "wood": 100 * multipliers["wood"],
            "stone": 30 * multipliers["stone"],
            "food": 50 * multipliers["food"]
        }
        
        # Add planned building costs
        for resource, amount in self.build_queue_costs.items():
            needs[resource] = base_needs.get(resource, 0) + amount
        
        # Add military upkeep estimates
        military_count = len(memory["military_units"])
        needs["food"] += military_count * 2  # Assume 2 food per military unit
        
        return needs
    
    def _get_target_income_rate(self, resource: str) -> float:
        """Get target income rate for resource"""
        # Base rates that should be maintained
        base_rates = {
            "gold": 2.0,  # 2 gold per second
            "wood": 3.0,  # 3 wood per second
            "stone": 1.0,  # 1 stone per second
            "food": 2.0   # 2 food per second
        }
        
        memory = self.ai_system.player_memory[self.player]
        phase = memory.get("game_phase", "early")
        
        # Adjust by game phase
        phase_multipliers = {
            "early": 0.5,
            "mid": 1.0,
            "late": 1.5
        }
        
        multiplier = phase_multipliers.get(phase, 1.0)
        return base_rates.get(resource, 1.0) * multiplier
    
    def _get_average_saturation(self, resource_type: str) -> float:
        """Get average worker saturation for resource type"""
        memory = self.ai_system.player_memory[self.player]
        
        if resource_type not in memory["resource_locations"]:
            return 0.0
        
        resources = memory["resource_locations"][resource_type]
        if not resources:
            return 0.0
        
        total_workers = 0
        for resource in resources:
            workers = self.resource_saturation.get(id(resource), 0)
            total_workers += workers
        
        return total_workers / len(resources)
    
    def _adapt_cached_assignments(self, workers: List) -> Dict:
        """Adapt cached assignments to current worker list"""
        assignments = defaultdict(list)
        cached = self.cached_assignments['assignments']
        
        # Simple adaptation: maintain resource distribution
        total_cached = sum(len(worker_list) for worker_list in cached.values())
        if total_cached == 0:
            return assignments
            
        worker_index = 0
        for res_type, cached_workers in cached.items():
            # Assign proportional number of current workers
            proportion = len(cached_workers) / total_cached
            num_workers = int(len(workers) * proportion)
            
            for _ in range(num_workers):
                if worker_index < len(workers):
                    assignments[res_type].append(workers[worker_index])
                    worker_index += 1
        
        # Assign any remaining workers to first available resource
        if worker_index < len(workers) and assignments:
            first_resource = next(iter(assignments.keys()))
            for i in range(worker_index, len(workers)):
                assignments[first_resource].append(workers[i])
        
        return assignments