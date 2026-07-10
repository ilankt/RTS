"""Fair perception (§7.2): with fog on, the AI blackboard only contains
enemies it has actually scouted; with fog off, perception is unchanged."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from systems.ai.utility.context import GoalContext


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(30):  # build the fog grids
        game.update(delta_time_override=1 / 60)
    return game


def test_unscouted_enemies_are_unknown(game):
    ai = game.players[1]
    human = game.players[0]
    human_castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    assert not game.fog_of_war.is_explored(ai, human_castle.x, human_castle.y)

    ctx = GoalContext.build(game, ai)
    assert human_castle not in ctx.enemy_buildings
    assert all(u.player is not human for u in ctx.enemy_units) or not ctx.enemy_units


def test_scouting_reveals_buildings_permanently_units_transiently(game):
    ai = game.players[1]
    human = game.players[0]
    human_castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    scout = next(u for u in game.units if u.player is ai)

    # Walk the scout into the human base and refresh fog
    old_pos = (scout.x, scout.y)
    scout.x, scout.y = human_castle.x + 80, human_castle.y
    game.fog_of_war.update()

    ctx = GoalContext.build(game, ai)
    assert human_castle in ctx.enemy_buildings          # seen
    assert any(u.player is human for u in ctx.enemy_units)  # human workers visible

    # Scout leaves; visibility fades but exploration is remembered
    scout.x, scout.y = old_pos
    game.fog_of_war.update()
    game.fog_of_war.update()

    ctx = GoalContext.build(game, ai)
    assert human_castle in ctx.enemy_buildings          # buildings remembered
    assert not any(u.player is human for u in ctx.enemy_units)  # units gone dark


def test_fog_off_keeps_omniscience_for_sims(game):
    ai = game.players[1]
    human = game.players[0]
    human_castle = next(b for b in game.buildings if b.player is human and b.name == "castle")

    game.fog_of_war_enabled = False
    try:
        ctx = GoalContext.build(game, ai)
        assert human_castle in ctx.enemy_buildings
        assert any(u.player is human for u in ctx.enemy_units)
    finally:
        game.fog_of_war_enabled = True


def test_blind_ai_still_develops_and_scouts():
    """A fair-perception AI in a human match must not stall: economy grows
    and the scout brain expands what it has explored."""
    random.seed(777)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    ai = game.players[1]
    explored_start = game.fog_of_war.get_exploration_percent(ai)

    for _ in range(60 * 180):  # three game-minutes
        game.update(delta_time_override=1 / 60)

    assert game.fog_of_war.get_exploration_percent(ai) > explored_start
    gathered = game.stats_resources_gathered.get(ai.name, 0)
    assert gathered > 100, f"blind AI economy stalled ({gathered})"
    built = [k for (name, k), v in game.stats_buildings_built.items() if name == ai.name]
    assert built, "blind AI never built anything"
