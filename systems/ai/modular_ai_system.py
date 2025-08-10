"""Modular AI system with specialized behavior modules"""
import json
import math
import pygame
from typing import Dict, List, Optional, Any
from entities.objects import Unit, Building, Resource, ConstructionSite
from systems.pathfinding import Pathfinding
from entities.player import Player
from utils.debug_logger import debug_log

# Import AI modules
from .economy_module import EconomyModule
from .military_module import MilitaryModule  
from .exploration_module import ExplorationModule
from .building_placement import BuildingPlacementManager


class ModularAISystem:
    """Modular AI system that coordinates specialized behavior modules"""
    
    def __init__(self, game):
        self.game = game
        self.ai_players = [p for p in game.players if not p.human]
        
        # Initialize modules for each AI player
        self.player_modules = {}
        self.building_placement_managers = {}
        for player in self.ai_players:
            # Create building placement manager first
            self.building_placement_managers[player] = BuildingPlacementManager(self, player)
            
            # Initialize modules with building placement access
            self.player_modules[player] = {
                "economy": EconomyModule(self, player),
                "military": MilitaryModule(self, player),
                "exploration": ExplorationModule(self, player)
            }
        
        # Task execution settings - Reduced frequency for performance
        self.max_tasks_per_update = 3  # Execute up to 3 tasks per update (increased for more action)
        self.task_cooldown = 1.0  # Minimum time between task executions (reduced for faster decisions)
        self.last_task_time = {player: 0 for player in self.ai_players}
        
        # Building cooldowns
        self.last_building_time = {player: 0 for player in self.ai_players}
        self.building_cooldown = 3.0  # Reduced from 5.0 for faster building
        
        # Player memory system
        self.player_memory = {
            player: {
                "idle_workers": [],
                "gathering_workers": [],
                "building_workers": [],
                "enemy_locations": [],
                "resource_locations": {},
                "last_building_position": None,
                "scout_units": [],
                "military_units": [],
                "buildings": {
                    "castle": None,
                    "barracks": [],
                    "houses": [],
                    "resource_buildings": []
                },
                "game_phase": "early",  # early, mid, late
                "last_unit_count": 0,  # Track unit count changes
                "new_units_detected": False  # Flag for new unit detection
            } for player in self.ai_players
        }
        
        # Cache cost data
        self.cost_data = self._load_cost_data()
        
        # Pathfinder caching for performance
        self.pathfinders = {player: Pathfinding(game.game_map, game) for player in self.ai_players}
        
        # Performance tracking
        self.update_times = []
        self.max_update_time = 0.05  # 50ms max per update
        
        # Memory caching for performance
        self.memory_cache_valid = {player: False for player in self.ai_players}
        self.last_memory_update = {player: 0 for player in self.ai_players}
        self.memory_update_interval = 1.0  # Update memory every 1 second instead of every frame
        
        # Staggered update system
        self.update_stagger = {player: i * 0.5 for i, player in enumerate(self.ai_players)}
        self.stagger_timer = 0
        
    def _load_cost_data(self):
        """Load and cache cost data from JSON files"""
        cost_data = {}
        
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            for unit in units_data:
                cost_data[unit['name']] = unit.get('costs', {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            debug_log.log(f"Warning: Could not load unit costs: {e}", "AI")
            
        try:
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            for building in buildings_data:
                cost_data[building['name']] = building.get('costs', {})
                # Debug log building costs
                if building['name'] in ['farm', 'quarry', 'mine', 'lumbermill', 'barracks']:
                    debug_log.log(f"Loaded costs for {building['name']}: {cost_data[building['name']]}", "AI_INIT")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            debug_log.log(f"Warning: Could not load building costs: {e}", "AI")
            
        return cost_data
    
    def update(self, delta_time: float) -> None:
        """Update AI for all AI players with staggered updates for performance"""
        self.stagger_timer += delta_time
        
        for player in self.ai_players:
            # Stagger updates to spread CPU load
            stagger_offset = self.update_stagger[player]
            if (self.stagger_timer + stagger_offset) % 1.0 < delta_time:  # Update every 1 second with stagger (faster)
                start_time = pygame.time.get_ticks() / 1000.0
                
                try:
                    # Update player memory only when needed
                    current_time = pygame.time.get_ticks() / 1000.0
                    if (current_time - self.last_memory_update[player] >= self.memory_update_interval or
                        not self.memory_cache_valid[player]):
                        self._update_player_memory(player)
                        self.last_memory_update[player] = current_time
                        self.memory_cache_valid[player] = True
                    
                    # Update game phase
                    self._update_game_phase(player)
                    
                    # Verify and fix worker states periodically
                    if current_time - getattr(self, '_last_state_check', 0) > 0.5:  # Check every 0.5 seconds
                        self._verify_worker_states(player)
                        self._last_state_check = current_time
                    
                    # Update building placement manager
                    self.building_placement_managers[player].update(delta_time)
                    
                    # Update each module with reduced frequency
                    modules = self.player_modules[player]
                    for module in modules.values():
                        module.update(delta_time)
                    
                    # Check if enough time has passed for task execution
                    # Also check if any module has force_next_update set
                    force_update = any(hasattr(m, 'force_next_update') and m.force_next_update 
                                     for m in modules.values())
                    
                    if current_time - self.last_task_time[player] >= self.task_cooldown or force_update:
                        # Collect tasks from all modules
                        all_tasks = []
                        for module_name, module in modules.items():
                            should_update = module.should_update()
                            if should_update:
                                tasks = module.get_tasks()
                                for task in tasks:
                                    task["module"] = module_name
                                all_tasks.extend(tasks)
                                module.reset_update_timer()
                        
                        if all_tasks:
                            all_tasks.sort(key=lambda t: t["priority"], reverse=True)
                            
                            executed = 0
                            for i, task in enumerate(all_tasks[:self.max_tasks_per_update]):
                                module = modules[task["module"]]
                                task_success = module.execute_task(task)
                                if task_success:
                                    executed += 1
                                    if executed >= self.max_tasks_per_update:
                                        break
                        
                            if executed > 0:
                                self.last_task_time[player] = current_time
                
                except Exception as e:
                    debug_log.log(f"Error updating AI for player {player.name}: {e}", "AI")
                
                # Track performance
                update_time = (pygame.time.get_ticks() / 1000.0) - start_time
                if update_time > self.max_update_time:
                    debug_log.log(f"AI update for {player.name} took {update_time:.3f}s (exceeds limit)", "AI")
    
    def _update_player_memory(self, player: Player) -> None:
        """Update what the AI knows about the game state"""
        memory = self.player_memory[player]
        
        # Count units before clearing lists
        previous_unit_count = memory.get("last_unit_count", 0)
        current_unit_count = len([u for u in self.game.units if u.player == player])
        
        # Detect new units
        if current_unit_count > previous_unit_count:
            memory["new_units_detected"] = True
            # Force economy module update for new workers
            if player in self.player_modules:
                economy_module = self.player_modules[player].get("economy")
                if economy_module:
                    economy_module.force_next_update = True
        else:
            memory["new_units_detected"] = False
        
        memory["last_unit_count"] = current_unit_count
        
        # Clear old data
        memory["idle_workers"].clear()
        memory["gathering_workers"].clear()
        memory["building_workers"].clear()
        memory["scout_units"].clear()
        memory["military_units"].clear()
        
        # Update unit lists with improved worker detection
        for unit in self.game.units:
            if hasattr(unit, 'player') and unit.player == player:
                if hasattr(unit, 'name') and unit.name == "worker":
                    # Check for building state
                    if unit.is_building or (unit.building_target and unit.status == "run"):
                        memory["building_workers"].append(unit)
                    # Check for gathering state
                    elif unit.is_gathering or (unit.gathering_target and unit.status == "run"):
                        memory["gathering_workers"].append(unit)
                    # Otherwise, worker is idle
                    else:
                        memory["idle_workers"].append(unit)
                elif hasattr(unit, 'name') and unit.name in ["warrior", "archer"]:
                    memory["military_units"].append(unit)
                    
        # Update building lists
        memory["buildings"]["castle"] = None
        memory["buildings"]["barracks"].clear()
        memory["buildings"]["houses"].clear()
        memory["buildings"]["resource_buildings"].clear()
        
        for building in self.game.buildings:
            if hasattr(building, 'player') and building.player == player:
                if hasattr(building, 'name'):
                    if building.name == "castle":
                        memory["buildings"]["castle"] = building
                    elif building.name == "barracks":
                        memory["buildings"]["barracks"].append(building)
                    elif building.name == "house":
                        memory["buildings"]["houses"].append(building)
                    elif building.name in ["mine", "quarry", "lumbermill", "farm"]:
                        memory["buildings"]["resource_buildings"].append(building)
        
        # Update resource locations with validation
        memory["resource_locations"].clear()
        resource_counts = {}
        for resource in self.game.resources:
            if hasattr(resource, 'amount_remaining') and resource.amount_remaining > 0:
                if hasattr(resource, 'name'):
                    res_type = resource.name
                    if res_type not in memory["resource_locations"]:
                        memory["resource_locations"][res_type] = []
                    memory["resource_locations"][res_type].append(resource)
                    resource_counts[res_type] = resource_counts.get(res_type, 0) + 1
        
        
                    
        # Update enemy locations
        memory["enemy_locations"].clear()
        for unit in self.game.units:
            if hasattr(unit, 'player') and unit.player != player:
                if hasattr(unit, 'x') and hasattr(unit, 'y'):
                    memory["enemy_locations"].append((unit.x, unit.y))
        for building in self.game.buildings:
            if hasattr(building, 'player') and building.player != player:
                if hasattr(building, 'x') and hasattr(building, 'y'):
                    memory["enemy_locations"].append((building.x, building.y))
    
    def _update_game_phase(self, player: Player) -> None:
        """Update game phase based on player progress"""
        memory = self.player_memory[player]
        
        # Count buildings and units
        building_count = sum(len(buildings) for buildings in memory["buildings"].values() if isinstance(buildings, list))
        if memory["buildings"]["castle"]:
            building_count += 1
            
        unit_count = len([u for u in self.game.units if u.player == player])
        
        # Determine phase
        if building_count < 3 or unit_count < 5:
            memory["game_phase"] = "early"
        elif building_count < 8 or unit_count < 15:
            memory["game_phase"] = "mid"
        else:
            memory["game_phase"] = "late"
        
        # Adjust module priorities based on phase
        modules = self.player_modules[player]
        if memory["game_phase"] == "early":
            modules["economy"].set_priority(0.9)
            modules["military"].set_priority(0.4)
            modules["exploration"].set_priority(0.6)
        elif memory["game_phase"] == "mid":
            modules["economy"].set_priority(0.7)
            modules["military"].set_priority(0.7)
            modules["exploration"].set_priority(0.4)
        else:  # late
            modules["economy"].set_priority(0.5)
            modules["military"].set_priority(0.9)
            modules["exploration"].set_priority(0.3)
    
    def _verify_worker_states(self, player: Player) -> None:
        """Verify and fix worker states to ensure consistency - simplified approach"""
        workers = [u for u in self.game.units if u.player == player and u.name == "worker"]
        
        for worker in workers:
            # Simple recovery: if worker has been idle too long with gathering target, clear target
            if (hasattr(worker, 'gathering_target') and worker.gathering_target and 
                worker.status == "idle" and 
                not getattr(worker, 'is_gathering', False) and
                not worker.destination and not worker.path):
                
                # Worker is stuck - clear target so it can be reassigned
                worker.gathering_target = None
                worker.is_engaging = False
    
    # Command interface methods (used by modules)
    
    def _can_afford(self, player: Player, item_type: str) -> bool:
        """Check if player can afford to build/train something"""
        costs = self.cost_data.get(item_type, {})
        
        if not costs:
            return False
            
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False
                
        return True
    
    def _command_unit_move(self, unit, target_pos):
        """Command a unit to move to position using cached pathfinder"""
        try:
            pathfinder = self.pathfinders[unit.player]
            self.game.selection_manager._move_unit_to_position(unit, target_pos, pathfinder)
        except Exception as e:
            debug_log.log(f"Error commanding unit move: {e}", "AI")
    
    def _command_unit_attack(self, unit, target):
        """Command a unit to attack target using cached pathfinder"""
        try:
            pathfinder = self.pathfinders[unit.player]
            self.game.selection_manager._attack_target(unit, target, pathfinder)
        except Exception as e:
            debug_log.log(f"Error commanding unit attack: {e}", "AI")
    
    def _command_worker_gather(self, worker, resource):
        """Command a worker to gather from resource"""
        try:
            # Add safety check for resource state
            if not resource or getattr(resource, 'amount_remaining', 0) <= 0:
                return
            
            # Use selection manager's gather method for proper pathfinding
            pathfinder = Pathfinding(self.game.game_map, self.game)
            pathfinder.gathering_target = resource
            self.game.selection_manager._gather_from_target(worker, resource, pathfinder)
            
            debug_log.log(f"AI {worker.player.name}: === GATHER TASK SUCCESS ===", "AI")
            debug_log.log(f"Worker assigned to gather from {resource.name} at ({resource.x:.0f}, {resource.y:.0f})", "AI")
                
        except Exception as e:
            debug_log.log(f"AI {worker.player.name}: Worker gather command failed: {e}", "AI")
            # Clean up worker state if command failed
            if hasattr(worker, 'gathering_target'):
                worker.gathering_target = None
    
    def _build_structure(self, player, building_type):
        """Command a worker to build a structure"""
        memory = self.player_memory[player]
        
        # Check building cooldown
        current_time = pygame.time.get_ticks() / 1000.0
        if current_time - self.last_building_time.get(player, 0) < self.building_cooldown:
            debug_log.log(f"AI {player.name}: Building on cooldown, {self.building_cooldown - (current_time - self.last_building_time.get(player, 0)):.1f}s remaining", "AI")
            return
        
        # Count actual workers
        idle_count = len(memory.get("idle_workers", []))
        gathering_count = len(memory.get("gathering_workers", []))
        building_count = len(memory.get("building_workers", []))
        total_workers = idle_count + gathering_count + building_count
        
        debug_log.log(f"AI {player.name}: Worker check for {building_type} - Idle: {idle_count}, Gathering: {gathering_count}, Building: {building_count}, Total: {total_workers}", "AI")
        
        if not memory["idle_workers"]:
            debug_log.log(f"AI {player.name}: No idle workers for building {building_type}", "AI")
            return
            
        # Find a truly idle worker (not already building)
        worker = None
        for w in memory["idle_workers"]:
            # Extra check: ensure worker is not assigned to any construction site
            already_assigned = False
            for site in self.game.construction_sites:
                if site.builder == w:
                    already_assigned = True
                    debug_log.log(f"AI {player.name}: Worker already assigned to construction site", "AI")
                    break
            
            if not already_assigned and (not hasattr(w, 'building_target') or w.building_target is None):
                worker = w
                break
        
        if not worker:
            debug_log.log(f"AI {player.name}: No truly idle workers available for construction", "AI")
            return
        
        # Use building placement manager to find optimal position
        position = self.building_placement_managers[player].find_optimal_position(building_type)
        if position:
            # Check if there's already a construction site at or near this position
            for site in self.game.construction_sites:
                distance = math.sqrt((site.x - position[0])**2 + (site.y - position[1])**2)
                if distance < 50:  # Within 50 units is considered the same location
                    debug_log.log(f"AI {player.name}: Construction already in progress at ({position[0]:.0f}, {position[1]:.0f})", "AI")
                    return
            
            # Reserve the position
            self.building_placement_managers[player].reserve_position(position[0], position[1], building_type)
            
            self._command_worker_build(worker, building_type, position)
            memory["last_building_position"] = position
            self.last_building_time[player] = pygame.time.get_ticks() / 1000.0
            
            # Invalidate memory cache so the worker is no longer considered idle
            self.invalidate_memory_cache(player)
    
    def get_building_placement_manager(self, player):
        """Get building placement manager for player"""
        return self.building_placement_managers.get(player)
    
    def get_ai_debug_info(self, player):
        """Get AI debug information for display"""
        if player not in self.player_modules:
            return None
        
        modules = self.player_modules[player]
        memory = self.player_memory[player]
        
        debug_info = {
            'game_phase': memory.get('game_phase', 'Unknown'),
            'formations': 0,
            'priority_resource': 'Unknown',
            'decision_timer': 0.0,
            'idle_workers': len(memory.get('idle_workers', [])),
            'gathering_workers': len(memory.get('gathering_workers', [])),
            'building_workers': len(memory.get('building_workers', [])),
            'military_units': len(memory.get('military_units', [])),
            'buildings': {
                'total': sum(len(buildings) for buildings in memory.get('buildings', {}).values() if isinstance(buildings, list)),
                'castle': 1 if memory.get('buildings', {}).get('castle') else 0,
                'barracks': len(memory.get('buildings', {}).get('barracks', [])),
                'houses': len(memory.get('buildings', {}).get('houses', [])),
            },
            'military_breakdown': self._get_military_breakdown(memory),
            'production_queue': self._get_production_status(memory),
            'current_tasks': self._get_current_tasks(player),
        }
        
        # Get formation count from military module
        military_module = modules.get('military')
        if military_module and hasattr(military_module, 'formation_manager'):
            debug_info['formations'] = len(military_module.formation_manager.formations)
        
        # Get priority resource from economy module
        economy_module = modules.get('economy')
        if economy_module and hasattr(economy_module, 'resource_manager'):
            priority = economy_module.resource_manager.get_priority_resource()
            debug_info['priority_resource'] = priority or 'None'
        
        # Calculate next decision timer
        last_task_time = self.last_task_time.get(player, 0)
        current_time = pygame.time.get_ticks() / 1000.0
        time_since_last = current_time - last_task_time
        debug_info['decision_timer'] = max(0, self.task_cooldown - time_since_last)
        
        return debug_info
    
    def _get_military_breakdown(self, memory):
        """Get breakdown of military units by type"""
        breakdown = {}
        for unit in memory.get('military_units', []):
            unit_type = getattr(unit, 'name', 'Unknown')
            breakdown[unit_type] = breakdown.get(unit_type, 0) + 1
        return breakdown
    
    def _get_production_status(self, memory):
        """Get current production queue status"""
        production_items = []
        
        # Check castle production
        castle = memory.get('buildings', {}).get('castle')
        if castle and hasattr(castle, 'production_queue'):
            for item in castle.production_queue:
                production_items.append(f"Castle: {item}")
        
        # Check barracks production
        for barracks in memory.get('buildings', {}).get('barracks', []):
            if hasattr(barracks, 'production_queue'):
                for item in barracks.production_queue:
                    production_items.append(f"Barracks: {item}")
        
        return ', '.join(production_items) if production_items else 'None'
    
    def _get_current_tasks(self, player):
        """Get list of current AI tasks for player"""
        # This could be enhanced to track active tasks
        # For now, return a simple count based on worker states
        memory = self.player_memory[player]
        tasks = []
        
        if memory.get('idle_workers'):
            tasks.append(f"Assign {len(memory['idle_workers'])} workers")
        if memory.get('building_workers'):
            tasks.append(f"Construction ({len(memory['building_workers'])} workers)")
        
        return tasks
    
    def invalidate_memory_cache(self, player=None):
        """Invalidate memory cache when game state changes significantly"""
        if player:
            self.memory_cache_valid[player] = False
            # Force immediate update for economy module when workers are produced
            if player in self.player_modules:
                economy_module = self.player_modules[player].get("economy")
                if economy_module:
                    economy_module.force_next_update = True
        else:
            # Invalidate for all players
            for p in self.ai_players:
                self.memory_cache_valid[p] = False
    
    def _command_worker_build(self, worker, building_type, position):
        """Command a worker to build at position"""
        from utils.debug_logger import debug_log
        try:
            costs = self.cost_data.get(building_type, {})
            
            # Double-check affordability right before spending
            for resource, amount in costs.items():
                if worker.player.resources.get(resource, 0) < amount:
                    debug_log.log(f"AI {worker.player.name}: ERROR - Cannot afford {building_type} at build time!", "AI_BUILD")
                    debug_log.log(f"  Need {amount} {resource}, have {worker.player.resources.get(resource, 0)}", "AI_BUILD")
                    return  # Abort building
            
            # Deduct resources
            for resource, amount in costs.items():
                worker.player.resources[resource] -= amount
                debug_log.log(f"AI {worker.player.name}: Spent {amount} {resource} on {building_type} (remaining: {worker.player.resources[resource]})", "AI_BUILD")
                
            building_template = self.game.game_data["buildings"][building_type]
            
            # Create building_data dict with ALL properties including combat
            building_data = {
                'name': building_type,
                'size': building_template.size,
                'hp': building_template.hp,
                'sprite': building_template.sprite,
                'build_duration': building_template.build_duration,
                'costs': costs,
                'armor_type': getattr(building_template, 'armor_type', 'fortified'),
                'armor_value': getattr(building_template, 'armor_value', 0),
                'can_attack': getattr(building_template, 'can_attack', False),
                'min_damage': getattr(building_template, 'min_damage', 0),
                'max_damage': getattr(building_template, 'max_damage', 0),
                'attack_type': getattr(building_template, 'attack_type', 'slash'),
                'attack_speed': getattr(building_template, 'attack_speed', 1.0),
                'attack_range': getattr(building_template, 'attack_range', 0)
            }
            
            # Calculate radius from size (same as in BuildingSystem)
            building_size = building_template.size
            building_radius = building_size[0] * 32  # TILE_WIDTH = 32
            
            construction_site = ConstructionSite(
                building_name=building_type,
                building_data=building_data,
                x=position[0],
                y=position[1],
                radius=building_radius,
                player=worker.player
            )
            
            self.game.construction_sites.append(construction_site)
            construction_site.builder = worker
            
            # Command worker to build
            debug_log.log(f"AI assigning worker at ({worker.x:.0f}, {worker.y:.0f}) to build at ({construction_site.x:.0f}, {construction_site.y:.0f})", "AI_BUILD")
            worker.building_target = construction_site
            worker.status = "run"
            worker.gathering_target = None
            worker.is_building = False
            debug_log.log(f"  Worker building_target set, status={worker.status}, is_building={worker.is_building}", "AI_BUILD")
            
            # Set up pathfinding using cached pathfinder
            pathfinder = self.pathfinders[worker.player]
            pathfinder.building_target = construction_site  # Allow pathfinding to construction site
            path = pathfinder.find_path(
                (worker.x, worker.y),
                (construction_site.x, construction_site.y),
                worker.radius,
                worker
            )
            
            if path:
                worker.path = path
                worker.path_index = 0
                worker.path_target = (construction_site.x, construction_site.y)
                worker.destination = path[0] if path else None
                debug_log.log(f"  Path found! Length: {len(path)}, First point: ({path[0][0]:.0f}, {path[0][1]:.0f})", "AI_BUILD")
            else:
                debug_log.log(f"  ERROR: No path found to construction site!", "AI_BUILD")
            
            # Clear pathfinder state
            pathfinder.building_target = None
            
        except Exception as e:
            debug_log.log(f"AI {worker.player.name}: ERROR in _command_worker_build: {str(e)}", "AI_BUILD")
            debug_log.log(f"  Building type: {building_type}, Position: {position}", "AI_BUILD")
            # Refund resources since building failed
            for resource, amount in costs.items():
                worker.player.resources[resource] += amount
                debug_log.log(f"  Refunded {amount} {resource} (total: {worker.player.resources[resource]})", "AI_BUILD")
    
    def _train_unit(self, player, unit_type):
        """Train a unit from appropriate building"""
        memory = self.player_memory[player]
        
        # Find building that can train this unit
        if unit_type == "worker":
            building = memory["buildings"]["castle"]
        elif unit_type in ["warrior", "archer"]:
            if memory["buildings"]["barracks"]:
                building = memory["buildings"]["barracks"][0]
            else:
                return
        else:
            return
            
        if building and not hasattr(building, 'production_queue'):
            building.production_queue = []
            
        if building and len(building.production_queue) < 5:
            # Add to production queue
            if self.game.production_manager:
                success, message = self.game.production_manager.start_production(building, unit_type)
                if not success:
                    pass