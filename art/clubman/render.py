"""Render a procedural clubman with Blender. Run: blender -b -t 4 --python art/clubman/render.py
Outputs real (never mirrored) views with a fixed orthographic camera.
"""
import bpy
import math
import json
from pathlib import Path
from mathutils import Vector

OUT = Path(__file__).resolve().parent
FRAMES = 8
SIZE = 192
DIRECTIONS = {'E': 90, 'SE': 45, 'S': 0, 'SW': 315, 'W': 270, 'NW': 225, 'N': 180, 'NE': 135}
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

def material(name, color):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Roughness'].default_value = .82
    return m

skin = material('Warm ochre skin', (.57, .30, .15))
leather = material('Hide tunic', (.24, .105, .04))
fur = material('Fur mantle', (.41, .26, .105))
hair = material('Dark hair and beard', (.065, .03, .018))
wood = material('Club hardwood', (.20, .075, .023))
wrap = material('Linen wraps', (.67, .56, .36))
team = material('Team colour - blue sash', (.10, .38, .64))
eye = material('Eyes', (.02, .013, .009))

def pivot(name, location, parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    return obj

def ball(name, location, scale, mat, parent, sub=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1)
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = location
    obj.scale = scale
    obj.data.materials.append(mat)
    return obj

def rod(name, a, b, r1, r2, mat, parent, vertices=10):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=(b-a).length)
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = (a+b)/2
    obj.rotation_euler = (b-a).to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(mat)
    return obj

root = pivot('Character facing', (0,0,0))
body = pivot('Body bob', (0,0,0), root)
ball('Barrel chest', (0,0,1.39), (.39,.23,.40), skin, body)
rod('Hide kilt', (0,0,.73), (0,0,1.19), .35,.25, leather, body, 12)
rod('Belt', (0,0,1.09), (0,0,1.19), .28,.28, wrap, body, 12)
ball('Team belt knot', (0,-.277,1.14), (.09,.028,.085), team, body)
ball('Fur shoulder mantle', (0,.035,1.68), (.44,.235,.17), fur, body)
for i in range(11):
    t=i*math.tau/11
    ball('Mantle tuft', (.34*math.cos(t),.18*math.sin(t),1.59), (.095,.08,.15), fur, body, 1)
rod('Neck', (0,0,1.69), (0,0,1.88), .14,.145, skin, body)
ball('Head', (0,-.012,2.02), (.245,.217,.30), skin, body)
ball('Hair cap', (0,.025,2.18), (.252,.216,.17), hair, body)
ball('Beard', (0,-.15,1.87), (.196,.117,.17), hair, body)
ball('Nose', (0,-.227,2.04), (.075,.085,.09), skin, body, 1)
for x in [-.09,.09]:
    ball('Eye', (x,-.215,2.105), (.025,.018,.025), eye, body)
    rod('Brow', (x-.04,-.215,2.15), (x+.04,-.22,2.15), .024,.026,hair,body,6)
legs=[]
arms=[]
for side in [-1,1]:
    leg=pivot(('Left' if side<0 else 'Right')+' hip', (side*.18,0,.85),body)
    rod('Thigh', (0,0,0), (0,0,-.36), .13,.11,skin,leg)
    ball('Knee',(0,-.02,-.38),(.11,.115,.12),skin,leg)
    rod('Shin', (0,0,-.39), (0,0,-.70), .10,.075,wrap,leg)
    ball('Leather foot', (0,-.075,-.75), (.125,.20,.09),leather,leg)
    legs.append(leg)
    arm=pivot(('Left' if side<0 else 'Right')+' shoulder',(side*.39,0,1.61),body)
    rod('Upper arm',(0,0,0),(side*.07,-.035,-.30),.14,.10,skin,arm)
    ball('Elbow',(side*.07,-.035,-.30),(.105,.105,.11),skin,arm)
    rod('Forearm',(side*.07,-.035,-.30),(side*.09,-.14,-.54),.105,.075,skin,arm)
    rod('Wrist wrap',(side*.085,-.12,-.46),(side*.09,-.15,-.54),.084,.08,team if side<0 else wrap,arm)
    ball('Hand',(side*.09,-.16,-.58),(.095,.11,.105),skin,arm)
    arms.append(arm)
weapon=pivot('Club held in right hand',(.09,-.16,-.58),arms[1])
rod('Club handle',(0,0,-.10),(0,-.12,.40),.047,.070,wood,weapon)
rod('Heavy club head',(0,-.12,.35),(0,-.25,.87),.115,.17,wood,weapon,9)
ball('Club head end',(0,-.25,.87),(.17,.17,.12),wood,weapon,1)
for z in [.39,.48]:
    rod('Club binding',(0,-.12-(z-.35)*.25,z),(0,-.12-(z-.35)*.25,z+.045),.121,.13,wrap,weapon)

scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.samples=12
scene.cycles.use_denoising=True
scene.render.resolution_x=SIZE
scene.render.resolution_y=SIZE
scene.render.resolution_percentage=100
scene.render.film_transparent=True
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGBA'
scene.world.color=(.30,.30,.30)
scene.view_settings.view_transform='Standard'
for name,location,power,size in [('Key',(-3,-4,7),450,4),('Fill',(4,-1,4),220,4),('Rim',(1,4,6),350,3)]:
    data=bpy.data.lights.new(name,'AREA')
    obj=bpy.data.objects.new(name,data)
    bpy.context.collection.objects.link(obj)
    obj.location=location
    obj.rotation_euler=(Vector((0,0,1.2))-obj.location).to_track_quat('-Z','Y').to_euler()
    data.energy=power
    data.shape='DISK'
    data.size=size
bpy.ops.object.camera_add(location=(0,-7,5.3))
cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,1.18))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO'
cam.data.ortho_scale=3.1
scene.camera=cam

# Eight distinct poses per action, sampled cyclically. Game runs these on game time.
def pose(action,i):
    phase=math.tau*i/FRAMES
    body.location.z=0
    body.rotation_euler=(0,0,0)
    for joint in legs+arms:
        joint.rotation_euler=(0,0,0)
    if action=='idle':
        body.location.z=.018*math.sin(phase)
        arms[1].rotation_euler.x=.06*math.sin(phase)
    elif action=='run':
        body.location.z=.04*(1-math.cos(2*phase))
        body.rotation_euler.x=.08
        for j,side in enumerate([-1,1]):
            legs[j].rotation_euler.x=side*.55*math.sin(phase)
            arms[j].rotation_euler.x=-side*.45*math.sin(phase)
    else:
        # Wind up, snap down, recover. Right hand retains the same weapon in every view.
        swing=[0,-.55,-1.6,-2.35,-1.3,.6,.35,.12][i]
        arms[1].rotation_euler.x=swing
        arms[0].rotation_euler.x=-.30-.2*math.sin(phase)
        body.rotation_euler.z=[0,-.12,-.25,-.35,.18,.22,.12,.04][i]
        body.rotation_euler.x=[0,-.03,-.06,-.08,.18,.13,.06,.02][i]
        legs[0].rotation_euler.x=.15
        legs[1].rotation_euler.x=-.15

scene.render.fps=10
for a,action in enumerate(['idle','run','attack']):
    for i in range(FRAMES):
        pose(action,i)
        for obj in [body]+legs+arms:
            obj.keyframe_insert('location',frame=a*FRAMES+i+1)
            obj.keyframe_insert('rotation_euler',frame=a*FRAMES+i+1)
scene.frame_start=1
scene.frame_end=24
for frame,name in [(1,'Idle'),(9,'Walk'),(17,'Attack')]:
    scene.timeline_markers.new(name,frame=frame)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'clubman.blend'))
for action_index,action in enumerate(['idle','run','attack']):
    for direction,angle in DIRECTIONS.items():
        root.rotation_euler.z=math.radians(angle)
        folder=OUT/'frames'/action/direction
        folder.mkdir(parents=True,exist_ok=True)
        for i in range(FRAMES):
            scene.frame_set(action_index*FRAMES+i+1)
            scene.render.filepath=str(folder/f'{i:02}.png')
            bpy.ops.render.render(write_still=True)
(OUT/'manifest.json').write_text(json.dumps({'size':SIZE,'frames':FRAMES,'fps':10,'directions':list(DIRECTIONS),'actions':['idle','run','attack'],'source':'clubman.blend','projection':'orthographic','mirrored':False},indent=2))
