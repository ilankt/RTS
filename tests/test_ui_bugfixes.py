"""User-reported windowed bugs (2026-07-10): construction bars reading as
0 HP, untouchable orphaned foundations, debug selection circles, minimap
ignoring fog."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture()
def game():
    random.seed(4321)
    from core.game import Game

    game = Game(mode="human_1v1", player_count=2)
    for _ in range(30):
        game.update(delta_time_override=1 / 60)
    return game


def place_site(game, x=None, y=None):
    from entities import ConstructionSite

    human = game.players[0]
    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    template = game.game_data["buildings"]["farm"]
    site = ConstructionSite(
        "farm",
        {"name": "farm", "size": template.size, "hp": template.hp,
         "sprite": template.sprite, "build_duration": template.build_duration,
         "costs": {}},
        x if x is not None else castle.x + 150,
        y if y is not None else castle.y,
        template.size[0] * 32,
        human,
    )
    game.construction_sites.append(site)
    game.pathfinder.notify_blocker_added(site)
    return site


def test_fresh_construction_bar_shows_a_sliver(game):
    """Bug 1: a 0%-progress foundation must not draw an all-black bar."""
    site = place_site(game)
    surface = pygame.Surface((400, 400))
    surface.fill((20, 80, 20))

    class Cam:
        zoom = 2.5
        x = -site.x * 2.5 + 200
        y = -site.y * 2.5 + 200

    game.floating_ui.draw_construction_bar(surface, site, Cam)
    blue = game.floating_ui.health_colors['construction']
    found = any(
        surface.get_at((x, y))[:3] == blue
        for y in range(120, 160) for x in range(160, 240)
    )
    assert found, "no construction-blue fill pixel found for a fresh site"

    game.construction_sites.remove(site)
    game.pathfinder.notify_blocker_removed(site)


def test_orphaned_site_is_selectable_and_resumable(game):
    """Bug 2: click-select the foundation, right-click a worker to resume."""
    human = game.players[0]
    site = place_site(game)
    sm = game.selection_manager

    # Selectable at its world position
    found = sm._get_object_at_position((site.x, site.y))
    assert found is site

    # The panel classifies it so the Cancel button appears
    for u in game.units:
        u.selected = False
    site.selected = True
    info = game.ui_manager.unit_panel.get_selected_object_info()
    assert info["type"] == "Construction"
    site.selected = False

    # A worker right-clicked onto it resumes building
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    spec = sm._command_spec_for(worker, site, (site.x, site.y))
    assert spec == ("build", site)
    sm._execute_command_spec(worker, spec)
    task = game.worker_task_system.active_task(worker)
    assert task is not None and task.kind == "build"
    assert task.construction_site is site

    game.worker_task_system.cancel(worker)
    game.construction_sites.remove(site)
    game.pathfinder.notify_blocker_removed(site)


def test_enemy_site_is_not_resumable(game):
    site = place_site(game)
    site.player = game.players[1]  # enemy foundation
    human_worker = next(u for u in game.units
                        if u.player is game.players[0] and u.name == "worker")
    spec = game.selection_manager._command_spec_for(
        human_worker, site, (site.x, site.y)
    )
    assert spec[0] != "build"

    game.construction_sites.remove(site)
    game.pathfinder.notify_blocker_removed(site)


def test_selection_marker_is_subtle_ellipse(game):
    """Bug 3: no more bright-green debug circles."""
    import inspect
    from managers import selection_manager as sm_module

    source = inspect.getsource(sm_module)
    assert "range(0, 360, 45)" not in source  # tick-mark circle is gone
    assert "draw.ellipse" in source           # replaced by the ground ellipse


def test_minimap_masks_unexplored_terrain(game):
    """Bug 4: minimap hides what the human hasn't scouted."""
    human = game.players[0]
    fog = game.fog_of_war
    minimap = game.minimap
    minimap._render_fog_mask()

    castle = next(b for b in game.buildings if b.player is human and b.name == "castle")
    enemy_castle = next(b for b in game.buildings if b.player is not human and b.name == "castle")
    assert not fog.is_explored(human, enemy_castle.x, enemy_castle.y)

    own_mini = minimap.world_to_mini(castle.x, castle.y)
    enemy_mini = minimap.world_to_mini(enemy_castle.x, enemy_castle.y)
    own_alpha = minimap._fog_surface.get_at(own_mini)[3]
    enemy_alpha = minimap._fog_surface.get_at(enemy_mini)[3]
    assert own_alpha == 0, "own base must be clear on the minimap"
    assert enemy_alpha == 255, "unscouted enemy base must be blacked out"

    # Fog off (spectator): no mask at all
    game.fog_of_war_enabled = False
    minimap._render_fog_mask()
    game.fog_of_war_enabled = True
    assert minimap._fog_surface.get_at(enemy_mini)[3] == 0


def test_enemy_float_does_not_spawn_in_unexplored_fog(game):
    """§8.13.2 spawn gate: an enemy farm's +food float over never-explored
    ground must not even be created (7 AI players' farms fire these)."""
    human = game.players[0]
    enemy_castle = next(b for b in game.buildings
                        if b.player is not human and b.name == "castle")
    assert not game.fog_of_war.is_explored(human, enemy_castle.x, enemy_castle.y)

    game.floating_ui.notifications.clear()
    game.floating_ui.add_resource_notification(enemy_castle, "food", 10)
    assert game.floating_ui.notifications == [], \
        "float spawned for a building the viewer has never seen"

    # The human's own buildings always spawn floats, fog notwithstanding
    own_castle = next(b for b in game.buildings
                      if b.player is human and b.name == "castle")
    game.floating_ui.add_resource_notification(own_castle, "food", 10)
    assert len(game.floating_ui.notifications) == 1
    game.floating_ui.notifications.clear()


def test_enemy_float_never_renders_through_fog(game):
    """§8.13.2 render gate: a float whose origin sits under fog draws no
    pixels, even if it was spawned when the spot was visible (fog rebuilds
    at 5 Hz while floats live ~1 s)."""
    from ui.floating_ui import FloatingNotification

    human = game.players[0]
    enemy_castle = next(b for b in game.buildings
                        if b.player is not human and b.name == "castle")
    ui = game.floating_ui
    ui.notifications.clear()
    ui.notifications.append(FloatingNotification(
        "+10", enemy_castle.x, enemy_castle.y - 60, (255, 255, 255),
        owner=enemy_castle.player, origin=(enemy_castle.x, enemy_castle.y),
    ))

    background = (20, 80, 20)
    surface = pygame.Surface((400, 400))
    surface.fill(background)

    class Cam:
        zoom = 1.0
        x = -enemy_castle.x + 200
        y = -enemy_castle.y + 200

    ui.draw_notifications(surface, Cam)
    dirty = any(
        surface.get_at((x, y))[:3] != background
        for y in range(60, 220, 2) for x in range(100, 300, 2)
    )
    assert not dirty, "enemy float rendered over unexplored fog"

    # Spectator reveal shows everything — same float, same camera
    game.spectator_reveal_display = True
    ui.draw_notifications(surface, Cam)
    game.spectator_reveal_display = False
    dirty = any(
        surface.get_at((x, y))[:3] != background
        for y in range(60, 220, 2) for x in range(100, 300, 2)
    )
    assert dirty, "spectator reveal must show the float"
    ui.notifications.clear()


def test_float_visibility_judged_by_origin_not_drifted_position(game):
    """§8.13.2: update() drifts a float upward ~30 px/s; visibility must key
    on the fixed spawn origin so it can't flicker across a fog border
    mid-flight (own floats aside, which always pass)."""
    from ui.floating_ui import FloatingNotification

    human = game.players[0]
    own_castle = next(b for b in game.buildings
                      if b.player is human and b.name == "castle")
    # A visible-tile origin, judged as an un-owned (neutral) float so the
    # positional path is what's exercised.
    note = FloatingNotification(
        "+5", own_castle.x, own_castle.y - 60, (255, 255, 255),
        owner=None, origin=(own_castle.x, own_castle.y),
    )
    assert game.floating_ui._notification_visible(note)
    note.update(1.0)  # drifts 30 px up, across tile borders
    assert note.origin == (own_castle.x, own_castle.y), "origin must not drift"
    assert game.floating_ui._notification_visible(note), \
        "visibility flipped because the drifted position was sampled"

    # Own-player floats pass even when the origin is under fog
    enemy_area = next(b for b in game.buildings
                      if b.player is not human and b.name == "castle")
    own_under_fog = FloatingNotification(
        "+5", enemy_area.x, enemy_area.y, (255, 255, 255),
        owner=human, origin=(enemy_area.x, enemy_area.y),
    )
    assert game.floating_ui._notification_visible(own_under_fog), \
        "own floats must never vanish at fog edges"


def test_full_frame_renders_with_all_fixes(game):
    """Smoke: a real frame with a selected unit + fresh site draws cleanly."""
    human = game.players[0]
    site = place_site(game)
    worker = next(u for u in game.units if u.player is human and u.name == "worker")
    worker.selected = True
    game.selection_manager.selected_objects = [worker]

    game.rendering_system.draw_frame(game.screen, game.map_surface, game.camera, 1 / 60)

    worker.selected = False
    game.selection_manager.selected_objects = []
    game.construction_sites.remove(site)
    game.pathfinder.notify_blocker_removed(site)
