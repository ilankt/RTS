"""Tier-one mounted spearman: a separate articulated horse and seated rider.
Blender: --python art/mounted_units/render.py [-- --preview]
"""
import bpy
import math
import json
import sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'art/clubman/options/1_cartoon/clubman.blend'))
scene=bpy.context.scene
for obj in scene.objects: obj.animation_data_clear()
root=bpy.data.objects['Facing'];rider=bpy.data.objects['Body']
arms=sorted([o for o in rider.children if o.name.startswith('Shoulder')],key=lambda o:o.location.x)

def descendants(obj):
    return [obj]+[child for c in obj.children for child in descendants(c)]
for name in ['Right-hand club','Left-hand wooden buckler']+[o.name for o in rider.children if o.name.startswith('Hip')]:
    for obj in reversed(descendants(bpy.data.objects[name])): bpy.data.objects.remove(obj,do_unlink=True)

def mat(name,color):
    m=bpy.data.materials['1_cartoon wood'].copy();m.name=name
    rgb=[int(color[i:i+2],16)/255 for i in (0,2,4)]
    rgb=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    ramp=next(n for n in m.node_tree.nodes if n.type=='VALTORGB')
    for e,f in zip(ramp.color_ramp.elements,[.47,.82,1.14]): e.color=(*[min(1,c*f) for c in rgb],1)
    return m
coat=mat('Warm bay coat','AD7246');muzzle=mat('Soft brown muzzle','815536')
mane=mat('Dark mane and tail','49352B');hoof=mat('Charcoal hooves','39312D')
leather=mat('Plain saddle leather','795333');linen=bpy.data.materials['1_cartoon linen']
wood=bpy.data.materials['1_cartoon wood'];cloth=bpy.data.materials['1_cartoon blue cloth']
eye=mat('Horse eyes','20273C');glint=mat('Eye glint','F2DDAE')

def pivot(name,loc,parent):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o);o.parent=parent;o.location=loc;return o

def ball(name,loc,scale,material,parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12)
    o=bpy.context.object;o.name=name;o.parent=parent;o.location=loc;o.scale=scale;o.data.materials.append(material)
    for p in o.data.polygons:p.use_smooth=True
    return o

def rod(name,a,b,r1,r2,material,parent):
    a,b=Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=16,radius1=r1,radius2=r2,depth=(b-a).length)
    o=bpy.context.object;o.name=name;o.parent=parent;o.location=(a+b)/2;o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();o.data.materials.append(material)
    bevel=o.modifiers.new('Rounded edges','BEVEL');bevel.width=.015;bevel.segments=2
    for p in o.data.polygons:p.use_smooth=True
    return o

horse=pivot('Horse body suspension',(0,0,0),root)
ball('Horse barrel',(0,.16,1.44),(.33,.88,.30),coat,horse)
ball('Horse chest',(0,-.43,1.47),(.30,.35,.34),coat,horse)
ball('Horse rump',(0,.77,1.48),(.32,.35,.32),coat,horse)
neck=pivot('Neck nod',(0,-.48,1.56),horse)
rod('Sloping neck',(0,0,0),(0,-.40,.70),.24,.17,coat,neck)
ball('Neck crest',(0,-.20,.38),(.19,.22,.43),coat,neck)
head=pivot('Head',(0,-.43,.74),neck)
ball('Horse head',(0,-.09,0),(.19,.31,.22),coat,head)
ball('Long muzzle',(0,-.39,-.13),(.16,.29,.14),muzzle,head)
for side in [-1,1]:
    ear=ball('Upright ear',(side*.12,.015,.24),(.052,.065,.125),coat,head)
    ear.rotation_euler.y=side*.16
    ball('Inner ear',(side*.12,-.042,.25),(.026,.018,.073),muzzle,head)
    ball('Horse eye',(side*.182,-.16,.09),(.031,.054,.042),eye,head)
    ball('Eye highlight',(side*.200,-.176,.106),(.010,.018,.015),glint,head)
    ball('Nostril',(side*.125,-.605,-.10),(.033,.028,.027),hoof,head)
    rod('Bridle cheek',(side*.19,-.04,.13),(side*.19,-.45,-.10),.020,.020,leather,head)
rod('Nose strap',(-.19,-.45,-.10),(.19,-.45,-.10),.020,.020,leather,head)
# A clean crest of mane follows the back of the neck.
for i in range(7):
    t=i/6
    ball('Mane lock',(0,.12-.33*t,.06+.66*t),(.10,.13,.15),mane,neck)
ball('Forelock',(0,-.03,.24),(.14,.14,.12),mane,head)
tail=pivot('Tail sway',(0,1.04,1.55),horse)
rod('Tail root',(0,0,0),(0,.30,-.20),.10,.085,mane,tail)
ball('Tail fall',(0,.33,-.42),(.12,.12,.31),mane,tail)

# Four independent hip/shoulder and knee/hock chains: diagonal pairs trot.
legs=[]
for fore,y in [(True,-.43),(False,.77)]:
    for side in [-1,1]:
        hip=pivot(('Fore' if fore else 'Hind')+(' left' if side<0 else ' right'),(side*.25,y,1.35),horse)
        rod('Upper horse leg',(0,0,0),(0,0,-.65),.105,.065,coat,hip)
        ball('Knee',(0,0,-.65),(.073,.075,.072),coat,hip)
        knee=pivot('Knee flex',(0,0,-.65),hip)
        rod('Lower horse leg',(0,0,0),(0,0,-.60),.055,.048,coat,knee)
        ball('Hoof',(0,-.035,-.65),(.085,.115,.08),hoof,knee)
        legs.append((fore,side,hip,knee))
# Saddle only: no barding, blanket, plate or helmet.
ball('Leather saddle',(0,.15,1.76),(.32,.35,.075),leather,horse)
ball('Saddle pommel',(0,-.13,1.82),(.28,.07,.08),leather,horse)
ball('Saddle cantle',(0,.43,1.81),(.30,.07,.09),leather,horse)
for side in [-1,1]:
    rod('Saddle girth',(side*.33,.20,1.64),(side*.31,.20,1.20),.033,.033,leather,horse)
    ball('Saddle flap',(side*.30,.15,1.68),(.035,.22,.18),leather,horse)

rider.parent=horse;rider.scale=(.78,)*3;rider.location=(0,.12,1.35)
# Seated thighs and hanging shins replace the standing infantry leg chain.
for side in [-1,1]:
    rod('Rider thigh',(side*.18,0,.64),(side*.48,-.19,.28),.14,.12,cloth,rider)
    rod('Rider shin',(side*.48,-.19,.28),(side*.49,-.10,-.25),.11,.09,linen,rider)
    ball('Rider boot',(side*.49,-.19,-.25),(.14,.22,.13),hoof,rider)
    rod('Stirrup strap',(side*.50,.02,.50),(side*.51,-.10,-.32),.021,.021,leather,rider)
    rod('Wood stirrup',(side*.38,-.11,-.34),(side*.62,-.11,-.34),.024,.024,wood,rider)
spear=pivot('Rider wooden spear',(.07,-.17,-.445),arms[1])
rod('Long wood shaft',(0,0,-.50),(0,0,1.55),.038,.032,wood,spear)
rod('Wood spear point',(0,0,1.53),(0,0,1.85),.062,0,wood,spear)
# Reins follow the left hand and both sides of the bit each rendered pose.
reins=[]
for side in [-1,1]:
    reins.append(rod('Rein',(side*.19,-1.36,1.86),(-.32,-.25,1.90),.015,.015,leather,horse))
rein_lengths=[o.dimensions.z for o in reins]  # replaced with actual mesh lengths below
rein_lengths=[max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices) for o in reins]

DIRECTIONS={'E':90,'SE':45,'S':0,'SW':315,'W':270,'NW':225,'N':180,'NE':135}
actions=['idle','run','attack']
animated=[horse,neck,tail,rider,spear]+arms+[joint for _,_,h,k in legs for joint in (h,k)]+reins

def pose(action,i):
    phase=math.tau*i/8
    horse.location.z=0
    neck.rotation_euler.x=.015*math.sin(phase)
    tail.rotation_euler.x=.10;tail.rotation_euler.y=.10*math.sin(phase)
    rider.location=(0,.12,1.35);rider.rotation_euler=(0,0,0)
    arms[0].rotation_euler=( -.80,0,.15)
    arms[1].rotation_euler=(0,0,0);spear.rotation_euler=(0,0,0)
    if action=='run':
        horse.location.z=.035*(1-math.cos(phase*2))
        rider.location.z+=.022*math.cos(phase*2)
        rider.rotation_euler.x=.07
        neck.rotation_euler.x=.035*math.sin(phase*2)
        arms[1].rotation_euler.x=.07*math.sin(phase)
    elif action=='attack':
        reach=[0,.22,.65,1.12,1.43,1.08,.50,.12][i]
        arms[1].rotation_euler.x=reach
        rider.rotation_euler.x=.10*math.sin(math.pi*i/7)
        rider.rotation_euler.z=-.06*math.sin(math.pi*i/7)
    else:
        rider.location.z+=.006*math.sin(phase)
    # Two-bone IK pins each stance hoof to the ground. Diagonal pairs
    # alternate swing and stance; the rider follows the horse suspension.
    for fore,side,hip,knee in legs:
        dy=0;lift=0
        if action=='run':
            cycle=phase+(0 if (fore and side<0) or (not fore and side>0) else math.pi)
            dy=.21*math.sin(cycle)
            lift=.19*max(0,math.cos(cycle))
        down=hip.location.z+horse.location.z-(.08+lift)
        distance=min(1.299,math.hypot(dy,down))
        bend=math.acos(max(-1,min(1,(distance*distance-2*.65*.65)/(2*.65*.65))))
        sign=1 if fore else -1
        hip.rotation_euler.x=math.atan2(dy,down)+sign*bend/2
        knee.rotation_euler.x=-sign*bend
    bpy.context.view_layer.update()
    hand=horse.matrix_world.inverted() @ (arms[0].matrix_world @ Vector((-.07,-.17,-.445)))
    for side,rein,length in zip([-1,1],reins,rein_lengths):
        a=horse.matrix_world.inverted() @ (head.matrix_world @ Vector((side*.19,-.45,-.10)))
        b=hand
        rein.location=(a+b)/2;rein.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();rein.scale.z=(b-a).length/length

scene.render.resolution_x=192;scene.render.resolution_y=192
scene.camera.data.ortho_scale=5.6
scene.camera.location=(0,-7,5.6)
scene.camera.rotation_euler=(Vector((0,0,1.40))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
scene.timeline_markers.clear();scene.frame_start=1;scene.frame_end=24;scene.render.fps=10
for a,action in enumerate(actions):
    scene.timeline_markers.new(action,frame=a*8+1)
    for i in range(8):
        pose(action,i)
        for obj in animated:
            for prop in ['location','rotation_euler','scale']:obj.keyframe_insert(prop,frame=a*8+i+1)
scene.frame_set(1);root.rotation_euler.z=math.radians(45)
ground=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
(OUT/'manifest.json').write_text(json.dumps({'size':192,'frames':8,'directions':list(DIRECTIONS),'actions':actions,'ground_anchor':[ground.x,1-ground.y],'render_scale':5.6/4.1},indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'mounted_spearman.blend'))
preview='--preview' in sys.argv
for a,action in enumerate(actions):
    if preview and action!='idle':continue
    for direction,angle in DIRECTIONS.items():
        root.rotation_euler.z=math.radians(angle)
        folder=OUT/'frames'/action/direction;folder.mkdir(parents=True,exist_ok=True)
        for i in ([0] if preview else range(8)):
            scene.frame_set(a*8+i+1)
            scene.render.filepath=str(folder/f'{i:02}.png');bpy.ops.render.render(write_still=True)
    print('RENDERED mounted '+action,flush=True)
