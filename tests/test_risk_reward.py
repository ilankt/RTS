"""§7.3 risk/reward economy: raid targeting + worker-saturation curve."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from systems.ai.military_brain import MilitaryBrain
from systems.gathering_manager import saturation_multiplier


def _ctx(army_size, personality="balanced", castle_threat=100.0, mine_threat=0.0,
         with_mine=True):
    """Attacker at origin; enemy castle at (1000, 0); forward mine at (500, 500)."""
    enemy_castle = SimpleNamespace(name="castle", x=1000, y=0, hp=2500)
    buildings = [enemy_castle]
    if with_mine:
        buildings.append(SimpleNamespace(name="mine", x=500, y=500, hp=400))

    def threat_at(x, y):
        if (x, y) == (1000, 0):
            return castle_threat
        if (x, y) == (500, 500):
            return mine_threat
        return 0.0

    return SimpleNamespace(
        castle=SimpleNamespace(x=0, y=0),
        enemy_buildings=buildings,
        enemy_units=[],
        military=[object()] * army_size,
        player=SimpleNamespace(ai_personality=personality),
        threat_at=threat_at,
    )


def test_small_army_raids_soft_expansion():
    brain = MilitaryBrain(game=None)
    target = brain._find_attack_target(_ctx(army_size=5))
    assert target.name == "mine", "raid-sized army should hit the soft expansion"


def test_big_army_goes_for_the_castle():
    brain = MilitaryBrain(game=None)
    target = brain._find_attack_target(_ctx(army_size=20))
    assert target.name == "castle"


def test_no_raid_when_castle_is_equally_soft():
    brain = MilitaryBrain(game=None)
    target = brain._find_attack_target(_ctx(army_size=5, castle_threat=0.0))
    assert target.name == "castle", "undefended castle -> go for the kill"


def test_no_raid_when_expansion_is_defended():
    brain = MilitaryBrain(game=None)
    target = brain._find_attack_target(
        _ctx(army_size=5, castle_threat=100.0, mine_threat=90.0))
    assert target.name == "castle", "defended expansion isn't raid bait"


def test_rusher_raids_with_bigger_armies():
    brain = MilitaryBrain(game=None)
    assert brain._find_attack_target(_ctx(10, personality="rusher")).name == "mine"
    assert brain._find_attack_target(_ctx(10, personality="boomer")).name == "castle"


def test_saturation_curve_goes_flat_then_two_nodes_beat_one():
    from core.config import WORKER_SATURATION_CAP as CAP

    def one_node_total(n):
        return n * saturation_multiplier(n)

    # Total output grows up to the cap, then stays flat
    assert one_node_total(CAP) > one_node_total(CAP - 1)
    assert one_node_total(CAP + 3) == one_node_total(CAP)

    # Splitting the same workers across two nodes beats stacking one
    n = CAP * 2
    split = 2 * one_node_total(CAP)
    stacked = one_node_total(n)
    assert split > stacked
