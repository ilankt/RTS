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


def test_save_load_roundtrip_v4_fields(tmp_path):
    """v4: control groups, worker tasks, fog resource ghosts, tile rescale."""
    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)

    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(120):
        game.update(delta_time_override=1 / 60)

    human = game.players[0]

    # A worker actively gathering a specific node
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    resource = min(game.resources,
                   key=lambda r: (r.x - worker.x) ** 2 + (r.y - worker.y) ** 2)
    assert game.worker_task_system.assign_gather(worker, resource)
    target_pos = (resource.x, resource.y)

    # A control group with that worker + the castle
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    game.selection_manager.control_groups[3] = [worker, castle]

    # A fog ghost of a resource depleted out of sight
    game.fog_of_war.resource_ghosts[(5, 5, "wood")] = {"name": "wood", "x": 111.0, "y": 222.0}

    # §8.14.13: shift-queued commands, rally-onto-resource, farm timer
    worker.command_queue = [("move", (500.0, 600.0)), ("gather", resource)]
    castle.rally_point = (resource.x, resource.y)
    castle.rally_resource = resource
    castle.food_timer = 3.75

    # A completed upgrade (its stat effects re-derive from this on load)
    tech_id = next(iter(game.game_data["techs"]))
    human.upgrades = {tech_id: game.game_data["techs"][tech_id]}
    version_before = getattr(human, "upgrades_version", 0)

    # A zoom the tile cache must follow after load
    game.camera.zoom = 2.0
    saved_zoom = game.camera.zoom

    SaveManager.save_game(game, slot=7)
    success, message = SaveManager.load_game(game, slot=7)
    assert success, message

    # Camera zoom restored AND the tile cache rescaled to it (tiny-tiles bug)
    assert game.camera.zoom == saved_zoom
    assert game.game_map.current_zoom == saved_zoom

    # Control group 3 has a worker and the castle again
    members = game.selection_manager.control_groups[3]
    names = sorted(getattr(m, "name", "") for m in members)
    assert names == ["castle", "worker"]

    # The worker resumed its gather task on the same node
    worker2 = next(m for m in members if m.name == "worker")
    task = game.worker_task_system.active_task(worker2)
    assert task is not None and task.kind == "gather"
    assert (task.resource.x, task.resource.y) == target_pos

    # The fog ghost survived
    assert game.fog_of_war.resource_ghosts.get((5, 5, "wood")) == {
        "name": "wood", "x": 111.0, "y": 222.0}

    # §8.14.13: the shift-queue reloaded against the restored objects
    assert worker2.command_queue[0] == ("move", (500.0, 600.0))
    kind, target = worker2.command_queue[1]
    assert kind == "gather" and (target.x, target.y) == target_pos

    # Rally-onto-resource and the farm's food cycle survived
    castle2 = next(b for b in game.buildings if b.name == "castle"
                   and b.player is game.players[0])
    assert castle2.rally_resource is not None
    assert (castle2.rally_resource.x, castle2.rally_resource.y) == target_pos
    assert castle2.food_timer == 3.75

    # Completed upgrades reload AND the stat cache is invalidated so their
    # effects re-apply (upgrades_version bump)
    assert tech_id in game.players[0].upgrades
    assert game.players[0].upgrades_version > version_before

    # And the loaded game still simulates
    for _ in range(60):
        game.update(delta_time_override=1 / 60)


def test_four_player_save_survives_load_into_default_game(tmp_path):
    """§8.14.12 (user-reported): a 4-player save loaded from the main menu
    used to come back with only 2 players — every object owned by AI 2/3
    silently vanished, and the human 'thrived' against a half-empty map."""
    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)

    random.seed(555)
    from core.game import Game

    game4 = Game(mode="human_1v1", player_count=4)
    for _ in range(60):
        game4.update(delta_time_override=1 / 60)
    game4.players[2].ai_personality = "rusher"  # identity must survive too
    saved_names = [p.name for p in game4.players]
    SaveManager.save_game(game4, slot=6)

    # The header advertises what to construct
    header = SaveManager.peek_header(slot=6)
    assert header["player_count"] == 4
    assert header["mode"] == "human_1v1"
    assert header["map_size"] == (game4.game_map.width, game4.game_map.height)

    # Worst case: load into a DEFAULT 2-player Game (the old menu path)
    random.seed(556)
    game2 = Game(map_size=header["map_size"])
    assert len(game2.players) == 2
    success, message = SaveManager.load_game(game2, slot=6)
    assert success, message

    assert [p.name for p in game2.players] == saved_names
    castles = {b.player.name for b in game2.buildings if b.name == "castle"}
    assert castles == set(saved_names), "every player's castle must survive the load"
    for player in game2.players:
        assert any(u.player is player for u in game2.units), \
            f"{player.name} lost every unit in the load"

    # The appended AIs actually think: the roster cache was refreshed
    ai_players = {p for p in game2.players if not p.human}
    assert set(game2.ai_system.ai_players) == ai_players
    assert all(p in game2.ai_system.tick_timer for p in ai_players)
    assert game2.players[2].ai_personality == "rusher"

    # And the loaded game still simulates with everyone in it
    for _ in range(60):
        game2.update(delta_time_override=1 / 60)
    assert {b.player.name for b in game2.buildings if b.name == "castle"} == set(saved_names)


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
