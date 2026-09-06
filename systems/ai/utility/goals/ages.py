"""Age investment uses the shared blackboard, costs and research path."""
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import queue_research
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
        for name, techs in UNIT_LINE_TECHS.items():
            for tech in techs:
                if ctx.count_units(name)>=2 and ctx.can_research(tech): return tech
        return None

    def score(self, ctx):
        return 110 if current_age(ctx.player) > 1 and self._next(ctx) else 0

    def execute(self, ctx):
        tech = self._next(ctx)
        producer=ctx.tech_data[tech]['building'] if tech else None
        return bool(tech and queue_research(ctx,ctx.find_idle_research_building(producer),tech))
