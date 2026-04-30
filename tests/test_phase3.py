import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit
from entities.building import Building
from entities.player import Player


class MockPlayer:
    def __init__(self, human=True, personality="balanced"):
        self.human = human
        self.name = "Test"
        self.color = (255, 255, 255)
        self.resources = {"food": 100, "gold": 200, "stone": 100, "wood": 200}
        self.ai_personality = personality


class MockGame:
    def __init__(self):
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = []
        self.game_map = None
        self.game_data = {"costs": {}, "units": {}, "buildings": {}}


# ---------------------------------------------------------------------------
# AI Personality Tests
# ---------------------------------------------------------------------------
class TestAIPersonalities:
    def test_rusher_personality_params(self):
        from systems.ai.simple_ai import SimpleAISystem
        game = MockGame()
        player = MockPlayer(human=False, personality="rusher")
        game.players = [player]
        ai = SimpleAISystem(game)
        params = ai.personality_params[player]
        assert params["attack_transition_threshold"] == 4
        assert params["target_workers"] == 4
        assert params["econ_focus"] is False
    
    def test_boomer_personality_params(self):
        from systems.ai.simple_ai import SimpleAISystem
        game = MockGame()
        player = MockPlayer(human=False, personality="boomer")
        game.players = [player]
        ai = SimpleAISystem(game)
        params = ai.personality_params[player]
        assert params["attack_transition_threshold"] == 8
        assert params["target_workers"] == 8
        assert params["econ_focus"] is True
    
    def test_turtle_personality_params(self):
        from systems.ai.simple_ai import SimpleAISystem
        game = MockGame()
        player = MockPlayer(human=False, personality="turtle")
        game.players = [player]
        ai = SimpleAISystem(game)
        params = ai.personality_params[player]
        assert params["attack_transition_threshold"] == 10
        assert params["retreat_threshold"] == 0.40
    
    def test_default_personality_is_balanced(self):
        from systems.ai.simple_ai import SimpleAISystem
        game = MockGame()
        player = MockPlayer(human=False, personality="balanced")
        game.players = [player]
        ai = SimpleAISystem(game)
        params = ai.personality_params[player]
        assert params["attack_transition_threshold"] == 6
        assert params["target_workers"] == 6


# ---------------------------------------------------------------------------
# Military Micro Tests
# ---------------------------------------------------------------------------
class TestMilitaryMicro:
    def test_retreat_threshold_default(self):
        from systems.ai.military_brain import MilitaryBrain
        game = MockGame()
        brain = MilitaryBrain(game)
        assert brain.RETREAT_HP_PERCENT == 0.30
    
    def test_should_retreat_low_hp(self):
        from systems.ai.military_brain import MilitaryBrain
        game = MockGame()
        brain = MilitaryBrain(game)
        unit = Unit("warrior", [1,1], 250, 50, 10, {}, radius=10, can_attack=True)
        unit.hp = 50  # 20% of 250
        assert brain._should_retreat(unit, 250) is True
    
    def test_should_not_retreat_high_hp(self):
        from systems.ai.military_brain import MilitaryBrain
        game = MockGame()
        brain = MilitaryBrain(game)
        unit = Unit("warrior", [1,1], 250, 50, 10, {}, radius=10, can_attack=True)
        unit.hp = 200  # 80% of 250
        assert brain._should_retreat(unit, 250) is False
    
    def test_archer_kite_distance_set(self):
        from systems.ai.military_brain import MilitaryBrain
        game = MockGame()
        brain = MilitaryBrain(game)
        assert brain.ARCHER_KITE_DISTANCE == 80


# ---------------------------------------------------------------------------
# Scout Brain Tests
# ---------------------------------------------------------------------------
class TestScoutBrain:
    def test_scout_brain_initializes(self):
        from systems.ai.scout_brain import ScoutBrain
        game = MockGame()
        brain = ScoutBrain(game)
        assert brain is not None
    
    def test_explored_tiles_empty_initially(self):
        from systems.ai.scout_brain import ScoutBrain
        game = MockGame()
        brain = ScoutBrain(game)
        player = MockPlayer()
        assert player not in brain.explored_tiles
    
    def test_is_idle_detects_idle_unit(self):
        from systems.ai.scout_brain import ScoutBrain
        game = MockGame()
        brain = ScoutBrain(game)
        unit = Unit("worker", [1,1], 100, 40, 0, {}, radius=10)
        unit.status = "idle"
        assert brain._is_idle(unit) is True
    
    def test_is_idle_detects_busy_unit(self):
        from systems.ai.scout_brain import ScoutBrain
        game = MockGame()
        brain = ScoutBrain(game)
        unit = Unit("worker", [1,1], 100, 40, 0, {}, radius=10)
        unit.status = "run"
        unit.destination = (100, 100)
        assert brain._is_idle(unit) is False


# ---------------------------------------------------------------------------
# Integration: Player gets personality at creation
# ---------------------------------------------------------------------------
class TestPlayerPersonalityIntegration:
    def test_player_has_personality_attribute(self):
        p = Player("AI", human=False)
        assert hasattr(p, 'ai_personality')
        assert p.ai_personality == "balanced"
    
    def test_human_player_has_personality_too(self):
        p = Player("Human", human=True)
        assert hasattr(p, 'ai_personality')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
