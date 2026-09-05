import os, sys, json, random
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R))
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from core.game import Game
from managers.save_manager import SaveManager
random.seed(4321)
game=Game(mode='ai_spectator',player_count=2)
castle=next(b for b in game.buildings if b.name=='castle')
data=next(u for u in json.loads((R/'data/units.json').read_text()) if u['name']=='warrior')
castle.current_production={'unit_type':'warrior','unit_data':data}
game.production_manager._complete_production(castle)
u=next(u for u in game.units if u.name=='warrior')
assert u.animations['run'].direction_count==8
assert not u.sprite_mirrored
for _ in range(5):
    game.update(delta_time_override=1/60)
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
pygame.image.save(game.screen,str(R/'art/clubman/game-smoke.png'))
SaveManager.SAVE_DIR=str(R/'art/clubman/test-saves')
SaveManager.save_game(game,slot=0)
ok,message=SaveManager.load_game(game,slot=0)
assert ok,message
u=next(u for u in game.units if u.name=='warrior')
assert all(a.direction_count==8 for a in u.animations.values())
assert len(u.animations['attack'].frames)==8
game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
pygame.quit()
print('PASS: clubman production, full game render, save/load, and post-load render.')
