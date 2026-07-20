"""§8.17.2: construction sites are targets (foundation-spam is answerable)
and site hp scales with construction progress."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from entities.construction_site import ConstructionSite
from entities.unit import Unit
from systems.ai.utility.context import GoalContext


@pytest.fixture(scope="module")
def game():
    random.seed(8817)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def make_site(game, player, name="house", x=800.0, y=800.0):
    data = {"size": [1, 1], "hp": game.game_data["buildings"][name].hp,
            "build_duration": game.game_data["buildings"][name].build_duration}
    site = ConstructionSite(name, data, x, y, radius=32, player=player)
    game.construction_sites.append(site)
    game.pathfinder.notify_blocker_added(site)
    game.collision_system.invalidate_static_index()
    return site


def remove_site(game, site):
    site.in_world = False
    if site in game.construction_sites:
        game.construction_sites.remove(site)
    game.pathfinder.notify_blocker_removed(site)
    game.collision_system.invalidate_static_index()


def spawn(game, player, name, x, y):
    unit = Unit(name=name, size=[1, 1], hp=250, movement_speed=50, attack=10,
                animations={}, x=x, y=y, radius=16, player=player,
                min_damage=18, max_damage=22, attack_speed=1.2, attack_range=48,
                can_attack=True)
    game.units.append(unit)
    return unit


def test_units_acquire_enemy_foundations(game):
    """The exploit's core: idle units must auto-acquire an enemy site."""
    human, ai = game.players[0], game.players[1]
    site = make_site(game, human, x=900, y=900)
    warrior = spawn(game, ai, "warrior", 950, 900)
    try:
        targets = game.combat_system.evaluate_combat_targets(warrior)
        assert any(t is site for t, _d in targets), \
            "enemy construction site must appear in acquisition targets"
    finally:
        remove_site(game, site)
        game.units.remove(warrior)
        warrior.in_world = False


def test_blackboard_sees_enemy_sites_and_defense_radius_counts_them(game):
    human, ai = game.players[1], game.players[0]  # ai player's view of human site
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    near = make_site(game, ai, x=castle.x + 150, y=castle.y)  # enemy site AT the base
    # The fixture game never ticks, so fog exploration grids are empty —
    # disable fog for the snapshot (the explored-gate reuses the proven
    # enemy_buildings pattern; this test owns the list membership).
    fog_was = getattr(game, "fog_of_war_enabled", True)
    game.fog_of_war_enabled = False
    try:
        ctx = GoalContext.build(game, human)
        assert near in ctx.enemy_construction_sites, \
            "enemy foundations must be on the blackboard"
        assert near not in ctx.construction_sites, "not one of OURS"
        assert near in ctx.enemies_near_base, \
            "a foundation planted in the defense radius is a threat"
    finally:
        game.fog_of_war_enabled = fog_was
        remove_site(game, near)


def test_attack_target_falls_back_to_sites(game):
    ai = game.players[1]
    brain = game.ai_system.military_brain
    site = make_site(game, game.players[0], x=1200, y=1200)
    try:
        ctx = GoalContext.build(game, ai)
        ctx.enemy_buildings = []          # nothing else known
        ctx.enemy_units = []
        ctx.enemy_construction_sites = [site]
        target = brain._find_attack_target(ctx)
        assert target is site, "a base reduced to foundations is still a target"
    finally:
        remove_site(game, site)


def test_site_hp_scales_with_progress_and_preserves_damage(game):
    human = game.players[0]
    site = make_site(game, human, name="castle", x=1400, y=1400)
    try:
        final_hp = game.game_data["buildings"]["castle"].hp
        assert site.hp == ConstructionSite.SITE_BASE_HP     # fresh = cheap to deny
        assert site.max_hp == ConstructionSite.SITE_BASE_HP

        # Half built: max is halfway between base and final; undamaged site
        # tracks its max exactly
        site.construction_progress = site.construction_duration / 2
        site.apply_progress_hp_growth()
        expected_mid = int(ConstructionSite.SITE_BASE_HP
                           + (final_hp - ConstructionSite.SITE_BASE_HP) * 0.5)
        assert site.max_hp == expected_mid
        assert site.hp == expected_mid

        # Take 100 damage, then finish building: the damage stays absolute
        site.hp -= 100
        site.construction_progress = site.construction_duration
        site.apply_progress_hp_growth()
        assert site.max_hp == final_hp
        assert site.hp == final_hp - 100, "building more must not heal damage"
    finally:
        remove_site(game, site)


def test_save_load_clamps_legacy_flat_site_hp(tmp_path):
    """A pre-8.17.2 save carries flat hp=100 sites; on load the max is
    recomputed from progress and hp clamps into the new range."""
    import json

    from managers.save_manager import SaveManager

    SaveManager.SAVE_DIR = str(tmp_path)
    random.seed(8818)
    from core.game import Game

    fresh = Game(mode="human_1v1", player_count=2)
    human = fresh.players[0]
    site = make_site(fresh, human, name="house", x=700, y=700)  # house final hp 500
    site.construction_progress = 0.0
    SaveManager.save_game(fresh, slot=6)

    path = os.path.join(str(tmp_path), "save_6.json")
    with open(path) as fh:
        state = json.load(fh)
    for cdata in state["construction_sites"]:
        cdata["hp"] = 100          # the old flat model
    with open(path, "w") as fh:
        json.dump(state, fh)

    ok, message = SaveManager.load_game(fresh, slot=6)
    assert ok, message
    loaded = next(s for s in fresh.construction_sites if s.building_name == "house")
    assert loaded.max_hp == ConstructionSite.SITE_BASE_HP
    assert loaded.hp == ConstructionSite.SITE_BASE_HP, \
        "legacy flat-100 hp must clamp to the progress-scaled max"
