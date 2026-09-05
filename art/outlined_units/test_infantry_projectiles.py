"""Projectile artwork is chosen by metadata, with legacy arrow fallback."""
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from systems.projectile_system import ProjectileSystem, SlingStone, Arrow

@pytest.mark.parametrize('kind,expected',[('stone',SlingStone),('arrow',Arrow),(None,Arrow)])
def test_ranged_projectile_metadata_and_legacy_fallback(kind,expected):
    template=SimpleNamespace() if kind is None else SimpleNamespace(projectile_type=kind)
    system=ProjectileSystem(SimpleNamespace(game_data={'units':{'archer':template}}))
    system.create_projectile(SimpleNamespace(name='archer',x=0,y=0),SimpleNamespace(x=100,y=0),12)
    projectile=system.projectiles[0]
    assert isinstance(projectile,expected)
    assert projectile.speed==300 and projectile.damage==12
    projectile.update(1)
    assert not projectile.alive
    assert (projectile.x,projectile.y)==(100,0)
