"""A legal next reinforcement and its budget, recomputed from the blackboard."""
from systems.ages import availability


def configure_closing_plan(ctx):
    ctx.closing_unit = None
    ctx.closing_producer = None
    ctx.closing_reserve = {}
    ctx.closing_reason = 'not_needed'
    if getattr(ctx.game, 'sim_time_elapsed', 0) < 600 or not ctx.enemy_buildings:
        return
    if ctx.castle_under_attack or not ctx.castle:
        return
    escorts = sum(ctx.count_units(n) for n in ('warrior', 'spearman', 'archer', 'cavalry', 'axeman', 'horse_archer'))
    wanted = ['spearman', 'warrior', 'archer'] if escorts < 4 else (['ram'] if ctx.count_units('ram') < 2 else [])
    for name in wanted:
        if not availability(ctx.player, name)[0]:
            continue
        producers = [b for group in ctx.buildings.values() for b in group
                     if b.hp > 0 and name in (getattr(b, 'can_produce', None) or [])
                     and len(getattr(b, 'production_queue', ())) < 5]
        costs = ctx.cost_data.get(name)
        if producers and costs:
            ctx.closing_unit = name
            ctx.closing_producer = min(producers, key=lambda b: len(getattr(b, 'production_queue', ())))
            ctx.closing_reserve = dict(costs)
            ctx.closing_reason = 'funding' if any(ctx.resources.get(r, 0) < v for r, v in costs.items()) else 'ready'
            # A closing package takes precedence over optional age savings.
            ctx.age_reserve = {}
            return
    if wanted:
        ctx.closing_reason = 'missing_usable_producer'


def respects_closing_budget(ctx, item, costs):
    reserve = getattr(ctx, 'closing_reserve', {})
    if item in {getattr(ctx, 'closing_unit', None), 'worker', 'house', 'farm',
                'market', 'mine', 'lumbermill'}:
        return True
    return all(ctx.resources.get(r, 0) - amount >= reserve.get(r, 0)
               for r, amount in costs.items())
