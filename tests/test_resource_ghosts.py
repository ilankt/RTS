"""Fog resource ghosts: resources depleted OUT of the viewer's sight keep a
ghost where last seen, pruned the moment the spot is actually revealed."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(31)
    from core.game import Game

    g = Game(mode="human_1v1", player_count=2)
    for _ in range(30):
        g.update(delta_time_override=1 / 60)
    return g


def _tile_of(game, resource):
    # The fog's own tiling (world_to_grid_fast) — the exact hex conversion
    # can land one column off, and the ghost keys must match the fog's view
    c, r = game.fog_of_war._world_to_tile(resource.x, resource.y)
    return r, c


def test_ghost_created_when_depleted_out_of_sight_and_pruned_on_reveal(game):
    fog = game.fog_of_war
    human = game.players[0]
    grid = fog.visibility_grid[human]

    # A resource on a tile the human has SEEN but can't see right now
    resource = next(r for r in game.resources
                    if grid[_tile_of(game, r)[0]][_tile_of(game, r)[1]] != fog.VISIBLE)
    r, c = _tile_of(game, resource)
    grid[r][c] = fog.EXPLORED

    resource.amount_remaining = 0
    game._cleanup_destroyed_objects()

    key = (r, c, resource.name)
    assert key in fog.resource_ghosts
    assert fog.resource_ghosts[key]["x"] == resource.x

    # Reveal the spot: a scout stands on it -> the ghost disappears
    scout = next(u for u in game.units if u.player is human)
    old_pos = (scout.x, scout.y)
    scout.x, scout.y = resource.x, resource.y
    fog.update()  # immediate rebuild
    assert key not in fog.resource_ghosts
    scout.x, scout.y = old_pos
    fog.update()


def test_no_ghost_when_depletion_was_visible(game):
    fog = game.fog_of_war
    human = game.players[0]
    grid = fog.visibility_grid[human]

    resource = next(r for r in game.resources if r.amount_remaining > 0)
    r, c = _tile_of(game, resource)
    grid[r][c] = fog.VISIBLE  # the player is watching

    resource.amount_remaining = 0
    game._cleanup_destroyed_objects()
    assert (r, c, resource.name) not in fog.resource_ghosts


def test_no_ghost_on_never_explored_ground(game):
    fog = game.fog_of_war
    human = game.players[0]
    grid = fog.visibility_grid[human]

    resource = next(r for r in game.resources if r.amount_remaining > 0)
    r, c = _tile_of(game, resource)
    grid[r][c] = fog.UNEXPLORED  # the player never saw this spot

    resource.amount_remaining = 0
    game._cleanup_destroyed_objects()
    assert (r, c, resource.name) not in fog.resource_ghosts
