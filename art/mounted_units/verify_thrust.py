"""Check the saved attack moves its spear along a fixed axis, not an arc."""
from pathlib import Path
import bpy
from mathutils import Vector
OUT=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(OUT/'mounted_spearman.blend'))
scene=bpy.context.scene;spear=bpy.data.objects['Rider wooden spear'];hand=bpy.data.objects['Rider spear hand']
tips=[];directions=[]
for frame in range(17,25):
    scene.frame_set(frame);bpy.context.view_layer.update()
    grip=spear.matrix_world.translation
    assert (grip-hand.matrix_world.translation).length<.0001
    tip=spear.matrix_world @ Vector((0,0,1.85))
    tips.append(tip);directions.append((tip-grip).normalized())
axis=directions[0]
for tip,direction in zip(tips,directions):
    assert direction.dot(axis)>.99999
    movement=tip-tips[0]
    assert (movement-axis*movement.dot(axis)).length<.0001
assert (tips[4]-tips[2]).dot(axis)>.30
assert (tips[-1]-tips[0]).length<.0001
print('PASS: spear stays aligned, translates along its axis, remains in the hand and returns to guard.')
