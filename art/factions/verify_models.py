"""Sampled review geometry audit using the project's evaluated-mesh checks."""
import bpy,sys,json,math
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent/'readability'))
from check_clearance import geometry,collision
results=[]
for unit in ['horse_archer','axeman']:
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'models'/f'{unit}.blend'))
    s=bpy.context.scene
    if unit=='axeman':
        equipment=[o for o in bpy.data.objects['Two handed axe'].children_recursive if o.type=='MESH']
        body=[o for o in s.objects if o.type=='MESH' and o not in equipment]
        pairs=[(a,b) for a in equipment for b in body if not (a.name.startswith(('Axe haft','Axe leather binding')) and b.name.startswith(('Axe hand','Axe wrist')))]
    else:
        equipment=[o for o in s.objects if o.type in ['MESH','CURVE'] and o.name.startswith('HA ')]
        body=[o for o in s.objects if o.type=='MESH' and not o.name.startswith(('HA ','Rider thigh','Rider shin','Rider boot','Stirrup','Wood stirrup','Rider leather cap','Vest'))]
        # Audit new upper body against horse and tack; inherited bow/arm mechanics unchanged.
        pairs=[(a,b) for a in equipment for b in body]
    hits={};checks=0;max_grip_error=0;loops=[];max_arm_length_error=0
    for start in [1,18,35]:
        first=None
        for k in range(65):
            t=start+k/4;s.frame_set(int(t),subframe=t%1)
            graph=bpy.context.evaluated_depsgraph_get()
            objects={o for pair in pairs for o in pair if not o.hide_render}
            cache={o:geometry(o,graph) for o in objects}
            for a,b in pairs:
                if a not in cache or b not in cache:continue
                checks+=1
                if collision(cache[a],cache[b]):hits.setdefault((a.name,b.name),[]).append(round(t,2))
            if unit=='axeman':
                axe=bpy.data.objects['Two handed axe']
                for side,z in [(1,0),(-1,-.24)]:
                    err=(axe.matrix_world@Vector((0,0,z))-bpy.data.objects['Axe hand '+str(side)].matrix_world.translation).length
                    max_grip_error=max(max_grip_error,err)
                    hand=bpy.data.objects['Axe hand '+str(side)]
                    upper=bpy.data.objects['Axe upper arm '+str(side)]
                    fore=bpy.data.objects['Axe forearm '+str(side)]
                    elbow=upper.location+upper.rotation_euler.to_matrix()@Vector((0,0,upper.scale.z/2))
                    assert abs(hand.location.x)<.20 and hand.location.y<-.40,(t,side,'off-center grip')
                    assert side*elbow.x>.12,(t,side,'elbow crosses torso')
                    max_arm_length_error=max(max_arm_length_error,abs(upper.scale.z-.43),abs(fore.scale.z-.23))
                    assert max_arm_length_error<.0001,(t,side,'arm stretching')
            else:
                bow=bpy.data.objects['HA Bow'];hand=bpy.data.objects['HA Weapon grip hand']
                err=(bow.matrix_world@Vector((-.03,-.02,0))-hand.matrix_world.translation).length
                max_grip_error=max(max_grip_error,err)
            signature={o.name:tuple(v for row in o.matrix_world for v in row) for o in s.objects if o.type=='MESH'}
            if k==0:first=signature
            if k==64:loops.append(max(abs(a-b) for n in first for a,b in zip(first[n],signature[n])))
    cutting=[]
    if unit=='axeman':
        axe=bpy.data.objects['Two handed axe']
        for t in [41.25,41.5,41.75,42,42.25,42.5,42.75]:
            positions=[]
            for dt in [-.01,.01]:
                s.frame_set(int(t+dt),subframe=(t+dt)%1);bpy.context.view_layer.update()
                positions.append(axe.matrix_world@Vector((0,-.58,.75)))
            s.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
            cutting.append((positions[1]-positions[0]).normalized().dot((axe.matrix_world.to_3x3()@Vector((0,-1,0))).normalized()))
        assert min(cutting)>.5,cutting
    result=dict(unit=unit,samples=195,pair_checks=checks,max_grip_error=max_grip_error,max_arm_length_error=max_arm_length_error,loop_transform_errors=loops,cutting_edge_alignment=cutting,
                collisions=[dict(part=a,target=b,times=ts) for (a,b),ts in hits.items()])
    results.append(result)
    print(unit,'checks',checks,'collision pairs',len(hits),'grip',max_grip_error,'loops',loops,flush=True)
(OUT/'geometry-checks.json').write_text(json.dumps(results,indent=2))
if any(r['collisions'] or r['max_grip_error']>.001 or max(r['loop_transform_errors'])>.001 for r in results):
    raise RuntimeError('Review geometry needs correction; see geometry-checks.json')
