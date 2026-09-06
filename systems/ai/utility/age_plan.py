"""Per-tick age investment policy, derived only from the AI blackboard."""
from systems.ages import current_age, IRON_SPECIALISTS, UNIT_LINE_TECHS


def configure_age_plan(ctx):
    """Save behind a viable army; release the budget when recovery is urgent.

    No timers or hidden resources: recomputing from the snapshot also releases
    a plan after losses, advancement, or the start of research.
    """
    ctx.age_target = None
    ctx.age_reserve = {}
    ctx.age_building = None
    ctx.age_farm_target = 0
    age = current_age(ctx.player)
    if age >= 3 or not ctx.castle or ctx.castle_under_attack:
        return
    if any(getattr(u, 'can_attack_flag', True) for u in ctx.enemies_near_base):
        return
    fighters = sum(getattr(u, 'hp', 1) > 0 and getattr(u, 'can_attack_flag', True)
                   for u in ctx.military)
    minimum_army = 6 if age == 1 else 10
    if len(ctx.workers) < 5 or fighters < minimum_army:
        return
    # Spend the first Bronze power spike before starting the next age bank.
    if age == 2 and not any(t in getattr(ctx.player, 'upgrades', {})
                            for line in UNIT_LINE_TECHS.values() for t in line):
        return
    tech = 'bronze_age' if age == 1 else 'iron_age'
    if tech in ctx.research_in_progress or tech not in ctx.tech_data:
        return
    ctx.age_target = tech
    ctx.age_reserve = dict(ctx.tech_data[tech]['costs'])
    ctx.age_farm_target = 4 if age == 1 else 6
    if age == 2:
        owned = {name for name, group in ctx.buildings.items()
                 if any(getattr(b, 'hp', 1) > 0 for b in group)}
        if 'blacksmith' not in owned:
            if 'blacksmith' not in ctx.site_types:
                ctx.age_building = 'blacksmith'
        elif len(owned & IRON_SPECIALISTS) < 2:
            # Existing specialists count; don't force a fixed build order
            # on a personality that already has a temple/market/towers.
            present = (owned | ctx.site_types) & IRON_SPECIALISTS
            if len(present) < 2:
                ctx.age_building = next((b for b in ('stable', 'siege_workshop')
                                         if b not in present), None)


def respects_age_budget(ctx, item, costs):
    reserve = ctx.age_reserve
    if not reserve:
        return True
    # Recovery/income/population must remain possible while investing.
    if item in {'worker', 'farm', 'house', 'lumbermill', 'mine', 'barracks',
                ctx.age_target, ctx.age_building}:
        return True
    if item == 'castle' and not ctx.castle:
        return True
    return all(ctx.resources.get(r, 0) - amount >= reserve.get(r, 0)
               for r, amount in costs.items() if amount > 0)
