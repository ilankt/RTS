"""Actual evaluated mesh clearance, tool grips and working-edge directions."""
import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
from check_clearance import geometry,collision

results=[]
for path in sorted((OUT/'models').glob('*.blend')):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene=bpy.context.scene
    roots=[bpy.data.objects[n] for n in ['Pickaxe','Building hammer']]
    equipment={o:root for root in roots for o in root.children_recursive if o.type=='MESH'}
    bodies=[o for o in scene.objects if o.type=='MESH' and o not in equipment]
    pairs=[];intentional=[]
    for part in equipment:
        for target in bodies:
            if part.name.startswith(('Pick handle','Hammer handle','Pick grip binding')) and target.name.startswith(('Fist','Weapon grip hand','Wrist')):
                intentional.append([part.name,target.name]);continue
            pairs.append((part,target))
    hits={};count=0;grips=0
    markers=sorted(scene.timeline_markers,key=lambda m:m.frame)
    for a,marker in enumerate(markers):
        end=markers[a+1].frame-1 if a+1<len(markers) else scene.frame_end
        for step in range((end-marker.frame)*8+1):
            t=marker.frame+step/8
            scene.frame_set(int(t),subframe=t%1)
            graph=bpy.context.evaluated_depsgraph_get()
            active=[(p,b) for p,b in pairs if not p.hide_render and not b.hide_render]
            cache={o:geometry(o,graph) for o in set(o for pair in active for o in pair)}
            for p,b in active:
                count+=1
                if collision(cache[p],cache[b]):hits.setdefault((marker.name,p.name,b.name),[]).append(t)
            tool=bpy.data.objects['Building hammer' if marker.name=='build' else 'Pickaxe']
            hand=bpy.data.objects.get('Weapon grip hand.001') or bpy.data.objects['Fist.001']
            assert (tool.matrix_world.translation-hand.matrix_world.translation).length<.001,(path.name,t,'grip')
            grips+=1
    results.append(dict(unit=path.stem,pair_checks=count,grip_checks=grips,intentional_contacts=intentional,collisions=[dict(action=k[0],part=k[1],target=k[2],times=v) for k,v in hits.items()]))
(OUT/'clearance.json').write_text(json.dumps(results,indent=2))
for r in results:
    print(r['unit'],r['pair_checks'],len(r['collisions']),'collision groups')
    for c in r['collisions']:print(c['action'],c['part'],c['target'],c['times'][0],c['times'][-1])
if '--strict' in sys.argv: assert not any(r['collisions'] for r in results)
