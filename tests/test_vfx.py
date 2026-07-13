"""§8.5 VFX/juice: particle presets, death fades, impact flashes,
staged construction rendering."""
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from systems.particle_system import ParticleSystem
from systems.projectile_system import Projectile, ProjectileSystem


@pytest.fixture(scope="module")
def game():
    random.seed(8555)
    from core.game import Game

    return Game(mode="human_1v1", player_count=2)


FLAT_CAMERA = SimpleNamespace(zoom=1.0, x=0, y=0)


def test_particles_do_not_consume_global_random():
    particles = ParticleSystem(game=None)
    random.seed(1234)
    state = random.getstate()
    particles.spawn_move_dust(10, 10)
    particles.spawn_muzzle_flash(10, 10)
    particles.spawn_impact_flash(10, 10)
    particles.spawn_death_particles(10, 10)
    assert random.getstate() == state, \
        "particle bursts must use their own RNG, not the seeded global stream"
    assert len(particles.particles) > 10


def test_projectile_arrival_spawns_impact_flash():
    fake_game = SimpleNamespace(particles=ParticleSystem(game=None))
    system = ProjectileSystem(fake_game)
    shooter = SimpleNamespace(name="archer")
    system.projectiles.append(Projectile(0, 0, 4, 0, speed=300, damage=5, owner=shooter))

    system.update(1 / 30)  # step reaches the target -> dies + flash
    assert not system.projectiles
    assert fake_game.particles.particles, "impact flash particles expected"


def test_death_fade_registers_caps_and_expires(game):
    renderer = game.rendering_system
    renderer._death_fades.clear()
    sprite = pygame.Surface((32, 32), pygame.SRCALPHA)
    obj = SimpleNamespace(x=100, y=100, size=(1, 1), name="warrior", facing_left=False)

    for _ in range(40):  # over the cap
        renderer.add_death_fade(obj, sprite)
    assert len(renderer._death_fades) == renderer._DEATH_FADE_MAX

    surface = pygame.Surface((300, 300))
    renderer._draw_death_fades(surface, FLAT_CAMERA, delta_time=0.2)
    assert renderer._death_fades, "fades should still be alive at 0.2s"
    renderer._draw_death_fades(surface, FLAT_CAMERA, delta_time=5.0)
    assert not renderer._death_fades, "fades expire past the fade duration"

    renderer.add_death_fade(obj, None)  # spriteless deaths are ignored
    assert not renderer._death_fades


def test_construction_stage_draws_building_slice(game):
    from entities.construction_site import ConstructionSite

    renderer = game.rendering_system
    human = game.players[0]
    data = game.game_data["buildings"]["barracks"]
    building_data = {
        "size": data.size, "build_duration": data.build_duration,
        "costs": dict(data.costs),
    }
    site = ConstructionSite("barracks", building_data, 200, 200, radius=30, player=human)

    surface = pygame.Surface((400, 400))
    surface.fill((1, 2, 3))

    site.construction_progress = 0.05 * site.construction_duration
    renderer._draw_construction_stage(site, 200, 200, FLAT_CAMERA, surface)
    early = pygame.surfarray.array3d(surface).sum()

    site.construction_progress = 0.9 * site.construction_duration
    renderer._draw_construction_stage(site, 200, 200, FLAT_CAMERA, surface)
    late = pygame.surfarray.array3d(surface).sum()

    assert late != early, "at 90% progress the building slice must draw pixels"
