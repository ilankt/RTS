"""Save/load completeness roundtrip (§9): the v2 fields survive a cycle."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def test_save_load_roundtrip_v2_fields(tmp_path):
    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)

    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(120):
        game.update(delta_time_override=1 / 60)

    human = game.players[0]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")

    # Set up v2 state: production queue, rally, stats, clock, victory, fog
    ok, _ = game.production_manager.start_production(castle, "worker")
    assert ok
    game.production_manager.start_production(castle, "worker")  # queues one
    castle.rally_point = (castle.x + 200, castle.y + 100)
    game.victory_condition = "economic"
    game.stats_resources_gathered[human.name] = 123
    game.stats_units_trained[(human.name, "worker")] = 7
    unit = next(u for u in game.units if u.player is human)
    unit.stance = "defensive"
    unit.stance_home_position = (400.0, 500.0)
    saved_sim_time = game.sim_time_elapsed
    saved_progress = castle.current_production["progress"]
    saved_explored = game.fog_of_war.get_exploration_percent(human)
    assert saved_explored > 0

    SaveManager.save_game(game, slot=9)
    success, message = SaveManager.load_game(game, slot=9)
    assert success, message

    human2 = game.players[0]
    castle2 = next(b for b in game.buildings if b.player is human2 and b.name == "castle")
    assert castle2.current_production is not None
    assert castle2.current_production["unit_type"] == "worker"
    assert abs(castle2.current_production["progress"] - saved_progress) < 1e-6
    assert castle2.production_queue == ["worker"]
    assert castle2.rally_point == (castle.x + 200, castle.y + 100)

    assert game.victory_condition == "economic"
    assert abs(game.sim_time_elapsed - saved_sim_time) < 1e-6
    assert game.stats_resources_gathered[human2.name] == 123
    assert game.stats_units_trained[(human2.name, "worker")] == 7

    unit2 = next(u for u in game.units if u.player is human2 and u.stance == "defensive")
    assert unit2.stance_home_position == (400.0, 500.0)

    # Fog exploration survives (within a tile of rounding)
    assert abs(game.fog_of_war.get_exploration_percent(human2) - saved_explored) < 1.0

    # And the loaded game still simulates
    for _ in range(60):
        game.update(delta_time_override=1 / 60)


def test_gate_passable_state_survives(tmp_path):
    from managers.save_manager import SaveManager
    from entities.building import Building

    SaveManager.SAVE_DIR = str(tmp_path)

    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    human = game.players[0]
    template = game.game_data["buildings"]["gate"]
    gate = Building(
        name="gate", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=800, y=800, radius=template.radius,
        player=human, armor_type=template.armor_type,
    )
    gate.toggle_gate()  # open it
    game.buildings.append(gate)

    SaveManager.save_game(game, slot=8)
    success, _ = SaveManager.load_game(game, slot=8)
    assert success

    gate2 = next(b for b in game.buildings if b.name == "gate")
    assert gate2.is_gate and gate2.passable  # still open after load
