"""Directional sprite mirroring: sheets face right; units moving or
attacking leftwards render mirrored."""
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


def own_worker(game):
    human = game.players[0]
    return next(u for u in game.units if u.player is human and u.name == "worker")


def test_facing_follows_horizontal_movement(game):
    unit = own_worker(game)
    move = game.movement_system

    assert unit.facing_left is False  # sheets face right by default

    move._update_unit_position(unit, pygame.Vector2(unit.x - 5, unit.y))
    assert unit.facing_left is True

    move._update_unit_position(unit, pygame.Vector2(unit.x + 5, unit.y))
    assert unit.facing_left is False

    # Pure vertical movement keeps the last horizontal facing
    move._update_unit_position(unit, pygame.Vector2(unit.x - 5, unit.y))
    move._update_unit_position(unit, pygame.Vector2(unit.x, unit.y + 5))
    assert unit.facing_left is True


def test_attack_faces_the_target(game):
    unit = own_worker(game)
    enemy_castle = next(b for b in game.buildings if b.player is game.players[1])

    unit.facing_left = enemy_castle.x > unit.x  # deliberately wrong way
    unit.start_attack(enemy_castle)
    assert unit.facing_left == (enemy_castle.x < unit.x)
    unit.stop()
    unit.current_target = None
    unit.in_combat = False


def test_renderer_mirrors_facing_left(game):
    """The blitted pixels for facing_left must be the horizontal mirror of
    the facing_right render."""
    unit = own_worker(game)
    rendering = game.rendering_system

    sprite = unit.get_current_sprite()
    assert sprite is not None

    class Cam:
        zoom = 1.0
        x = 0
        y = 0

    size = 128
    right_surface = pygame.Surface((size, size), pygame.SRCALPHA)
    left_surface = pygame.Surface((size, size), pygame.SRCALPHA)

    unit.facing_left = False
    rendering._render_sprite(sprite, unit, size // 2, size // 2, Cam, right_surface)
    unit.facing_left = True
    rendering._render_sprite(sprite, unit, size // 2, size // 2, Cam, left_surface)
    unit.facing_left = False

    right_pixels = pygame.image.tostring(right_surface, "RGBA")
    left_pixels = pygame.image.tostring(left_surface, "RGBA")
    mirrored = pygame.image.tostring(
        pygame.transform.flip(left_surface, True, False), "RGBA")
    assert right_pixels != left_pixels       # facing changes the render
    assert right_pixels == mirrored          # and it is an exact mirror
