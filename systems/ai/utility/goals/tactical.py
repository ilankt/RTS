"""Tactical goals: defend, attack, scout.

These goals don't build or train — they switch the AI into a behavior mode
that the sub-brains read on their next call. DefendBaseGoal takes priority
over everything by design; AttackGoal flips the military_brain into attack
mode for one tick.
"""
from systems.ai.utility.goal import Goal


class DefendBaseGoal(Goal):
    name = "defend_base"
    category = "tactical"

    def score(self, ctx):
        if not ctx.castle:
            return 0
        threats = ctx.enemies_near_base
        if not threats:
            return 0
        # Highest priority — overrides economy/military goals.
        # Per-threat ramp so a swarm scores higher than a lone raider.
        return 200 + len(threats) * 10

    def execute(self, ctx):
        # Behavior-mode goal: military_brain handles the actual response when
        # we tell it should_attack=False (defense is its default). We just need
        # to claim the tick so no other goal fires.
        return True


class AttackGoal(Goal):
    name = "attack"
    category = "tactical"

    MIN_ARMY = 6
    SCALE = 8  # +SCALE per extra unit beyond the minimum

    def score(self, ctx):
        n = len(ctx.military)
        if n < self.MIN_ARMY:
            return 0
        # Need a target to attack, otherwise pointless
        if not ctx.enemy_buildings:
            return 0
        return 70 + (n - self.MIN_ARMY) * self.SCALE

    def execute(self, ctx):
        # Behavior flag is read by UtilityAISystem after goal selection;
        # see ai.py — military_brain is called with should_attack=True when
        # the chosen goal is AttackGoal.
        return True


class ScoutGoal(Goal):
    name = "scout"
    category = "tactical"

    def score(self, ctx):
        scout_brain = getattr(ctx.game.ai_system, "scout_brain", None)
        if not scout_brain:
            return 0
        explored = scout_brain.get_exploration_percent(ctx.player)
        if explored >= 60:
            return 0
        return 20

    def execute(self, ctx):
        # scout_brain.update() runs unconditionally each tick — this goal just
        # claims the slot so the panel can show it as "AI is scouting."
        return True
