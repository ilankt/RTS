"""Render a before/after comparison of actual in-game selection markers."""
from pathlib import Path
import os,sys,json,random
ROOT=Path(__file__).resolve().parents[2]
os.chdir(ROOT);sys.path.insert(0,str(ROOT))
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from PIL import Image,ImageDraw,ImageFont
from core.game import Game
from core.config import MAP_VIEW_WIDTH,MAP_VIEW_HEIGHT
random.seed(4321)
game=Game(mode='human_1v1',player_count=2)
castle=next(b for b in game.buildings if b.name=='castle' and b.player.human)
worker=next(u for u in game.units if u.name=='worker' and u.player.human)
data=next(u for u in json.loads((ROOT/'data/units.json').read_text()) if u['name']=='warrior')
castle.current_production={'unit_type':'warrior','unit_data':data}
game.production_manager._complete_production(castle)
clubman=next(u for u in game.units if u.name=='warrior')
for i,u in enumerate([worker,clubman]):
    u.x=castle.x+125+i*65;u.y=castle.y+30
    u.status='idle';u.facing_direction=6;u.selected=True
    game.fog_of_war.reveal_home_area(u.player,u.x,u.y)
game.selection_manager.selected_objects=[worker,clubman]
game.camera.zoom=2
center_x=(worker.x+clubman.x)/2;center_y=worker.y
game.camera.x=MAP_VIEW_WIDTH/2-center_x*2;game.camera.y=MAP_VIEW_HEIGHT/2-center_y*2
game.game_map.scale_tiles(2)
draw_markers=game.selection_manager.draw_selection_circles
game.rendering_system._draw_fog_overlay = lambda *args: None  # Compare in clear visibility.
captures=[]
for active in [False,True]:
    game.selection_manager.draw_selection_circles = draw_markers if active else (lambda *args: None)
    game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
    if not active:
        draw_markers(game.map_surface,game.camera)
    crop=game.map_surface.subsurface(pygame.Rect(MAP_VIEW_WIDTH//2-150,MAP_VIEW_HEIGHT//2-85,300,150))
    captures.append(Image.frombytes('RGB',crop.get_size(),pygame.image.tobytes(crop,'RGB')))
board=Image.new('RGB',(640,210),'#24312d');draw=ImageDraw.Draw(board)
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',19)
for i,label in enumerate(['Before: ring over feet','Fixed: feet over ring']):
    draw.text((i*320+12,12),label,font=font,fill='#efdfbe')
    board.paste(captures[i],(i*320+10,49))
board.save(ROOT/'art/outlined_units/ring-occlusion.png')
pygame.quit()
print('Saved verified marker comparison.')
