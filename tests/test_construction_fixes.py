"""Regressions for the 2026-07-18 construction bug batch:

1. A selected construction site must be DE-selected by _clear_all_selections,
   or its Cancel card leaks over every later building selection.
2. Reassigning a worker to a new site must release the old site's .builder,
   or both sites advance in lockstep off the worker's global is_building flag
   ("two buildings constructed together as one").
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest


@pytest.fixture(scope="module")
def game():
    random.seed(1234)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


def _make_site(game, player, name, x, y):
    from entities import ConstructionSite
    from core.config import TILE_WIDTH

    template = game.game_data["buildings"][name]
    site = ConstructionSite(
        building_name=name,
        building_data={
            "name": name, "size": template.size, "hp": template.hp,
            "sprite": template.sprite, "build_duration": template.build_duration,
            "costs": {},
        },
        x=x, y=y,
        radius=template.size[0] * TILE_WIDTH / 2,
        player=player,
    )
    game.construction_sites.append(site)
    return site


def test_clear_all_selections_clears_construction_sites(game):
    human = game.players[0]
    site = _make_site(game, human, "farm", 900, 900)
    site.selected = True

    game.selection_manager._clear_all_selections()

    assert site.selected is False
    game.construction_sites.remove(site)


def test_reassigning_builder_releases_previous_site(game):
    human = game.players[0]
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    site_a = _make_site(game, human, "farm", 950, 950)
    site_b = _make_site(game, human, "house", 1100, 1100)
    wts = game.worker_task_system

    assert wts.assign_build(worker, site_a)
    assert site_a.builder is worker

    # Placing/starting the second build reassigns the same worker
    assert wts.assign_build(worker, site_b)
    assert site_b.builder is worker
    assert site_a.builder is None, (
        "old site kept its builder — it would advance in lockstep with site B")

    # A plain move order (the 'stop' in build->stop->build) releases too
    wts.assign_move(worker, (1200, 1200))
    assert site_b.builder is None

    game.construction_sites.remove(site_a)
    game.construction_sites.remove(site_b)
    wts.cancel(worker)
