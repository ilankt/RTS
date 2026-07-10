"""Covert DDA (§7.2): opt-in reaction-time nudges, never stats."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def set_scores(game, human_gathered, ai_gathered):
    human, ai = game.players[0], game.players[1]
    game.stats_resources_gathered[human.name] = human_gathered
    game.stats_resources_gathered[ai.name] = ai_gathered
    return ai


def test_dda_off_by_default(game):
    ai_player = set_scores(game, human_gathered=100, ai_gathered=10000)
    assert not getattr(game, "adaptive_difficulty", False)
    assert game.ai_system._dda_multiplier(ai_player) == 1.0


def test_dda_nudges_reaction_time_both_ways(game):
    ai = game.ai_system
    game.adaptive_difficulty = True
    try:
        # Human far behind -> AI thinks slower
        ai_player = set_scores(game, human_gathered=100, ai_gathered=10000)
        assert ai._dda_multiplier(ai_player) == ai.DDA_SLOW

        # Human far ahead -> AI sharpens up
        set_scores(game, human_gathered=10000, ai_gathered=100)
        assert ai._dda_multiplier(ai_player) == ai.DDA_FAST

        # Close game -> no nudge
        set_scores(game, human_gathered=1000, ai_gathered=900)
        assert ai._dda_multiplier(ai_player) == 1.0
    finally:
        game.adaptive_difficulty = False


def test_dda_never_touches_stats_or_resources(game):
    """The §7.1 fairness guardrail: DDA only changes tick cadence."""
    game.adaptive_difficulty = True
    try:
        ai_player = set_scores(game, human_gathered=100, ai_gathered=10000)
        resources_before = dict(ai_player.resources)
        game.ai_system._dda_multiplier(ai_player)
        assert ai_player.resources == resources_before
    finally:
        game.adaptive_difficulty = False
