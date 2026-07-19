import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities import Building, ConstructionSite, load_game_data
from managers.save_manager import SaveManager
from ui.components.command_card import CommandCard


def _building_from_template(template, player):
    return Building(
        name=template.name,
        size=template.size,
        hp=template.hp,
        sprite=template.sprite,
        build_duration=template.build_duration,
        radius=template.radius,
        player=player,
        costs=template.costs,
        armor_type=template.armor_type,
        armor_value=template.armor_value,
        can_attack=template.can_attack,
        min_damage=template.min_damage,
        max_damage=template.max_damage,
        attack_type=template.attack_type,
        attack_speed=template.attack_speed,
        attack_range=template.attack_range,
    )


def _building_data_from_template(template):
    return {
        "name": template.name,
        "size": template.size,
        "hp": template.hp,
        "sprite": template.sprite,
        "build_duration": template.build_duration,
        "costs": template.costs,
        "armor_type": template.armor_type,
        "armor_value": template.armor_value,
        "can_attack": template.can_attack,
        "min_damage": template.min_damage,
        "max_damage": template.max_damage,
        "attack_type": template.attack_type,
        "attack_speed": template.attack_speed,
        "attack_range": template.attack_range,
    }


class FakePathfinder:
    def __init__(self):
        self.dirty = False

    def mark_dirty(self):
        self.dirty = True


class FakeGame:
    def __init__(self):
        self.players = [
            SimpleNamespace(
                name="Human",
                human=True,
                color=(255, 255, 255),
                resources={"food": 100, "gold": 200, "wood": 200},
            ),
            SimpleNamespace(
                name="AI",
                human=False,
                color=(255, 0, 0),
                resources={"food": 100, "gold": 200, "wood": 200},
            ),
        ]
        self.game_data = load_game_data()
        self.buildings = []
        self.units = []
        self.resources = []
        self.construction_sites = []
        self.selection_manager = SimpleNamespace(selected_objects=[])
        self.pathfinder = FakePathfinder()
        self.camera = SimpleNamespace(x=0, y=0, zoom=1.0)
        self.game_speed = 1.0


def test_build_menu_uses_nested_costs_for_watchtower_affordability():
    player = SimpleNamespace(resources={"gold": 999, "wood": 149})
    building = {"name": "watchtower", "costs": {"gold": 150, "wood": 150}}

    assert CommandCard._can_afford(player, building) is False
    assert CommandCard._format_costs(building) == "Gold: 150, Wood: 150"

    player.resources["wood"] = 150
    assert CommandCard._can_afford(player, building) is True


def test_watchtower_load_preserves_combat_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(SaveManager, "SAVE_DIR", str(tmp_path))
    game = FakeGame()
    template = game.game_data["buildings"]["watchtower"]
    tower = _building_from_template(template, game.players[0])
    tower.x = 120
    tower.y = 140
    game.buildings.append(tower)

    SaveManager.save_game(game, slot=7)
    game.buildings.clear()

    success, _ = SaveManager.load_game(game, slot=7)

    assert success is True
    loaded_tower = game.buildings[0]
    assert loaded_tower.can_attack is True
    assert loaded_tower.min_damage == 14
    assert loaded_tower.max_damage == 18
    assert loaded_tower.attack_type == "pierce"
    assert loaded_tower.attack_speed == 1.5
    # Towers out-range archers INCLUDING the radius-reach math (reach =
    # range + target radius, so the archer gets the tower's fat radius for
    # free): 255 + 16 > 200 + 64, fletching cancels — a lone archer must
    # never plink a tower down for free (user-reported twice, 2026-07-14)
    assert loaded_tower.attack_range == 255


def test_tower_out_reaches_a_plinking_archer():
    """The actual duel (user-reported twice): an archer standing at ITS
    maximum reach against the tower (archer range + the tower's fat radius)
    must be inside the tower's reach too — reach math is radius-aware on
    both sides now."""
    from types import SimpleNamespace
    from entities.unit import Unit
    from entities.building import Building

    p1 = SimpleNamespace(name="P1", human=False, upgrades={}, upgrades_version=0)
    p2 = SimpleNamespace(name="P2", human=False, upgrades={}, upgrades_version=0)
    tower = Building(name="watchtower", size=[2, 2], hp=1500, sprite=None,
                     build_duration=15, x=0, y=0, radius=64, player=p1,
                     can_attack=True, min_damage=14, max_damage=18,
                     attack_speed=1.5, attack_range=255)
    archer = Unit(name="archer", size=[1, 1], hp=150, movement_speed=60,
                  attack=7, animations={}, x=0, y=0, radius=16, player=p2,
                  min_damage=12, max_damage=16, attack_speed=1.0,
                  attack_range=200, can_attack=True)

    # Place the archer at its maximum plink distance from the tower
    max_plink = archer.attack_range + tower.radius
    archer.x = max_plink
    assert archer.can_attack(tower), "sanity: archer is at its own max reach"
    assert tower.can_attack_target(archer), \
        "the tower must reach a max-range plinking archer"


def test_watchtower_construction_load_preserves_future_combat_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(SaveManager, "SAVE_DIR", str(tmp_path))
    game = FakeGame()
    template = game.game_data["buildings"]["watchtower"]
    site = ConstructionSite(
        "watchtower",
        _building_data_from_template(template),
        x=200,
        y=220,
        radius=template.radius,
        player=game.players[0],
    )
    game.construction_sites.append(site)

    SaveManager.save_game(game, slot=8)
    game.construction_sites.clear()

    success, _ = SaveManager.load_game(game, slot=8)

    assert success is True
    loaded_site = game.construction_sites[0]
    assert loaded_site.building_data["can_attack"] is True
    assert loaded_site.building_data["min_damage"] == 14
    assert loaded_site.building_data["max_damage"] == 18
    assert loaded_site.building_data["attack_type"] == "pierce"
    assert loaded_site.building_data["attack_speed"] == 1.5
    assert loaded_site.building_data["attack_range"] == 255
