"""Unified sidebar command card (§8.2.1 Phase A).

The headline fix: selecting a worker immediately shows the build grid with
always-visible Economy/Military tab chips — no two-level drill-down, no Back
button. Plus position-mapped grid hotkeys (Q W / A S / Z X / C V), card
content per selection type, and camera-pan key suppression.
"""
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


@pytest.fixture()
def card(game):
    """Fresh card state per test on the shared game."""
    card = game.ui_manager.command_card
    card.active_tab = 'economy'
    clear_selection(game)
    game.building_system.cancel_building_placement()
    for resource in game.players[0].resources:
        game.players[0].resources[resource] = 10000
    yield card
    clear_selection(game)
    game.building_system.cancel_building_placement()


def clear_selection(game):
    for obj in game.units + game.buildings + game.resources + game.construction_sites:
        obj.selected = False
    game.selection_manager.selected_objects = []


def select(game, *objects):
    clear_selection(game)
    for obj in objects:
        obj.selected = True
    game.selection_manager.selected_objects = list(objects)


def key(name):
    return pygame.key.key_code(name)


def own_worker(game):
    human = game.players[0]
    return next(u for u in game.units if u.player is human and u.name == "worker")


def own_castle(game):
    human = game.players[0]
    return next(b for b in game.buildings if b.player is human and b.name == "castle")


def spawn_own_unit(game, unit_type, x, y):
    from entities import Unit

    data = game.production_manager.units_data[unit_type]
    unit = Unit(
        name=unit_type, size=data['size'], hp=data['hp'],
        movement_speed=data['movement_speed'], attack=data.get('attack'),
        animations={}, x=x, y=y, radius=8, player=game.players[0],
        can_build=data.get('can_build', False),
        can_attack=data.get('can_attack', False),
        min_damage=data.get('min_damage', 0),
        max_damage=data.get('max_damage', 0),
        attack_type=data.get('attack_type', 'slash'),
        armor_type=data.get('armor_type', 'light'),
        armor_value=data.get('armor_value', 0),
    )
    game.units.append(unit)
    return unit


def build_own_building(game, name, x, y):
    from entities import Building

    template = game.game_data["buildings"][name]
    building = Building(
        name=template.name, size=template.size, hp=template.hp,
        sprite=template.sprite, build_duration=template.build_duration,
        radius=template.radius, player=game.players[0], costs=template.costs,
    )
    building.x, building.y = x, y
    game.buildings.append(building)
    return building


# --------------------------------------------------------------------- #
# the headline: build card with tabs, no drill-down                      #
# --------------------------------------------------------------------- #

def test_worker_selection_shows_build_grid_immediately(game, card):
    select(game, own_worker(game))
    content = card.refresh()

    assert content['context'] == 'build'
    assert [tab for tab, _ in content['chips']] == ['economy', 'military']
    names = [slot['name'] for slot in content['slots'] if slot]
    assert names == ['farm', 'house', 'lumbermill', 'mine', 'market', 'castle']
    assert content['slots'][7] is None  # economy leaves the last slot empty


def test_tab_swap_hotkey_and_memory(game, card):
    select(game, own_worker(game))
    card.refresh()

    assert card.handle_hotkey(key("tab")) is True  # Tab swaps the build tabs
    content = card.refresh()
    names = [slot['name'] for slot in content['slots'] if slot]
    # wall/wooden_wall/gate are deferred (buildable:false in data) so the menu
    # skips them — see MASTER_PLAN §8.10. Re-add here when walls ship.
    # temple enabled 2026-07-17 (builds the healer).
    assert names == ['barracks', 'stable', 'blacksmith', 'siege_workshop',
                     'temple', 'watchtower']

    # Remembered while the worker stays selected (and across reselection)
    clear_selection(game)
    select(game, own_worker(game))
    assert card.refresh()['context'] == 'build'
    assert card.active_tab == 'military'


def test_slot_hotkey_enters_placement_mode(game, card):
    select(game, own_worker(game))
    card.refresh()

    assert card.handle_hotkey(key("q")) is True  # slot 0 = farm
    assert game.building_system.building_placement_mode
    assert game.building_system.building_to_place['name'] == 'farm'


def test_unaffordable_tile_consumes_key_without_acting(game, card):
    human = game.players[0]
    for resource in human.resources:
        human.resources[resource] = 0
    select(game, own_worker(game))
    card.refresh()

    assert card.handle_hotkey(key("q")) is True  # consumed: error feedback
    assert not game.building_system.building_placement_mode
    for resource in human.resources:
        human.resources[resource] = 10000


def test_locked_building_shows_requirement(game, card):
    select(game, own_worker(game))
    card.active_tab = 'military'
    content = card.refresh()
    stable = next(s for s in content['slots'] if s and s['name'] == 'stable')
    assert not stable['enabled']
    assert stable['reason'].startswith("Requires")


# --------------------------------------------------------------------- #
# production / research cards                                            #
# --------------------------------------------------------------------- #

def test_castle_card_produces_on_hotkey(game, card):
    human = game.players[0]
    castle = own_castle(game)
    select(game, castle)
    content = card.refresh()

    assert content['context'] == 'production'
    assert content['slots'][0]['unit_type'] == 'worker'

    before = dict(human.resources)
    assert card.handle_hotkey(key("q")) is True
    assert game.production_manager.get_production_info(castle) is not None
    assert sum(human.resources.values()) < sum(before.values())
    game.production_manager.cancel_production(castle)


def test_blacksmith_card_lists_techs_and_researches(game, card):
    blacksmith = build_own_building(game, "blacksmith", 900, 900)
    select(game, blacksmith)
    content = card.refresh()

    assert content['context'] == 'production'
    tech_slots = [s for s in content['slots'] if s and s['kind'] == 'tech']
    assert len(tech_slots) == 6

    assert card.handle_hotkey(key("q")) is True
    assert blacksmith.current_research is not None
    game.buildings.remove(blacksmith)


def test_right_click_tile_refunds_queued_unit(game, card):
    human = game.players[0]
    castle = own_castle(game)
    select(game, castle)

    game.production_manager.start_production(castle, "worker")
    game.production_manager.start_production(castle, "worker")  # queued
    assert castle.production_queue == ["worker"]
    before = sum(human.resources.values())

    panel = pygame.Surface((184, 480))
    card.draw(panel, 1080, 208, 184, 480, [castle])
    slot_rect = card._slot_rects[0][1]
    assert card.handle_right_click(slot_rect.center) is True
    assert castle.production_queue == []
    assert sum(human.resources.values()) > before  # full refund
    game.production_manager.cancel_production(castle)


# --------------------------------------------------------------------- #
# military / construction cards                                          #
# --------------------------------------------------------------------- #

def test_military_card_on_bottom_rows(game, card):
    a = spawn_own_unit(game, "warrior", 700, 700)
    b = spawn_own_unit(game, "warrior", 730, 700)
    select(game, a, b)
    content = card.refresh()

    assert content['context'] == 'military'
    assert content['slots'][0] is None            # W/A/S keep panning
    assert content['slots'][4]['kind'] == 'stop'
    assert content['slots'][5]['kind'] == 'stance'
    assert content['slots'][6]['kind'] == 'formation'

    stance_before = a.stance
    assert card.handle_hotkey(key("x")) is True   # slot 5 = stance
    assert a.stance != stance_before

    # Unoccupied slot keys fall through to the global bindings
    assert card.handle_hotkey(key("q")) is False

    game.units.remove(a)
    game.units.remove(b)


def test_construction_site_gets_cancel_tile(game, card):
    from entities import ConstructionSite

    human = game.players[0]
    castle = own_castle(game)
    template = game.game_data["buildings"]["farm"]
    site = ConstructionSite(
        "farm",
        {"name": "farm", "size": template.size, "hp": template.hp,
         "sprite": template.sprite, "build_duration": template.build_duration,
         "costs": {}},
        castle.x + 150, castle.y, template.size[0] * 32, human,
    )
    game.construction_sites.append(site)
    select(game, site)

    content = card.refresh()
    assert content['context'] == 'construction'
    assert content['slots'][0]['kind'] == 'cancel_construction'

    assert card.handle_hotkey(key("q")) is True
    assert site not in game.construction_sites


# --------------------------------------------------------------------- #
# Phase B: multi-building production (SC2 model)                         #
# --------------------------------------------------------------------- #

def test_group_production_routes_to_shortest_queue(game, card):
    castle = own_castle(game)
    a = build_own_building(game, "barracks", castle.x + 300, castle.y)
    b = build_own_building(game, "barracks", castle.x + 300, castle.y + 100)
    select(game, a, b)
    content = card.refresh()

    assert content['context'] == 'production'
    warrior = next(s for s in content['slots'] if s and s.get('unit_type') == 'warrior')
    assert len(warrior['producers']) == 2

    card._activate(warrior)   # first press -> a (both empty, first wins)
    card._activate(warrior)   # second press must route to the idle one
    assert a.current_production is not None
    assert b.current_production is not None

    game.production_manager.cancel_production(a)
    game.production_manager.cancel_production(b)
    game.buildings.remove(a)
    game.buildings.remove(b)


def test_union_card_for_mixed_building_types(game, card):
    castle = own_castle(game)
    barracks = build_own_building(game, "barracks", castle.x + 300, castle.y)
    stable = build_own_building(game, "stable", castle.x + 300, castle.y + 100)
    select(game, barracks, stable)
    content = card.refresh()

    types = [s['unit_type'] for s in content['slots'] if s and s['kind'] == 'unit']
    assert 'warrior' in types and 'cavalry' in types  # union of both producers
    cavalry = next(s for s in content['slots'] if s['unit_type'] == 'cavalry')
    assert cavalry['producers'] == [stable]

    game.buildings.remove(barracks)
    game.buildings.remove(stable)


def test_shift_batch_spreads_across_producers(game, card, monkeypatch):
    castle = own_castle(game)
    a = build_own_building(game, "barracks", castle.x + 300, castle.y)
    b = build_own_building(game, "barracks", castle.x + 300, castle.y + 100)
    select(game, a, b)
    content = card.refresh()
    warrior = next(s for s in content['slots'] if s and s.get('unit_type') == 'warrior')

    monkeypatch.setattr(card, "_shift_held", lambda: True)
    game.batch_queue_size = 4
    card._activate(warrior)

    depths = sorted(card._queue_depth(x) for x in (a, b))
    assert depths == [2, 2]  # 4 units spread evenly over both queues

    for building in (a, b):
        building.production_queue.clear()
        game.production_manager.cancel_production(building)
        game.buildings.remove(building)
    del game.batch_queue_size


def test_buildings_join_control_groups(game, card):
    castle = own_castle(game)
    a = build_own_building(game, "barracks", castle.x + 300, castle.y)
    b = build_own_building(game, "barracks", castle.x + 300, castle.y + 100)
    sm = game.selection_manager

    select(game, a, b)
    sm.set_control_group(7)
    clear_selection(game)

    assert sm.recall_control_group(7) is True
    assert set(sm.selected_objects) == {a, b}
    assert a.selected and b.selected

    # Dead buildings drop out on recall
    game.buildings.remove(a)
    assert sm.recall_control_group(7) is True
    assert sm.selected_objects == [b]

    game.buildings.remove(b)
    sm.control_groups[7] = []
    clear_selection(game)


# --------------------------------------------------------------------- #
# Phase C: global build-queue strip + select-all-production              #
# --------------------------------------------------------------------- #

def test_global_queue_lists_all_production(game, card):
    screen = pygame.Surface((1280, 720))
    strip = game.ui_manager.global_queue
    castle = own_castle(game)
    barracks = build_own_building(game, "barracks", castle.x + 300, castle.y)
    smith = build_own_building(game, "blacksmith", castle.x + 300, castle.y + 100)

    game.production_manager.start_production(castle, "worker")
    game.production_manager.start_production(barracks, "warrior")
    game.production_manager.start_production(barracks, "warrior")  # queued
    game.research_manager.start_research(smith, "forged_blades")

    items = strip._items()
    kinds = sorted((i['kind'], i['key']) for i in items)
    assert kinds == [('tech', 'forged_blades'), ('unit', 'warrior'), ('unit', 'worker')]
    warrior_row = next(i for i in items if i['key'] == 'warrior')
    assert warrior_row['queued'] == 1

    strip.draw(screen)
    assert len(strip._rows) == 3

    # Click jumps camera to + selects the producer
    rect, item = next((r, i) for r, i in strip._rows if i['key'] == 'warrior')
    assert strip.handle_click(rect.center) is True
    assert barracks.selected

    game.production_manager.cancel_production(castle)
    barracks.production_queue.clear()
    game.production_manager.cancel_production(barracks)
    game.research_manager.cancel_research(smith)
    game.buildings.remove(barracks)
    game.buildings.remove(smith)


def test_cancel_research_refunds_half(game, card):
    human = game.players[0]
    castle = own_castle(game)
    smith = build_own_building(game, "blacksmith", castle.x + 300, castle.y)
    before = sum(human.resources.values())

    game.research_manager.start_research(smith, "forged_blades")
    spent = before - sum(human.resources.values())
    assert spent > 0

    ok, _ = game.research_manager.cancel_research(smith)
    assert ok and smith.current_research is None
    refunded = sum(human.resources.values()) - (before - spent)
    assert 0 < refunded <= spent // 2 + 1  # 50% back (integer division)

    game.buildings.remove(smith)


def test_select_all_military_production(game, card):
    castle = own_castle(game)
    barracks = build_own_building(game, "barracks", castle.x + 300, castle.y)
    stable = build_own_building(game, "stable", castle.x + 300, castle.y + 100)
    sm = game.selection_manager

    assert sm.select_all_military_production() is True
    assert set(sm.selected_objects) == {barracks, stable}  # castle excluded
    assert card.refresh()['context'] == 'production'

    game.buildings.remove(barracks)
    game.buildings.remove(stable)
    clear_selection(game)


# --------------------------------------------------------------------- #
# camera-pan key suppression                                             #
# --------------------------------------------------------------------- #

def test_consumes_key_only_for_occupied_slots(game, card):
    # Nothing selected: never consume
    card.refresh()
    assert not card.consumes_key(key("r"))

    # Worker (economy tab): r=lumbermill occupied (2026-07-18 WASD-free
    # layout: Q E R T / Z X C V), d unbound
    select(game, own_worker(game))
    card.refresh()
    assert card.consumes_key(key("r"))
    assert card.consumes_key(key("tab"))  # tab swap while chips visible
    assert not card.consumes_key(key("d"))
    # WASD is NEVER a card key now — camera pan always wins (user decision)
    assert not card.consumes_key(key("w"))
    assert not card.consumes_key(key("a"))
    assert not card.consumes_key(key("s"))

    # Army: Z (stop) is consumed; WASD still free
    warrior = spawn_own_unit(game, "warrior", 700, 700)
    select(game, warrior)
    card.refresh()
    assert not card.consumes_key(key("w"))
    assert not card.consumes_key(key("s"))
    assert card.consumes_key(key("z"))
    game.units.remove(warrior)


# --------------------------------------------------------------------- #
# §8.2.2 icon-first anatomy: glyph costs, name/duration in the tooltip   #
# --------------------------------------------------------------------- #

def test_cost_bearing_tiles_carry_a_costs_dict(game, card):
    """The tile cost row is glyph+number pairs now, so slots carry a real
    costs dict, not the old pre-joined "500G 500W" string."""
    select(game, own_worker(game))
    card.active_tab = 'economy'
    content = card.refresh()
    castle = next(s for s in content['slots'] if s and s['name'] == 'castle')
    assert isinstance(castle['costs'], dict)
    assert castle['costs'] == {'gold': 500, 'wood': 500}
    assert 'cost' not in castle, "old pre-joined cost string must be gone"
    # The name left the tile — it must survive as the tooltip's title row.
    assert castle['tooltip'][0] == castle['label']


def test_cost_glyphs_load_at_requested_size(game):
    """All four glyphs (3 resources + duration) load as square surfaces —
    if any is missing the tile silently falls back to a letter."""
    loader = game.ui_manager.command_card.icon_loader
    for name in ('gold', 'wood', 'food', 'time'):
        glyph = loader.get_cost_glyph(name, 13)
        assert glyph is not None, f"{name} glyph did not load"
        assert glyph.get_size() == (13, 13)


def test_tooltip_carries_a_cost_row_with_duration(game, card):
    """Tooltip owns cost (glyphs) + build time (clock) per the anatomy."""
    select(game, own_worker(game))
    card.active_tab = 'economy'
    content = card.refresh()
    castle = next(s for s in content['slots'] if s and s['name'] == 'castle')
    cost_rows = [x for x in castle['tooltip'] if isinstance(x, dict)]
    assert len(cost_rows) == 1
    assert cost_rows[0]['costs'] == {'gold': 500, 'wood': 500}
    assert cost_rows[0]['duration'], "castle tooltip must show a build duration"


def test_unit_tooltip_shows_build_time_from_json(game, card):
    """Regression: build_time lives in the raw JSON, not the Unit template
    object, so the tooltip must read it from production_manager.units_data.
    The old text tooltip silently showed no unit duration."""
    barracks = build_own_building(game, 'barracks',
                                  own_castle(game).x + 200, own_castle(game).y)
    barracks.can_produce = ['warrior']
    select(game, barracks)
    content = card.refresh()
    warrior = next(s for s in content['slots']
                   if s and s.get('unit_type') == 'warrior')
    cost_rows = [x for x in warrior['tooltip'] if isinstance(x, dict)]
    assert cost_rows and cost_rows[0]['duration'] == 8  # units.json warrior
    game.buildings.remove(barracks)


def test_frame_with_hovered_cost_tile_renders(game, card, monkeypatch):
    """End-to-end: a real frame with a cost tile hovered draws the glyph
    cost row and the glyph tooltip without raising (the preview confirmed
    it visually; this guards against a blit/scale regression)."""
    select(game, own_worker(game))
    card.active_tab = 'economy'
    game.rendering_system.draw_frame(game.screen, game.map_surface, game.camera, 1/60)
    castle_rect = next(r for i, r in card._slot_rects
                       if card._content['slots'][i]
                       and card._content['slots'][i].get('name') == 'castle')
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: castle_rect.center)
    game.rendering_system.draw_frame(game.screen, game.map_surface, game.camera, 1/60)
    assert card._hovered_slot is not None
    assert card._hovered_slot.get('name') == 'castle'


def test_tooltip_wraps_instead_of_truncating(game, card):
    """The old `line[:34]` chopped gate/stable/fletching mid-word. Wrapping
    must be lossless and every wrapped piece must fit the box."""
    long_line = ("Wall segment your units can pass through freely "
                 "but enemies cannot")
    usable = card.TOOLTIP_WIDTH - 2 * card.TOOLTIP_PAD_X
    pieces = card._wrap_tooltip_line(long_line, usable)

    assert len(pieces) >= 2, "a 60+ char line must wrap"
    assert " ".join(pieces) == long_line, "wrap must not drop characters"
    for piece in pieces:
        assert card.cost_font.size(piece)[0] <= usable

    # Short lines pass through untouched
    assert card._wrap_tooltip_line("Farm", usable) == ["Farm"]


def test_tooltip_draws_over_map_border(game, card, monkeypatch):
    """§8.2.2 occlusion regression: 'tooltip last' was only last within
    draw_ui_panel — the ornate map border (drawn later in draw_frame)
    overpainted its right edge. Drive a REAL frame with a hovered tile and
    assert the tooltip's right-edge interior survives everything."""
    select(game, own_worker(game))

    # Frame 1 populates the slot rects, then aim the mouse at a real tile.
    game.rendering_system.draw_frame(game.screen, game.map_surface,
                                     game.camera, 1 / 60)
    assert card._slot_rects, "worker selection must produce build tiles"
    tile = card._slot_rects[0][1]
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: tile.center)

    game.rendering_system.draw_frame(game.screen, game.map_surface,
                                     game.camera, 1 / 60)

    assert card._hovered_slot is not None, "tile under mouse must hover"
    # Sample inside the tooltip, within the band the ornate border rail
    # overpaints (rail spans ~[panel.x-24, panel.x]); the tooltip fill must
    # win there because it draws after the border (§8.2.2).
    probe_x = card._panel_rect.x - 16
    probe_y = min(max(6, tile.y), 100000) + 12
    assert game.screen.get_at((probe_x, probe_y))[:3] == (18, 18, 24), \
        "tooltip right edge was painted over (draw order regressed)"


def test_draw_ui_panel_no_longer_owns_the_tooltip(game):
    """Belt-and-braces for the order: the panel must not draw the tooltip
    (it draws before the map border); draw_frame must, after the border."""
    import inspect
    from systems import rendering_system as rs_module
    from ui import ui_manager as ui_module

    panel_src = inspect.getsource(ui_module.UIManager.draw_ui_panel)
    assert "draw_tooltip" not in panel_src

    frame_src = inspect.getsource(rs_module.RenderingSystem.draw_frame)
    border_at = frame_src.index("_draw_map_border")
    tooltip_at = frame_src.index("draw_tooltip")
    assert border_at < tooltip_at, "tooltip must draw after the map border"
