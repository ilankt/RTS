"""Foot anchors must drive both markers and shadows at every zoom."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pygame
import pytest
from systems.rendering_system import RenderingSystem
from managers.selection_manager import SelectionManager

@pytest.mark.parametrize('name',['worker','warrior','archer','spearman','healer'])
@pytest.mark.parametrize('zoom',[.5,1.0,1.5,2.0])
def test_marker_and_shadow_share_blender_ground_point(name,zoom):
    data=json.loads((ROOT/'data/units.json').read_text())
    anchor=next(u['ground_anchor'] for u in data if u['name']==name)
    renderer=RenderingSystem.__new__(RenderingSystem)
    renderer._render_scales={}
    renderer._ground_anchors={name:anchor}
    unit=SimpleNamespace(name=name,x=100,y=200,radius=8,size=[1,1])
    camera=SimpleNamespace(x=17,y=-31,zoom=zoom)
    point=renderer.ground_position(unit,camera)
    assert point[0]==pytest.approx(100*zoom+17)
    assert point[1]==pytest.approx(200*zoom-31+(anchor[1]-.5)*64*zoom)
    assert point[1] > 200*zoom-31+8*zoom*.55+4*zoom
    manager=SelectionManager(SimpleNamespace(rendering_system=renderer))
    assert manager._ground_marker_position(unit,camera)==point
    shadow=renderer._shadow_geometry(unit,pygame.Surface((192,192)),camera)
    assert shadow[:2]==point


def test_legacy_units_keep_their_marker_position():
    renderer=RenderingSystem.__new__(RenderingSystem)
    renderer._render_scales={};renderer._ground_anchors={}
    unit=SimpleNamespace(name='archer',x=100,y=200,radius=8,size=[1,1])
    camera=SimpleNamespace(x=0,y=0,zoom=1)
    assert renderer.ground_position(unit,camera)==(100,204.4)
