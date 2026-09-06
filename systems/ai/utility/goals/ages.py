"""Age investment uses the shared blackboard, costs and research path."""
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import queue_research, start_construction
from systems.ages import current_age, completed_tier_one, iron_requirement, UNIT_LINE_TECHS


class AdvanceAgeGoal(Goal):
    name = 'advance_age'
    category = 'economy'

    def score(self, ctx):
        if current_age(ctx.player) >= 3 or not ctx.castle:
            return 0
        tech='bronze_age' if current_age(ctx.player)==1 else 'iron_age'
        if tech in ctx.research_in_progress:
            return 0
        buildings = (b for group in ctx.buildings.values() for b in group)
        if (completed_tier_one(buildings,ctx.player)<3 if tech=='bronze_age' else not iron_requirement(buildings,ctx.player)):
            return 0
        if not ctx.can_afford(tech):
            return 0
        return 160

    def execute(self, ctx):
        return queue_research(ctx, ctx.castle, 'bronze_age' if current_age(ctx.player)==1 else 'iron_age')


class UpgradeUnitLineGoal(Goal):
    name = 'upgrade_unit_line'
    category = 'military'

    def _next(self, ctx):
        candidates = []
        for name, techs in UNIT_LINE_TECHS.items():
            count = sum(u.name == name and getattr(u, 'hp', 1) > 0 for u in ctx.military)
            if count < 2:
                continue
            for tech in techs:
                if not ctx.can_research(tech):
                    continue
                data = ctx.tech_data[tech]
                if ctx.find_idle_research_building(data['building']) is None:
                    continue
                # Prefer the upgrade benefiting most fielded units per
                # resource, rather than always starting with swordsmen.
                value = count / max(1, sum(data.get('costs', {}).values()))
                candidates.append((value, tech))
        return max(candidates)[1] if candidates else None

    def score(self, ctx):
        return 110 if current_age(ctx.player) > 1 and self._next(ctx) else 0

    def execute(self, ctx):
        tech = self._next(ctx)
        producer=ctx.tech_data[tech]['building'] if tech else None
        return bool(tech and queue_research(ctx,ctx.find_idle_research_building(producer),tech))


class PrepareAgeGoal(Goal):
    name = 'prepare_age'
    category = 'economy'

    def score(self, ctx):
        building = ctx.age_building
        if not building or ctx.has_building_or_site(building):
            return 0
        return 150 if ctx.workers and ctx.can_afford(building) else 0

    def execute(self, ctx):
        return start_construction(ctx, ctx.age_building, ctx.game.ai_system.building_placer)
