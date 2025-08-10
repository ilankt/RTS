import random
import math
import pygame
import json
from enum import Enum
from entities.objects import Unit, Building, Resource, ConstructionSite
from systems.pathfinding import Pathfinding
from core.config import TILE_WIDTH, TILE_HEIGHT
from utils.debug_logger import debug_log


class AIState(Enum):
    """AI player states"""
    EXPLORING = "exploring"
    BUILDING = "building"
    DEFENDING = "defending"
    ATTACKING = "attacking"


class AISystem:
    """Manages AI player behavior and decision making"""
    
    def __init__(self, game):
        self.game = game
        self.ai_players = [p for p in game.players if not p.human]
        
        # AI state for each player
        self.player_states = {player: AIState.BUILDING for player in self.ai_players}
        
        # Decision timers (in seconds)
        self.decision_timers = {player: 0 for player in self.ai_players}
        self.decision_interval = 2.0  # Make decisions every 2 seconds
        
        # Building cooldowns to prevent spam
        self.last_building_time = {player: 0 for player in self.ai_players}
        self.building_cooldown = 5.0  # Minimum seconds between building attempts
        
        # AI memory for each player
        self.player_memory = {
            player: {
                "idle_workers": [],
                "gathering_workers": [],
                "building_workers": [],  # Track workers that are building
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
                }
            } for player in self.ai_players
        }
        
        # Resource priorities (will be adjusted based on game state)
        self.resource_priorities = {
            "gold": 0.4,
            "wood": 0.25,
            "desert_wood": 0.25,
            "stone": 0.1
        }
        
        # Building priorities
        self.building_queue = []
        
        # Combat settings
        self.min_attack_force = 3  # Minimum units before attacking
        self.defense_radius = 300  # Distance to defend around base
        
        # Cache cost data for efficient access
        self.cost_data = self._load_cost_data()
        
    def _load_cost_data(self):
        """Load and cache cost data from JSON files"""
        cost_data = {}
        
        # Load unit costs
        try:
            with open('data/units.json', 'r') as f:
                units_data = json.load(f)
            for unit in units_data:
                cost_data[unit['name']] = unit.get('costs', {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            debug_log.log(f"Warning: Could not load unit costs: {e}", "AI")
            
        # Load building costs
        try:
            with open('data/buildings.json', 'r') as f:
                buildings_data = json.load(f)
            for building in buildings_data:
                cost_data[building['name']] = building.get('costs', {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            debug_log.log(f"Warning: Could not load building costs: {e}", "AI")
            
        return cost_data
        
    def update(self, delta_time):
        """Update AI for all AI players"""
        for player in self.ai_players:
            # Update decision timer
            self.decision_timers[player] += delta_time
            
            if self.decision_timers[player] >= self.decision_interval:
                self.decision_timers[player] = 0
                self._make_decisions(player)
                
            # Always update unit assignments
            self._update_unit_assignments(player)
    
    def _make_decisions(self, player):
        """Make strategic decisions for an AI player"""
        try:
            # Update player memory
            self._update_player_memory(player)
            
            # Evaluate current state
            state = self._evaluate_state(player)
            self.player_states[player] = state
            
            # Make decisions based on state
            if state == AIState.BUILDING:
                self._handle_building_state(player)
            elif state == AIState.EXPLORING:
                self._handle_exploring_state(player)
            elif state == AIState.DEFENDING:
                self._handle_defending_state(player)
            elif state == AIState.ATTACKING:
                self._handle_attacking_state(player)
                
        except Exception as e:
            debug_log.log(f"Error making decisions for player {player.name}: {e}", "AI")
    
    def _update_player_memory(self, player):
        """Update what the AI knows about the game state"""
        try:
            memory = self.player_memory[player]
            
            # Clear old data
            memory["idle_workers"].clear()
            memory["gathering_workers"].clear()
            memory["building_workers"].clear()
            memory["scout_units"].clear()
            memory["military_units"].clear()
            
            # Update unit lists
            for unit in self.game.units:
                if hasattr(unit, 'player') and unit.player == player:
                    if hasattr(unit, 'name') and unit.name == "worker":
                        # Check if worker is actively building
                        if (hasattr(unit, 'building_target') and unit.building_target) or \
                           (hasattr(unit, 'is_building') and unit.is_building):
                            memory["building_workers"].append(unit)
                        # If worker has resources, command it to drop them off
                        if hasattr(worker, 'resource_amount') and worker.resource_amount > 0:
                            if not worker.drop_off_target:
                                self._command_worker_drop_off(worker)
                        elif hasattr(unit, 'status') and unit.status == "idle":
                            memory["idle_workers"].append(unit)
                        elif hasattr(unit, 'gathering_target') and unit.gathering_target:
                            memory["gathering_workers"].append(unit)
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
            
            # Update resource locations
            memory["resource_locations"].clear()
            for resource in self.game.resources:
                if hasattr(resource, 'amount_remaining') and resource.amount_remaining > 0:
                    if hasattr(resource, 'name'):
                        res_type = resource.name
                        if res_type not in memory["resource_locations"]:
                            memory["resource_locations"][res_type] = []
                        memory["resource_locations"][res_type].append(resource)
                        
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
                        
        except Exception as e:
            debug_log.log(f"Error updating player memory: {e}", "AI")
    
    def _evaluate_state(self, player):
        """Determine what state the AI should be in"""
        memory = self.player_memory[player]
        
        # Check if under attack
        if self._is_under_attack(player):
            return AIState.DEFENDING
            
        # Check if we have enough military to attack
        if len(memory["military_units"]) >= self.min_attack_force:
            if memory["enemy_locations"]:
                return AIState.ATTACKING
                
        # Check if we need to explore
        total_resources = sum(len(locs) for locs in memory["resource_locations"].values())
        if total_resources < 3:  # Not many resources found
            return AIState.EXPLORING
            
        # Default to building/economy
        return AIState.BUILDING
    
    def _is_under_attack(self, player):
        """Check if player's base is under attack"""
        memory = self.player_memory[player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return False
            
        # Check for nearby enemies
        for enemy_pos in memory["enemy_locations"]:
            distance = math.sqrt((enemy_pos[0] - castle.x)**2 + 
                               (enemy_pos[1] - castle.y)**2)
            if distance < self.defense_radius:
                return True
                
        return False
    
    def _handle_building_state(self, player):
        """Handle economic building and resource gathering"""
        memory = self.player_memory[player]
        
        debug_log.log(f"AI {player.name}: Building state - Workers: idle={len(memory['idle_workers'])}, gathering={len(memory['gathering_workers'])}, building={len(memory['building_workers'])}", "AI")
        
        # Assign idle workers to gather resources
        if memory["idle_workers"]:
            self._assign_workers_to_resources(player, memory["idle_workers"])
            
        # Check if we need more workers
        total_workers = len(memory["idle_workers"]) + len(memory["gathering_workers"]) + len(memory["building_workers"])
        if total_workers < 5 and self._can_afford(player, "worker"):
            self._train_unit(player, "worker")
            
        # Check if we need houses (limit to prevent spam)
        current_pop = len([u for u in self.game.units if u.player == player])
        pop_limit = self._get_population_limit(player)
        if current_pop >= pop_limit - 2 and self._can_afford(player, "house"):
            # Check if we already have houses being built
            house_count = len(memory["buildings"]["houses"])
            houses_building = len([s for s in self.game.construction_sites if s.player == player and s.building_name == "house"])
            if house_count + houses_building < 5:  # Limit total houses
                self._build_structure(player, "house")
            
        # Build resource buildings near resources (with limits)
        if len(memory["buildings"]["resource_buildings"]) < 2:
            # Check if we're already building resource buildings
            resource_buildings_under_construction = len([s for s in self.game.construction_sites 
                                                       if s.player == player and 
                                                       s.building_name in ["mine", "quarry", "lumbermill", "farm"]])
            if resource_buildings_under_construction == 0:
                self._build_resource_building(player)
            
        # Build barracks if we don't have one
        if not memory["buildings"]["barracks"] and self._can_afford(player, "barracks"):
            # Check if we're already building a barracks
            barracks_building = any(s.player == player and s.building_name == "barracks" 
                                  for s in self.game.construction_sites)
            if not barracks_building:
                self._build_structure(player, "barracks")

        # Check if we need more farms
        farm_count = len([b for b in self.game.buildings if b.player == player and b.name == "farm"]) + \
                     len([s for s in self.game.construction_sites if s.player == player and s.building_name == "farm"])
        if farm_count < (total_workers // 3) and self._can_afford(player, "farm"):
            self._build_structure(player, "farm", neat=True)
            
        # Train military units if we have barracks
        if memory["buildings"]["barracks"] and len(memory["military_units"]) < self.min_attack_force:
            if random.random() < 0.5 and self._can_afford(player, "warrior"):
                self._train_unit(player, "warrior")
            elif self._can_afford(player, "archer"):
                self._train_unit(player, "archer")
    
    def _handle_exploring_state(self, player):
        """Send units to explore the map"""
        memory = self.player_memory[player]
        
        # Use idle workers or military units as scouts
        scouts = memory["idle_workers"][:1] + memory["military_units"][:1]
        
        for scout in scouts:
            # Send to random unexplored location
            target_x = random.randint(100, self.game.game_map.width * TILE_WIDTH - 100)
            target_y = random.randint(100, self.game.game_map.height * TILE_HEIGHT - 100)
            
            # Command unit to move
            self._command_unit_move(scout, (target_x, target_y))
    
    def _handle_defending_state(self, player):
        """Defend against attacks"""
        memory = self.player_memory[player]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return
            
        # Rally all military units to castle
        for unit in memory["military_units"]:
            nearest_enemy = self._find_nearest_enemy(unit, player)
            if nearest_enemy:
                self._command_unit_attack(unit, nearest_enemy)
            else:
                # Move to castle if no enemies nearby
                self._command_unit_move(unit, (castle.x, castle.y))
    
    def _handle_attacking_state(self, player):
        """Launch attacks on enemies"""
        memory = self.player_memory[player]
        
        # Find enemy buildings (prioritize castle)
        enemy_targets = []
        for building in self.game.buildings:
            if building.player != player:
                if building.name == "castle":
                    enemy_targets.insert(0, building)  # Priority target
                else:
                    enemy_targets.append(building)
                    
        if enemy_targets:
            target = enemy_targets[0]
            
            # Send all military units to attack
            for unit in memory["military_units"]:
                self._command_unit_attack(unit, target)
    
    def _update_unit_assignments(self, player):
        """Continuously update unit tasks"""
        memory = self.player_memory[player]
        
        # Check gathering workers
        for worker in memory["gathering_workers"]:
            if hasattr(worker, 'gathering_target') and worker.gathering_target:
                if worker.gathering_target.amount_remaining <= 0:
                    # Resource depleted, check if worker has resources to drop off
                    if worker.resource_amount > 0:
                        self._command_worker_drop_off(worker)
                    else:
                        # Find new resource to gather
                        self._assign_workers_to_resources(player, [worker])
    
    def _assign_workers_to_resources(self, player, workers):
        """Assign workers to gather resources"""
        memory = self.player_memory[player]
        
        for worker in workers:
            # Find best resource based on priorities
            best_resource = None
            best_score = -1
            
            for res_type, priority in self.resource_priorities.items():
                if res_type in memory["resource_locations"]:
                    for resource in memory["resource_locations"][res_type]:
                        if resource.amount_remaining > 0:
                            # Score based on priority and distance
                            distance = math.sqrt((resource.x - worker.x)**2 + 
                                               (resource.y - worker.y)**2)
                            score = priority * 1000 / (distance + 1)
                            
                            if score > best_score:
                                best_score = score
                                best_resource = resource
                                
            if best_resource:
                self._command_worker_gather(worker, best_resource)
    
    def _can_afford(self, player, item_type):
        """Check if player can afford to build/train something"""
        # Use cached cost data
        costs = self.cost_data.get(item_type, {})
        
        if not costs:
            return False
            
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False
                
        return True
    
    def _get_population_limit(self, player):
        """Calculate population limit for player"""
        memory = self.player_memory[player]
        base_limit = 5  # Starting limit
        house_bonus = len(memory["buildings"]["houses"]) * 5
        return base_limit + house_bonus

    def _find_neat_farm_position(self, player):
        """Find a position for a new farm, neatly next to existing ones."""
        memory = self.player_memory[player]
        existing_farms = [b for b in self.game.buildings if b.player == player and b.name == "farm"]

        if not existing_farms:
            return None

        # Try to find a spot next to an existing farm
        for farm in existing_farms:
            for angle in range(0, 360, 45):
                distance = TILE_WIDTH * 1.5  # Adjust as needed
                build_x = farm.x + distance * math.cos(math.radians(angle))
                build_y = farm.y + distance * math.sin(math.radians(angle))

                if self._is_valid_build_position(build_x, build_y, "farm"):
                    return (build_x, build_y)
        
        return None
    
    def _build_structure(self, player, building_type, neat=False):
        """Command a worker to build a structure"""
        memory = self.player_memory[player]
        
        # Check building cooldown
        current_time = pygame.time.get_ticks() / 1000.0
        if current_time - self.last_building_time.get(player, 0) < self.building_cooldown:
            time_left = self.building_cooldown - (current_time - self.last_building_time.get(player, 0))
            debug_log.log(f"AI {player.name}: Building on cooldown ({time_left:.1f}s left)", "AI")
            return
        
        # Check if another worker is already building
        for site in self.game.construction_sites:
            if site.player == player and site.builder:
                debug_log.log(f"AI {player.name}: Another worker is already building.", "AI")
                return

        if not memory["idle_workers"]:
            return
            
        worker = memory["idle_workers"][0]
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return

        # If neat flag is true, try to find a neat position first
        if neat:
            neat_pos = self._find_neat_farm_position(player)
            if neat_pos:
                self._command_worker_build(worker, building_type, neat_pos)
                memory["last_building_position"] = neat_pos
                self.last_building_time[player] = pygame.time.get_ticks() / 1000.0
                debug_log.log(f"AI {player.name}: Commanded worker to build {building_type} neatly at ({neat_pos[0]:.0f}, {neat_pos[1]:.0f})", "AI")
                return
            
        # Find valid build position near castle
        for attempt in range(20):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(150, 300)
            
            build_x = castle.x + distance * math.cos(angle)
            build_y = castle.y + distance * math.sin(angle)
            
            # Check if position is valid
            if self._is_valid_build_position(build_x, build_y, building_type):
                self._command_worker_build(worker, building_type, (build_x, build_y))
                memory["last_building_position"] = (build_x, build_y)
                self.last_building_time[player] = pygame.time.get_ticks() / 1000.0
                debug_log.log(f"AI {player.name}: Commanded worker to build {building_type} at ({build_x:.0f}, {build_y:.0f})", "AI")
                break
    
    def _build_resource_building(self, player):
        """Build appropriate resource gathering building"""
        memory = self.player_memory[player]
        
        # Determine what type to build based on nearby resources
        resource_counts = {}
        castle = memory["buildings"]["castle"]
        
        if not castle:
            return
            
        # Count nearby resources
        for res_type, resources in memory["resource_locations"].items():
            for resource in resources:
                distance = math.sqrt((resource.x - castle.x)**2 + 
                                   (resource.y - castle.y)**2)
                if distance < 500:  # Within reasonable distance
                    resource_counts[res_type] = resource_counts.get(res_type, 0) + 1
                    
        # Build based on what's available
        if resource_counts.get("gold", 0) > 0 and self._can_afford(player, "mine"):
            self._build_structure(player, "mine")
        elif resource_counts.get("stone", 0) > 0 and self._can_afford(player, "quarry"):
            self._build_structure(player, "quarry")
        elif (resource_counts.get("wood", 0) > 0 or resource_counts.get("desert_wood", 0) > 0) and self._can_afford(player, "lumbermill"):
            self._build_structure(player, "lumbermill")
        elif self._can_afford(player, "farm"):
            self._build_structure(player, "farm")
    
    def _is_valid_build_position(self, x, y, building_type):
        """Check if position is valid for building"""
        # Get building size
        building_template = self.game.game_data["buildings"][building_type]
        size = building_template.size
        
        # Check terrain
        grid_x = int(x / TILE_WIDTH)
        grid_y = int(y / TILE_HEIGHT)
        
        if (grid_x < 0 or grid_x >= self.game.game_map.width or
            grid_y < 0 or grid_y >= self.game.game_map.height):
            return False
            
        terrain = self.game.game_map.grid[grid_y][grid_x]
        if terrain not in ["grass", "plains", "dirt"]:
            return False
            
        # Check for collisions with other objects
        for building in self.game.buildings:
            distance = math.sqrt((x - building.x)**2 + 
                               (y - building.y)**2)
            min_distance = (size[0] + building.size[0]) * TILE_WIDTH / 2 + 20
            if distance < min_distance:
                return False
        
        # Check collision with construction sites
        for site in self.game.construction_sites:
            distance = math.sqrt((x - site.x)**2 + (y - site.y)**2)
            min_distance = (size[0] * TILE_WIDTH / 2) + site.radius + 20
            if distance < min_distance:
                return False
        
        # Check collision with resources
        for resource in self.game.resources:
            distance = math.sqrt((x - resource.x)**2 + (y - resource.y)**2)
            min_distance = (size[0] * TILE_WIDTH / 2) + resource.radius + 20
            if distance < min_distance:
                return False
                
        return True
    
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
            self._command_building_train(building, unit_type)
    
    def _find_nearest_enemy(self, unit, player):
        """Find nearest enemy unit or building"""
        nearest = None
        min_distance = float('inf')
        
        # Check enemy units
        for enemy in self.game.units:
            if enemy.player != player:
                distance = math.sqrt((enemy.x - unit.x)**2 + 
                                   (enemy.y - unit.y)**2)
                if distance < min_distance:
                    min_distance = distance
                    nearest = enemy
                    
        # Check enemy buildings
        for building in self.game.buildings:
            if building.player != player:
                distance = math.sqrt((building.x - unit.x)**2 + 
                                   (building.y - unit.y)**2)
                if distance < min_distance:
                    min_distance = distance
                    nearest = building
                    
        return nearest
    
    # Command methods that interface with game systems
    
    def _command_unit_move(self, unit, target_pos):
        """Command a unit to move to position"""
        try:
            # Create pathfinder instance
            pathfinder = Pathfinding(self.game.game_map, self.game)
            
            # Use _move_unit_to_position directly with world coordinates
            self.game.selection_manager._move_unit_to_position(unit, target_pos, pathfinder)
        except Exception as e:
            debug_log.log(f"Error commanding unit move: {e}", "AI")
    
    def _command_unit_attack(self, unit, target):
        """Command a unit to attack target"""
        try:
            # Create pathfinder instance
            pathfinder = Pathfinding(self.game.game_map, self.game)
            
            # Use _attack_target directly
            self.game.selection_manager._attack_target(unit, target, pathfinder)
        except Exception as e:
            debug_log.log(f"Error commanding unit attack: {e}", "AI")
    
    def _command_worker_gather(self, worker, resource):
        """Command a worker to gather from resource"""
        try:
            # Create pathfinder instance
            pathfinder = Pathfinding(self.game.game_map, self.game)
            
            # Use _gather_from_target directly
            self.game.selection_manager._gather_from_target(worker, resource, pathfinder)
        except Exception as e:
            debug_log.log(f"Error commanding worker gather: {e}", "AI")
    
    def _command_worker_build(self, worker, building_type, position):
        """Command a worker to build at position"""
        try:
            # Get costs from cached data
            costs = self.cost_data.get(building_type, {})
            
            # Deduct resources
            for resource, amount in costs.items():
                worker.player.resources[resource] -= amount
                
            # Get building template for other attributes
            building_template = self.game.game_data["buildings"][building_type]
            
            # Create construction site
            # Need to create building_data dict for ConstructionSite with all required fields
            building_data = {
                'name': building_type,
                'size': building_template.size,
                'hp': building_template.hp,  # Add missing hp field
                'sprite': building_template.sprite,  # Add missing sprite field
                'build_duration': building_template.build_duration,
                'costs': costs
            }
            construction_site = ConstructionSite(
                building_name=building_type,
                building_data=building_data,
                x=position[0],
                y=position[1],
                radius=building_template.radius,
                player=worker.player
            )
            
            # Add to game
            self.game.construction_sites.append(construction_site)
            
            # Assign builder to construction site (important for construction progress)
            construction_site.builder = worker
            
            # Command worker to build (using correct attribute name)
            worker.building_target = construction_site
            worker.status = "run"  # Worker runs to construction site first
            worker.gathering_target = None
            worker.is_building = False  # Will be set true when worker arrives
            
            # Set up pathfinding to construction site
            pathfinder = Pathfinding(self.game.game_map, self.game)
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
            
        except Exception as e:
            debug_log.log(f"Error commanding worker build: {e}", "AI")
    
    def _command_building_train(self, building, unit_type):
        """Command a building to train a unit"""
        # Add to production queue
        if self.game.production_manager:
            success, message = self.game.production_manager.start_production(building, unit_type)
            if not success:
                debug_log.log(f"AI {building.player.name}: Failed to train {unit_type} - {message}", "AI")

    def _find_nearest_dropoff(self, worker):
        """Finds the nearest valid drop-off building for a worker."""
        if not hasattr(worker, 'resource_type') or not worker.resource_type:
            return None

        resource_type = worker.resource_type
        
        # Define valid drop-off points for each resource
        dropoff_map = {
            "gold": ["castle", "mine"],
            "wood": ["castle", "lumbermill"],
            "stone": ["castle", "quarry"],
            "food": ["castle"] # Assuming food is dropped at castle
        }
        
        valid_building_types = dropoff_map.get(resource_type, ["castle"])

        memory = self.player_memory[worker.player]
        closest_building = None
        min_dist = float('inf')

        # Check all buildings owned by the player
        all_player_buildings = []
        if memory['buildings']['castle']:
            all_player_buildings.append(memory['buildings']['castle'])
        all_player_buildings.extend(memory['buildings']['barracks'])
        all_player_buildings.extend(memory['buildings']['houses'])
        all_player_buildings.extend(memory['buildings']['resource_buildings'])

        for building in all_player_buildings:
            if building.name in valid_building_types:
                dist = math.sqrt((worker.x - building.x)**2 + (worker.y - building.y)**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_building = building
        
        return closest_building

    def _command_worker_drop_off(self, worker):
        """Commands a worker to find a drop-off and return resources."""
        drop_off_building = self._find_nearest_dropoff(worker)
        if drop_off_building:
            pathfinder = Pathfinding(self.game.game_map, self.game)
            path = pathfinder.find_path((worker.x, worker.y), (drop_off_building.x, drop_off_building.y), worker.radius, worker)
            
            if path:
                worker.path = path
                worker.path_index = 0
                worker.path_target = path[-1]
                worker.destination = path[0] if path else None
                worker.drop_off_target = drop_off_building
                worker.status = "run"
                worker.is_gathering = False
                worker.gathering_target = None