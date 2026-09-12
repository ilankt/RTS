"""Install the approved faction models' exact sheets and content definitions."""
import json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'art/factions'
units=json.loads((ROOT/'data/units.json').read_text())
art=json.loads((ROOT/'data/age_units.json').read_text())
specs={
    'horse_archer':dict(display_name='Horse Archer',role='Steppe ranged cavalry: fast raider; vulnerable to spears',requires=['stable'],hp=190,movement_speed=90,min_damage=14,max_damage=18,attack_range=180,attack_speed=1.0,attack_type='pierce',armor_type='light',armor_value=1,costs={'gold':100,'wood':60,'food':130},build_time=13,strong_against=['worker','axeman'],weak_against=['spearman','cavalry','watchtower'],collision_radius=14),
    'axeman':dict(display_name='Axeman',role='Highland shock infantry: breaks sword infantry; vulnerable to ranged fire',requires=['barracks'],hp=220,movement_speed=52,min_damage=28,max_damage=34,attack_range=48,attack_speed=1.0,attack_type='slash',armor_type='light',armor_value=1,costs={'gold':75,'food':90},build_time=10,strong_against=['warrior'],counter_multiplier=3.25,weak_against=['archer','horse_archer'],collision_radius=8),
}
for name,spec in specs.items():
    meta=json.loads((OUT/'models'/f'{name}.json').read_text())
    folder=ROOT/'assets/sprites/Units/Factions'/name;folder.mkdir(parents=True,exist_ok=True)
    animations={}
    for action in meta['actions']:
        shutil.copy2(OUT/'sheets'/name/f'{action}.png',folder/f'{action}.png')
        animations[action]=(folder/f'{action}.png').relative_to(ROOT).as_posix()
    icon=ROOT/'assets/ui/Units/Factions'/f'{name}.png';icon.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(OUT/'portraits'/f'{name}.png',icon)
    spec.update(name=name,size=[1,1],can_build=False,can_attack=True,buildable=True,animations=animations,animation_directions=8,animation_fps=20,ground_anchor=meta['ground_anchor'],render_scale=meta['render_scale'],icon=icon.relative_to(ROOT).as_posix(),projectile_type='arrow')
    units=[u for u in units if u['name']!=name];units.append(spec)
    art[name]=dict(name=spec['display_name'],animations=animations,icon=spec['icon'],frame_size=192,fps=20,frames_per_direction=16,animation_directions=8,ground_anchor=meta['ground_anchor'],render_scale=meta['render_scale'])
for u in units:
    if u['name']=='spearman' and 'horse_archer' not in u['strong_against']:u['strong_against'].append('horse_archer')
    if u['name']=='cavalry' and 'horse_archer' not in u['strong_against']:u['strong_against'].append('horse_archer')
(ROOT/'data/units.json').write_text(json.dumps(units,indent=2)+'\n')
(ROOT/'data/age_units.json').write_text(json.dumps(art,indent=2)+'\n')
techs=json.loads((ROOT/'data/techs.json').read_text())
for tech in techs:
    if tech.get('building')!='blacksmith':continue
    for table in tech.get('effects',{}).values():
        if not isinstance(table,dict):continue
        for new,source in [('axeman','warrior'),('horse_archer','archer')]:
            if source in table:table[new]=dict(table[source])
(ROOT/'data/techs.json').write_text(json.dumps(techs,indent=2)+'\n')
print('Installed approved faction sprites and content.')
