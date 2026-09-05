"""Measure the ground origin projected by the saved Blender cameras."""
import bpy
import json
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
OUT=Path(__file__).resolve().parent
path=OUT/'manifest.json'
manifest=json.loads(path.read_text())
anchors={}
for unit in ['clubman','worker']:
    bpy.ops.wm.open_mainfile(filepath=str(OUT/f'{unit}.blend'))
    scene=bpy.context.scene
    scene.frame_set(1)
    point=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
    anchors[unit]=[round(point.x,6),round(1-point.y,6)]
manifest['ground_anchors']=anchors
path.write_text(json.dumps(manifest,indent=2))
print('GROUND ANCHORS',anchors)
