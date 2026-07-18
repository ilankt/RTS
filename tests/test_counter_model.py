"""§8.4 counter-model tests: strong_against tags change real damage."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entities.unit import Unit
from systems.combat_rules import calculate_damage, has_bonus_against


def make(name, attack_type, armor_type, strong_against, min_damage=10, max_damage=10):
    return Unit(
        name=name,
        size=[1, 1],
        hp=100,
        movement_speed=100,
        attack=10,
        animations={},
        x=0,
        y=0,
        radius=8,
        player=None,
        can_attack=True,
        min_damage=min_damage,
        max_damage=max_damage,
        attack_type=attack_type,
        armor_type=armor_type,
        strong_against=strong_against,
    )


def test_spearman_counters_cavalry_harder_than_archer():
    # Same pierce attack profile; only the strong_against tag differs.
    spearman = make("spearman", "pierce", "light", ["cavalry"])
    archer = make("archer", "pierce", "light", ["warrior", "spearman"])
    cavalry = make("cavalry", "slash", "heavy", ["archer", "worker"])

    spear_damage = sum(calculate_damage(spearman, cavalry) for _ in range(50))
    archer_damage = sum(calculate_damage(archer, cavalry) for _ in range(50))

    assert has_bonus_against(spearman, cavalry)
    assert not has_bonus_against(archer, cavalry)
    assert spear_damage > archer_damage * 1.3  # distinctly more, not noise


def test_warrior_bonus_vs_ram():
    warrior = make("warrior", "slash", "heavy", ["archer", "ram"])
    ram = make("ram", "siege", "siege", ["building"])
    assert has_bonus_against(warrior, ram)
    assert not has_bonus_against(ram, warrior)


def test_building_token_matches_buildings():
    from entities.building import Building

    ram = make("ram", "siege", "siege", ["building", "castle"])
    barracks = Building(
        name="barracks", size=[2, 2], hp=500, sprite=None, build_duration=10,
        x=0, y=0, radius=32, armor_type="fortified",
    )
    assert has_bonus_against(ram, barracks)


def test_is_resisted_by_flags_type_disadvantage():
    """§8.4 "Resisted!" cue: armor-class resistance or weak_against tags."""
    from types import SimpleNamespace
    from systems.combat_rules import is_resisted_by

    # Pierce into siege armor: 0.45x -> resisted
    archer = SimpleNamespace(attack_type="pierce", weak_against=[])
    ram = SimpleNamespace(name="ram", armor_type="siege")
    assert is_resisted_by(archer, ram)

    # Slash into light armor: 1.35x, no weak tag -> not resisted
    warrior = SimpleNamespace(attack_type="slash", weak_against=[])
    worker = SimpleNamespace(name="worker", armor_type="light")
    assert not is_resisted_by(warrior, worker)

    # weak_against tag flags it even at neutral effectiveness
    spearman = SimpleNamespace(attack_type="pierce", weak_against=["archer"])
    enemy_archer = SimpleNamespace(name="archer", armor_type="light")
    assert is_resisted_by(spearman, enemy_archer)


def test_forest_cover_mechanic_is_gone():
    """§11.1 roster simplification: the forest tile and its cover mechanic
    were removed together (user decision 2026-07-18)."""
    import systems.combat_rules as rules

    assert not hasattr(rules, "terrain_cover_multiplier")
    assert not hasattr(rules, "set_terrain_provider")
