"""Render working-edge contact against an ore mound and practice targets.

Review-only props: never included in the production sprite sheets.
"""
import bpy
import math
import sys
from pathlib import Path
from mathutils import Vector

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from render import ball, rod, material

for unit in ['bronze_worker','bronze_swordsman','bronze_spearman']:
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'models'/f'{unit}.blend'))
    scene=bpy.context.scene; facing=bpy.data.objects['Facing']
    wood=bpy.data.materials['1_cartoon wood']; linen=bpy.data.materials['1_cartoon linen']
    if unit=='bronze_worker':
        rock=material('Review rock','777A66'); gold=material('Review ore','CDA94E')
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1)
        obj=bpy.context.object;obj.name='Review ore mound';obj.parent=facing
        obj.location=(0,-1.32,.30);obj.scale=(.35,.40,.33);obj.data.materials.append(rock)
        for x,y,z in [(0,-1.27,.60),(.15,-1.30,.53),(-.16,-1.23,.49),(.10,-1.04,.40)]:
            ball('Exposed ore',(x,y,z),(.08,.075,.04),gold,facing)
    else:
        y=-1.70 if unit=='bronze_swordsman' else -2.30
        rod('Target post',(0,y,0),(0,y,1.45),.07,.07,wood,facing)
        ball('Straw target torso',(0,y,1.0),(.27,.18,.35),linen,facing)
        ball('Straw target head',(0,y,1.49),(.19,.17,.19),linen,facing)
        for side in [-1,1]:
            rod('Target crossbar',(0,y,1.16),(side*.36,y,1.16),.055,.055,wood,facing)
    for direction,angle in [('E',90),('SE',45)]:
        facing.rotation_euler.z=math.radians(angle)
        folder=OUT/'contact-frames'/unit/direction;folder.mkdir(parents=True,exist_ok=True)
        for i in range(16):
            scene.frame_set(35+i);scene.render.filepath=str(folder/f'{i:02}.png')
            bpy.ops.render.render(write_still=True)
    print('CONTACT_REVIEW',unit,flush=True)
