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
        # Once a core army exists cavalry adds raid/counter value — outrank
        # the flat train goals so the stable actually gets built (it never
        # did under the lean economy at a flat 50).
        return 70 if len(ctx.military) >= 3 else 45

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
    # "support" so turtle (support 1.5x) prioritizes towers and rusher
    # (support 0.5x) mostly skips them - fits the identities (§8.10).
    category = "support"

    def score(self, ctx):
        if getattr(ctx.game, "is_building_disabled", None) and ctx.game.is_building_disabled("watchtower"):
            return 0  # §7.5 no_towers mutator
        if ctx.has_construction_in_progress("watchtower"):
            return 0
        if not ctx.castle:
            return 0
        if len(ctx.workers) < 3:
            return 0
        if not ctx.can_afford("watchtower"):
            return 0
        from systems.ai.utility.personality import tower_cap

        towers = len(ctx.buildings.get("watchtower", []))
        if towers >= tower_cap(getattr(ctx.player, "ai_personality", "balanced")):
            return 0
        threat = ctx.threat_at(ctx.castle.x, ctx.castle.y)
        pressure = min(50, threat * 0.05)
        if towers == 0:
            return 45 + pressure
        # §8.12 batch 3: tower #2 guards the forward economy (the §7.3 raid
        # targets) and needs no pressure — the pressure gate meant every AI
        # stopped at exactly one tower in practice. From #3 on, pressure.
        if towers == 1:
            return 35 + pressure
        if pressure <= 0:
            return 0
        return 20 + pressure

    def execute(self, ctx):
        return start_construction(ctx, "watchtower", ctx.game.ai_system.building_placer)


class BuildWallGoal(Goal):
    """§8.10 AI walling: lay a wall line (with a gate) across the threat bearing.

    One segment per successful tick; the placer re-plans the same deterministic
    line each time and returns the first unbuilt slot, so the line fills in
    incrementally between other goals. Only personalities with a nonzero
    WALL_SEGMENT_TARGETS entry (turtle) ever score it.
    """
    name = "build_wall_line"
    category = "support"

    def _segments(self, ctx):
        from systems.ai.utility.personality import wall_segments

        return wall_segments(getattr(ctx.player, "ai_personality", "balanced"))

    def score(self, ctx):
        segments = self._segments(ctx)
        if segments <= 0 or not ctx.castle:
            return 0
        if len(ctx.workers) < 5:
            return 0  # walls are a mid-game investment, not an opening
        if ctx.has_construction_in_progress("wooden_wall") or ctx.has_construction_in_progress("gate"):
            return 0  # one segment at a time
        piece = ctx.game.ai_system.building_placer.next_wall_piece(ctx, segments)
        if piece is None:
            return 0  # line complete or unplannable
        # Walls are deferred (buildings.json buildable:false) — skip so a turtle
        # doesn't burn its top goal slot every tick on a piece it can't build.
        template = ctx.game.game_data.get("buildings", {}).get(piece[0])
        if template is not None and not getattr(template, "buildable", True):
            return 0
        if not ctx.can_afford(piece[0]):
            return 0
        # High base on purpose: AttackGoal succeeds every tick it wins, so a
        # lower score would never execute. Weighted 90 for turtle beats attack
        # (weighted 49 + 5.6/unit past threshold) until the army is ~14 —
        # the wall goes up before massing, which is the turtle identity.
        threat = ctx.threat_at(ctx.castle.x, ctx.castle.y)
        return 60 + min(30, threat * 0.03)

    def execute(self, ctx):
        placer = ctx.game.ai_system.building_placer
        piece = placer.next_wall_piece(ctx, self._segments(ctx))
        if piece is None:
            return False
        piece_name, position = piece
        return start_construction(ctx, piece_name, placer, position=position)


def _military_fraction(ctx, name):
    total = max(1, len(ctx.military))
    count = sum(1 for u in ctx.military if u.name == name)
    return count / total


class _TrainCompositionUnitGoal(Goal):
    """Shared base for composition-driven unit training (warrior/archer/
    spearman from the barracks, cavalry from the stable)."""
    category = "military"
    unit_name = "<unset>"
    production_building = "barracks"

    # §7.2 reactive counters: how strongly the enemy's army mix pulls this
    # personality off its signature composition, and how many enemy military
    # units must exist before there's anything worth reacting to.
    # EXPERIMENT LOG (2026-07-10): 0.5 amplified the warrior<->archer mutual-
    # counter loop across 20 same-seed matches (warrior 26->33%, archer
    # 17->25%, cavalry 15->7.5%) — softened to 0.25 with a lower cap.
    REACTIVE_WEIGHT = 0.25
    REACTIVE_MIN_ENEMIES = 4
    TARGET_FRACTION_CAP = 0.6

    def _counter_boost(self, ctx):
        """Extra target share when this unit counters what the enemy fields."""
        from systems.ai.utility.context import MILITARY_NAMES

        enemies = [e for e in ctx.enemy_units if e.name in MILITARY_NAMES]
        if len(enemies) < self.REACTIVE_MIN_ENEMIES:
            return 0.0
        template = ctx.game.game_data["units"].get(self.unit_name)
        tags = set(getattr(template, "strong_against", ()) or ())
        if not tags:
            return 0.0
        countered = sum(1 for e in enemies if e.name in tags)
        return self.REACTIVE_WEIGHT * countered / len(enemies)

    def _target_fraction(self, ctx):
        # Signature army composition per personality (§7.2), pulled toward
        # whatever counters the enemy's current army (reactive counters).
        from systems.ai.utility.personality import composition_target

        base = composition_target(getattr(ctx.player, "ai_personality", "balanced"), self.unit_name)
        return min(self.TARGET_FRACTION_CAP, base + self._counter_boost(ctx))

    def score(self, ctx):
        if not ctx.has_pop_space():
            return 0
        if not ctx.can_afford(self.unit_name):
            return 0
        building = ctx.find_idle_production_building(self.production_building)
        if not building:
            return 0
        target_fraction = self._target_fraction(ctx)
        # If no military yet, every trainable unit scores the same baseline
        # so personality / cost differences pick one. Once an army exists, push
        # whichever type is under-represented.
        frac = _military_fraction(ctx, self.unit_name) if ctx.military else target_fraction
        if frac >= target_fraction:
            return 25  # still produce sometimes for filler
        return 50 + (target_fraction - frac) * 100

    def execute(self, ctx):
        building = ctx.find_idle_production_building(self.production_building)
        return queue_unit(ctx, building, self.unit_name)


class TrainWarriorGoal(_TrainCompositionUnitGoal):
    name = "train_warrior"
    unit_name = "warrior"



class TrainArcherGoal(_TrainCompositionUnitGoal):
    name = "train_archer"
    unit_name = "archer"



class TrainSpearmanGoal(_TrainCompositionUnitGoal):
    name = "train_spearman"
    unit_name = "spearman"



class TrainCavalryGoal(_TrainCompositionUnitGoal):
    """Composition-driven like the barracks units (§7.2 signature armies) —
    sharing the base also gives cavalry the reactive counter boost (it gets
    trained up when the enemy fields what it's strong against)."""
    name = "train_cavalry"
    unit_name = "cavalry"
    production_building = "stable"


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
        # §8.12 batch 3: proportional hard cap. Rams are the only GOLD-FREE
        # combat unit, so a wood-flush gold-broke AI used to win every quiet
        # tick with the old flat filler score and mass ~30 rams. Now big ram
        # counts require a big army to escort them (25% of military, min 3),
        # and past the cap the goal is silent — no filler.
        rams = sum(1 for u in ctx.military if u.name == "ram")
        if rams >= max(self.CAP, int(0.25 * len(ctx.military))):
            return 0
        # §8.12 reactive counters vs fortifications: a towered-up enemy
        # visibly pulls siege production (unit-only counters missed this).
        # Capped low — the first tuning (+8 each, cap 4) stacked with the
        # base building bonus and pushed rams back to 35% of production.
        fortifications = sum(
            1 for b in ctx.enemy_buildings
            if b.name in ("watchtower", "castle", "wall", "wooden_wall", "gate"))
        return 65 + min(len(ctx.enemy_buildings), 4) * 5 + min(fortifications, 3) * 5

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
