"""Economy goals: train workers, build resource buildings, expand pop cap."""
from systems.ai.economy_helpers import score_dropoff_building_need
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import start_construction, queue_unit


class TrainWorkerGoal(Goal):
    name = "train_worker"
    category = "economy"

    TARGET = 6  # ramp falls off after this

    def score(self, ctx):
        if not ctx.castle:
            return 0
        if not ctx.has_pop_space():
            return 0
        if ctx.castle.current_production:
            return 0
        if not ctx.can_afford("worker"):
            return 0
        in_play = ctx.count_units("worker")
        if in_play >= self.TARGET:
            return 0
        # 30 base + 20 per missing worker → first worker scores 130, sixth scores 50
        return 30 + (self.TARGET - in_play) * 20

    def execute(self, ctx):
        return queue_unit(ctx, ctx.castle, "worker")


class BuildFarmGoal(Goal):
    name = "build_farm"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("farm"):
            return 0
        if not ctx.can_afford("farm"):
            return 0
        farms = len(ctx.buildings.get("farm", []))
        if farms == 0:
            return 80
        if farms < 3 and ctx.resources.get("food", 0) < 100:
            return 40
        return 0

    def execute(self, ctx):
        return start_construction(ctx, "farm", ctx.game.ai_system.building_placer)


class BuildHouseGoal(Goal):
    name = "build_house"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("house"):
            return 0
        if not ctx.can_afford("house"):
            return 0
        slack = ctx.pop_max - ctx.pop_current
        if slack <= 1:
            return 90  # urgent — about to hit cap
        if slack <= 3:
            return 50
        return 0

    def execute(self, ctx):
        return start_construction(ctx, "house", ctx.game.ai_system.building_placer)


class BuildLumbermillGoal(Goal):
    name = "build_lumbermill"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("lumbermill"):
            return 0
        if not ctx.can_afford("lumbermill"):
            return 0
        if len(ctx.workers) < 2:
            return 0
        return score_dropoff_building_need(ctx, "lumbermill")

    def execute(self, ctx):
        return start_construction(ctx, "lumbermill", ctx.game.ai_system.building_placer)


class BuildMineGoal(Goal):
    name = "build_mine"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("mine"):
            return 0
        if not ctx.can_afford("mine"):
            return 0
        if len(ctx.workers) < 2:
            return 0
        return score_dropoff_building_need(ctx, "mine")

    def execute(self, ctx):
        return start_construction(ctx, "mine", ctx.game.ai_system.building_placer)


class BuildQuarryGoal(Goal):
    name = "build_quarry"
    category = "economy"

    def score(self, ctx):
        if ctx.has_construction_in_progress("quarry"):
            return 0
        if not ctx.can_afford("quarry"):
            return 0
        if len(ctx.workers) < 3:
            return 0
        return score_dropoff_building_need(ctx, "quarry")

    def execute(self, ctx):
        return start_construction(ctx, "quarry", ctx.game.ai_system.building_placer)
