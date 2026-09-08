import bpy
import math
import sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
for unit in ['worker','bronze_worker','iron_worker']:
    if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]:continue
    for variant in ['original','B']:
        source=OUT/'models'/f'{unit}_option_b.blend' if variant=='B' else ROOT/('art/outlined_units/worker.blend' if unit=='worker' else f'art/ages/units/models/{unit}.blend')
        bpy.ops.wm.open_mainfile(filepath=str(source))
        scene=bpy.context.scene;scene.frame_set(1)
        scene.render.resolution_x=scene.render.resolution_y=768
        for direction,angle in [('SE',45),('NW',225)]:
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            folder=OUT/'details'/unit/variant;folder.mkdir(parents=True,exist_ok=True)
            scene.render.filepath=str(folder/f'{direction}.png')
            bpy.ops.render.render(write_still=True)
