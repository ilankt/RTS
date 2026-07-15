"""Attacking a construction site (user-reported crash).

`calculate_damage` -> `effective_armor_value` -> `effective_stat` did a hard
`getattr(target, "armor_value")`, which ConstructionSite never defined, so
any attack on an enemy foundation killed the match with an AttributeError.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.construction_site import ConstructionSite
from entities.unit import Unit


@pytest.fixture(scope="module")
def game():
    random.seed(4242)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def _site(game, player, x=1200, y=1200):
    template = game.game_data["buildings"]["barracks"]
    data = {
        "size": template.size,
        "build_duration": template.build_duration,
        "costs": dict(template.costs),
    }
    return ConstructionSite("barracks", data, x, y, radius=40, player=player)


def _warrior(game, player, x, y):
    return Unit(name="warrior", size=[1, 1], hp=250, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_type="slash",
                armor_type="heavy", armor_value=4, attack_speed=1.2,
                attack_range=48, can_attack=True)


def test_site_has_combat_attributes():
    from core.game import Game

    site = ConstructionSite("barracks", {"size": [1.5, 1.5], "build_duration": 10},
                            0, 0, radius=40)
    assert hasattr(site, "armor_value") and site.armor_value == 0
    assert site.armor_type == "light"


def test_attacking_a_construction_site_does_not_crash(game):
    """The exact traceback path: unit.calculate_damage(construction_site)."""
    human, enemy = game.players[0], game.players[1]
    site = _site(game, enemy)
    attacker = _warrior(game, human, site.x + 30, site.y)

    damage = attacker.calculate_damage(site)  # used to raise AttributeError
    assert damage >= 1


def test_full_combat_tick_against_a_site(game):
    """Drive the real loop (the crash came from
    check_for_attacks_and_spawn_projectiles)."""
    human, enemy = game.players[0], game.players[1]
    site = _site(game, enemy, x=1400, y=1400)
    game.construction_sites.append(site)
    archer = Unit(name="archer", size=[1, 1], hp=150, movement_speed=60, attack=7,
                  animations={}, x=site.x + 60, y=site.y, radius=16, player=human,
                  min_damage=12, max_damage=16, attack_type="pierce",
                  armor_type="light", armor_value=1, attack_speed=1.0,
                  attack_range=200, can_attack=True)
    game.units.append(archer)
    archer.current_target = site
    archer.is_engaging = True
    try:
        before = site.hp
        for _ in range(120):
            game.combat_system.update_combat_units(1 / 60)
        assert site.hp < before, "the foundation should actually take damage"
    finally:
        if archer in game.units:
            game.units.remove(archer)
        if site in game.construction_sites:
            game.construction_sites.remove(site)


def test_razed_site_releases_its_attackers(game):
    """Destroying a foundation must clear it from attackers, or they chase a
    removed object forever."""
    human, enemy = game.players[0], game.players[1]
    site = _site(game, enemy, x=1600, y=1600)
    game.construction_sites.append(site)
    attacker = _warrior(game, human, site.x + 30, site.y)
    game.units.append(attacker)
    attacker.current_target = site
    attacker.in_combat = True
    attacker.status = "attack"
    try:
        site.hp = 0
        game._cleanup_destroyed_objects()
        assert site not in game.construction_sites
        assert attacker.current_target is None
        assert attacker.in_combat is False and attacker.is_engaging is False
        assert attacker.status == "idle"
    finally:
        if attacker in game.units:
            game.units.remove(attacker)


def test_armor_value_defaults_for_targets_without_armor():
    """The safety net: no target may ever crash the damage path again."""
    from types import SimpleNamespace

    from systems.combat_rules import effective_armor_value

    assert effective_armor_value(SimpleNamespace(name="scenery")) == 0


def test_fountain_is_never_a_valid_target(game):
    from systems.combat_rules import is_valid_attack_target

    attacker = _warrior(game, game.players[0], 100, 100)
    fountain = game.fountains[0]
    assert is_valid_attack_target(attacker, fountain) is False
