import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.building import Building
from entities.data_loader import load_game_data
from entities.player import Player
from entities.unit import Unit
from systems.ai.utility.context import GoalContext
from systems.ai.utility.goals.military import (
    BuildBlacksmithGoal,
    BuildSiegeWorkshopGoal,
    TrainRamGoal,
)
from systems.research_manager import ResearchManager


class FakeGame:
    def __init__(self, player):
        self.players = [player]
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.game_data = load_game_data()
        self.research_manager = ResearchManager(self)


def test_strategy_data_loads_ram_siege_and_tech_costs():
    data = load_game_data()

    assert "ram" in data["units"]
    assert "siege_workshop" in data["buildings"]
    assert "improved_tools" in data["techs"]
    assert data["costs"]["siege_engineering"]["stone"] == 80
    assert data["units"]["healer"].buildable is False
    # Walls deferred 2026-07-12 (§8.10): mechanics are done but disabled via
    # buildable:false pending orientation-aware sprites — flip to re-enable.
    assert data["buildings"]["wall"].buildable is False
    assert data["buildings"]["wooden_wall"].buildable is False
    assert data["buildings"]["gate"].buildable is False
    assert data["buildings"]["temple"].buildable is False  # still content-gated


def test_default_game_mode_is_human_1v1_and_spectator_is_preserved():
    from core.game import Game

    human_game = Game()
    assert human_game.mode == "human_1v1"
    assert [p.human for p in human_game.players] == [True, False]
    # Forests regrow in every mode now (§8.3 wood = renewable), incl. human
    assert human_game.tree_regrowth_enabled is True

    spectator_game = Game(mode="ai_spectator", player_count=4)
    assert spectator_game.spectator_mode is True
    assert len(spectator_game.players) == 4
    assert all(not p.human for p in spectator_game.players)


def test_research_manager_completes_once_and_applies_effect_data():
    player = Player("Human", human=True)
    player.resources = {"gold": 500, "wood": 500, "stone": 500, "food": 500}
    game = FakeGame(player)
    blacksmith_template = game.game_data["buildings"]["blacksmith"]
    blacksmith = Building(
        blacksmith_template.name,
        blacksmith_template.size,
        blacksmith_template.hp,
        blacksmith_template.sprite,
        blacksmith_template.build_duration,
        radius=blacksmith_template.radius,
        player=player,
    )
    game.buildings.append(blacksmith)

    success, _ = game.research_manager.start_research(blacksmith, "forged_blades")
    assert success is True

    duplicate, reason = game.research_manager.start_research(blacksmith, "forged_blades")
    assert duplicate is False
    assert reason == "Already in progress"

    game.research_manager.update(999)
    assert "forged_blades" in player.upgrades
    assert game.research_manager.can_research(player, "forged_blades") is False

    warrior = Unit("warrior", [1, 1], 250, 50, 10, {}, player=player, min_damage=18, max_damage=22)
    assert warrior.get_effective_min_damage() > warrior.min_damage


def test_ai_scores_new_blacksmith_siege_and_ram_goals():
    player = Player("AI", human=False)
    player.resources = {"gold": 1000, "wood": 1000, "stone": 1000, "food": 1000}
    game = FakeGame(player)
    castle = Building("castle", [2.5, 2.5], 5000, None, 50, player=player)
    barracks = Building("barracks", [1.5, 1.5], 1000, None, 10, player=player)
    siege = Building("siege_workshop", [1.5, 1.5], 900, None, 12, player=player)
    game.buildings.extend([castle, barracks, siege])
    game.units.extend(Unit("worker", [1, 1], 100, 40, 0, {}, player=player) for _ in range(4))
    ctx = GoalContext.build(game, player)

    assert BuildBlacksmithGoal().score(ctx) > 0
    assert BuildSiegeWorkshopGoal().score(ctx) == 0
    assert TrainRamGoal().score(ctx) > 0


def test_siege_engineering_requires_siege_workshop():
    player = Player("Human", human=True)
    player.resources = {"gold": 500, "wood": 500, "stone": 500, "food": 500}
    game = FakeGame(player)
    blacksmith = Building("blacksmith", [1.5, 1.5], 800, None, 10, player=player)
    game.buildings.append(blacksmith)

    ok, reason = game.research_manager.research_status(player, "siege_engineering", building=blacksmith)

    assert ok is False
    assert reason == "Missing prerequisite"
