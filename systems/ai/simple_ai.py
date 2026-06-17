"""Simple AI system with a 4-phase state machine.

Phases:
  EARLY  - Follow scripted build order step by step
  GROW   - Expand economy (more workers, houses, resource buildings)
  ARMY   - Build up military while maintaining economy
  ATTACK - Send army to enemy, keep training replacements
"""
import pygame
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from entities import ConstructionSite
from utils.debug_logger import debug_log

from .worker_brain import WorkerBrain
from .military_brain import MilitaryBrain
from .building_placer import BuildingPlacer
from .scout_brain import ScoutBrain


# ---------------------------------------------------------------------------
# Fresh snapshot of the game state, rebuilt every tick.  No caching.
# ---------------------------------------------------------------------------
@dataclass
class AIGameState:
    """Immutable snapshot of everything the AI needs to know."""
    castle: object = None
    workers: List = field(default_factory=list)
    military: List = field(default_factory=list)
    buildings: Dict[str, list] = field(default_factory=dict)
    construction_sites: List = field(default_factory=list)
    resources: Dict[str, int] = field(default_factory=dict)
    pop_current: int = 0
    pop_max: int = 5


# ---------------------------------------------------------------------------
# Build-order steps for EARLY phase
# ---------------------------------------------------------------------------
class BuildStep:
    """One step in the scripted build order."""
    TRAIN = "train"
    BUILD = "build"

    def __init__(self, action: str, target: str, condition=None):
        self.action = action   # "train" or "build"
        self.target = target   # unit/building type name
        self.condition = condition  # optional callable(AIGameState)->bool


EARLY_BUILD_ORDER = [
    BuildStep(BuildStep.TRAIN, "worker"),      # Train 2nd worker
    BuildStep(BuildStep.TRAIN, "worker"),      # Train 3rd worker
    BuildStep(BuildStep.BUILD, "farm"),         # Build farm (75 wood)
    BuildStep(BuildStep.TRAIN, "worker"),      # Train 4th worker
    BuildStep(BuildStep.BUILD, "house"),        # Build house if near pop cap
    BuildStep(BuildStep.BUILD, "barracks"),     # Build barracks
]


# ---------------------------------------------------------------------------
# Main AI class
# ---------------------------------------------------------------------------
class SimpleAISystem:
    """Simple, predictable AI: gather -> economy -> army -> attack."""

    TICK_INTERVAL = 0.5  # Seconds between AI updates

    def __init__(self, game):
        self.game = game
        self.ai_players = [p for p in game.players if not p.human]

        # Sub-systems
        self.worker_brain = WorkerBrain(game)
        self.military_brain = MilitaryBrain(game)
        self.building_placer = BuildingPlacer(game)
        self.scout_brain = ScoutBrain(game)

        # Per-player state
        self.phase = {p: "EARLY" for p in self.ai_players}
        self.build_order_index = {p: 0 for p in self.ai_players}
        self.tick_timer = {p: 0.0 for p in self.ai_players}

        # Cost data lives on game.game_data (loaded once at startup)
        self.cost_data = game.game_data.get("costs", {})

        # Building cooldown to avoid spam
        self.last_build_time = {p: 0.0 for p in self.ai_players}
        self.build_cooldown = 3.0
        
        # Personality parameters per player
        self.personality_params = {p: self._get_personality_params(p) for p in self.ai_players}

    # ------------------------------------------------------------------
    # Public interface (called by game.py)
    # ------------------------------------------------------------------
    def update(self, delta_time: float):
        """Called every frame.  We only act every TICK_INTERVAL seconds."""
        for player in self.ai_players:
            self.tick_timer[player] += delta_time
            if self.tick_timer[player] < self.TICK_INTERVAL:
                continue
            self.tick_timer[player] = 0.0

            try:
                self._tick(player)
            except Exception as e:
                debug_log.log(f"AI {player.name}: Error in tick: {e}", "AI")

    def _get_personality_params(self, player):
        """Get AI behavior parameters based on player personality."""
        personality = getattr(player, 'ai_personality', 'balanced')
        
        params = {
            "rusher": {
                "early_workers": 2,
                "target_workers": 4,
                "army_transition_threshold": 2,
                "attack_transition_threshold": 4,
                "retreat_threshold": 0.15,
                "econ_focus": False,
            },
            "boomer": {
                "early_workers": 3,
                "target_workers": 8,
                "army_transition_threshold": 3,
                "attack_transition_threshold": 8,
                "retreat_threshold": 0.35,
                "econ_focus": True,
            },
            "turtle": {
                "early_workers": 3,
                "target_workers": 6,
                "army_transition_threshold": 4,
                "attack_transition_threshold": 10,
                "retreat_threshold": 0.40,
                "econ_focus": False,
            },
            "balanced": {
                "early_workers": 2,
                "target_workers": 6,
                "army_transition_threshold": 3,
                "attack_transition_threshold": 6,
                "retreat_threshold": 0.30,
                "econ_focus": False,
            },
        }
        return params.get(personality, params["balanced"])

    def invalidate_memory_cache(self, player=None):
        """No-op.  Kept for interface compatibility with game.py."""
        pass

    def get_ai_debug_info(self, player) -> Optional[dict]:
        """Return debug info in the format the F4 panel expects."""
        if player not in self.phase:
            return None

        state = self._snapshot(player)
        idle_w, gather_w, build_w = self.worker_brain.get_worker_counts(player)

        barracks_count = len(state.buildings.get("barracks", []))
        houses_count = len(state.buildings.get("house", []))
        total_buildings = sum(len(v) for v in state.buildings.values() if isinstance(v, list))
        if state.castle:
            total_buildings += 1

        military_breakdown = self.military_brain.get_military_breakdown(player)

        # Production queue string
        production_parts = []
        if state.castle and hasattr(state.castle, "production_queue"):
            if state.castle.current_production:
                production_parts.append(f"Castle: {state.castle.current_production['unit_type']}")
            for item in state.castle.production_queue:
                production_parts.append(f"Castle: {item}")
        for barracks in state.buildings.get("barracks", []):
            if hasattr(barracks, "current_production") and barracks.current_production:
                production_parts.append(f"Barracks: {barracks.current_production['unit_type']}")
            if hasattr(barracks, "production_queue"):
                for item in barracks.production_queue:
                    production_parts.append(f"Barracks: {item}")

        # Priority resource = the one we have least of
        if state.resources:
            priority_resource = min(state.resources, key=state.resources.get)
        else:
            priority_resource = "None"

        phase = self.phase[player]
        step_info = ""
        if phase == "EARLY":
            idx = self.build_order_index[player]
            if idx < len(EARLY_BUILD_ORDER):
                step = EARLY_BUILD_ORDER[idx]
                step_info = f" (step {idx+1}/{len(EARLY_BUILD_ORDER)}: {step.action} {step.target})"

        return {
            "game_phase": f"{phase}{step_info}",
            "formations": 0,
            "priority_resource": priority_resource,
            "decision_timer": max(0, self.TICK_INTERVAL - self.tick_timer.get(player, 0)),
            "idle_workers": idle_w,
            "gathering_workers": gather_w,
            "building_workers": build_w,
            "military_units": len(state.military),
            "military_breakdown": military_breakdown,
            "buildings": {
                "total": total_buildings,
                "castle": 1 if state.castle else 0,
                "barracks": barracks_count,
                "houses": houses_count,
            },
            "production_queue": ", ".join(production_parts) if production_parts else "None",
            "current_tasks": [],
        }

    # ------------------------------------------------------------------
    # Core tick logic
    # ------------------------------------------------------------------
    def _tick(self, player):
        """One AI decision tick for a player."""
        state = self._snapshot(player)

        # Phase-specific logic runs FIRST so building commands can grab workers
        phase = self.phase[player]
        if phase == "EARLY":
            self._tick_early(player, state)
        elif phase == "GROW":
            self._tick_grow(player, state)
        elif phase == "ARMY":
            self._tick_army(player, state)
        elif phase == "ATTACK":
            self._tick_attack(player, state)

        # Update scouting
        self.scout_brain.update(player, self.tick_timer[player])
        
        # Assign remaining idle workers AFTER phase logic has had a chance to grab workers for building
        self.worker_brain.assign_idle_workers(player)

    def _tick_early(self, player, state: AIGameState):
        """Adaptive early game: score possible actions and pick the best one."""
        params = self.personality_params[player]
        worker_count = self._count_workers(player, state)
        target_workers = params["early_workers"]
        
        # Check if we're done with early phase
        has_barracks = len(state.buildings.get("barracks", [])) > 0
        has_farm = len(state.buildings.get("farm", [])) > 0
        has_house = len(state.buildings.get("house", [])) > 0
        
        if worker_count >= target_workers and has_farm and has_house and has_barracks:
            debug_log.log(f"AI {player.name}: EARLY build order complete -> GROW", "AI")
            self.phase[player] = "GROW"
            return
        
        # Score possible actions
        actions = []
        
        # 1. Train worker - high priority until target reached
        if worker_count < target_workers and self._check_pop_space(state):
            need = target_workers - worker_count
            score = 100 + need * 20
            actions.append(("train_worker", score))
        
        # 2. Build farm - high priority if none exist, wood-dependent
        if not has_farm:
            wood = state.resources.get("wood", 0)
            if wood >= self.cost_data.get("farm", {}).get("wood", 0):
                score = 80 if worker_count >= 2 else 30
                actions.append(("build_farm", score))
        
        # 3. Build house - important if near pop cap
        if not has_house and worker_count >= 3:
            score = 70 if state.pop_current >= state.pop_max - 2 else 40
            actions.append(("build_house", score))
        
        # 4. Build barracks - transition requirement
        if not has_barracks and worker_count >= 2:
            # Check affordability
            costs = self.cost_data.get("barracks", {})
            can_afford = all(state.resources.get(r, 0) >= a for r, a in costs.items())
            if can_afford:
                score = 60
                # Higher priority if we have spare resources
                if state.resources.get("gold", 0) > 200:
                    score += 15
                actions.append(("build_barracks", score))
        
        # 5. Build lumbermill early if we need more wood
        if has_farm and has_barracks:
            has_lumbermill = any(b.name == "lumbermill" for bl in [state.buildings.get("lumbermill", [])] for b in bl)
            if not has_lumbermill and self._can_afford(player, "lumbermill"):
                wood = state.resources.get("wood", 0)
                score = 20 + min(40, max(0, 100 - wood))
                actions.append(("build_lumbermill", score))
        
        # Sort by score descending, pick best
        if actions:
            actions.sort(key=lambda x: x[1], reverse=True)
            best_action, _ = actions[0]
            
            if best_action == "train_worker":
                self._try_train(player, state, "worker")
            elif best_action == "build_farm":
                success = self._try_build(player, state, "farm")
                if success:
                    debug_log.log(f"AI {player.name}: Built farm (adaptive)", "AI")
            elif best_action == "build_house":
                success = self._try_build(player, state, "house")
                if success:
                    debug_log.log(f"AI {player.name}: Built house (adaptive)", "AI")
            elif best_action == "build_barracks":
                success = self._try_build(player, state, "barracks")
                if success:
                    debug_log.log(f"AI {player.name}: Built barracks (adaptive)", "AI")
            elif best_action == "build_lumbermill":
                self._try_build(player, state, "lumbermill")

    def _tick_grow(self, player, state: AIGameState):
        """Expand economy: workers, houses, resource buildings."""
        params = self.personality_params[player]
        
        # Build houses when near pop cap (cheap, high priority)
        if state.pop_current >= state.pop_max - 1:
            self._try_build(player, state, "house")

        # Train military FIRST - this is the bottleneck for phase transition
        has_barracks = len(state.buildings.get("barracks", [])) > 0
        if has_barracks:
            self.military_brain.train_units(player)

        # Train workers up to target AFTER military (count in-production to avoid over-queuing)
        worker_count = self._count_workers(player, state)
        if worker_count < params["target_workers"]:
            self._try_train(player, state, "worker")

        # Transition: has barracks + threshold military units
        military_count = self.military_brain.get_military_count(player)
        if has_barracks and military_count >= params["army_transition_threshold"]:
            debug_log.log(f"AI {player.name}: GROW complete -> ARMY", "AI")
            self.phase[player] = "ARMY"
            return

        # Build resource buildings last (expensive, not urgent for transition)
        has_lumbermill = any(b.name == "lumbermill" for bl in [state.buildings.get("lumbermill", [])] for b in bl)
        has_mine = any(b.name == "mine" for bl in [state.buildings.get("mine", [])] for b in bl)
        has_quarry = any(b.name == "quarry" for bl in [state.buildings.get("quarry", [])] for b in bl)

        if not has_lumbermill and self._can_afford(player, "lumbermill"):
            self._try_build(player, state, "lumbermill")
        if not has_mine and self._can_afford(player, "mine"):
            self._try_build(player, state, "mine")
        if not has_quarry and self._can_afford(player, "quarry"):
            self._try_build(player, state, "quarry")

    def _tick_army(self, player, state: AIGameState):
        """Build military, maintain economy."""
        params = self.personality_params[player]
        
        # Replace dead workers (count in-production)
        min_workers = 4 if not params["econ_focus"] else 6
        if self._count_workers(player, state) < min_workers:
            self._try_train(player, state, "worker")

        # Build houses when near pop cap
        if state.pop_current >= state.pop_max - 1:
            self._try_build(player, state, "house")

        # Train military
        self.military_brain.train_units(player)

        # Run military logic (defense only, not attacking yet)
        self.military_brain.update(player, should_attack=False)

        # Transition: army >= threshold
        if self.military_brain.get_military_count(player) >= params["attack_transition_threshold"]:
            debug_log.log(f"AI {player.name}: ARMY complete -> ATTACK", "AI")
            self.phase[player] = "ATTACK"

    def _tick_attack(self, player, state: AIGameState):
        """Send army to attack, keep training replacements."""
        params = self.personality_params[player]
        
        # Keep economy alive (count in-production)
        min_workers = 4 if not params["econ_focus"] else 6
        if self._count_workers(player, state) < min_workers:
            self._try_train(player, state, "worker")
        if state.pop_current >= state.pop_max - 1:
            self._try_build(player, state, "house")

        # Keep training military
        self.military_brain.train_units(player)

        # Attack!
        self.military_brain.update(player, should_attack=True)

        # Transition back to ARMY if army drops below threshold
        retreat_threshold = max(2, params["attack_transition_threshold"] // 2)
        if self.military_brain.get_military_count(player) < retreat_threshold:
            debug_log.log(f"AI {player.name}: Army depleted -> ARMY", "AI")
            self.phase[player] = "ARMY"

    # ------------------------------------------------------------------
    # Action helpers
    # ------------------------------------------------------------------
    def _try_train(self, player, state: AIGameState, unit_type: str) -> bool:
        """Try to train a unit.  Returns True if production started or already queued."""
        if not self._check_pop_space(state):
            return False

        if unit_type == "worker":
            building = state.castle
        elif unit_type in ("warrior", "archer"):
            barracks_list = state.buildings.get("barracks", [])
            building = barracks_list[0] if barracks_list else None
        else:
            return False

        if not building:
            return False

        # Don't over-queue
        queue_len = len(building.production_queue)
        if building.current_production:
            queue_len += 1
        if queue_len >= 2:
            return True  # Already queued, treat as "done" for build order

        success, msg = self.game.production_manager.start_production(building, unit_type)
        if success:
            debug_log.log(f"AI {player.name}: Training {unit_type}", "AI")
            return True
        return False

    def _try_build(self, player, state: AIGameState, building_type: str) -> bool:
        """Try to place and start building.  Returns True if construction started."""
        # Check cooldown
        current_time = pygame.time.get_ticks() / 1000.0
        time_left = self.build_cooldown - (current_time - self.last_build_time.get(player, 0))
        if time_left > 0:
            return False

        # Check affordability
        if not self._can_afford(player, building_type):
            return False

        # Need an idle worker
        idle_worker = self._find_idle_worker(player)
        if not idle_worker:
            return False

        # Check not already building this type
        for site in self.game.construction_sites:
            if site.player == player and site.building_name == building_type:
                return True  # Already in progress, treat as "done"

        # Find position
        position = self.building_placer.find_position(building_type, player)
        if not position:
            return False

        # Build!
        self._command_worker_build(idle_worker, building_type, position)
        self.last_build_time[player] = current_time
        return True

    # ------------------------------------------------------------------
    # Construction command (ported from old modular_ai_system)
    # ------------------------------------------------------------------
    def _command_worker_build(self, worker, building_type: str, position):
        """Create construction site, deduct resources, path worker to it."""
        costs = self.cost_data.get(building_type, {})

        # Final affordability check
        for resource, amount in costs.items():
            if worker.player.resources.get(resource, 0) < amount:
                debug_log.log(f"AI {worker.player.name}: Cannot afford {building_type} at build time!", "AI")
                return

        # Deduct resources
        for resource, amount in costs.items():
            worker.player.resources[resource] -= amount
            debug_log.log(f"AI {worker.player.name}: Spent {amount} {resource} on {building_type} (remaining: {worker.player.resources[resource]})", "AI")

        building_template = self.game.game_data["buildings"][building_type]

        # Build the building_data dict with ALL properties
        building_data = {
            "name": building_type,
            "size": building_template.size,
            "hp": building_template.hp,
            "sprite": building_template.sprite,
            "build_duration": building_template.build_duration,
            "costs": costs,
            "armor_type": getattr(building_template, "armor_type", "fortified"),
            "armor_value": getattr(building_template, "armor_value", 0),
            "can_attack": getattr(building_template, "can_attack", False),
            "min_damage": getattr(building_template, "min_damage", 0),
            "max_damage": getattr(building_template, "max_damage", 0),
            "attack_type": getattr(building_template, "attack_type", "slash"),
            "attack_speed": getattr(building_template, "attack_speed", 1.0),
            "attack_range": getattr(building_template, "attack_range", 0),
        }

        building_radius = building_template.radius

        try:
            construction_site = ConstructionSite(
                building_name=building_type,
                building_data=building_data,
                x=position[0],
                y=position[1],
                radius=building_radius,
                player=worker.player,
            )

            self.game.construction_sites.append(construction_site)
            self.game.pathfinder.mark_dirty()
            worker_tasks = getattr(self.game, "worker_task_system", None)
            if worker_tasks:
                success = worker_tasks.assign_build(worker, construction_site)
            else:
                success = self.game.pathfinder.issue_interact(worker, construction_site, "build")
            if success:
                debug_log.log(f"AI {worker.player.name}: Worker pathed to {building_type} site at ({position[0]:.0f}, {position[1]:.0f})", "AI")
            else:
                debug_log.log(f"AI {worker.player.name}: No path to {building_type} site!", "AI")

        except Exception as e:
            debug_log.log(f"AI {worker.player.name}: Build failed for {building_type}: {e}", "AI")
            # Refund resources
            for resource, amount in costs.items():
                worker.player.resources[resource] += amount
                debug_log.log(f"AI {worker.player.name}: Refunded {amount} {resource}", "AI")

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    def _snapshot(self, player) -> AIGameState:
        """Build a fresh snapshot of the game state for this player."""
        s = AIGameState()
        s.resources = dict(player.resources)

        for building in self.game.buildings:
            if building.player != player:
                continue
            if building.name == "castle":
                s.castle = building
            else:
                if building.name not in s.buildings:
                    s.buildings[building.name] = []
                s.buildings[building.name].append(building)

        for unit in self.game.units:
            if unit.player != player:
                continue
            if unit.name == "worker":
                s.workers.append(unit)
            elif unit.name in ("warrior", "archer", "spearman", "cavalry", "healer"):
                s.military.append(unit)

        s.construction_sites = [cs for cs in self.game.construction_sites if cs.player == player]

        s.pop_current = len([u for u in self.game.units if u.player == player])
        s.pop_max = 5  # Base castle
        houses = [b for b in self.game.buildings if b.player == player and b.name == "house"]
        s.pop_max += len(houses) * 5

        return s

    def _count_workers(self, player, state: AIGameState) -> int:
        """Count workers including those currently in production at the castle."""
        count = len(state.workers)
        if state.castle:
            if state.castle.current_production and state.castle.current_production.get("unit_type") == "worker":
                count += 1
            for queued in state.castle.production_queue:
                if queued == "worker":
                    count += 1
        return count

    def _can_afford(self, player, item_type: str) -> bool:
        """Check if player can afford to build/train something."""
        costs = self.cost_data.get(item_type, {})
        if not costs:
            return False
        for resource, amount in costs.items():
            if player.resources.get(resource, 0) < amount:
                return False
        return True

    def _check_pop_space(self, state: AIGameState) -> bool:
        """Check if there's population space for another unit."""
        return state.pop_current < state.pop_max

    def _find_idle_worker(self, player):
        """Find an available worker for building duty.

        Prefers truly idle workers, but will pull a gathering worker if needed.
        Won't pull workers that are mid-drop-off or already building.
        """
        idle_candidates = []
        gather_candidates = []
        worker_tasks = getattr(self.game, "worker_task_system", None)

        for unit in self.game.units:
            if unit.player != player or unit.name != "worker":
                continue
            if worker_tasks:
                task = worker_tasks.active_task(unit)
                if task and task.phase != "FAILED":
                    continue
            # Never pull from building or drop-off
            if unit.is_building or unit.building_target:
                continue
            if unit.is_dropping_off or unit.resource_amount > 0:
                continue
            # Check not assigned to any construction site
            assigned = any(site.builder == unit for site in self.game.construction_sites)
            if assigned:
                continue

            if unit.status == "idle" and not unit.destination and not unit.path:
                idle_candidates.append(unit)
            elif unit.is_gathering or unit.is_engaging or unit.gathering_target:
                gather_candidates.append(unit)

        # Prefer truly idle workers
        if idle_candidates:
            return idle_candidates[0]
        # Otherwise interrupt a gathering worker
        if gather_candidates:
            return gather_candidates[0]
        return None

