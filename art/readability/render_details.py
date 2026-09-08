"""Higher-resolution model close-ups; gameplay-size rows use 192 px sprites."""
import bpy
import math
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
for unit in ['clubman','bronze_swordsman','iron_swordsman']:
    for variant in ['original','B']:
        source=(OUT/'models'/f'{unit}_option_b.blend') if variant=='B' else ROOT/('art/outlined_units/clubman.blend' if unit=='clubman' else f'art/ages/units/models/{unit}.blend')
        bpy.ops.wm.open_mainfile(filepath=str(source))
        scene=bpy.context.scene
        scene.frame_set(1)
        scene.render.resolution_x=scene.render.resolution_y=768
        scene.render.resolution_percentage=100
        for direction, angle in [('SE',45),('NW',225)]:
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            folder=OUT/'details'/unit/variant
            folder.mkdir(parents=True,exist_ok=True)
            scene.render.filepath=str(folder/f'{direction}.png')
            bpy.ops.render.render(write_still=True)
