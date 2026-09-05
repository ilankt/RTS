"""Dust uses rendered feet; clicking and hover share enlarged unit targets."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pygame
import pytest
from managers.selection_manager import SelectionManager
from systems.rendering_system import RenderingSystem
from core.config import TOP_BAR_HEIGHT

@pytest.mark.parametrize('zoom',[.5,1,2])
def test_click_and_hover_share_larger_radius(zoom):
    pygame.init();pygame.display.set_mode((1,1))
    unit=NS(x=100,y=100,radius=8,selected=False,player=NS(human=True))
    game=NS(units=[unit],buildings=[],resources=[],construction_sites=[],camera=NS(x=17,y=-11,zoom=zoom))
    sm=SelectionManager(game)
    assert sm._get_object_at_position((121,100)) is unit
    sm._handle_single_click((121*zoom+17,100*zoom-11+TOP_BAR_HEIGHT))
    assert sm.selected_objects==[unit]
    assert sm._get_object_at_position((123,100)) is None
    assert unit.radius==8
    pygame.quit()

@pytest.mark.parametrize('zoom',[.5,1,2])
def test_dust_emits_at_shared_ground_anchor(zoom):
    unit=NS(name='archer',x=100,y=100,radius=8,size=[1,1],status='run',movement_speed=60)
    particles=Mock()
    renderer=RenderingSystem.__new__(RenderingSystem)
    renderer.game=NS(units=[unit],buildings=[],resources=[],construction_sites=[],shadows_enabled=False,particles=particles,frame_counter=1)
    renderer.selection_manager=Mock()
    renderer._draw_object=Mock()
    renderer._ground_anchors={'archer':(.5,.730059)}
    renderer._render_scales={}
    camera=NS(x=17,y=-11,zoom=zoom)
    renderer._draw_all_objects(pygame.Surface((600,600)),camera)
    x,y=particles.spawn_move_dust.call_args.args
    assert x==pytest.approx(100)
    assert y==pytest.approx(100+.230059*64)
