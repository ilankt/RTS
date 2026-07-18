"""§11.1 tileset variants: per-tile variant lists with a deterministic
per-coordinate pick, so high-coverage terrain stops reading as clones."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from core.config import TERRAIN_TYPES


@pytest.fixture(scope="module")
def game_map():
    pygame.init()
    pygame.display.set_mode((320, 240))
    random.seed(11)
    from world.map import Map

    return Map(30, 30, game=None)


def test_variant_lists_cover_every_terrain_type(game_map):
    from world.map import DERIVED_VARIANT_TILES

    assert set(game_map.tile_variants) == TERRAIN_TYPES
    for name, variants in game_map.tile_variants.items():
        if name in DERIVED_VARIANT_TILES:
            assert len(variants) == 4, f"{name} should carry derived variants"
        else:
            assert len(variants) == 1, f"{name} should stay single-variant"
        # Every variant keeps the sheet geometry
        for surface in variants:
            assert surface.get_size() == variants[0].get_size()


def test_derived_variants_are_visually_distinct(game_map):
    variants = game_map.tile_variants["grass"]
    base_bytes = pygame.image.tobytes(variants[0], "RGBA")
    assert any(pygame.image.tobytes(v, "RGBA") != base_bytes
               for v in variants[1:]), "flip variants must differ from the base"


def test_scale_tiles_scales_every_variant(game_map):
    game_map.scale_tiles(2.0)
    for name, variants in game_map.scaled_tile_variants.items():
        assert len(variants) == len(game_map.tile_variants[name])
        for surface in variants:
            assert surface.get_size() == (128, 112)  # 64x56 * 2.0
    # Back-compat alias points at the base variant
    assert game_map.scaled_tile_images["grass"] is game_map.scaled_tile_variants["grass"][0]
    game_map.scale_tiles(1.0)


def test_variant_pick_is_deterministic_and_varied(game_map):
    from world.map import Map

    # Same cell -> same variant, forever (saves/seeds reproduce the look)
    assert Map.variant_index(7, 12, 4) == Map.variant_index(7, 12, 4)
    # A field of one terrain type shows more than one variant
    picks = {Map.variant_index(r, c, 4) for r in range(4) for c in range(4)}
    assert len(picks) > 1, "a 4x4 field must not be 16 identical bitmaps"
    # Single-variant tiles always pick the base
    assert Map.variant_index(5, 9, 1) == 0
