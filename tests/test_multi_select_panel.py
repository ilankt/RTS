"""Multi-select panel (§8.2): mixed selections group by type with counts."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(4321)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def test_selection_groups_by_type_largest_first(game):
    panel = game.ui_manager.unit_panel
    all_units = list(game.units)
    assert all_units

    selection = all_units + ["not-a-unit", game.buildings[0]]
    groups = panel.group_selected_units(selection)

    sizes = [len(units) for _name, units in groups]
    assert sizes == sorted(sizes, reverse=True)       # biggest group first
    assert sum(sizes) == len(all_units)               # non-units dropped
    for name, units in groups:
        assert all(u.name == name for u in units)     # grouped by type


def test_draw_multi_selection_smoke(game):
    panel = game.ui_manager.unit_panel
    human = game.players[0]
    units = [u for u in game.units if u.player is human]
    surface = pygame.Surface((220, 500))
    panel._draw_multi_selection(surface, units)  # must not raise


def test_building_header_uses_unit_style_glyph_rows(game):
    """§8.17.1 (user decision 2026-07-20): a selected watchtower reads like a
    unit — glyph rows for attack/speed/armor/range; non-attacking buildings
    show the armor-only glyph row, not the old text label soup."""
    from entities.building import Building

    panel = game.ui_manager.unit_panel
    human = game.players[0]
    template = game.game_data["buildings"]["watchtower"]
    tower = Building(
        name="watchtower", size=template.size, hp=template.hp, sprite=template.sprite,
        build_duration=template.build_duration, x=500, y=500, radius=template.radius,
        player=human, armor_type=template.armor_type, armor_value=template.armor_value,
        can_attack=True, min_damage=template.min_damage, max_damage=template.max_damage,
        attack_type=template.attack_type, attack_speed=template.attack_speed,
        attack_range=template.attack_range)

    info = {"object": tower, "type": "Building", "name": "Watchtower",
            "owner": human.name, "player_color": human.color}
    _icon, hp, lines = panel._single_selection_model(info)
    assert hp is not None
    glyphs = [line[0][0] for line in lines if isinstance(line, list)]
    assert glyphs == ["attack", "speed", "armor", "range"], glyphs

    farm_template = game.game_data["buildings"]["farm"]
    farm = Building(
        name="farm", size=farm_template.size, hp=farm_template.hp,
        sprite=farm_template.sprite, build_duration=farm_template.build_duration,
        x=600, y=500, radius=farm_template.radius, player=human,
        armor_type=farm_template.armor_type, armor_value=farm_template.armor_value)
    info = {"object": farm, "type": "Building", "name": "Farm",
            "owner": human.name, "player_color": human.color}
    _icon, _hp, lines = panel._single_selection_model(info)
    glyphs = [line[0][0] for line in lines if isinstance(line, list)]
    assert glyphs == ["armor"], "non-attacking buildings show the armor-only row"
