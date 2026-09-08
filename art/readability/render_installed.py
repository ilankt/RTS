"""Blender -b -t 4 --python art/readability/render_installed.py [-- --unit NAME]."""
import bpy,json,math,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
manifest=json.loads((OUT/'installed.json').read_text())
directions=dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135)
for unit,meta in manifest['units'].items():
    if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]:continue
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/meta['model']))
    scene=bpy.context.scene;scene.render.resolution_x=scene.render.resolution_y=192;scene.render.resolution_percentage=100
    count=meta['frames_per_direction'];stride=8 if count==8 else 17
    for a,action in enumerate(meta['actions']):
        for d,angle in directions.items():
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            for n in range(count):
                scene.frame_set(a*stride+n+1)
                path=ROOT/meta['frame_source']/unit/action/d/f'{n:02}.png';path.parent.mkdir(parents=True,exist_ok=True)
                scene.render.filepath=str(path);bpy.ops.render.render(write_still=True)
