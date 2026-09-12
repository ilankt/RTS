"""Render review-only scenes. --quick gives two close-ups per unit."""
import bpy,json,math,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
DIRS=dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135)
for unit in ['horse_archer','axeman']:
    if '--unit' in sys.argv and sys.argv[sys.argv.index('--unit')+1]!=unit:continue
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'models'/f'{unit}.blend'))
    s=bpy.context.scene;meta=json.loads((OUT/'models'/f'{unit}.json').read_text())
    quick='--quick' in sys.argv
    s.render.resolution_x=s.render.resolution_y=640 if quick else 192
    for a,action in enumerate(meta['actions']):
        if quick and a!=(2 if '--attack-details' in sys.argv else 0):continue
        for d,angle in DIRS.items():
            if quick and d not in (['E','SE','S','NW'] if unit=='axeman' else ['SE','NW']):continue
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            folder=OUT/('details' if quick else 'frames')/unit/action/d;folder.mkdir(parents=True,exist_ok=True)
            for i in ([0,4,6,8,10,14] if quick and '--pose-strip' in sys.argv else [8] if quick and '--attack-details' in sys.argv else [0] if quick else range(16)):
                target=folder/f'{i:02}.png'
                if '--resume' in sys.argv and target.exists():continue
                s.frame_set(a*17+i+1);s.render.filepath=str(target);bpy.ops.render.render(write_still=True)
        print('FACTION_RENDER',unit,action,flush=True)
