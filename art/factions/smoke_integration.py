"""Actual game recruitment, save/load, rendering and short AI use smoke."""
import os,sys,json,copy,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from core.game import Game
from core.config import MAP_VIEW_WIDTH,MAP_VIEW_HEIGHT
from managers.save_manager import SaveManager
from screens.match_setup import MatchSetupScreen
OUT=ROOT/'art/factions/integration';OUT.mkdir(exist_ok=True)
random.seed(2841)
g=Game(mode='human_1v1',player_count=2,map_size=(40,40))
g.fog_of_war_enabled=False
recruits=[]
for i,(unit,producer) in enumerate([('horse_archer','stable'),('axeman','barracks')]):
    p=g.players[i];p.resources=dict(food=10000,gold=10000,wood=10000)
    p.upgrades['bronze_age']=g.game_data['techs']['bronze_age'];p.upgrades_version+=1
    castle=next(b for b in g.buildings if b.player is p and b.name=='castle')
    b=copy.deepcopy(g.game_data['buildings'][producer]);b.player=p;b.x=castle.x+180;b.y=castle.y+100
    g.buildings.append(b)
    assert g.production_manager.start_production(b,unit)[0]
    g.production_manager._update_building_production(b,20)
    u=next(u for u in g.units if u.name==unit);u.hp=137;recruits.append(u)
    assert g.production_manager.start_production(b,unit)[0]
    assert g.production_manager.start_production(b,unit)[0]
    g.production_manager._update_building_production(b,2)
    assert u._age_art==unit and u.animations['idle'].animation_speed==50
old_dir=SaveManager.SAVE_DIR;SaveManager.SAVE_DIR=str(ROOT/'_gen/faction-save-smoke')
try:
    save=SaveManager.save_game(g,slot=0)
    data=json.loads(Path(save).read_text());assert data['version']==8
    g.players[0].faction='highland';g.players[1].faction='steppe'
    ok,msg=SaveManager.load_game(g,slot=0);assert ok,msg
    assert [p.faction for p in g.players]==['steppe','highland']
    for name in ['horse_archer','axeman']:
        u=next(u for u in g.units if u.name==name)
        assert u.hp==137 and u._age_art==name and u.animations['idle'].animation_speed==50
        b=next(b for b in g.buildings if b.current_production and b.current_production['unit_type']==name)
        assert b.production_queue==[name] and b.current_production['progress']==2
    # A v7 save with no faction fields gets a deterministic migration.
    data['version']=7
    for p in data['players']:p.pop('faction',None)
    legacy=Path(SaveManager.SAVE_DIR)/'save_1.json';legacy.write_text(json.dumps(data))
    ok,msg=SaveManager.load_game(g,slot=1);assert ok,msg
    assert [p.faction for p in g.players]==['steppe','highland']
finally:SaveManager.SAVE_DIR=old_dir
for name in ['horse_archer','axeman']:
    u=next(u for u in g.units if u.name==name)
    g.camera.zoom=2;g.camera.x=MAP_VIEW_WIDTH/2-u.x*2;g.camera.y=MAP_VIEW_HEIGHT/2-u.y*2
    g.selection_manager.selected_objects=[u];u.selected=True
    g.draw();pygame.image.save(g.screen,OUT/f'{name}-game.png');u.selected=False
setup=MatchSetupScreen(g.screen);setup.draw();pygame.image.save(g.screen,OUT/'match-setup.png')
for _ in range(180):g.update(delta_time_override=1/60)
(OUT/'smoke.json').write_text(json.dumps(dict(recruitment=True,save_v8=True,legacy_v7=True,wounds_preserved=True,queues_preserved=True,rendered=True,post_load_updates=180,factions=[p.faction for p in g.players]),indent=2))
print('Faction recruitment, v8/legacy saves, queues, HP, sprites and game rendering passed.')
pygame.quit()
