"""Audit visible moving equipment against heads and torsos at sub-frame poses.

Intentional joints (hands holding weapons, armor sitting on clothing) are not
collision pairs. Checks use evaluated mesh triangles, not just object origins.
"""
import bpy
import json
from pathlib import Path
from mathutils.bvhtree import BVHTree

OUT=Path(__file__).resolve().parent
REPORT=[]
CHECKS=0

def geometry(obj,graph):
    evaluated=obj.evaluated_get(graph)
    data=evaluated.to_mesh()
    vertices=[evaluated.matrix_world @ v.co for v in data.vertices]
    faces=[tuple(p.vertices) for p in data.polygons]
    evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(vertices,faces), vertices

for path in sorted((OUT/'models').glob('*.blend')):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene=bpy.context.scene
    meshes=[o for o in scene.objects if o.type=='MESH']
    heads=[o for o in meshes if o.name in ['Face','Hair cap','Cloth cap','Cap brim','Hood','Open-face helmet','Elongated face','Compact flattened muzzle','Neck','Nose'] or o.name.startswith('Helmet cheek guard')]
    torsos=[o for o in meshes if o.name in ['Blue sleeveless tunic','Cream robe','Apron bib','Horse barrel','Sloping horse neck','Buckler wood','Buckler dark rim','Bolt bed'] or o.name.startswith(('Heavy frame cheek','Bolt guide rail','Timber chassis runner'))]
    roots=[o for o in scene.objects if o.name in ['Pickaxe','Building hammer','Sword grip','Bronze spear','Pike','Bow','Crossbow','Healing staff','Rider wooden spear','Siege bolt']]
    equipment=[o for o in meshes if any(o in root.children_recursive for root in roots)]
    equipment += [o for o in meshes if o.name.startswith(('Spare arrow','Quiver fletching'))]
    equipment += [o for o in meshes if o.name.startswith(('Wheel rim','Wheel spoke'))]
    arms=[o for o in meshes if o.name.startswith(('Articulated upper arm','Articulated forearm','Weapon grip hand'))]
    collisions={}
    for marker in scene.timeline_markers:
        for sample in range(65):
            time=marker.frame+sample/4
            scene.frame_set(int(time),subframe=time%1)
            graph=bpy.context.evaluated_depsgraph_get()
            targets={o:geometry(o,graph) for o in heads+torsos}
            for obj in equipment+arms:
                if obj.hide_render: continue
                shape,vertices=geometry(obj,graph)
                for target,(other,_) in targets.items():
                    if obj in arms and target in torsos: continue
                    CHECKS+=1
                    overlaps=shape.overlap(other)
                    if overlaps:
                        key=(marker.name,obj.name,target.name)
                        collisions.setdefault(key,[]).append(round(time,2))
    REPORT.append(dict(unit=path.stem,mesh_names=[o.name for o in meshes],heads=[o.name for o in heads],torsos=[o.name for o in torsos],
                       collisions=[dict(action=k[0],part=k[1],target=k[2],times=v) for k,v in collisions.items()]))

(OUT/'clearance-report.json').write_text(json.dumps(dict(checks=CHECKS,units=REPORT),indent=2))
for unit in REPORT:
    print(unit['unit'],[(c['action'],c['part'],c['target'],c['times'][0]) for c in unit['collisions']])
print('Mesh pair checks:',CHECKS)
assert all(not unit['collisions'] for unit in REPORT),'See clearance-report.json for intersections'
