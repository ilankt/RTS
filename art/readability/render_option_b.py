"""Non-destructive Option B review, using the actual approved Blender scenes.

blender -b -t 4 --python art/readability/render_option_b.py
"""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector
from mathutils import Quaternion
from bpy_extras.object_utils import world_to_camera_view

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DIRECTIONS = dict(E=90, SE=45, S=0, SW=315, W=270, NW=225, N=180, NE=135)
SOURCES = {
    'clubman': 'art/outlined_units/clubman.blend',
    'bronze_swordsman': 'art/ages/units/models/bronze_swordsman.blend',
    'iron_swordsman': 'art/ages/units/models/iron_swordsman.blend',
}


def broaden(unit):
    torso = bpy.data.objects['Body' if unit == 'clubman' else 'Sword torso']
    # A static parent leaves every animated child channel and grip intact.
    width = bpy.data.objects.new('Option B shoulder breadth', None)
    bpy.context.collection.objects.link(width)
    width.parent = torso
    head_names = ('Neck', 'Face', 'Hair', 'Ear', 'Sideburn', 'Eye', 'Pupil',
                  'Brow', 'Nose', 'Short beard', 'Headband', 'Helmet', 'Open-face')
    for child in list(torso.children):
        if child == width or child.name.startswith(head_names) or child.name.startswith('Hip'):
            continue
        child.parent = width
    width.scale.x = 1.18
    # Widen the stance independently, without enlarging boots or the head.
    for hip in [o for o in bpy.data.objects if o.name.startswith('Hip')]:
        parent = bpy.data.objects.new('Option B stance offset', None)
        bpy.context.collection.objects.link(parent)
        parent.parent = hip.parent
        parent.location.x = .025 if hip.location.x > 0 else -.025
        hip.parent = parent
    shield = bpy.data.objects['Left-hand wooden buckler']
    shield.scale.x *= 1.30
    shield.scale.z *= 1.30
    # Shift the shield slightly forward to accommodate the larger rim.
    shield.location.y -= .035
    if unit == 'clubman':
        club = bpy.data.objects['Right-hand club']
        club.scale = (1.30, 1.20, 1.36)
    else:
        # Edit only the blade mesh, retaining the original hilt and grip rig.
        blade = bpy.data.objects['Sword blade']
        for v in blade.data.vertices:
            v.co.x *= 1.55
            v.co.y *= 1.15
        for obj in bpy.data.objects:
            if obj.name.startswith('Pauldron'):
                obj.scale.x *= 1.08


def clearance_poses(unit):
    # Move the whole shield-bearing arm, not just its shield attachment.
    for name, offset in [('Shoulder',(-.055,-.26,0))] + ([('Shoulder.001',(.15,0,0))] if unit=='clubman' else []):
        joint=bpy.data.objects[name]
        helper=bpy.data.objects.new('Option B arm clearance '+name,None)
        bpy.context.collection.objects.link(helper)
        helper.parent=joint.parent; helper.location=offset; joint.parent=helper
    if unit=='clubman':
        bpy.data.objects['Right-hand club'].rotation_euler.x=.24
        forearm=bpy.data.objects['Forearm.001']
        forearm.scale.z *= .70
        forearm.location -= forearm.rotation_euler.to_matrix() @ Vector((0,0,.035))
        anchor_upper_arms()
        return
    scene=bpy.context.scene
    sword=bpy.data.objects['Sword grip']
    hand=bpy.data.objects['Weapon grip hand']
    upper=bpy.data.objects['Articulated upper arm']
    fore=bpy.data.objects['Articulated forearm']
    wrap=bpy.data.objects['Wrist wrap']
    shoulder=bpy.data.objects['Shoulder.001']
    sys.path.insert(0,str(OUT))
    from check_clearance import geometry,collision
    shield_root=bpy.data.objects['Left-hand wooden buckler']
    equipment=[o for root in [sword,shield_root] for o in root.children_recursive if o.type=='MESH']
    # Sample source before replacing the arm curves. Keep the sword cut, but
    # carry its grip a little farther forward so the pommel clears the armor.
    samples=[]
    for i in range((scene.frame_end-1)*4+1):
        t=1+i/4; scene.frame_set(int(t),subframe=t%1)
        follow=math.sin(math.pi*max(0,min(1,(t-41)/8))) if 41<t<49 else 0
        grip=sword.location.copy()+Vector((.07,-.10-.32*follow,0))
        axis=(sword.rotation_euler.to_matrix()@Vector((0,0,1))).normalized()
        previous_elbow=fore.location-fore.rotation_euler.to_matrix()@Vector((0,0,fore.scale.z/2))
        bend=previous_elbow-sword.location
        bend-=axis*bend.dot(axis)
        if bend.length<.01: bend=Vector((1,0,0))
        sword.location=grip; hand.location=grip
        bpy.context.view_layer.update()
        graph=bpy.context.evaluated_depsgraph_get()
        targets={o:geometry(o,graph) for o in equipment}
        best=None
        # Keep the wrist perpendicular to the hilt. Choose the nearest natural
        # elbow bend that clears the actual enlarged weapon and shield meshes.
        for degrees in [0,15,-15,30,-30,45,-45,60,-60,90,-90,120,-120,150,-150,180]:
            offset=Quaternion(axis,math.radians(degrees))@bend.normalized()*.32
            elbow=grip+offset; wrist=grip+offset.normalized()*.15
            transforms=[]
            for obj,a,b in [(upper,shoulder.location,elbow),(fore,elbow,wrist),(wrap,wrist,grip+offset.normalized()*.075)]:
                loc=(a+b)/2; rot=(b-a).to_track_quat('Z','Y').to_euler(); length=(b-a).length
                obj.location=loc; obj.rotation_euler=rot; obj.scale.z=length
                transforms.append((obj,loc.copy(),rot.copy(),length))
            bpy.context.view_layer.update()
            graph=bpy.context.evaluated_depsgraph_get()
            count=0
            for obj in [upper,fore,wrap]:
                shape=geometry(obj,graph)
                for target,other in targets.items():
                    if obj==wrap and target.name.startswith(('Leather sword grip','Hilt leather wrap','Sword pommel')): continue
                    count+=bool(collision(shape,other))
            if best is None or count<best[0]: best=(count,transforms)
            if count==0: break
        if best[0]: print('UNRESOLVED_ARM',unit,t,best[0],flush=True)
        transforms=best[1]
        if samples:
            for current,previous in zip(transforms,samples[-1][2]):
                current[2].make_compatible(previous[2])
        samples.append((t,grip,transforms))
    for t,grip,transforms in samples:
        for obj in [sword,hand]:
            obj.location=grip; obj.keyframe_insert('location',frame=t)
        for obj,loc,rot,length in transforms:
            obj.location=loc; obj.rotation_euler=rot; obj.scale.z=length
            for prop in ['location','rotation_euler','scale']: obj.keyframe_insert(prop,frame=t)
    for obj in [sword,hand,upper,fore,wrap]:
        for layer in obj.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points: key.interpolation='LINEAR'
    scene.frame_set(1)
    anchor_upper_arms()


def anchor_upper_arms():
    """Retarget shifted arms back to their original shoulder attachment."""
    scene=bpy.context.scene
    for name in ['Upper arm','Upper arm.001']:
        obj=bpy.data.objects.get(name)
        if obj is None: continue
        shoulder=obj.parent
        helper=shoulder.parent
        if not helper.name.startswith('Option B arm clearance'): continue
        depth=max(v.co.z for v in obj.data.vertices)-min(v.co.z for v in obj.data.vertices)
        endpoint=Vector((.055 if name.endswith('.001') else -.055,-.025,-.20))
        for i in range((scene.frame_end-1)*4+1):
            t=1+i/4; scene.frame_set(int(t),subframe=t%1)
            bpy.context.view_layer.update()
            start=shoulder.matrix_world.inverted() @ (helper.parent.matrix_world @ shoulder.location)
            obj.location=(start+endpoint)/2
            obj.rotation_euler=(endpoint-start).to_track_quat('Z','Y').to_euler()
            obj.scale.z=(endpoint-start).length/depth
            for prop in ['location','rotation_euler','scale']: obj.keyframe_insert(prop,frame=t)
    scene.frame_set(1)


for unit, source in SOURCES.items():
    if '--unit' in sys.argv and unit != sys.argv[sys.argv.index('--unit') + 1]:
        continue
    bpy.ops.wm.open_mainfile(filepath=str(ROOT / source))
    scene = bpy.context.scene
    scene.frame_set(1)
    broaden(unit)
    clearance_poses(unit)
    # The longer follow-through needs more camera room in the Iron variant.
    # Compensating render_scale below preserves the unit's world-space size.
    if unit=='iron_swordsman': scene.camera.data.ortho_scale=5.6
    scene.render.resolution_x = scene.render.resolution_y = 192
    scene.render.resolution_percentage = 100
    bpy.context.preferences.filepaths.save_version = 0
    facing = bpy.data.objects['Facing']
    facing.rotation_euler.z = math.radians(45)
    bpy.context.view_layer.update()
    model_dir = OUT / 'models'
    model_dir.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(model_dir / f'{unit}_option_b.blend'))
    ground = world_to_camera_view(scene, scene.camera, Vector((0, 0, 0)))
    (model_dir / f'{unit}.json').write_text(json.dumps({
        'source': source, 'ground_anchor': [ground.x, 1-ground.y],
        'camera_ortho_scale': scene.camera.data.ortho_scale,
        'render_scale': scene.camera.data.ortho_scale / 4.1,
        'changes': '18% broader torso; wider stance; 30% larger shield; heavier club or 55% wider sword blade',
    }, indent=2))
    if '--models-only' in sys.argv: continue
    stride = 8 if unit == 'clubman' else 17
    for action_index, action in enumerate(['idle', 'run', 'attack']):
        for direction, angle in DIRECTIONS.items():
            if action != 'idle' and direction not in ['SE', 'NW'] and '--full' not in sys.argv:
                continue
            facing.rotation_euler.z = math.radians(angle)
            count=8 if unit=='clubman' else 16
            samples=range(count) if '--full' in sys.argv else (range(8) if action != 'idle' else [0])
            for sample in samples:
                frame = action_index * stride + 1 + sample * (1 if unit == 'clubman' or '--full' in sys.argv else 2)
                scene.frame_set(frame)
                folder = OUT / ('full-frames' if '--full' in sys.argv else 'frames') / unit / action / direction
                folder.mkdir(parents=True, exist_ok=True)
                scene.render.filepath = str(folder / f'{sample:02}.png')
                bpy.ops.render.render(write_still=True)
        print(f'REVIEW_RENDERED {unit} {action}', flush=True)
