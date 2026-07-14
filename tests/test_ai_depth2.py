"""§8.12 AI depth batch 2: castle rebuild, elimination rule, worker flee,
ram fortification reaction."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_rebuild_castle_goal_scores_only_without_castle():
    from systems.ai.utility.goals.economy import RebuildCastleGoal

    goal = RebuildCastleGoal()
    base = dict(castle=None, workers=[object()],
                has_construction_in_progress=lambda name: False,
                can_afford=lambda name: True)
    assert goal.score(SimpleNamespace(**base)) == 300
    assert goal.score(SimpleNamespace(**{**base, "castle": object()})) == 0
    assert goal.score(SimpleNamespace(**{**base, "workers": []})) == 0
    assert goal.score(SimpleNamespace(
        **{**base, "can_afford": lambda name: False})) == 0


def test_player_can_continue_rules():
    from core.game import Game

    player = SimpleNamespace(name="P", human=False)
    other = SimpleNamespace(name="O", human=False)
    game = SimpleNamespace(
        construction_sites=[], units=[],
        _player_can_continue=Game._player_can_continue,
    )

    # castle alive -> in the game
    assert game._player_can_continue(game, player, 1)
    # nothing left -> out
    assert not game._player_can_continue(game, player, 0)
    # a castle construction site keeps you in
    game.construction_sites = [SimpleNamespace(player=player, building_name="castle")]
    assert game._player_can_continue(game, player, 0)
    # a surviving worker keeps you in (rebuild path)
    game.construction_sites = []
    game.units = [SimpleNamespace(player=player, name="worker", hp=50)]
    assert game._player_can_continue(game, player, 0)
    # someone else's worker doesn't
    game.units = [SimpleNamespace(player=other, name="worker", hp=50)]
    assert not game._player_can_continue(game, player, 0)


def test_ram_goal_reacts_to_fortifications():
    from systems.ai.utility.goals.military import TrainRamGoal

    goal = TrainRamGoal()

    def ctx_with(buildings):
        return SimpleNamespace(
            has_pop_space=lambda: True,
            can_afford=lambda name: True,
            find_idle_production_building=lambda name: object(),
            military=[],
            enemy_buildings=buildings,
        )

    open_base = [SimpleNamespace(name="farm"), SimpleNamespace(name="house")]
    towered = [SimpleNamespace(name="watchtower"), SimpleNamespace(name="castle")]
    assert goal.score(ctx_with(towered)) > goal.score(ctx_with(open_base))


def test_ai_worker_flees_when_attacked():
    from tests.test_worker_task_system import FakeGame, FakeWorker, FakeObject

    game = FakeGame()
    player = game.players[0]
    castle = FakeObject("castle", 128, 160, 42, player)
    game.buildings.append(castle)
    worker = FakeWorker(player, 600, 600)
    game.units.append(worker)
    game.pathfinder.mark_dirty()

    attacker = FakeObject("warrior", 620, 600, 16, SimpleNamespace(name="E", human=False))
    game.frame_counter = 100
    worker.last_attacker = attacker
    worker._last_damage_frame = 100

    game.worker_task_system.update_pre_movement(0.1)

    assert worker._fleeing_until > game.frame_counter
    assert worker.destination or worker.path, "worker should be running home"
