"""Match mutators (§7.5): double resources, no towers, revealed map."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_double_resources_doubles_gather_tick(game):
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    wood = next(r for r in game.resources if r.name == "wood" and r.amount_remaining > 20)

    worker.resource_amount = 0
    game.mutators = set()
    game.gathering_manager.gather_resource_tick(worker, wood, 1.0)
    normal = worker.resource_amount

    worker.resource_amount = 0
    game.mutators = {"double_resources"}
    game.gathering_manager.gather_resource_tick(worker, wood, 1.0)
    assert worker.resource_amount == pytest.approx(normal * 2)


def test_no_towers_blocks_human_and_ai(game):
    game.mutators = {"no_towers"}
    assert game.is_building_disabled("watchtower")
    assert not game.is_building_disabled("barracks")

    # Human build path
    tower_data = {"name": "watchtower", "requires": [], "costs": {}}
    assert not game.building_system.can_player_build(game.players[0], tower_data)

    # AI goal path
    from systems.ai.utility.context import GoalContext
    from systems.ai.utility.goals.military import BuildWatchtowerGoal

    ctx = GoalContext.build(game, game.players[1])
    assert BuildWatchtowerGoal().score(ctx) == 0


def test_mutators_survive_save_load(game, tmp_path):
    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)
    game.mutators = {"no_towers"}
    game.fog_of_war_enabled = False

    SaveManager.save_game(game, slot=7)
    game.mutators = set()
    game.fog_of_war_enabled = True
    success, _ = SaveManager.load_game(game, slot=7)
    assert success
    assert game.mutators == {"no_towers"}
    assert game.fog_of_war.enabled is False


def test_setup_wiring_applies_mutator(monkeypatch):
    import main as main_module

    random.seed(4321)
    setup = {
        "mode": "play", "opponents": 1, "personality": "random",
        "difficulty": "normal", "victory": "annihilation",
        "mutator": "revealed_map", "seed": 4321, "speed": 1,
    }
    game = main_module.create_game_from_setup(setup)
    assert game.mutators == {"revealed_map"}
    assert game.fog_of_war.enabled is False


def test_comeback_mutator_boosts_trailing_player(game):
    gm = game.gathering_manager
    human, ai = game.players[0], game.players[1]

    # AI leads massively on score
    game.stats_resources_gathered[human.name] = 100
    game.stats_resources_gathered[ai.name] = 10000

    game.mutators = set()
    assert gm._comeback_multiplier(human) == 1.0  # mutator off: no bonus

    game.mutators = {"comeback"}
    gm._comeback_cache = None  # force recompute
    assert gm._comeback_multiplier(human) == gm.COMEBACK_BONUS
    assert gm._comeback_multiplier(ai) == 1.0     # the leader gets nothing

    # Close game: nobody qualifies
    game.stats_resources_gathered[human.name] = 9000
    gm._comeback_cache = None
    assert gm._comeback_multiplier(human) == 1.0
    game.mutators = set()
