"""Per-tick snapshot of the game state, consumed by every goal and sub-brain.

This is the AI blackboard (MASTER_PLAN Phase 4): built once at the top of each
AI tick with a single pass over each world list, then passed to every
Goal.score()/execute() call and every sub-brain that tick. Goals and brains
never re-scan game.units/game.buildings themselves — they read this snapshot
(enforced by tests/test_ai_contract.py), which keeps tick cost predictable and
makes goals trivially testable with a mock context.
"""
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

DEFENSE_RADIUS = 300  # enemies within this range of the castle are "at the gates"
MILITARY_NAMES = ("warrior", "archer", "spearman", "cavalry", "ram", "healer")


@dataclass
class GoalContext:
    game: object
    player: object

    workers: list = field(default_factory=list)
    military: list = field(default_factory=list)
    castle: object = None

    buildings: Dict[str, list] = field(default_factory=dict)
    construction_sites: list = field(default_factory=list)
    site_types: set = field(default_factory=set)

    resources: Dict[str, int] = field(default_factory=dict)
    cost_data: Dict[str, dict] = field(default_factory=dict)
    tech_data: Dict[str, dict] = field(default_factory=dict)

    pop_current: int = 0
    pop_max: int = 5

    # --- Blackboard (single world scan per tick) ---
    enemy_units: list = field(default_factory=list)
    enemy_buildings: list = field(default_factory=list)
    enemies_near_base: list = field(default_factory=list)
    castle_under_attack: bool = False  # §8.11: castle hit in the last ~3s
    fountains: list = field(default_factory=list)  # §8.9: explored fountains
    regrouping: bool = False  # §8.9: army is re-massing after a retreat
    known_resources_by_type: Dict[str, list] = field(default_factory=dict)
    gatherers_by_resource: Dict[int, int] = field(default_factory=dict)
    gathering_counts_by_type: Dict[str, int] = field(default_factory=dict)
    research_in_progress: set = field(default_factory=set)
    _dropoff_need_cache: Dict[str, float] = field(default_factory=dict)

    # Coarse influence map: enemy combat strength summed per cell
    threat_cells: Dict[tuple, float] = field(default_factory=dict)
    threat_cell_size: float = 400.0

    @classmethod
    def build(cls, game, player) -> "GoalContext":
        ctx = cls(game=game, player=player)
        ctx.resources = dict(player.resources)  # snapshot, not live ref
        ctx.cost_data = game.game_data.get("costs", {})
        ctx.tech_data = game.game_data.get("techs", {})

        # Fair perception (§7.2): with fog on, the AI only knows enemy
        # buildings it has EXPLORED (buildings are remembered once seen) and
        # enemy units it can currently SEE. With fog off (spectator mode,
        # balance sims) perception stays omniscient, as before.
        fog = getattr(game, "fog_of_war", None)
        fog_on = bool(fog and getattr(fog, "enabled", True))

        for building in game.buildings:
            if building.player is player:
                if building.name == "castle":
                    ctx.castle = building
                ctx.buildings.setdefault(building.name, []).append(building)
                current = getattr(building, "current_research", None)
                if current:
                    ctx.research_in_progress.add(current.get("tech_id"))
                ctx.research_in_progress.update(getattr(building, "research_queue", ()))
            elif building.hp > 0:
                if not fog_on or fog.is_explored(player, building.x, building.y):
                    ctx.enemy_buildings.append(building)

        ctx.gathering_counts_by_type = {"gold": 0, "wood": 0, "stone": 0}
        pop = 0
        for unit in game.units:
            if unit.name == "worker":
                # Crowding counts include every player's workers (matches the
                # pre-blackboard behavior of _count_workers_at_resource).
                target = getattr(unit, "gathering_target", None)
                if target is not None:
                    ctx.gatherers_by_resource[id(target)] = ctx.gatherers_by_resource.get(id(target), 0) + 1
                previous = getattr(unit, "previous_gathering_target", None)
                if previous is not None:
                    ctx.gatherers_by_resource[id(previous)] = ctx.gatherers_by_resource.get(id(previous), 0) + 1
            if unit.player is player:
                pop += 1
                if unit.name == "worker":
                    ctx.workers.append(unit)
                    target = getattr(unit, "gathering_target", None)
                    name = getattr(target, "name", None)
                    if name in ctx.gathering_counts_by_type:
                        ctx.gathering_counts_by_type[name] += 1
                elif unit.name in MILITARY_NAMES:
                    ctx.military.append(unit)
            elif unit.hp > 0:
                if not fog_on or fog.is_visible(player, unit.x, unit.y):
                    ctx.enemy_units.append(unit)

        for site in game.construction_sites:
            if site.player is player:
                ctx.construction_sites.append(site)
                ctx.site_types.add(site.building_name)

        # §8.9 garrisoned units are out of game.units but still take pop
        for group in ctx.buildings.values():
            for building in group:
                pop += len(getattr(building, "garrison", ()))

        ctx.pop_current = pop
        ctx.pop_max = 5 + 5 * len(ctx.buildings.get("house", []))

        if ctx.castle:
            cx, cy = ctx.castle.x, ctx.castle.y
            radius_sq = DEFENSE_RADIUS * DEFENSE_RADIUS
            ctx.enemies_near_base = [
                e
                for e in ctx.enemy_units
                if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= radius_sq
            ] + [
                e
                for e in ctx.enemy_buildings
                if (e.x - cx) ** 2 + (e.y - cy) ** 2 <= radius_sq
            ]
            # §8.11 emergency defense: the castle took a hit within the last
            # ~3 sim-seconds (combat stamps _last_damage_frame on victims).
            last_hit = getattr(ctx.castle, "_last_damage_frame", None)
            ctx.castle_under_attack = (
                last_hit is not None
                and last_hit >= getattr(game, "frame_counter", 0) - 180
            )

        for resource in getattr(game, "resources", []):
            if getattr(resource, "amount_remaining", 0) <= 0:
                continue
            if fog_on and not fog.is_explored(player, resource.x, resource.y):
                continue
            ctx.known_resources_by_type.setdefault(resource.name, []).append(resource)

        # §8.9 healing fountains the player has scouted
        for fountain in getattr(game, "fountains", ()):
            if not fog_on or fog.is_explored(player, fountain.x, fountain.y):
                ctx.fountains.append(fountain)

        # §8.9 squad regroup state (set by the military brain on retreat)
        brain = getattr(getattr(game, "ai_system", None), "military_brain", None)
        if brain is not None and hasattr(brain, "is_regrouping"):
            ctx.regrouping = brain.is_regrouping(player)

        # Coarse enemy-strength influence map (Phase 4): combat units weigh
        # their hp, defensive buildings weigh double.
        cell = ctx.threat_cell_size
        threat = ctx.threat_cells
        for enemy in ctx.enemy_units:
            if enemy.name in MILITARY_NAMES:
                key = (int(enemy.x // cell), int(enemy.y // cell))
                threat[key] = threat.get(key, 0.0) + enemy.hp
        for enemy in ctx.enemy_buildings:
            if getattr(enemy, "can_attack", False):
                key = (int(enemy.x // cell), int(enemy.y // cell))
                threat[key] = threat.get(key, 0.0) + enemy.hp * 2.0

        return ctx

    def threat_at(self, x: float, y: float) -> float:
        """Enemy strength in the 3x3 coarse cells around a point."""
        cell = self.threat_cell_size
        cell_x = int(x // cell)
        cell_y = int(y // cell)
        total = 0.0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                total += self.threat_cells.get((cell_x + dx, cell_y + dy), 0.0)
        return total

    def known_resources(self, resource_type: Optional[str] = None) -> list:
        if resource_type is not None:
            return self.known_resources_by_type.get(resource_type, [])
        merged = []
        for resources in self.known_resources_by_type.values():
            merged.extend(resources)
        return merged

    def count_workers_at_resource(self, resource) -> int:
        return self.gatherers_by_resource.get(id(resource), 0)

    def score_dropoff_need(self, building_type: str) -> float:
        """Memoized per tick — three goals ask for the same numbers."""
        cached = self._dropoff_need_cache.get(building_type)
        if cached is None:
            from systems.ai.economy_helpers import score_dropoff_building_need

            cached = self._dropoff_need_cache[building_type] = score_dropoff_building_need(self, building_type)
        return cached

    # --- Helpers used by goals ---

    def can_afford(self, item_name: str) -> bool:
        costs = self.cost_data.get(item_name, {})
        if not costs:
            return False
        return all(self.resources.get(r, 0) >= a for r, a in costs.items())

    def has_pop_space(self) -> bool:
        return self.pop_current < self.pop_max

    def has_construction_in_progress(self, building_name: str) -> bool:
        return building_name in self.site_types

    def has_building_or_site(self, building_name: str) -> bool:
        return bool(self.buildings.get(building_name)) or self.has_construction_in_progress(building_name)

    def find_idle_worker(self) -> Optional[object]:
        """Return a worker free to take a new job.

        Prefers truly idle workers; falls back to a gathering worker if none
        are idle. Skips workers mid-build, mid-drop-off, or carrying resources.
        """
        idle, gathering = [], []
        worker_tasks = getattr(self.game, "worker_task_system", None)
        for w in self.workers:
            if worker_tasks:
                task = worker_tasks.active_task(w)
                if task and task.phase != "FAILED":
                    continue
            if w.is_building or w.building_target:
                continue
            if w.is_dropping_off or w.resource_amount > 0:
                continue
            if any(s.builder is w for s in self.construction_sites):
                continue
            if w.status == "idle" and not w.destination and not w.path:
                idle.append(w)
            elif w.is_gathering or w.is_engaging or w.gathering_target:
                gathering.append(w)
        if idle:
            return idle[0]
        if gathering:
            return gathering[0]
        return None

    def count_units(self, unit_name: str) -> int:
        """Includes units currently in production at this player's buildings."""
        n = sum(1 for u in self.workers if u.name == unit_name)
        n += sum(1 for u in self.military if u.name == unit_name)
        for building_list in self.buildings.values():
            for b in building_list:
                if b.current_production and b.current_production.get("unit_type") == unit_name:
                    n += 1
                n += sum(1 for q in b.production_queue if q == unit_name)
        if self.castle and self.castle.current_production:
            # castle is also in self.buildings, so its production was already counted
            pass
        return n

    def find_idle_production_building(self, name: str, max_queue: int = 2):
        """First building of `name` whose queue has room."""
        for b in self.buildings.get(name, []):
            queue_len = len(b.production_queue) + (1 if b.current_production else 0)
            if queue_len < max_queue:
                return b
        return None

    def find_idle_research_building(self, name: str, max_queue: int = 2):
        for b in self.buildings.get(name, []):
            queue_len = len(b.research_queue) + (1 if b.current_research else 0)
            if queue_len < max_queue:
                return b
        return None

    def can_research(self, tech_id: str) -> bool:
        manager = getattr(self.game, "research_manager", None)
        if not manager:
            return False
        ok, _ = manager.research_status(self.player, tech_id, in_progress=self.research_in_progress)
        return ok
