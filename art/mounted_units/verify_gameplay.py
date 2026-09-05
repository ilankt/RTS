"""Verify the new roster through production, rendering and save/load."""
import os
import sys
import json
import random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from PIL import Image,ImageDraw,ImageFont
from core.game import Game
from core.config import MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT
from managers.save_manager import SaveManager
from systems.projectile_system import SlingStone

random.seed(4321)
game=Game(mode='human_1v1',player_count=2)
castle=next(b for b in game.buildings if b.name=='castle' and b.player.human)
data=json.loads((ROOT/'data/units.json').read_text())
units=[]
for i,name in enumerate(['warrior','cavalry','spearman']):
    record=next(u for u in data if u['name']==name)
    castle.current_production={'unit_type':name,'unit_data':record}
    game.production_manager._complete_production(castle)
    u=next(u for u in game.units if u.name==name and u.player.human)
    u.x=castle.x+100+i*55;u.y=castle.y+35
    u.facing_direction=1;u.status='idle';u.selected=True
    u._facing_position=(u.x,u.y)
    assert all(a.direction_count==8 and len(a.frames)==8 for a in u.animations.values())
    if name=='cavalry': assert u.radius==14
    assert not u.sprite_mirrored
    units.append(u)
game.selection_manager.selected_objects=units
game.collision_system._rebuild_unit_index()
game.camera.zoom=2
game.game_map.scale_tiles(2)
game.camera.x=MAP_VIEW_WIDTH/2-(castle.x+155)*2
game.camera.y=MAP_VIEW_HEIGHT/2-(castle.y+35)*2
# Show an unobscured art-review crop of the actual gameplay renderer.
game.rendering_system._draw_fog_overlay=lambda *args: None
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
crop=game.map_surface.subsurface(pygame.Rect(MAP_VIEW_WIDTH//2-210,MAP_VIEW_HEIGHT//2-95,420,180))
pygame.image.save(crop,str(ROOT/'art/mounted_units/gameplay.png'))
SaveManager.SAVE_DIR=str(ROOT/'art/mounted_units/validation-saves')
SaveManager.save_game(game,slot=0)
ok,message=SaveManager.load_game(game,slot=0)
assert ok,message
for name in ['warrior','cavalry','spearman']:
    u=next(u for u in game.units if u.name==name and u.player.human)
    assert all(a.direction_count==8 for a in u.animations.values())
    if name=='cavalry': assert u.radius==14
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
pygame.quit()

print('PASS: mounted production, 8-direction animation, feet/rendering, save/load and post-load rendering.')
