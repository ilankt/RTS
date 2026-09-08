"""Worker readability variants; originals and live gameplay assets stay intact."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Matrix, Vector
from bpy_extras.object_utils import world_to_camera_view

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
import motion_corrections
ROOT=OUT.parents[2]
DIRECTIONS=dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135)
SOURCES={'bronze_worker':'art/ages/units/models/bronze_worker.blend','iron_worker':'art/ages/units/models/iron_worker.blend','worker':'art/outlined_units/worker.blend'}

def reshape(obj,center,factors):
    # Alter mesh vertices in the tool's coordinates; animated root scales and
    # hand attachment points are preserved, including both age-worker grips.
    matrix=Matrix.LocRotScale(obj.location,obj.rotation_euler.to_quaternion(),obj.scale)
    inverse=matrix.inverted();center=Vector(center)
    for v in obj.data.vertices:
        p=matrix@v.co-center
        p=Vector(tuple(p[i]*factors[i] for i in range(3)))+center
        v.co=inverse@p

def fix_grips(unit):
    scene=bpy.context.scene
    if unit=='worker':
        shoulder=bpy.data.objects['Shoulder.001']
        offset=bpy.data.objects.new('Tool arm clearance',None)
        bpy.context.collection.objects.link(offset);offset.parent=shoulder.parent
        offset.location.x=.15;shoulder.parent=offset
        for name in ['Pickaxe','Building hammer']:
            tool=bpy.data.objects[name]
            tool.rotation_euler.x=.35
        bpy.data.objects['Pickaxe'].rotation_euler.z=math.pi/2
        fore=bpy.data.objects['Forearm.001']
        fore.scale.z*=.70;fore.location-=fore.rotation_euler.to_matrix()@Vector((0,0,.035))
        upper=bpy.data.objects['Upper arm.001']
        depth=max(v.co.z for v in upper.data.vertices)-min(v.co.z for v in upper.data.vertices)
        endpoint=Vector((.055,-.025,-.20))
        for i in range((scene.frame_end-1)*4+1):
            t=1+i/4;scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
            start=shoulder.matrix_world.inverted()@(offset.parent.matrix_world@shoulder.location)
            upper.location=(start+endpoint)/2;upper.rotation_euler=(endpoint-start).to_track_quat('Z','Y').to_euler()
            upper.scale.z=(endpoint-start).length/depth
            for prop in ['location','rotation_euler','scale']:upper.keyframe_insert(prop,frame=t)
    else:
        samples=[]
        for i in range((scene.frame_end-1)*4+1):
            t=1+i/4;scene.frame_set(int(t),subframe=t%1)
            transforms=[]
            for suffix in ['', '.001']:
                fore=bpy.data.objects['Articulated forearm'+suffix]
                wrap=bpy.data.objects['Wrist wrap'+suffix]
                hand=bpy.data.objects['Weapon grip hand'+suffix]
                direction=fore.rotation_euler.to_matrix()@Vector((0,0,1))
                elbow=fore.location-direction*fore.scale.z/2
                if suffix=='.001':
                    tool=bpy.data.objects['Building hammer' if t>=52 else 'Pickaxe']
                    axis=tool.rotation_euler.to_matrix()@Vector((0,0,1))
                    bend=elbow-hand.location;bend-=axis*bend.dot(axis)
                    elbow=hand.location+bend.normalized()*.30
                    direction=(hand.location-elbow).normalized()
                    upper=bpy.data.objects['Articulated upper arm.001']
                    shoulder=bpy.data.objects['Shoulder.001'].location
                    transforms.append((upper,(shoulder+elbow)/2,(elbow-shoulder).to_track_quat('Z','Y').to_euler(),(elbow-shoulder).length))
                wrist=hand.location-direction*.15
                for obj,a,b in [(fore,elbow,wrist),(wrap,wrist,hand.location-direction*.075)]:
                    transforms.append((obj,(a+b)/2,(b-a).to_track_quat('Z','Y').to_euler(),(b-a).length))
            samples.append((t,transforms))
        previous={}
        for t,transforms in samples:
            for obj,loc,rot,length in transforms:
                if obj in previous:rot.make_compatible(previous[obj])
                previous[obj]=rot.copy()
                obj.location=loc;obj.rotation_euler=rot;obj.scale.z=length
                for prop in ['location','rotation_euler','scale']:obj.keyframe_insert(prop,frame=t)
    scene.frame_set(1)

for unit,source in SOURCES.items():
    if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]: continue
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/source))
    scene=bpy.context.scene;scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version=0
    apron=bpy.data.objects['Apron bib'];apron.scale.x*=1.18;apron.scale.z*=1.12
    pouch=bpy.data.objects['Tool pouch'];pouch.scale*=1.35;pouch.location.x-=.035
    for obj in bpy.data.objects['Pickaxe'].children:
        if obj.type!='MESH': continue
        if unit=='worker' and obj.name.startswith(('Pick left blade','Pick right blade')):
            reshape(obj,(0,-.13,.59),(1.45,1.15,1.15))
        elif obj.name.startswith(('Pick cutting horn','Pick rear horn','Pick head socket')):
            reshape(obj,(0,0,.65),(1.20,1.45,1.15))
    hammer=bpy.data.objects['Hammer head']
    reshape(hammer,(0,-.08,.36) if unit=='worker' else (0,0,.54),(1.40,1.40,1.20))
    # Keep contact markers attached to the modified working surfaces.
    if unit!='worker':
        bpy.data.objects['Pick cutting edge'].location=(0,-.38*1.45,.65+.05*1.15)
        bpy.data.objects['Hammer striking face'].location=(0,-.145*1.40,.54)
    fix_grips(unit)
    if unit=='worker':motion_corrections.worker()
    scene.frame_set(1)
    bpy.context.view_layer.update()
    model_dir=OUT/'models';model_dir.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(model_dir/f'{unit}_option_b.blend'))
    ground=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
    (model_dir/f'{unit}.json').write_text(json.dumps(dict(source=source,ground_anchor=[ground.x,1-ground.y],render_scale=scene.camera.data.ortho_scale/4.1,camera_ortho_scale=scene.camera.data.ortho_scale),indent=2))
    if '--models-only' in sys.argv: continue
    for a,action in enumerate(['idle','run','gather','build']):
        for direction,angle in DIRECTIONS.items():
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            for n in range(8 if unit=='worker' else 16):
                scene.frame_set(a*(8 if unit=='worker' else 17)+n+1)
                folder=OUT/'frames'/unit/action/direction;folder.mkdir(parents=True,exist_ok=True)
                scene.render.filepath=str(folder/f'{n:02}.png')
                bpy.ops.render.render(write_still=True)
        print('WORKER_RENDERED',unit,action,flush=True)
