"""§8.11 fair spectating: AIs play under fog rules even in spectator mode
(the viewer's display is revealed, the players' perception is not), and
building placement requires explored ground."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(20260714)
    from core.game import Game

    g = Game(mode="ai_spectator", player_count=2)
    for _ in range(120):  # 2 sim-seconds: fog grids stamp around bases
        g.update(delta_time_override=1 / 60)
    return g


def test_spectator_keeps_fog_rules_but_reveals_display(game):
    assert game.fog_of_war_enabled is True, "fog RULES stay on for the AIs"
    assert game.spectator_reveal_display is True
    fog = game.fog_of_war

    p1, p2 = game.players[0], game.players[1]
    enemy_castle = next(b for b in game.buildings if b.player is p2 and b.name == "castle")

    # The AI has NOT explored the enemy base at match start...
    assert not fog.is_explored(p1, enemy_castle.x, enemy_castle.y)
    # ...but the spectator's display shows everything.
    assert fog.is_object_visible(enemy_castle)
    assert fog.get_tile_state(p1, 0, 0) == fog.VISIBLE  # display consumer


def test_ai_perception_is_fog_gated_in_spectator(game):
    from systems.ai.utility.context import GoalContext

    p1 = game.players[0]
    ctx = GoalContext.build(game, p1)

    known = sum(len(v) for v in ctx.known_resources_by_type.values())
    assert known < len(game.resources), \
        "early-game AI must not know every resource on the map"
    assert not ctx.enemy_buildings, "enemy base unscouted -> unknown"


def test_placement_requires_explored_ground(game):
    from systems.ai.utility.context import GoalContext

    p1 = game.players[0]
    fog = game.fog_of_war
    placer = game.ai_system.building_placer
    ctx = GoalContext.build(game, p1)

    # Find ground that passes EVERY placement rule except fog: scan with fog
    # disabled (rule off -> is_explored short-circuits True), keep a spot the
    # AI hasn't actually explored.
    candidate = None
    game.fog_of_war_enabled = False
    try:
        for row in range(3, game.game_map.height - 3, 2):
            for col in range(3, game.game_map.width - 3, 2):
                x, y = game.game_map.grid_to_world(col, row)
                if fog.visibility_grid[p1][row][col] != fog.UNEXPLORED:
                    continue
                if placer._is_valid_position(x, y, "farm", ctx):
                    candidate = (x, y)
                    break
            if candidate:
                break
    finally:
        game.fog_of_war_enabled = True
    assert candidate, "seeded map should have unexplored buildable ground"
    x, y = candidate

    assert not placer._is_valid_position(x, y, "farm", ctx), \
        "AI must not build on unexplored ground"

    # Same spot is legal when fog is off as a game RULE (revealed_map)
    game.fog_of_war_enabled = False
    try:
        assert placer._is_valid_position(x, y, "farm", ctx), \
            "revealed-map games legitimately allow it"
    finally:
        game.fog_of_war_enabled = True


def test_human_placement_respects_fog(game):
    """The same no-building-in-the-dark rule applies to the human."""
    p1 = game.players[0]
    fog = game.fog_of_war
    bs = game.building_system

    farm = {"size": [1.5, 1.5], "name": "farm"}
    bs.building_to_place = farm
    bs.selected_builder = next(u for u in game.units if u.player is p1)

    castle = next(b for b in game.buildings if b.player is p1 and b.name == "castle")
    explored_pos = (castle.x + 150, castle.y + 150)

    unexplored_pos = None
    for row in range(3, game.game_map.height - 3):
        for col in range(3, game.game_map.width - 3):
            x, y = game.game_map.grid_to_world(col, row)
            if not fog.is_explored(p1, x, y):
                unexplored_pos = (x, y)
                break
        if unexplored_pos:
            break

    try:
        assert unexplored_pos is not None
        assert not bs.is_valid_building_position(unexplored_pos)
        # Sanity: fog is not what blocks a spot near the castle
        fog_ok_near_base = fog.is_explored(p1, *explored_pos)
        assert fog_ok_near_base
    finally:
        bs.building_to_place = None
        bs.selected_builder = None
