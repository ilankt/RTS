"""Tests for the utility AI: scoring, personality weights, integration."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from systems.ai.utility.context import GoalContext
from systems.ai.utility.personality import get_weight, PERSONALITY_WEIGHTS
from systems.ai.utility.goals.economy import (
    TrainWorkerGoal,
    BuildFarmGoal,
    BuildHouseGoal,
    BuildLumbermillGoal,
    BuildMineGoal,
    BuildQuarryGoal,
)
from systems.ai.worker_brain import WorkerBrain
from systems.ai.utility.goals.military import (
    BuildBarracksGoal,
    TrainWarriorGoal,
)
from systems.ai.utility.goals.tactical import (
    DefendBaseGoal,
    AttackGoal,
)


# --- Fakes ----------------------------------------------------------------

class FakePlayer:
    def __init__(self, personality="balanced"):
        self.name = "AI"
        self.human = False
        self.color = (255, 0, 0)
        self.resources = {"gold": 200, "wood": 200, "stone": 100, "food": 100}
        self.ai_personality = personality


class FakeBuilding:
    def __init__(self, name, player, x=0, y=0, hp=100):
        self.name = name
        self.player = player
        self.x = x
        self.y = y
        self.hp = hp
        self.current_production = None
        self.production_queue = []


class FakeUnit:
    def __init__(self, name, player, x=0, y=0):
        self.name = name
        self.player = player
        self.x = x
        self.y = y
        self.hp = 100
        self.is_gathering = False
        self.is_building = False
        self.is_dropping_off = False
        self.is_engaging = False
        self.gathering_target = None
        self.building_target = None
        self.resource_amount = 0
        self.status = "idle"
        self.destination = None
        self.path = None


class FakeGame:
    def __init__(self, player):
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = [player]
        self.game_data = {
            "costs": {
                "worker":   {"gold": 50, "food": 25},
                "warrior":  {"gold": 100, "wood": 25, "food": 50},
                "archer":   {"gold": 75, "wood": 50, "food": 40},
                "spearman": {"gold": 60, "wood": 25, "food": 35},
                "cavalry":  {"gold": 120, "food": 80},
                "farm":     {"wood": 75},
                "house":    {"gold": 50, "wood": 50},
                "barracks": {"gold": 150, "wood": 100, "stone": 50},
                "lumbermill": {"gold": 75, "wood": 75},
                "mine": {"gold": 75, "wood": 75, "stone": 25},
                "quarry": {"gold": 75, "wood": 50, "stone": 50},
            },
            "buildings": {},
            "units": {},
        }


class FakeResource:
    def __init__(self, name, x, y, amount=600):
        self.name = name
        self.x = x
        self.y = y
        self.radius = 16
        self.amount_remaining = amount
        self.gatherers = []


class FakeFog:
    enabled = True

    def __init__(self, explored=True):
        self.explored = explored

    def is_explored(self, player, x, y):
        return self.explored


def _ctx_with(player, *, units=(), buildings=(), sites=(), resources=(), fog=None):
    """Convenience: build a context against a tiny fake game."""
    game = FakeGame(player)
    for b in buildings:
        game.buildings.append(b)
    for u in units:
        game.units.append(u)
    for s in sites:
        game.construction_sites.append(s)
    for r in resources:
        game.resources.append(r)
    if fog:
        game.fog_of_war = fog
    return GoalContext.build(game, player)


# --- Personality weights --------------------------------------------------

class TestPersonalityWeights:
    def test_rusher_prefers_military(self):
        assert get_weight("rusher", "military") > get_weight("rusher", "economy")

    def test_boomer_prefers_economy(self):
        assert get_weight("boomer", "economy") > get_weight("boomer", "military")

    def test_balanced_is_uniform(self):
        weights = PERSONALITY_WEIGHTS["balanced"]
        assert all(v == 1.0 for v in weights.values())

    def test_unknown_personality_falls_back_to_balanced(self):
        assert get_weight("nonexistent", "economy") == 1.0


# --- Economy goals --------------------------------------------------------

class TestTrainWorkerGoal:
    def test_high_score_with_one_worker(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        worker = FakeUnit("worker", p)
        ctx = _ctx_with(p, units=[worker], buildings=[castle])
        score = TrainWorkerGoal().score(ctx)
        assert score > 100  # 30 + (6-1)*20 = 130

    def test_zero_when_castle_is_producing(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        castle.current_production = {"unit_type": "worker", "progress": 0.5}
        ctx = _ctx_with(p, buildings=[castle])
        assert TrainWorkerGoal().score(ctx) == 0

    def test_zero_when_pop_capped(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        units = [FakeUnit("worker", p) for _ in range(5)]
        ctx = _ctx_with(p, units=units, buildings=[castle])
        # 1 castle = pop_max 5, 5 workers = pop full
        assert TrainWorkerGoal().score(ctx) == 0


class TestBuildFarmGoal:
    def test_high_score_with_no_farm(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        ctx = _ctx_with(p, buildings=[castle])
        assert BuildFarmGoal().score(ctx) == 80

    def test_zero_when_farm_in_progress(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        site = type("Site", (), {})()
        site.player = p
        site.building_name = "farm"
        ctx = _ctx_with(p, buildings=[castle], sites=[site])
        assert BuildFarmGoal().score(ctx) == 0

    def test_zero_when_cannot_afford(self):
        p = FakePlayer()
        p.resources["wood"] = 0
        castle = FakeBuilding("castle", p)
        ctx = _ctx_with(p, buildings=[castle])
        assert BuildFarmGoal().score(ctx) == 0


class TestBuildHouseGoal:
    def test_high_score_when_pop_capped(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        # 5 units against pop_max 5 → slack=0, urgent
        units = [FakeUnit("worker", p) for _ in range(5)]
        ctx = _ctx_with(p, units=units, buildings=[castle])
        assert BuildHouseGoal().score(ctx) == 90

    def test_zero_with_lots_of_room(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        ctx = _ctx_with(p, buildings=[castle])  # no units, slack=5
        assert BuildHouseGoal().score(ctx) == 0


class TestResourceDropoffGoals:
    @pytest.mark.parametrize(
        "goal_cls,building_name,resource_name,min_workers",
        [
            (BuildLumbermillGoal, "lumbermill", "wood", 2),
            (BuildMineGoal, "mine", "gold", 2),
            (BuildQuarryGoal, "quarry", "stone", 3),
        ],
    )
    def test_scores_when_known_resource_cluster_is_unserved(self, goal_cls, building_name, resource_name, min_workers):
        p = FakePlayer()
        castle = FakeBuilding("castle", p, x=0, y=0)
        existing = FakeBuilding(building_name, p, x=100, y=0)
        workers = [FakeUnit("worker", p) for _ in range(min_workers)]
        resource = FakeResource(resource_name, x=1200, y=0)

        ctx = _ctx_with(p, units=workers, buildings=[castle, existing], resources=[resource])

        assert goal_cls().score(ctx) > 0

    @pytest.mark.parametrize(
        "goal_cls,building_name,resource_name,min_workers",
        [
            (BuildLumbermillGoal, "lumbermill", "wood", 2),
            (BuildMineGoal, "mine", "gold", 2),
            (BuildQuarryGoal, "quarry", "stone", 3),
        ],
    )
    def test_zero_when_known_resource_cluster_is_already_serviced(self, goal_cls, building_name, resource_name, min_workers):
        p = FakePlayer()
        castle = FakeBuilding("castle", p, x=0, y=0)
        serviced_dropoff = FakeBuilding(building_name, p, x=1120, y=0)
        workers = [FakeUnit("worker", p) for _ in range(min_workers)]
        resource = FakeResource(resource_name, x=1200, y=0)

        ctx = _ctx_with(p, units=workers, buildings=[castle, serviced_dropoff], resources=[resource])

        assert goal_cls().score(ctx) == 0

    def test_zero_when_resource_is_hidden_by_fog(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p, x=0, y=0)
        workers = [FakeUnit("worker", p), FakeUnit("worker", p)]
        resource = FakeResource("wood", x=1200, y=0)

        ctx = _ctx_with(p, units=workers, buildings=[castle], resources=[resource], fog=FakeFog(explored=False))

        assert BuildLumbermillGoal().score(ctx) == 0


class TestWorkerResourceChoice:
    def test_prefers_serviced_loop_over_closer_unserviced_resource(self):
        p = FakePlayer()
        game = FakeGame(p)
        worker = FakeUnit("worker", p, x=500, y=0)
        close_unserviced = FakeResource("wood", x=520, y=0)
        farther_serviced = FakeResource("wood", x=900, y=0)
        game.units.append(worker)
        game.buildings.append(FakeBuilding("castle", p, x=0, y=0))
        game.buildings.append(FakeBuilding("lumbermill", p, x=900, y=0))
        game.resources.extend([close_unserviced, farther_serviced])

        chosen = WorkerBrain(game)._find_best_resource_to_gather(worker, p)

        assert chosen is farther_serviced


# --- Military goals -------------------------------------------------------

class TestBuildBarracksGoal:
    def test_high_score_when_no_barracks(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        workers = [FakeUnit("worker", p), FakeUnit("worker", p)]
        ctx = _ctx_with(p, units=workers, buildings=[castle])
        assert BuildBarracksGoal().score(ctx) == 90

    def test_zero_when_barracks_exists(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        barracks = FakeBuilding("barracks", p)
        workers = [FakeUnit("worker", p), FakeUnit("worker", p)]
        ctx = _ctx_with(p, units=workers, buildings=[castle, barracks])
        assert BuildBarracksGoal().score(ctx) == 0

    def test_personality_weighting_applies(self):
        rusher_score = 90 * get_weight("rusher", "military")
        boomer_score = 90 * get_weight("boomer", "military")
        assert rusher_score > boomer_score


class TestTrainWarriorGoal:
    def test_zero_without_barracks(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        ctx = _ctx_with(p, buildings=[castle])
        assert TrainWarriorGoal().score(ctx) == 0

    def test_scores_when_barracks_idle(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        barracks = FakeBuilding("barracks", p)
        # Need a house for pop space (1 castle + 1 worker = pop 1, max 5 — fine)
        worker = FakeUnit("worker", p)
        ctx = _ctx_with(p, units=[worker], buildings=[castle, barracks])
        assert TrainWarriorGoal().score(ctx) > 0


# --- Tactical goals -------------------------------------------------------

class TestDefendBaseGoal:
    def test_zero_with_no_threats(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p, x=500, y=500)
        ctx = _ctx_with(p, buildings=[castle])
        assert DefendBaseGoal().score(ctx) == 0

    def test_high_score_with_enemy_at_castle(self):
        p = FakePlayer()
        enemy_player = FakePlayer()
        castle = FakeBuilding("castle", p, x=500, y=500)
        enemy = FakeUnit("warrior", enemy_player, x=520, y=520)
        ctx = _ctx_with(p, units=[enemy], buildings=[castle])
        score = DefendBaseGoal().score(ctx)
        assert score >= 200  # always overrides economy/military

    def test_far_enemy_does_not_trigger(self):
        p = FakePlayer()
        enemy_player = FakePlayer()
        castle = FakeBuilding("castle", p, x=500, y=500)
        # 2000 away — well beyond DEFENSE_RADIUS=300
        enemy = FakeUnit("warrior", enemy_player, x=2500, y=2500)
        ctx = _ctx_with(p, units=[enemy], buildings=[castle])
        assert DefendBaseGoal().score(ctx) == 0


class TestAttackGoal:
    def test_zero_with_small_army(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        military = [FakeUnit("warrior", p) for _ in range(3)]  # below MIN_ARMY=6
        ctx = _ctx_with(p, units=military, buildings=[castle])
        assert AttackGoal().score(ctx) == 0

    def test_scores_with_large_army_and_enemy(self):
        p = FakePlayer()
        enemy = FakePlayer()
        castle = FakeBuilding("castle", p)
        enemy_castle = FakeBuilding("castle", enemy, x=2000, y=2000)
        military = [FakeUnit("warrior", p) for _ in range(8)]
        ctx = _ctx_with(p, units=military, buildings=[castle, enemy_castle])
        score = AttackGoal().score(ctx)
        # 70 + (8-6)*8 = 86
        assert score == 86


# --- Context helpers ------------------------------------------------------

class TestGoalContext:
    def test_pop_max_increases_with_houses(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        houses = [FakeBuilding("house", p) for _ in range(2)]
        ctx = _ctx_with(p, buildings=[castle, *houses])
        assert ctx.pop_max == 5 + 5 * 2

    def test_can_afford_true(self):
        p = FakePlayer()
        ctx = _ctx_with(p, buildings=[FakeBuilding("castle", p)])
        assert ctx.can_afford("farm") is True  # wood 200 >= 75

    def test_can_afford_false(self):
        p = FakePlayer()
        p.resources["wood"] = 0
        ctx = _ctx_with(p, buildings=[FakeBuilding("castle", p)])
        assert ctx.can_afford("farm") is False

    def test_count_units_includes_in_production(self):
        p = FakePlayer()
        castle = FakeBuilding("castle", p)
        castle.current_production = {"unit_type": "worker", "progress": 0.3}
        castle.production_queue = ["worker", "worker"]
        worker = FakeUnit("worker", p)
        ctx = _ctx_with(p, units=[worker], buildings=[castle])
        assert ctx.count_units("worker") == 4  # 1 alive + 1 in progress + 2 queued


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
