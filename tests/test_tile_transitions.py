"""§11.1 hex edge transitions: higher-priority terrain feathers into its
lower-priority neighbours, with parity-correct directions."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(scope="module")
def game_map():
    pygame.init()
    pygame.display.set_mode((320, 240))
    random.seed(17)
    from world.map import Map

    return Map(20, 20, game=None)


def paint(game_map, name):
    for r in range(game_map.height):
        for c in range(game_map.width):
            game_map.grid[r][c] = name


# Direction order contract (shared with hex_neighbors): N S NW SW NE SE
N, S, NW, SW, NE, SE = range(6)


def test_masks_feather_from_their_own_edge(game_map):
    masks = game_map._build_edge_masks(24, 0.0)  # smooth profile: exact asserts
    assert len(masks) == 6
    tile_w = game_map.tileset["tile_width"]
    tile_h = game_map.tileset["tile_height"]
    for mask in masks:
        assert mask.get_size() == (tile_w, tile_h)
    # N mask: strong at the top edge's midpoint, gone at the bottom
    assert masks[N].get_at((tile_w // 2, 1)).a > 200
    assert masks[N].get_at((tile_w // 2, tile_h - 2)).a == 0
    # S mask: the reverse
    assert masks[S].get_at((tile_w // 2, tile_h - 2)).a > 200
    assert masks[S].get_at((tile_w // 2, 1)).a == 0
    # NE mask: strong just inside the upper-right diagonal, gone toward
    # the lower-left interior (probe points must lie INSIDE the hex)
    assert masks[NE].get_at((tile_w - 22, tile_h // 4)).a > 120
    assert masks[NE].get_at((tile_w * 5 // 16, tile_h * 3 // 4)).a == 0


def test_ragged_masks_differ_from_smooth(game_map):
    smooth = game_map._build_edge_masks(24, 0.0)
    ragged = game_map._build_edge_masks(24, 0.95)
    assert (pygame.image.tobytes(smooth[N], "RGBA")
            != pygame.image.tobytes(ragged[N], "RGBA"))
    # Determinism: the same parameters always produce the same mask
    again = game_map._build_edge_masks(24, 0.95)
    assert (pygame.image.tobytes(ragged[N], "RGBA")
            == pygame.image.tobytes(again[N], "RGBA"))


def test_higher_priority_neighbour_bleeds_in(game_map):
    paint(game_map, "desert")
    r, c = 10, 10
    game_map.grid[r - 1][c] = "grass"   # due north
    game_map.build_transitions()
    assert game_map.edge_overlays.get((r, c)) == [(N, "grass")]
    # The grass tile does NOT get a desert overlay (lower priority)
    assert (r - 1, c) not in game_map.edge_overlays


def test_directions_respect_column_parity(game_map):
    # Even column: NE neighbour is (r-1, c+1)
    paint(game_map, "desert")
    r, c = 10, 8
    assert c % 2 == 0
    game_map.grid[r - 1][c + 1] = "grass"
    game_map.build_transitions()
    assert game_map.edge_overlays.get((r, c)) == [(NE, "grass")]

    # Odd column: NE neighbour is (r, c+1)
    paint(game_map, "desert")
    r, c = 10, 9
    assert c % 2 == 1
    game_map.grid[r][c + 1] = "grass"
    game_map.build_transitions()
    assert game_map.edge_overlays.get((r, c)) == [(NE, "grass")]


def test_water_land_transition_chain(game_map):
    """dirt bleeds into shallow, shallow into deep — never the reverse."""
    paint(game_map, "water_deep")
    game_map.grid[10][10] = "dirt"
    game_map.grid[10][11] = "water_shallow"  # odd col: NW neighbour is (10,10)
    game_map.build_transitions()
    shallow = dict(game_map.edge_overlays.get((10, 11), []))
    assert shallow.get(NW) == "dirt"          # land bleeds into the shallows
    assert (10, 10) not in game_map.edge_overlays  # nothing bleeds into land here
    deep = dict(game_map.edge_overlays.get((11, 11), []))
    assert "water_shallow" in deep.values()   # shallow bleeds into the deep


def test_scaled_transition_surfaces_follow_zoom(game_map):
    paint(game_map, "grass")
    game_map.build_transitions()
    game_map.current_zoom = None
    game_map.scale_tiles(2.0)
    surface = game_map.scaled_transitions[("grass", N)]
    assert surface.get_size() == (128, 112)
    game_map.current_zoom = None
    game_map.scale_tiles(1.0)
