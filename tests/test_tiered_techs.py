"""§8.17 upgrades follow-up: 3-level tech chains — gating, card visibility
(only the next level shows; finished families disappear), effect stacking,
and the AI pursuing the next level."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.building import Building


@pytest.fixture
def game():
    random.seed(8820)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


@pytest.fixture
def blacksmith(game):
    human = game.players[0]
    template = game.game_data["buildings"]["blacksmith"]
    smith = Building(
        name="blacksmith", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=600, y=600, radius=template.radius,
        player=human, armor_type=template.armor_type)
    game.buildings.append(smith)
    return smith


def complete(game, player, tech_id):
    tech = game.game_data["techs"][tech_id]
    player.upgrades[tech_id] = tech
    player.upgrades_version = getattr(player, "upgrades_version", 0) + 1


def visible_ids(game, building):
    return {tech["id"] for tech, _ok, _reason in
            game.research_manager.available_for_building(building)}


def test_levels_are_gated_and_families_show_only_next(game, blacksmith):
    human = game.players[0]
    human.resources = {"gold": 5000, "wood": 5000, "food": 5000}
    rm = game.research_manager

    ids = visible_ids(game, blacksmith)
    assert "improved_tools" in ids
    assert "improved_tools_2" not in ids, "level 2 hidden until level 1 is done"
    ok, reason = rm.research_status(human, "improved_tools_2")
    assert not ok and reason == "Missing prerequisite"

    complete(game, human, "improved_tools")
    ids = visible_ids(game, blacksmith)
    assert "improved_tools" not in ids, "a completed level's button disappears"
    assert "improved_tools_2" in ids
    assert rm.can_research(human, "improved_tools_2")

    complete(game, human, "improved_tools_2")
    complete(game, human, "improved_tools_3")
    ids = visible_ids(game, blacksmith)
    assert not any(i.startswith("improved_tools") for i in ids), \
        "a finished family vanishes from the card entirely"


def test_effects_stack_across_levels(game):
    from systems.upgrade_effects import effective_gather_rate_multiplier

    human = game.players[0]
    assert effective_gather_rate_multiplier(human, "gold") == 1.0
    for tech_id in ("improved_tools", "improved_tools_2", "improved_tools_3"):
        complete(game, human, tech_id)
    total = effective_gather_rate_multiplier(human, "gold")
    assert abs(total - 1.08 ** 3) < 1e-9, f"three 8% levels compound, got {total}"


def test_armor_levels_add(game):
    from systems.upgrade_effects import effective_unit_stat
    from entities.unit import Unit

    ai = game.players[1]
    warrior = Unit(name="warrior", size=[1, 1], hp=250, movement_speed=50, attack=10,
                   animations={}, x=0, y=0, radius=16, player=ai,
                   armor_type="heavy", armor_value=4, can_attack=True)
    assert effective_unit_stat(warrior, "armor_value", 4) == 4
    complete(game, ai, "padded_armor")
    complete(game, ai, "padded_armor_2")
    assert effective_unit_stat(warrior, "armor_value", 4) == 6


def test_ai_goal_pursues_next_level(game, blacksmith):
    from systems.ai.utility.goals.military import ResearchImprovedToolsGoal

    goal = ResearchImprovedToolsGoal()
    ai = game.players[1]
    ctx_player = ai
    ctx = type("Ctx", (), {})()
    ctx.player = ctx_player
    assert goal._next_tech_id(ctx) == "improved_tools"
    complete(game, ai, "improved_tools")
    assert goal._next_tech_id(ctx) == "improved_tools_2"
    complete(game, ai, "improved_tools_2")
    complete(game, ai, "improved_tools_3")
    assert goal._next_tech_id(ctx) is None, "a finished family stops scoring"
