"""Focused contracts for the approved outlined unit production assets."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pygame
import pytest
from entities.unit import Unit
from systems.animation import Animation
from managers.sprite_manager import tint_directional_team

@pytest.mark.parametrize('unit_name',['worker','warrior','archer','spearman','healer'])
def test_all_production_sheets_have_eight_directions(unit_name):
    data=json.loads((ROOT/'data/units.json').read_text())
    unit=next(u for u in data if u['name']==unit_name)
    assert unit['animation_directions']==8
    for path in set(unit['animations'].values()):
        animation=Animation(pygame.image.load(str(ROOT/path)),192,192,100,8)
        assert len(animation.frames)==8
        assert len({pygame.image.tobytes(animation.get_current_frame(d),'RGBA') for d in range(8)})==8
        animation.update(delta_time=.3)
        assert animation.current_frame_index==3 or animation.current_frame_index==2

@pytest.mark.parametrize('status,is_building,field,direction',[('gather',False,'gathering_target',6),('idle',True,'building_target',4)])
def test_worker_faces_work_target_and_uses_correct_direction(status,is_building,field,direction):
    sheet=pygame.Surface((8,64),pygame.SRCALPHA)
    for d in range(8):sheet.fill((d*30,0,0,255),(0,d*8,8,8))
    animations={a:Animation(sheet,8,8,100,8) for a in ['idle','gather','build']}
    u=Unit('worker',[1,1],100,40,0,animations,can_build=True)
    u.status=status;u.is_building=is_building
    setattr(u,field,SimpleNamespace(x=-10 if direction==4 else 0,y=-10 if direction==6 else 0))
    u.update_animation(.1)
    assert u.facing_direction==direction
    assert u.get_current_sprite().get_at((0,0))[0]==direction*30
    u.facing_left=True
    assert not u.sprite_mirrored


def test_worker_walk_faces_motion_even_with_resource_assignment():
    u=Unit('worker',[1,1],100,40,0,{})
    u.status='run';u.x=10;u.y=10
    u.gathering_target=SimpleNamespace(x=-10,y=0)
    u.update_animation(.1)
    assert u.facing_direction==1


def test_worker_tools_and_player_colours_are_distinct():
    pygame.init();pygame.display.set_mode((1,1))
    base=ROOT/'assets/sprites/Units/WorkerOutlined'
    gather=pygame.image.load(str(base/'gather.png')).convert_alpha()
    build=pygame.image.load(str(base/'build.png')).convert_alpha()
    assert pygame.image.tobytes(gather,'RGBA')!=pygame.image.tobytes(build,'RGBA')
    red=tint_directional_team(gather,(220,40,40))
    blue=tint_directional_team(gather,(40,80,220))
    assert pygame.image.tobytes(red,'RGBA')!=pygame.image.tobytes(blue,'RGBA')
    assert pygame.surfarray.array_alpha(red).tolist()==pygame.surfarray.array_alpha(gather).tolist()
    pygame.quit()
