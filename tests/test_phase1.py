import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit, STANCE_AGGRESSIVE, STANCE_DEFENSIVE, STANCE_STAND_GROUND, STANCE_NO_ATTACK
from managers.selection_manager import SelectionManager


class MockPlayer:
    def __init__(self, human=True):
        self.human = human
        self.name = "Test"
        self.color = (255, 255, 255)
        self.resources = {"food": 100, "gold": 200, "wood": 200}


class MockGame:
    def __init__(self):
        self.units = []
        self.buildings = []
        self.resources = []
        self.construction_sites = []
        self.players = [MockPlayer(human=True), MockPlayer(human=False)]


# ---------------------------------------------------------------------------
# Unit Stance Tests
# ---------------------------------------------------------------------------
class TestUnitStances:
    def test_default_stance_is_aggressive(self):
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True)
        assert unit.stance == STANCE_AGGRESSIVE
    
    def test_stance_can_be_changed(self):
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True)
        unit.stance = STANCE_DEFENSIVE
        assert unit.stance == STANCE_DEFENSIVE
        
        unit.stance = STANCE_STAND_GROUND
        assert unit.stance == STANCE_STAND_GROUND
        
        unit.stance = STANCE_NO_ATTACK
        assert unit.stance == STANCE_NO_ATTACK
    
    def test_stance_home_position_defaults_none(self):
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True)
        assert unit.stance_home_position is None
    
    def test_stance_chase_distance_exists(self):
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True)
        assert unit.stance_chase_distance > 0


# ---------------------------------------------------------------------------
# Control Group Tests
# ---------------------------------------------------------------------------
class TestControlGroups:
    def test_control_groups_initialized_empty(self):
        game = MockGame()
        sm = SelectionManager(game)
        for i in range(1, 10):
            assert sm.control_groups[i] == []
    
    def test_set_control_group(self):
        game = MockGame()
        sm = SelectionManager(game)
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True, player=game.players[0])
        game.units.append(unit)
        sm.selected_objects = [unit]
        
        sm.set_control_group(1)
        assert len(sm.control_groups[1]) == 1
        assert sm.control_groups[1][0] == unit
    
    def test_recall_control_group(self):
        game = MockGame()
        sm = SelectionManager(game)
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True, player=game.players[0])
        game.units.append(unit)
        sm.control_groups[1] = [unit]
        
        result = sm.recall_control_group(1)
        assert result is True
        assert unit in sm.selected_objects
        assert unit.selected is True
    
    def test_recall_empty_group_returns_false(self):
        game = MockGame()
        sm = SelectionManager(game)
        result = sm.recall_control_group(1)
        assert result is False
    
    def test_add_to_control_group(self):
        game = MockGame()
        sm = SelectionManager(game)
        unit1 = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True, player=game.players[0])
        unit2 = Unit("archer", [1,1], 80, 60, 7, {}, radius=10, can_attack=True, player=game.players[0])
        game.units.extend([unit1, unit2])
        
        sm.selected_objects = [unit1]
        sm.set_control_group(1)
        
        sm.selected_objects = [unit2]
        sm.set_control_group(1, add=True)
        
        assert len(sm.control_groups[1]) == 2
        assert unit1 in sm.control_groups[1]
        assert unit2 in sm.control_groups[1]
    
    def test_recall_filters_dead_units(self):
        game = MockGame()
        sm = SelectionManager(game)
        unit = Unit("warrior", [1,1], 100, 50, 10, {}, radius=10, can_attack=True, player=game.players[0])
        game.units.append(unit)
        sm.control_groups[1] = [unit]
        
        # Kill the unit
        unit.hp = 0
        result = sm.recall_control_group(1)
        assert result is False
        assert sm.control_groups[1] == []


# ---------------------------------------------------------------------------
# Formation Tests
# ---------------------------------------------------------------------------
class TestFormations:
    def test_ring_formation_center_first(self):
        game = MockGame()
        sm = SelectionManager(game)
        offsets = sm._generate_ring_formation(5, 22)
        assert offsets[0] == (0, 0)
        assert len(offsets) == 5
    
    def test_line_formation_horizontal(self):
        game = MockGame()
        sm = SelectionManager(game)
        offsets = sm._generate_line_formation(5, 22)
        assert offsets[0][1] == 0  # All y = 0
        assert offsets[-1][1] == 0
        assert len(offsets) == 5
    
    def test_box_formation_grid(self):
        game = MockGame()
        sm = SelectionManager(game)
        offsets = sm._generate_box_formation(9, 22)
        # 9 units -> 3x3 grid
        assert len(offsets) == 9
    
    def test_wedge_formation_tip_first(self):
        game = MockGame()
        sm = SelectionManager(game)
        offsets = sm._generate_wedge_formation(5, 22)
        assert offsets[0] == (0, 0)  # Tip at origin
        assert len(offsets) == 5
    
    def test_cycle_formation(self):
        game = MockGame()
        sm = SelectionManager(game)
        assert sm.formation_type == "ring"
        
        sm.cycle_formation()
        assert sm.formation_type == "line"
        
        sm.cycle_formation()
        assert sm.formation_type == "box"
        
        sm.cycle_formation()
        assert sm.formation_type == "wedge"
        
        sm.cycle_formation()
        assert sm.formation_type == "ring"


# ---------------------------------------------------------------------------
# Save Manager Tests (without pygame dependency)
# ---------------------------------------------------------------------------
class TestSaveManager:
    def test_ensure_save_dir(self):
        from managers.save_manager import SaveManager
        SaveManager.ensure_save_dir()
        assert os.path.exists("saves")
    
    def test_list_saves_empty(self):
        from managers.save_manager import SaveManager
        SaveManager.ensure_save_dir()
        saves = SaveManager.list_saves()
        # Should not crash even with no saves
        assert isinstance(saves, list)


# ---------------------------------------------------------------------------
# Victory/Defeat Logic Tests
# ---------------------------------------------------------------------------
class TestVictoryDefeat:
    def test_human_no_castle_is_defeat(self):
        game = MockGame()
        # No buildings at all
        from entities import Building
        # Only AI has a castle
        ai_castle = Building("castle", [2.5,2.5], 5000, None, 50, radius=80, player=game.players[1])
        game.buildings.append(ai_castle)
        
        # Simulate check
        castles_by_player = {}
        for building in game.buildings:
            if building.name == "castle":
                castles_by_player[building.player] = castles_by_player.get(building.player, 0) + 1
        
        human_player = game.players[0]
        assert castles_by_player.get(human_player, 0) == 0
    
    def test_all_ai_no_castle_is_victory(self):
        game = MockGame()
        from entities import Building
        # Only human has a castle
        human_castle = Building("castle", [2.5,2.5], 5000, None, 50, radius=80, player=game.players[0])
        game.buildings.append(human_castle)
        
        ai_players = [p for p in game.players if not p.human]
        castles_by_player = {}
        for building in game.buildings:
            if building.name == "castle":
                castles_by_player[building.player] = castles_by_player.get(building.player, 0) + 1
        
        all_ai_defeated = all(castles_by_player.get(p, 0) == 0 for p in ai_players)
        assert all_ai_defeated is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
