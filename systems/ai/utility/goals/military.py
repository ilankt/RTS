"""Military goals: build production buildings and train combat units."""
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import start_construction, queue_unit


class BuildBarracksGoal(Goal):
    name = "build_barracks"
    category = "military"

    def score(self, ctx):
        if ctx.has_construction_in_progress("barracks"):
            return 0
        if ctx.buildings.get("barracks"):
            return 0
        if len(ctx.workers) < 2:
            return 0
        if not ctx.can_afford("barracks"):
            return 0
        return 90

    def execute(self, ctx):
        return start_construction(ctx, "barracks", ctx.game.ai_system.building_placer)


class BuildStableGoal(Goal):
    name = "build_stable"
    category = "military"

    def score(self, ctx):
        if ctx.has_construction_in_progress("stable"):
            return 0
        if ctx.buildings.get("stable"):
            return 0
        if not ctx.buildings.get("barracks"):
            return 0  # tech-tree-ish prerequisite
        if len(ctx.workers) < 4:
            return 0
        if not ctx.can_afford("stable"):
            return 0
        return 50

    def execute(self, ctx):
        return start_construction(ctx, "stable", ctx.game.ai_system.building_placer)


class BuildWatchtowerGoal(Goal):
    name = "build_watchtower"
    category = "military"

    def score(self, ctx):
        if ctx.has_construction_in_progress("watchtower"):
            return 0
        if ctx.buildings.get("watchtower"):
            return 0
        if not ctx.castle:
            return 0
        if len(ctx.workers) < 3:
            return 0
        if not ctx.can_afford("watchtower"):
            return 0
        return 45

    def execute(self, ctx):
        return start_construction(ctx, "watchtower", ctx.game.ai_system.building_placer)


def _military_fraction(ctx, name):
    total = max(1, len(ctx.military))
    count = sum(1 for u in ctx.military if u.name == name)
    return count / total


class _TrainBarracksUnitGoal(Goal):
    """Shared base for warrior/archer/spearman."""
    category = "military"
    unit_name = "<unset>"
    target_fraction = 0.33

    def score(self, ctx):
        if not ctx.has_pop_space():
            return 0
        if not ctx.can_afford(self.unit_name):
            return 0
        building = ctx.find_idle_production_building("barracks")
        if not building:
            return 0
        # If no military yet, all three barracks-units score the same baseline
        # so personality / cost differences pick one. Once an army exists, push
        # whichever type is under-represented.
        frac = _military_fraction(ctx, self.unit_name) if ctx.military else self.target_fraction
        if frac >= self.target_fraction:
            return 25  # still produce sometimes for filler
        return 50 + (self.target_fraction - frac) * 100

    def execute(self, ctx):
        building = ctx.find_idle_production_building("barracks")
        return queue_unit(ctx, building, self.unit_name)


class TrainWarriorGoal(_TrainBarracksUnitGoal):
    name = "train_warrior"
    unit_name = "warrior"
    target_fraction = 0.40


class TrainArcherGoal(_TrainBarracksUnitGoal):
    name = "train_archer"
    unit_name = "archer"
    target_fraction = 0.30


class TrainSpearmanGoal(_TrainBarracksUnitGoal):
    name = "train_spearman"
    unit_name = "spearman"
    target_fraction = 0.30


class TrainCavalryGoal(Goal):
    name = "train_cavalry"
    category = "military"

    CAP = 3

    def score(self, ctx):
        if not ctx.has_pop_space():
            return 0
        if not ctx.can_afford("cavalry"):
            return 0
        building = ctx.find_idle_production_building("stable")
        if not building:
            return 0
        cavalry = sum(1 for u in ctx.military if u.name == "cavalry")
        if cavalry >= self.CAP:
            return 20
        return 55

    def execute(self, ctx):
        building = ctx.find_idle_production_building("stable")
        return queue_unit(ctx, building, "cavalry")
