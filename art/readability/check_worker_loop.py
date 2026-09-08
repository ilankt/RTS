import bpy,json
from pathlib import Path
OUT=Path(__file__).resolve().parent
result=[]
for unit in ['worker','bronze_worker','iron_worker']:
 bpy.ops.wm.open_mainfile(filepath=str(OUT/'workers/models'/f'{unit}_option_b.blend'))
 stride=8 if unit=='worker' else 17
 for a in [2,3]:
  names=[o.name for o in bpy.context.scene.objects if o.name.startswith(('Articulated','Wrist wrap','Weapon grip'))]
  frames=[a*stride+1,a*stride+(8 if unit=='worker' else 15),a*stride+(8.5 if unit=='worker' else 16)]
  poses=[]
  for t in frames:
   bpy.context.scene.frame_set(int(t),subframe=t%1);poses.append({n:(bpy.data.objects[n].location.copy(),bpy.data.objects[n].rotation_euler.to_quaternion()) for n in names})
  diffs={n:[round((poses[k][n][0]-poses[0][n][0]).length,5) for k in [1,2]] for n in names}
  result.append(dict(unit=unit,action=a,frames=frames,differences=diffs))
  first=poses[0]
  for i in range(17):
   t=a*stride+(8 if unit=='worker' else 15)+i/16
   bpy.context.scene.frame_set(int(t),subframe=t%1)
   for n,(p,q) in first.items():
    o=bpy.data.objects[n]
    assert (o.location-p).length<1e-5 and abs(o.rotation_euler.to_quaternion().dot(q))>.99999,(unit,a,t,n)
(OUT/'motion-feedback/worker-loop.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
