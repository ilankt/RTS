"""Derive both armored swordsmen from the approved, unchanged Clubman rig.

The same shoulder/body animation drives the sword; its blade is rolled so an
edge leads the downswing. Run with Blender; --models-only skips rendering.
"""
import bpy
import json
import math
import sys
import hashlib
import shutil
from pathlib import Path
from mathutils import Matrix, Quaternion, Vector
from bpy_extras.object_utils import world_to_camera_view

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
APPROVED=OUT/'models/clubman_option_b.blend'
approved_hash=hashlib.sha256(APPROVED.read_bytes()).hexdigest()
DIRECTIONS=dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135)

def copy_cycles():
    scene=bpy.context.scene
    objects=[o for o in scene.objects if o.animation_data and o.animation_data.action]
    samples=[]
    for action in range(3):
        for step in range(65):
            phase=step/8
            old=action*8+1+min(phase,7)
            scene.frame_set(int(old),subframe=old%1)
            values={o:(o.location.copy(),o.rotation_euler.to_quaternion(),o.scale.copy()) for o in objects}
            if phase>7:
                scene.frame_set(action*8+1)
                f=phase-7
                values={o:(loc.lerp(o.location,f),rot.slerp(o.rotation_euler.to_quaternion(),f),scale.lerp(o.scale,f)) for o,(loc,rot,scale) in values.items()}
            samples.append((action*17+1+step/4,values))
    for o in objects: o.animation_data_clear()
    previous={}
    for time,values in samples:
        for o,(loc,quat,scale) in values.items():
            rot=quat.to_euler('XYZ',previous[o]) if o in previous else quat.to_euler('XYZ')
            previous[o]=rot.copy()
            o.location=loc; o.rotation_euler=rot; o.scale=scale
            for prop in ['location','rotation_euler','scale']: o.keyframe_insert(prop,frame=time)
    for o in objects:
        for layer in o.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points: key.interpolation='LINEAR'
    scene.timeline_markers.clear()
    for a,action in enumerate(['idle','run','attack']): scene.timeline_markers.new(action,frame=a*17+1)
    scene.frame_start=1;scene.frame_end=51;scene.render.fps=20;scene.frame_set(1)

for unit in ['bronze_swordsman','iron_swordsman']:
    if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]: continue
    destination=OUT/'models'/f'{unit}_option_b.blend'
    backup=OUT/'previous-sword-slash'/destination.name
    if not backup.exists():
        backup.parent.mkdir(exist_ok=True)
        shutil.copyfile(destination,backup)
    bpy.ops.wm.open_mainfile(filepath=str(APPROVED))
    copy_cycles()
    scene=bpy.context.scene
    body=bpy.data.objects['Body']; width=bpy.data.objects['Option B shoulder breadth']
    sword=bpy.data.objects['Right-hand club']
    for child in list(sword.children_recursive): bpy.data.objects.remove(child,do_unlink=True)
    sword.name='Sword grip';sword.scale=(1,1,1)
    # Club axis unchanged. Rotate the sword about that axis: wide x edges now
    # occupy the swing plane, while the thin y faces point across the swing.
    sword.rotation_euler=(Quaternion((1,0,0),.55)@Quaternion((0,0,1),math.pi/2)).to_euler()
    bpy.data.objects['Fist.001'].name='Weapon grip hand'
    bpy.data.objects['Wrist binding.001'].name='Wrist wrap'
    for name in ['Hair cap','Headband']: bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    source=ROOT/'art/ages/units/models'/f'{unit}.blend'
    weapon_prefix=('Sword blade','Leather sword grip','Sword crossguard','Hilt leather wrap','Sword pommel','Sword cutting tip')
    armor_prefix=('Open-face helmet','Helmet','Back cuirass','Pauldron','Cuirass edging','Armor fastening','Mail collar','Lamellar skirt')
    with bpy.data.libraries.load(str(source),link=False) as (available,loaded):
        loaded.objects=[n for n in available.objects if n.startswith(weapon_prefix+armor_prefix)]
    for obj in loaded.objects:
        bpy.context.collection.objects.link(obj)
        obj.animation_data_clear()
        obj.parent=sword if obj.name.startswith(weapon_prefix) else body if obj.name.startswith(('Open-face helmet','Helmet')) else width
        obj.matrix_parent_inverse.identity()
        if obj.name.startswith('Sword blade'):
            top=max(v.co.z for v in obj.data.vertices)
            for v in obj.data.vertices:
                v.co.x*=1.55;v.co.y*=1.15
                v.co.z=.26+(v.co.z-.18)*(top-.26)/(top-.18)
        if obj.name.startswith(('Sword crossguard','Guard swept tip')):
            matrix=Matrix.LocRotScale(obj.location,obj.rotation_euler.to_quaternion(),obj.scale); inverse=matrix.inverted()
            for vertex in obj.data.vertices:
                point=matrix@vertex.co; point.x*=.60
                vertex.co=inverse@point
            obj.location.z+=.08
        if obj.name=='Leather sword grip':
            for v in obj.data.vertices:
                if v.co.z>0: v.co.z*=1.65
        if obj.name.startswith('Pauldron'): obj.scale.x*=1.08
    metal=bpy.data.objects['Sword blade'].data.materials[0]
    shield=bpy.data.objects['Left-hand wooden buckler']
    for obj in shield.children_recursive:
        if obj.type=='MESH' and obj.data.materials: obj.data.materials[0]=metal
    if unit=='iron_swordsman': shield.scale*=1.22
    scene.camera.data.ortho_scale=5.6 if unit=='iron_swordsman' else 4.8
    scene.render.resolution_x=scene.render.resolution_y=192
    scene.render.resolution_percentage=100
    bpy.context.preferences.filepaths.save_version=0
    scene.frame_set(1)
    facing=bpy.data.objects['Facing'];facing.rotation_euler.z=math.radians(45)
    bpy.context.view_layer.update()
    ground=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
    bpy.ops.wm.save_as_mainfile(filepath=str(destination))
    (OUT/'models'/f'{unit}.json').write_text(json.dumps(dict(source=str(APPROVED.relative_to(ROOT)),ground_anchor=[ground.x,1-ground.y],camera_ortho_scale=scene.camera.data.ortho_scale,render_scale=scene.camera.data.ortho_scale/4.1,changes='Approved Clubman animation with armored swordsman appearance and edge-leading sword'),indent=2))
    if '--models-only' in sys.argv: continue
    for a,action in enumerate(['idle','run','attack']):
        for direction,angle in DIRECTIONS.items():
            facing.rotation_euler.z=math.radians(angle)
            for n in range(16):
                scene.frame_set(a*17+n+1)
                folder=OUT/'full-frames'/unit/action/direction
                folder.mkdir(parents=True,exist_ok=True)
                scene.render.filepath=str(folder/f'{n:02}.png')
                bpy.ops.render.render(write_still=True)
        print('SWORD_RENDERED',unit,action,flush=True)
assert hashlib.sha256(APPROVED.read_bytes()).hexdigest()==approved_hash,'Approved Clubman changed'
