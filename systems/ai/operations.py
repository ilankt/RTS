"""Bounded operation history and delivery contracts; no world rescans."""
from collections import Counter, deque
from dataclasses import dataclass, field


@dataclass
class Operation:
    id: int
    player: str
    target: object
    members: list
    started: float
    deadline: float
    phase: str = "assemble"
    outcome: str = "pending"
    escorts: dict = field(default_factory=dict)
    objective_damage: float = 0.0


class OperationLedger:
    def __init__(self):
        self.next_id = 1
        self.active = {}
        self.events = deque(maxlen=512)
        self.counts = Counter()
        self.failures = {}
        self.samples = deque(maxlen=96)
        self.last_sample = {}
        self.unit_sequence = 0

    def sample(self, ctx, now):
        if now - self.last_sample.get(ctx.player.name, -100) < 5:
            return
        self.last_sample[ctx.player.name] = now
        rows = []
        for unit in ctx.military:
            if not hasattr(unit, '_operation_unit_id'):
                self.unit_sequence += 1
                unit._operation_unit_id = self.unit_sequence
            recovery = getattr(unit, '_recovery_job', None)
            assault = getattr(unit, '_assault_order', None)
            assembly = getattr(unit, '_assembly_muster', None)
            if recovery:
                job, deadline = 'recovery', recovery['deadline']
            elif getattr(unit, '_flee_rally', None):
                job, deadline = 'retreat', None
            elif getattr(unit, '_local_defense_target', None):
                job, deadline = 'local_defense', None
            elif assault:
                job, deadline = assault['phase'], assault.get('deadline')
            elif assembly:
                job, deadline = 'assembly', getattr(assembly.get('operation'), 'deadline', None)
            elif unit.in_combat or unit.is_engaging:
                job, deadline = 'tactical_combat', None
            elif getattr(unit, '_pending_path_seq', None) is not None or unit.path or unit.destination:
                job, deadline = 'navigation', None
            elif not getattr(unit, 'can_attack_flag', True):
                job, deadline = 'healing_support', None
            elif getattr(unit, '_guard_post', None):
                job, deadline = 'guard', None
            else:
                job, deadline = 'unassigned', now + 1
            rows.append(dict(id=unit._operation_unit_id, type=unit.name, hp=unit.hp,
                             x=round(unit.x), y=round(unit.y), job=job, deadline=deadline))
        self.samples.append(dict(time=now, player=ctx.player.name, units=rows,
                                 resources=dict(getattr(ctx.player, 'resources', {})),
                                 production_reason=getattr(ctx, 'closing_reason', None)))

    def report(self):
        return dict(events=list(self.events), samples=list(self.samples),
                    counts={outcome+':'+reason: count for (outcome, reason), count in self.counts.items()},
                    active=[dict(id=o.id, phase=o.phase, target=o.target.name,
                                 target_owner=getattr(getattr(o.target, 'player', None), 'name', None),
                                 damage=o.objective_damage, members=len(o.members)) for o in self.active.values()])

    def record(self, now, operation, outcome, reason, unit=None):
        self.counts[(outcome, reason)] += 1
        self.events.append(dict(time=now, operation=operation.id if operation else None,
                                outcome=outcome, reason=reason,
                                unit=getattr(unit, "name", None), hp=getattr(unit, "hp", None),
                                objective_damage=operation.objective_damage if operation else 0))

    def open(self, player, target, members, now, travel_time):
        operation = Operation(self.next_id, player, target, list(members), now,
                              now + travel_time + 50)
        self.next_id += 1
        self.active[operation.id] = operation
        self.record(now, operation, "pending", "assembly")
        return operation

    def close(self, operation, now, outcome, reason):
        if operation.id not in self.active:
            return
        operation.outcome = outcome
        self.record(now, operation, outcome, reason)
        self.active.pop(operation.id)
        if outcome == "failed":
            key = (operation.player, id(operation.target))
            previous = self.failures.get(key)
            # Keep a strong target reference to avoid object-id reuse.
            count = previous[0] + 1 if previous else 1
            self.failures[key] = (count, operation.target,
                                  sum(max(0, u.hp) for u in operation.members), operation.target.hp)


def escort_delivery(ctx, game):
    """Only a paid live queue is a promise. Affordable is not ordered."""
    types = {"warrior", "spearman", "archer", "cavalry", "horse_archer", "axeman"}
    for group in ctx.buildings.values():
        for producer in group:
            if getattr(producer, "hp", 0) <= 0 or not getattr(producer, "in_world", True):
                continue
            production = getattr(producer, "current_production", None)
            if not production:
                continue
            eta = max(0, production.get("total_time", 10) - production.get("progress", 0))
            if production.get("unit_type") in types:
                return producer, eta
            for name in getattr(producer, "production_queue", ()):
                eta += getattr(game, "production_manager", None).units_data.get(name, {}).get("build_time", 10) if getattr(game, "production_manager", None) else 10
                if name in types:
                    return producer, eta
    return None
