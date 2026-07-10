"""Reactive counters (§7.2): the AI shifts production toward what counters
the enemy's army instead of blindly following its signature composition."""
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from systems.ai.utility.context import GoalContext
from systems.ai.utility.goals.military import (
    TrainSpearmanGoal,
    TrainArcherGoal,
    TrainWarriorGoal,
)
from systems.ai.utility.personality import composition_target


def make_ctx(enemy_army):
    """Blackboard with a mocked enemy army; game only supplies unit tags."""
    units_data = {
        "warrior": SimpleNamespace(strong_against=["archer", "ram"]),
        "archer": SimpleNamespace(strong_against=["warrior", "spearman"]),
        "spearman": SimpleNamespace(strong_against=["cavalry"]),
    }
    game = SimpleNamespace(game_data={"units": units_data})
    player = SimpleNamespace(name="AI 1", ai_personality="balanced")
    ctx = GoalContext(game=game, player=player)
    ctx.enemy_units = [SimpleNamespace(name=name, hp=50) for name in enemy_army]
    return ctx


def test_cavalry_heavy_enemy_boosts_spearmen():
    ctx = make_ctx(["cavalry"] * 8 + ["warrior"] * 2)
    base = composition_target("balanced", "spearman")
    boosted = TrainSpearmanGoal()._target_fraction(ctx)
    assert boosted > base
    # 80% cavalry * 0.5 weight = +0.4 over base, capped at 0.8
    assert boosted == pytest.approx(min(0.8, base + 0.4))

    # Warriors counter neither cavalry nor warrior: no boost
    assert TrainWarriorGoal()._target_fraction(ctx) == pytest.approx(
        composition_target("balanced", "warrior")
    )


def test_melee_heavy_enemy_boosts_archers():
    ctx = make_ctx(["warrior"] * 5 + ["spearman"] * 5)
    base = composition_target("balanced", "archer")
    assert TrainArcherGoal()._target_fraction(ctx) == pytest.approx(min(0.8, base + 0.5))


def test_tiny_enemy_army_is_ignored():
    ctx = make_ctx(["cavalry"] * 3)  # below the reaction threshold
    assert TrainSpearmanGoal()._target_fraction(ctx) == pytest.approx(
        composition_target("balanced", "spearman")
    )


def test_no_enemy_army_keeps_signature_composition():
    ctx = make_ctx([])
    for goal_cls, unit in ((TrainWarriorGoal, "warrior"),
                           (TrainArcherGoal, "archer"),
                           (TrainSpearmanGoal, "spearman")):
        assert goal_cls()._target_fraction(ctx) == pytest.approx(
            composition_target("balanced", unit)
        )
