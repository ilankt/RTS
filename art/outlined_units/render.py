"""Render the approved outlined cartoon clubman and matching worker with Blender 5.2.
Run from repository root: blender -b -t 4 --python art/outlined_units/render.py
"""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
SOURCE=ROOT/'art/clubman/options/1_cartoon/clubman.blend'
DIRECTIONS={'E':90,'SE':45,'S':0,'SW':315,'W':270,'NW':225,'N':180,'NE':135}
UNITS={'clubman':['idle','run','attack'],'worker':['idle','run','gather','build']}
anchors = json.loads((OUT/'manifest.json').read_text()).get('ground_anchors', {}) if (OUT/'manifest.json').exists() else {}


def descendants(obj):
    return [obj]+[child for c in obj.children for child in descendants(c)]


def ball(name,loc,scale,material,parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=10,radius=1)
    obj=bpy.context.object
    obj.name=name;obj.parent=parent;obj.location=loc;obj.scale=scale
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth=True
    return obj


def rod(name,a,b,r1,r2,material,parent):
    a,b=Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=12,radius1=r1,radius2=r2,depth=(b-a).length)
    obj=bpy.context.object
    obj.name=name;obj.parent=parent;obj.location=(a+b)/2
    obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(material)
    bevel=obj.modifiers.new('Crafted edge','BEVEL');bevel.width=.014;bevel.segments=2
    for polygon in obj.data.polygons:
        polygon.use_smooth=True
    return obj


def pivot(name,loc,parent):
    obj=bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(obj)
    obj.parent=parent;obj.location=loc
    return obj


for unit,actions in UNITS.items():
    if '--unit' in sys.argv and unit != sys.argv[sys.argv.index('--unit') + 1]:
        continue
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene=bpy.context.scene
    scene.render.resolution_x=192;scene.render.resolution_y=192
    root=bpy.data.objects['Facing'];body=bpy.data.objects['Body']
    arms=sorted([o for o in body.children if o.name.startswith('Shoulder')],key=lambda o:o.location.x)
    legs=sorted([o for o in body.children if o.name.startswith('Hip')],key=lambda o:o.location.x)
    assert len(arms)==len(legs)==2
    for obj in scene.objects:
        obj.animation_data_clear()
    tools={}
    if unit=='worker':
        for name in ['Right-hand club','Left-hand wooden buckler','Short beard','Hair cap','Headband']:
            for obj in reversed(descendants(bpy.data.objects[name])):
                bpy.data.objects.remove(obj,do_unlink=True)
        mats={name:(bpy.data.materials.get('1_cartoon '+name) or bpy.data.materials['1_cartoon wood']) for name in ['blue cloth','ochre hide','linen','wood','dark seam']}
        ball('Cloth cap',(0,.025,1.98),(.37,.33,.14),mats['ochre hide'],body)
        ball('Cap brim',(0,-.245,1.93),(.31,.17,.036),mats['ochre hide'],body)
        ball('Apron bib',(0,-.302,.95),(.205,.042,.235),mats['ochre hide'],body)
        for x in [-.12,.12]:
            rod('Apron strap',(x,-.30,1.10),(x,-.22,1.27),.026,.026,mats['linen'],body)
        ball('Tool pouch',(-.31,-.01,.77),(.14,.115,.16),mats['ochre hide'],body)
        metal=mats['linen'].copy();metal.name='Worker steel'
        ramp=next(n for n in metal.node_tree.nodes if n.type=='VALTORGB')
        for e,factor in zip(ramp.color_ramp.elements,[.47,.82,1.14]):
            e.color=(.36*factor,.48*factor,.51*factor,1)
        pick=pivot('Pickaxe',(.07,-.17,-.445),arms[1])
        rod('Pick handle',(0,0,-.10),(0,-.13,.59),.042,.049,mats['wood'],pick)
        rod('Pick left blade',(0,-.13,.59),(-.25,-.17,.53),.075,.012,metal,pick)
        rod('Pick right blade',(0,-.13,.59),(.24,-.17,.53),.075,.012,metal,pick)
        hammer=pivot('Building hammer',(.07,-.17,-.445),arms[1])
        rod('Hammer handle',(0,0,-.1),(0,-.08,.36),.042,.047,mats['wood'],hammer)
        rod('Hammer head',(-.14,-.08,.36),(.14,-.08,.36),.095,.095,metal,hammer)
        tools={'gather':descendants(pick),'build':descendants(hammer)}

    def pose(action,i):
        phase=math.tau*i/8
        body.location=(0,0,0);body.rotation_euler=(0,0,0)
        for joint in arms+legs:
            joint.rotation_euler=(0,0,0)
        if action=='idle':
            body.location.z=.012*math.sin(phase)
            arms[1].rotation_euler.x=.04*math.sin(phase)
        elif action=='run':
            body.location.z=.025*(1-math.cos(2*phase))
            for j,side in enumerate([-1,1]):
                legs[j].rotation_euler.x=side*.45*math.sin(phase)
                arms[j].rotation_euler.x=-side*.35*math.sin(phase)
        else:
            if action=='attack':
                swing=[0,-.5,-1.35,-2.05,-.85,.65,.35,.10]
                arms[0].rotation_euler.x=-.15
                body.rotation_euler.z=[0,-.09,-.18,-.24,.15,.18,.08,.02][i]
            elif action=='gather':
                swing=[-.1,-.5,-1.1,-1.8,-.6,.8,.5,.12]
                arms[0].rotation_euler.x=.25
            else:
                swing=[-.1,-.35,-.65,-1.2,-.4,.6,.3,.1]
                arms[0].rotation_euler.x=.4
            arms[1].rotation_euler.x=swing[i]
            body.rotation_euler.x=[0,-.02,-.04,-.07,.11,.12,.06,.02][i]
            legs[0].rotation_euler.x=.10;legs[1].rotation_euler.x=-.10
        for kind,objects in tools.items():
            visible=(action=='build') if kind=='build' else (action!='build')
            for obj in objects:
                obj.hide_render=not visible
                obj.hide_viewport=not visible

    scene.timeline_markers.clear()
    scene.render.fps=10
    scene.frame_start=1;scene.frame_end=len(actions)*8
    for a,action in enumerate(actions):
        scene.timeline_markers.new(action,frame=a*8+1)
        for i in range(8):
            pose(action,i)
            for obj in [body]+arms+legs:
                obj.keyframe_insert('location',frame=a*8+i+1)
                obj.keyframe_insert('rotation_euler',frame=a*8+i+1)
            for objects in tools.values():
                for obj in objects:
                    obj.keyframe_insert('hide_render',frame=a*8+i+1)
                    obj.keyframe_insert('hide_viewport',frame=a*8+i+1)
    scene.frame_set(1)
    root.rotation_euler.z=math.radians(45)
    ground = world_to_camera_view(scene, scene.camera, Vector((0,0,0)))
    anchors[unit] = [round(ground.x,6), round(1-ground.y,6)]
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/f'{unit}.blend'))
    for a,action in enumerate(actions):
        for direction,angle in DIRECTIONS.items():
            root.rotation_euler.z=math.radians(angle)
            folder=OUT/'frames'/unit/action/direction
            folder.mkdir(parents=True,exist_ok=True)
            for i in range(8):
                scene.frame_set(a*8+i+1)
                scene.render.filepath=str(folder/f'{i:02}.png')
                bpy.ops.render.render(write_still=True)
        print(f'RENDERED {unit} {action}',flush=True)
(OUT/'manifest.json').write_text(json.dumps({'size':192,'frames':8,'fps':10,'directions':list(DIRECTIONS),'units':UNITS,'style':'Outlined cartoon (option 1)','ground_anchors':anchors},indent=2))
