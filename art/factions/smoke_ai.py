"""Seeded Bronze-age AI scenario to exercise both faction units."""
import os,sys,random,copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.chdir(ROOT)
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
from core.game import Game
random.seed(8934)
g=Game(mode='ai_spectator',player_count=2,map_size=(50,50));g.game_speed=5
for i,p in enumerate(g.players):
    p.resources=dict(food=12000,wood=12000,gold=12000)
    p.upgrades['bronze_age']=g.game_data['techs']['bronze_age'];p.upgrades_version+=1
    home=next(b for b in g.buildings if b.player is p and b.name=='castle')
    for k,name in enumerate(['barracks','stable','house','house','house','house']):
        b=copy.deepcopy(g.game_data['buildings'][name]);b.player=p
        b.x=home.x+(k%3-1)*160;b.y=home.y+200+(k//3)*160
        g.buildings.append(b)
g.pathfinder.mark_dirty()
chosen={p.name:set() for p in g.players};kite_samples=0
for n in range(2400):
    g.update(delta_time_override=1/60)
    for p in g.players:
        goal=g.ai_system.last_chosen_action.get(p)
        if goal:chosen[p.name].add(goal.name)
    kite_samples+=sum(getattr(u,'_kite_remaining',0)>0 for u in g.units)
stats={f'{p}:{u}':n for (p,u),n in g.stats_units_trained.items()}
assert any(k.endswith(':horse_archer') and n>0 for k,n in stats.items()),stats
assert any(k.endswith(':axeman') and n>0 for k,n in stats.items()),stats
for p in g.players:
    forbidden='axeman' if p.faction=='steppe' else 'horse_archer'
    assert not any(u.player is p and u.name==forbidden for u in g.units)
report=dict(seconds=g.sim_time_elapsed,factions={p.name:p.faction for p in g.players},trained=stats,
            chosen={p:sorted(names) for p,names in chosen.items()},kite_samples=kite_samples)
(ROOT/'art/factions/integration/ai-smoke.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
