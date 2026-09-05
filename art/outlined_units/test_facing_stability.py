"""Regressions for noisy steering at eight-direction sprite boundaries."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from entities.unit import Unit


@pytest.mark.parametrize('direction', range(8))
@pytest.mark.parametrize('turn', [-1, 1])
def test_boundary_noise_does_not_flicker_and_real_turn_still_works(direction, turn):
    unit = Unit('warrior', [1, 1], 100, 50, 10, {})
    unit.facing_direction = direction

    def face(offset):
        angle = math.radians(direction * 45 + turn * offset)
        unit.face_vector(math.cos(angle), math.sin(angle))

    # Cross the ordinary 22.5-degree boundary repeatedly in both directions.
    for offset in [20, 25, 21, 24] * 30:
        face(offset)
        assert unit.facing_direction == direction

    face(32)
    adjacent = (direction + turn) % 8
    assert unit.facing_direction == adjacent
    for offset in [20, 25, 21, 24] * 30:
        face(offset)
        assert unit.facing_direction == adjacent

    face(12)
    assert unit.facing_direction == direction
    face(180)
    assert unit.facing_direction == (direction + 4) % 8


def test_stationary_unit_retains_facing():
    unit = Unit('worker', [1, 1], 100, 40, 0, {})
    unit.facing_direction = 7
    for vector in [(0, 0), (.001, -.001), (-.001, .001)]:
        unit.face_vector(*vector)
        assert unit.facing_direction == 7
