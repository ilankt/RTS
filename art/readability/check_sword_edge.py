"""Verify the copied Clubman timing and sharp-edge-leading impact motion."""
import bpy
import json
from pathlib import Path
from mathutils import Vector

OUT=Path(__file__).resolve().parent

def at(t):
    bpy.context.scene.frame_set(int(t),subframe=t%1)
    bpy.context.view_layer.update()

bpy.ops.wm.open_mainfile(filepath=str(OUT/'models/clubman_option_b.blend'))
reference=[]
for i in range(8):
    at(17+i)
    reference.append({name:tuple(bpy.data.objects[name].rotation_euler) for name in ['Body','Shoulder','Shoulder.001','Hip','Hip.001']})
results=[]
for unit in ['bronze_swordsman','iron_swordsman']:
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'models'/f'{unit}_option_b.blend'))
    for i,pose in enumerate(reference):
        at(35+i*2)
        for name,rot in pose.items():
            assert (Vector(bpy.data.objects[name].rotation_euler)-Vector(rot)).length<1e-4,(unit,i,name)
    sword=bpy.data.objects['Sword grip']
    samples=[]
    # Main downswing: the original Clubman's windup-to-impact-to-follow-through.
    for i in range(33):
        t=41+i/8
        at(t-.02); before=sword.matrix_world@Vector((0,0,1.0))
        at(t+.02); after=sword.matrix_world@Vector((0,0,1.0))
        at(t)
        matrix=sword.matrix_world.to_3x3()
        axis=(matrix@Vector((0,0,1))).normalized()
        edge=(matrix@Vector((1,0,0))).normalized()
        face=(matrix@Vector((0,1,0))).normalized()
        velocity=after-before
        tangent=(velocity-axis*velocity.dot(axis)).normalized()
        alignment=abs(edge.dot(tangent));flat=abs(face.dot(tangent))
        # Frame 41 is the windup reversal. The powered stroke spans 42-45,
        # carrying the blade forward and down through the follow-through.
        if 42<=t<=45: assert alignment>.95 and flat<.32,(unit,t,alignment,flat)
        samples.append(dict(frame=t,edge_alignment=alignment,flat_face_alignment=flat))
    results.append(dict(unit=unit,clubman_pose_checks=40,min_strike_edge_alignment=min(s['edge_alignment'] for s in samples if s['frame']>=42),samples=samples))
(OUT/'sword-edge-checks.json').write_text(json.dumps(results,indent=2))
print([(r['unit'],r['min_strike_edge_alignment']) for r in results])
