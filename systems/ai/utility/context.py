"""Per-tick snapshot of the game state, consumed by every goal.

Built once at the top of each AI tick and passed to every Goal.score() and
Goal.execute() call that tick. Goals never re-scan the world themselves — they
read from this snapshot, which keeps cost predictable and makes goals trivially
testable with a mock context.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional


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

    pop_current: int = 0
    pop_max: int = 5

    @classmethod
    def build(cls, game, player) -> "GoalContext":
        ctx = cls(game=game, player=player)
        ctx.resources = dict(player.resources)  # snapshot, not live ref
        ctx.cost_data = game.game_data.get("costs", {})

        for building in game.buildings:
            if building.player is not player:
                continue
            if building.name == "castle":
                ctx.castle = building
            ctx.buildings.setdefault(building.name, []).append(building)

        military_names = ("warrior", "archer", "spearman", "cavalry", "healer")
        for unit in game.units:
            if unit.player is not player:
                continue
            if unit.name == "worker":
                ctx.workers.append(unit)
            elif unit.name in military_names:
                ctx.military.append(unit)

        for site in game.construction_sites:
            if site.player is player:
                ctx.construction_sites.append(site)
                ctx.site_types.add(site.building_name)

        ctx.pop_current = sum(1 for u in game.units if u.player is player)
        ctx.pop_max = 5 + 5 * len(ctx.buildings.get("house", []))

        return ctx

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
