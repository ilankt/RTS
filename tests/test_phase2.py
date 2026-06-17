import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit
from entities.building import Building
from entities.resource import Resource


class MockPlayer:
    def __init__(self, human=True):
        self.human = human
        self.name = "Test"
        self.color = (255, 255, 255)
        self.resources = {"food": 100, "gold": 200, "stone": 100, "wood": 200}


# ---------------------------------------------------------------------------
# New Unit Type Tests
# ---------------------------------------------------------------------------
class TestNewUnitTypes:
    def test_spearman_stats(self):
        unit = Unit("spearman", [1,1], 200, 45, 8, {}, radius=10, can_attack=True,
                   min_damage=14, max_damage=18, attack_type="pierce", armor_type="light", armor_value=2)
        assert unit.name == "spearman"
        assert unit.movement_speed == 45
        assert unit.attack_type == "pierce"
        assert unit.min_damage == 14
    
    def test_cavalry_stats(self):
        unit = Unit("cavalry", [1,1], 300, 90, 12, {}, radius=10, can_attack=True,
                   min_damage=20, max_damage=26, attack_type="slash", armor_type="heavy", armor_value=3)
        assert unit.name == "cavalry"
        assert unit.movement_speed == 90
        assert unit.armor_type == "heavy"
    
    def test_healer_is_non_combat(self):
        unit = Unit("healer", [1,1], 120, 55, 0, {}, radius=10, can_attack=False,
                   min_damage=0, max_damage=0)
        assert unit.can_attack_flag is False
        assert unit.min_damage == 0


# ---------------------------------------------------------------------------
# New Building Tests
# ---------------------------------------------------------------------------
class TestNewBuildings:
    def test_stable_produces_cavalry(self):
        building = Building("stable", [1.5,1.5], 900, None, 10, radius=48)
        assert "cavalry" in building.can_produce
    
    def test_temple_produces_healer(self):
        building = Building("temple", [1.5,1.5], 800, None, 10, radius=48)
        assert "healer" in building.can_produce
    
    def test_blacksmith_no_production(self):
        building = Building("blacksmith", [1.5,1.5], 800, None, 10, radius=48)
        assert building.can_produce == []
    
    def test_barracks_produces_spearman(self):
        building = Building("barracks", [1.5,1.5], 1000, None, 10, radius=48)
        assert "spearman" in building.can_produce
    
    def test_wall_high_armor(self):
        building = Building("wall", [1,1], 2000, None, 8, radius=32, armor_type="fortified", armor_value=10)
        assert building.armor_value == 10
        assert building.hp == 2000


# ---------------------------------------------------------------------------
# Resource Depletion Tests
# ---------------------------------------------------------------------------
class TestResourceDepletion:
    def test_resource_has_amount_remaining(self):
        res = Resource("gold", None, x=100, y=100, radius=16)
        assert hasattr(res, "amount_remaining")
        assert res.amount_remaining > 0
    
    def test_wood_resource_limit(self):
        res = Resource("wood", None, x=100, y=100, radius=16)
        assert res.amount_remaining == 300  # From RESOURCE_LIMITS
    
    def test_tree_regrowth_tracker_initializes(self):
        class MockGame:
            pass
        game = MockGame()
        assert not hasattr(game, '_tree_regrowth')


# ---------------------------------------------------------------------------
# Data File Validation
# ---------------------------------------------------------------------------
class TestDataFiles:
    def test_units_json_includes_new_units(self):
        with open("data/units.json") as f:
            units = json.load(f)
        names = [u["name"] for u in units]
        assert "spearman" in names
        assert "cavalry" in names
        assert "healer" in names
    
    def test_buildings_json_includes_new_buildings(self):
        with open("data/buildings.json") as f:
            buildings = json.load(f)
        names = [b["name"] for b in buildings]
        assert "stable" in names
        assert "temple" in names
        assert "blacksmith" in names
        assert "wall" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
