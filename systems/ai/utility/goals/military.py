"""Military goals: build production buildings and train combat units."""
from systems.ai.utility.goal import Goal
from systems.ai.utility.actions import start_construction, queue_unit, queue_research


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


class BuildBlacksmithGoal(Goal):
    name = "build_blacksmith"
    category = "military"

    def score(self, ctx):
        if ctx.has_building_or_site("blacksmith"):
            return 0
        if not ctx.buildings.get("barracks"):
            return 0
        if len(ctx.workers) < 3:
            return 0
        if not ctx.can_afford("blacksmith"):
            return 0
        return 80

    def execute(self, ctx):
        return start_construction(ctx, "blacksmith", ctx.game.ai_system.building_placer)


class BuildSiegeWorkshopGoal(Goal):
    name = "build_siege_workshop"
    category = "military"

    def score(self, ctx):
        if ctx.has_building_or_site("siege_workshop"):
            return 0
        if not ctx.buildings.get("blacksmith"):
            return 0
        if len(ctx.workers) < 4:
            return 0
        if not ctx.can_afford("siege_workshop"):
            return 0
        if len(ctx.military) < 4:
            return 75
        return 100

    def execute(self, ctx):
        return start_construction(ctx, "siege_workshop", ctx.game.ai_system.building_placer)


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


class TrainRamGoal(Goal):
    name = "train_ram"
    category = "military"

    CAP = 3

    def score(self, ctx):
        if not ctx.has_pop_space():
            return 0
        if not ctx.can_afford("ram"):
            return 0
        building = ctx.find_idle_production_building("siege_workshop")
        if not building:
            return 0
        rams = sum(1 for u in ctx.military if u.name == "ram")
        if rams >= self.CAP:
            return 15
        return 65 + min(len(ctx.enemy_buildings), 4) * 5

    def execute(self, ctx):
        building = ctx.find_idle_production_building("siege_workshop")
        return queue_unit(ctx, building, "ram")


class ResearchTechGoal(Goal):
    name = "research_tech"
    category = "military"
    tech_id = "<unset>"
    base_score = 45

    def score(self, ctx):
        if not ctx.can_research(self.tech_id):
            return 0
        building = ctx.find_idle_research_building("blacksmith")
        if not building:
            return 0
        return self._score(ctx)

    def _score(self, ctx):
        return self.base_score

    def execute(self, ctx):
        building = ctx.find_idle_research_building("blacksmith")
        return queue_research(ctx, building, self.tech_id)


class ResearchImprovedToolsGoal(ResearchTechGoal):
    name = "research_improved_tools"
    category = "economy"
    tech_id = "improved_tools"
    base_score = 70

    def _score(self, ctx):
        if len(ctx.workers) < 3:
            return 0
        return self.base_score


class ResearchForgedBladesGoal(ResearchTechGoal):
    name = "research_forged_blades"
    tech_id = "forged_blades"
    base_score = 55

    def _score(self, ctx):
        melee = sum(1 for u in ctx.military if u.name in ("warrior", "spearman", "cavalry"))
        return self.base_score + melee * 4 if melee >= 2 else 0


class ResearchFletchingGoal(ResearchTechGoal):
    name = "research_fletching"
    tech_id = "fletching"
    base_score = 55

    def _score(self, ctx):
        archers = sum(1 for u in ctx.military if u.name == "archer")
        towers = len(ctx.buildings.get("watchtower", []))
        return self.base_score + archers * 5 + towers * 5 if archers or towers else 0


class ResearchPaddedArmorGoal(ResearchTechGoal):
    name = "research_padded_armor"
    tech_id = "padded_armor"
    base_score = 45

    def _score(self, ctx):
        return self.base_score if len(ctx.military) >= 5 else 0


class ResearchReinforcedFramesGoal(ResearchTechGoal):
    name = "research_reinforced_frames"
    category = "support"
    tech_id = "reinforced_frames"
    base_score = 35

    def _score(self, ctx):
        return self.base_score if len(ctx.buildings) >= 4 else 0


class ResearchSiegeEngineeringGoal(ResearchTechGoal):
    name = "research_siege_engineering"
    tech_id = "siege_engineering"
    base_score = 65

    def _score(self, ctx):
        rams = sum(1 for u in ctx.military if u.name == "ram")
        return self.base_score + rams * 8 if ctx.buildings.get("siege_workshop") else 0
