"""Evaluated-mesh equipment clearance, including subframes and containment.

Only deliberate grip contacts and the shield-bearing forearm are excluded.
Body parts, clothes, helmet, opposite arm and equipment-to-equipment are checked.
Facing rotates the entire rig rigidly, so one facing suffices for 3D intersections.
"""
import bpy
import json
import sys
from collections import Counter
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT=Path(__file__).resolve().parent

def geometry(obj, graph):
    evaluated=obj.evaluated_get(graph)
    mesh=evaluated.to_mesh()
    verts=[evaluated.matrix_world@v.co for v in mesh.vertices]
    faces=[tuple(p.vertices) for p in mesh.polygons]
    edges=Counter(tuple(sorted((f[i],f[(i+1)%len(f)]))) for f in faces for i in range(len(f)))
    closed=all(n==2 for n in edges.values())
    evaluated.to_mesh_clear()
    lo=Vector(tuple(min(v[a] for v in verts) for a in range(3)))
    hi=Vector(tuple(max(v[a] for v in verts) for a in range(3)))
    return BVHTree.FromPolygons(verts,faces),verts,lo,hi,closed

def inside(point, tree):
    direction=Vector((.831,.371,.413)).normalized()
    origin=point.copy(); hits=0
    for _ in range(100):
        loc,normal,index,distance=tree.ray_cast(origin,direction)
        if loc is None: return hits%2==1
        hits+=1; origin=loc+direction*1e-5
    raise RuntimeError('Ray containment did not converge')

def collision(a,b):
    if any(a[3][k]<b[2][k] or b[3][k]<a[2][k] for k in range(3)): return False
    if a[0].overlap(b[0]): return True
    return (b[4] and inside(a[1][0],b[0])) or (a[4] and inside(b[1][0],a[0]))

def audit(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene=bpy.context.scene
    meshes=[o for o in scene.objects if o.type=='MESH' and not o.hide_render]
    roots=[bpy.data.objects.get(n) for n in ['Right-hand club','Sword grip','Left-hand wooden buckler']]
    groups={o:r.name for r in roots if r for o in r.children_recursive if o.type=='MESH'}
    equipment=list(groups)
    body=[o for o in meshes if o not in groups]
    pairs=[]; exclusions=[]
    for obj in equipment:
        for target in body:
            # Explicit attachment surfaces, never head/torso/other hand.
            intentional=(groups[obj]=='Left-hand wooden buckler' and target.name in ['Forearm','Fist','Wrist binding'])
            intentional |= (obj.name in ['Club haft'] and target.name in ['Fist.001','Wrist binding.001'])
            intentional |= (obj.name.startswith(('Leather sword grip','Hilt leather wrap','Sword pommel')) and target.name in ['Weapon grip hand','Wrist wrap'])
            if intentional: exclusions.append([obj.name,target.name])
            else: pairs.append((obj,target))
    pairs += [(a,b) for i,a in enumerate(equipment) for b in equipment[i+1:] if groups[a]!=groups[b]]
    hits={}; checks=0; samples=0; grips=0
    markers=sorted(scene.timeline_markers,key=lambda m:m.frame)
    for mi,marker in enumerate(markers):
        end=markers[mi+1].frame-1 if mi+1<len(markers) else scene.frame_end
        steps=8
        for sample in range((end-marker.frame)*steps+1):
            time=marker.frame+sample/steps
            scene.frame_set(int(time),subframe=time%1)
            graph=bpy.context.evaluated_depsgraph_get()
            cache={o:geometry(o,graph) for o in set(o for pair in pairs for o in pair)}
            for a,b in pairs:
                checks+=1
                if collision(cache[a],cache[b]):
                    hits.setdefault((marker.name,a.name,b.name),[]).append(time)
            if 'Sword grip' in bpy.data.objects:
                assert (bpy.data.objects['Sword grip'].matrix_world.translation-bpy.data.objects['Weapon grip hand'].matrix_world.translation).length<.001
            else:
                assert (bpy.data.objects['Right-hand club'].matrix_world.translation-bpy.data.objects['Fist.001'].matrix_world.translation).length<.001
            grips+=1; samples+=1
    return dict(unit=path.stem,samples=samples,pair_checks=checks,grip_checks=grips,
                intentional_contacts=exclusions,collisions=[dict(action=k[0],part=k[1],target=k[2],times=v) for k,v in hits.items()])

if __name__=='__main__':
    paths=sorted((OUT/'models').glob('*_option_b.blend'))
    if '--unit' in sys.argv: paths=[p for p in paths if p.stem==sys.argv[sys.argv.index('--unit')+1]+'_option_b']
    results=[audit(p) for p in paths]
    output=sys.argv[sys.argv.index('--report')+1] if '--report' in sys.argv else 'clearance.json'
    (OUT/output).write_text(json.dumps(results,indent=2))
    for result in results:
        print(result['unit'],result['pair_checks'],'pairs',len(result['collisions']),'collision groups')
        for c in result['collisions']: print(c['action'],c['part'],c['target'],c['times'][0],c['times'][-1])
    if '--strict' in sys.argv: assert not any(r['collisions'] for r in results)
