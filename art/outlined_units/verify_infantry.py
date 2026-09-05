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
for i,name in enumerate(['archer','spearman','healer']):
    record=next(u for u in data if u['name']==name)
    castle.current_production={'unit_type':name,'unit_data':record}
    game.production_manager._complete_production(castle)
    u=next(u for u in game.units if u.name==name and u.player.human)
    u.x=castle.x+100+i*55;u.y=castle.y+35
    u.facing_direction=1;u.status='idle';u.selected=True
    u._facing_position=(u.x,u.y)
    assert all(a.direction_count==8 and len(a.frames)==8 for a in u.animations.values())
    assert not u.sprite_mirrored
    units.append(u)
game.selection_manager.selected_objects=units
game.collision_system._rebuild_unit_index()
units[1].hp-=30
game.combat_system._update_healer(units[2],1/60)
assert units[1].hp>170
assert units[2].facing_direction==4
units[2].status='idle';units[2].facing_direction=1
game.projectile_system.create_projectile(units[0],units[1],1)
assert isinstance(game.projectile_system.projectiles[-1],SlingStone)
game.projectile_system.clear()
game.camera.zoom=2
game.game_map.scale_tiles(2)
game.camera.x=MAP_VIEW_WIDTH/2-(castle.x+155)*2
game.camera.y=MAP_VIEW_HEIGHT/2-(castle.y+35)*2
# Show an unobscured art-review crop of the actual gameplay renderer.
game.rendering_system._draw_fog_overlay=lambda *args: None
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
crop=game.map_surface.subsurface(pygame.Rect(MAP_VIEW_WIDTH//2-210,MAP_VIEW_HEIGHT//2-95,420,180))
pygame.image.save(crop,str(ROOT/'art/outlined_units/infantry-gameplay.png'))
SaveManager.SAVE_DIR=str(ROOT/'art/outlined_units/validation-saves')
SaveManager.save_game(game,slot=0)
ok,message=SaveManager.load_game(game,slot=0)
assert ok,message
for name in ['archer','spearman','healer']:
    u=next(u for u in game.units if u.name==name and u.player.human)
    assert all(a.direction_count==8 for a in u.animations.values())
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
pygame.quit()

font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',20)
manifest=json.loads((ROOT/'art/outlined_units/manifest.json').read_text())
frames=[]
for frame in range(24):
    board=Image.new('RGB',(1536,690),'#29362f');draw=ImageDraw.Draw(board)
    for row,(unit,label) in enumerate([('slinger','Slingshot Man'),('spearman','Wooden Spearman'),('healer','Healer')]):
        action=manifest['units'][unit][frame//8]
        draw.text((12,row*230+8),f'{label} / {action}',font=font,fill='#efdfbe')
        for col,direction in enumerate(manifest['directions']):
            im=Image.open(ROOT/'art/outlined_units/frames'/unit/action/direction/f'{frame%8:02}.png').convert('RGBA')
            board.paste(im,(col*192,row*230+28),im)
            draw.text((col*192+83,row*230+204),direction,font=font,fill='#efdfbe')
    frames.append(board)
frames[0].save(ROOT/'art/outlined_units/infantry-directions.gif',save_all=True,append_images=frames[1:],duration=140,loop=0)
frames[0].save(ROOT/'art/outlined_units/infantry-directions.png')
frames[20].save(ROOT/'art/outlined_units/infantry-actions.png')
print('PASS: three new units produced, eight-direction assets, healing/facing, stone projectile, gameplay render, save/load and post-load render.')
