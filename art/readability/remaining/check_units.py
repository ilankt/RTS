"""Remaining infantry: visible evaluated meshes, grips and string attachments."""
import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
from check_clearance import geometry,collision

ROOTS={'slinger':'Forked wooden slingshot','archer':'Bow','crossbowman':'Crossbow','spearman':'Wooden spear','bronze_spearman':'Bronze spear','pikeman':'Pike','healer':'Healing staff','priest':'Healing staff'}

def intentional(unit,part,target,shield):
    name=part.name;body=target.name
    if shield:return body in ['Forearm','Fist','Wrist binding']
    if unit=='slinger':
        return (name=='Grip' and body in ['Fist','Wrist binding']) or (name.startswith(('Sling band','Elastic pouch')) and body in ['Fist.001','Wrist binding.001'])
    if unit in ['archer','crossbowman']:
        if name.startswith('Draw string'):return body in ['Weapon grip hand.001','Wrist wrap.001']
        if name.startswith(('Projectile shaft','Projectile fletching')):return body.startswith(('Weapon grip hand','Wrist wrap'))
        if name.startswith(('Bow grip','Curved wooden bow','Bow limb','Continuous wooden bow')):return body in ['Weapon grip hand','Wrist wrap']
        if name in ['Crossbow stock','Bolt rail','Trigger lever']:return body.startswith(('Weapon grip hand','Wrist wrap'))
        return False
    return name.startswith(('Spear shaft','Wood shaft','Spear grip binding','Staff shaft','Staff grip binding')) and body in ['Weapon grip hand','Wrist wrap','Fist.001','Wrist binding.001']

results=[]
for path in sorted((OUT/'models').glob('*.blend')):
    unit=path.stem.removesuffix('_option_b');meta=json.loads(path.with_name(unit+'.json').read_text())
    if '--group' in sys.argv and meta['group']!=sys.argv[sys.argv.index('--group')+1]:continue
    bpy.ops.wm.open_mainfile(filepath=str(path));scene=bpy.context.scene
    root=bpy.data.objects[ROOTS[unit]]
    shield=bpy.data.objects.get('Left-hand wooden buckler')
    equipment={o:False for o in root.children_recursive if o.type in ['MESH','CURVE']}
    if shield:equipment.update({o:True for o in shield.children_recursive if o.type=='MESH'})
    bodies=[o for o in scene.objects if o.type=='MESH' and o not in equipment]
    pairs=[];exclusions=[]
    for part,is_shield in equipment.items():
        for target in bodies:
            if intentional(unit,part,target,is_shield):exclusions.append([part.name,target.name])
            else:pairs.append((part,target))
    if shield:pairs += [(a,b) for a,s in equipment.items() if not s for b,s2 in equipment.items() if s2]
    hits={};count=0;grips=0;connections=0;connection_errors=[]
    markers=sorted(scene.timeline_markers,key=lambda m:m.frame)
    for a,marker in enumerate(markers):
        end=markers[a+1].frame-1 if a+1<len(markers) else scene.frame_end
        for step in range((end-marker.frame)*8+1):
            t=marker.frame+step/8;scene.frame_set(int(t),subframe=t%1);graph=bpy.context.evaluated_depsgraph_get()
            active=[(p,b) for p,b in pairs if not p.hide_render and not b.hide_render]
            cache={o:geometry(o,graph) for o in set(o for pair in active for o in pair)}
            for part,target in active:
                count+=1
                if collision(cache[part],cache[target]):hits.setdefault((marker.name,part.name,target.name),[]).append(t)
            hand=bpy.data.objects['Fist' if unit=='slinger' else 'Fist.001' if unit=='spearman' else 'Weapon grip hand']
            local=Vector((-.03,-.02,-.08 if unit=='crossbowman' else 0)) if unit in ['archer','crossbowman'] else Vector((0,0,0))
            assert ((root.matrix_world@local)-hand.matrix_world.translation).length<.001,(unit,t,'grip')
            grips+=1
            if unit=='archer':
                for string_name,index in [('Draw string',0),('Draw string.001',16)]:
                    string=bpy.data.objects[string_name];limb=bpy.data.objects['Continuous wooden bow']
                    end=limb.matrix_world@limb.data.splines[0].points[index].co.to_3d()
                    if ((string.matrix_world@Vector((0,0,-.5)))-end).length>=.002:connection_errors.append([t,'bow string'])
                    connections+=1
            if unit=='crossbowman':
                for side,name in [(-1,'Draw string'),(1,'Draw string.001')]:
                    if ((bpy.data.objects[name].matrix_world@Vector((0,0,-.5)))-(root.matrix_world@Vector((side*.48*1.35,-.26,0)))).length>=.002:connection_errors.append([t,'crossbow string'])
                    connections+=1
            if unit=='slinger':
                for side,name in [(-1,'Sling band'),(1,'Sling band.001')]:
                    band=bpy.data.objects[name];depth=max(v.co.z for v in band.data.vertices)-min(v.co.z for v in band.data.vertices)
                    if ((band.matrix_world@Vector((0,0,-depth/2)))-(root.matrix_world@Vector((side*.24,0,.47)))).length>=.002:connection_errors.append([t,'sling band'])
                    connections+=1
    results.append(dict(unit=unit,group=meta['group'],pair_checks=count,grip_checks=grips,connection_checks=connections,connection_errors=connection_errors,intentional_contacts=exclusions,collisions=[dict(action=k[0],part=k[1],target=k[2],times=v) for k,v in hits.items()]))
report='clearance-'+sys.argv[sys.argv.index('--group')+1]+'.json' if '--group' in sys.argv else 'clearance.json'
(OUT/report).write_text(json.dumps(results,indent=2))
for r in results:
    print(r['unit'],r['pair_checks'],len(r['collisions']),'collision groups')
    if r['connection_errors']:print('CONNECTION_ERRORS',r['connection_errors'][:10])
    for c in r['collisions']:print(c['action'],c['part'],c['target'],c['times'][0],c['times'][-1])
if '--strict' in sys.argv:assert not any(r['collisions'] or r['connection_errors'] for r in results)
