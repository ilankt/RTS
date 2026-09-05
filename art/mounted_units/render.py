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
coat=mat('Warm bay coat','AD7246');muzzle=mat('Cream muzzle','D9C49A')
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
ball('Horse barrel',(0,.22,1.40),(.38,1.03,.43),coat,horse)
ball('Horse chest',(0,-.52,1.44),(.35,.42,.44),coat,horse)
ball('Horse rump',(0,.99,1.45),(.38,.43,.43),coat,horse)
# Fuse the barrel, shoulder and hindquarter into one flowing silhouette.
bpy.ops.object.select_all(action='DESELECT')
for name in ['Horse barrel','Horse chest','Horse rump']:bpy.data.objects[name].select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects['Horse barrel']
bpy.ops.object.join()
body_mesh=bpy.context.object
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
remesh=body_mesh.modifiers.new('Continuous torso','REMESH');remesh.mode='VOXEL';remesh.voxel_size=.055
bpy.ops.object.modifier_apply(modifier=remesh.name)
smooth=body_mesh.modifiers.new('Soft anatomy','SMOOTH');smooth.factor=1.0;smooth.iterations=4
bpy.ops.object.modifier_apply(modifier=smooth.name)
for polygon in body_mesh.data.polygons:polygon.use_smooth=True
neck=pivot('Neck nod',(0,-.50,1.48),horse)
# Broad shoulder attachment tapering along a forward-sloping crest.
# Elliptical rings form one continuous neck surface rather than stacked balls.
sections=[(.16,-.06,.31,.35),(-.08,.20,.29,.40),(-.36,.47,.23,.34),(-.54,.67,.20,.25),(-.68,.73,.17,.19)]
verts=[];faces=[];segments=20
for y,z,rx,rz in sections:
    for j in range(segments):
        t=math.tau*j/segments
        verts.append((rx*math.cos(t),y,z+rz*math.sin(t)))
for ring in range(len(sections)-1):
    for j in range(segments):
        k=ring*segments+j;n=ring*segments+(j+1)%segments
        faces.append((k,n,n+segments,k+segments))
faces.append(tuple(reversed(range(segments))))
faces.append(tuple(range((len(sections)-1)*segments,len(sections)*segments)))
mesh=bpy.data.meshes.new('Anatomical neck mesh');mesh.from_pydata(verts,[],faces);mesh.update()
obj=bpy.data.objects.new('Sloping horse neck',mesh);bpy.context.collection.objects.link(obj);obj.parent=neck;obj.data.materials.append(coat)
for polygon in mesh.polygons:polygon.use_smooth=True
sub=obj.modifiers.new('Smooth neck contour','SUBSURF');sub.levels=2
head=pivot('Head',(0,-.68,.73),neck)
head.scale=(1.13,1.06,1.10)
ball('Horse poll',(0,-.04,0),(.19,.23,.22),coat,head)
rod('Elongated face',(0,-.08,-.04),(0,-.45,-.27),.17,.135,coat,head)
ball('Long muzzle',(0,-.49,-.28),(.155,.21,.135),muzzle,head)
for side in [-1,1]:
    ear=ball('Upright ear',(side*.12,.015,.24),(.052,.065,.125),coat,head)
    ear.rotation_euler.y=side*.16
    ball('Inner ear',(side*.12,-.042,.25),(.026,.018,.073),muzzle,head)
    ball('Horse eye',(side*.182,-.10,.045),(.031,.054,.042),eye,head)
    ball('Eye highlight',(side*.200,-.116,.060),(.010,.018,.015),glint,head)
    ball('Nostril',(side*.125,-.625,-.245),(.033,.028,.027),hoof,head)
    rod('Bridle cheek',(side*.19,-.04,.13),(side*.15,-.49,-.24),.020,.020,leather,head)
rod('Nose strap',(-.15,-.49,-.24),(.15,-.49,-.24),.020,.020,leather,head)
# A clean crest of mane follows the back of the neck.
for i in range(7):
    t=i/6
    ball('Mane lock',(0,.09-.66*t,.36+.51*t),(.125,.17,.15),mane,neck)
ball('Forelock',(0,-.03,.24),(.14,.14,.12),mane,head)
tail=pivot('Tail sway',(0,1.33,1.66),horse)
rod('Tail root',(0,0,0),(0,.10,-.36),.09,.075,mane,tail)
ball('Tail fall',(0,.20,-.66),(.18,.17,.48),mane,tail)

# Four independent hip/shoulder and knee/hock chains: diagonal pairs trot.
legs=[]
for fore,y in [(True,-.62),(False,1.00)]:
    for side in [-1,1]:
        hip=pivot(('Fore' if fore else 'Hind')+(' left' if side<0 else ' right'),(side*.25,y,1.35),horse)
        rod('Upper horse leg',(0,0,0),(0,0,-.65),.16,.084,coat,hip)
        ball('Knee',(0,0,-.65),(.073,.075,.072),coat,hip)
        knee=pivot('Knee flex',(0,0,-.65),hip)
        rod('Lower horse leg',(0,0,0),(0,0,-.60),.077,.063,coat,knee)
        rod('Cream fetlock',(0,0,-.43),(0,0,-.60),.085,.10,linen,knee)
        ball('Hoof',(0,-.035,-.65),(.115,.145,.09),hoof,knee)
        legs.append((fore,side,hip,knee))
# Decorative cloth is player-colored, with gold edging; no horse armor.
gold=mat('Warm gold trim','D5B36A')
def panel(name,vertices,material,parent):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(vertices,[],[tuple(range(len(vertices)))]);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj.parent=parent;obj.data.materials.append(material)
    solid=obj.modifiers.new('Cloth thickness','SOLIDIFY');solid.thickness=.022
    bevel=obj.modifiers.new('Soft cloth edge','BEVEL');bevel.width=.025;bevel.segments=2
    return obj
for side in [-1,1]:
    corners=[(side*.34,-.19,1.79),(side*.35,.69,1.79),(side*.41,.65,1.05),(side*.42,-.23,1.08)]
    panel('Blue saddle cloth',corners,cloth,horse)
    for i in range(4):rod('Gold saddle edging',corners[i],corners[(i+1)%4],.025,.025,gold,horse)
    rod('Blue breast strap',(side*.33,-.51,1.63),(side*.30,-.83,1.29),.075,.075,cloth,horse)
    rod('Breast strap edging',(side*.34,-.53,1.58),(side*.31,-.85,1.24),.021,.021,gold,horse)
panel('Blue chest pendant',[(-.26,-.85,1.43),(.26,-.85,1.43),(.19,-.88,1.04),(0,-.90,.95),(-.19,-.88,1.04)],cloth,horse)
ball('Breast medallion',(0,-.91,1.39),(.115,.035,.12),gold,horse)
ball('Forehead blaze',(0,-.24,-.04),(.055,.06,.15),linen,head)
for side in [-1,1]:
    ball('Bridle button',(side*.20,-.10,.035),(.035,.045,.045),gold,head)

ball('Leather saddle',(0,.15,1.86),(.35,.35,.075),leather,horse)
ball('Saddle pommel',(0,-.13,1.92),(.30,.07,.08),leather,horse)
ball('Saddle cantle',(0,.43,1.91),(.32,.07,.09),leather,horse)
for side in [-1,1]:
    rod('Saddle girth',(side*.38,.20,1.72),(side*.36,.20,1.08),.033,.033,leather,horse)
    ball('Saddle flap',(side*.34,.15,1.77),(.035,.22,.18),leather,horse)

rider.parent=horse;rider.scale=(.78,)*3;rider.location=(0,.12,1.45)
# Seated thighs and hanging shins replace the standing infantry leg chain.
for side in [-1,1]:
    rod('Rider thigh',(side*.18,0,.64),(side*.48,-.19,.28),.14,.12,cloth,rider)
    rod('Rider shin',(side*.48,-.19,.28),(side*.49,-.10,-.25),.11,.09,linen,rider)
    ball('Rider boot',(side*.49,-.19,-.25),(.14,.22,.13),hoof,rider)
    rod('Stirrup strap',(side*.50,.02,.50),(side*.51,-.10,-.32),.021,.021,leather,rider)
    rod('Wood stirrup',(side*.38,-.11,-.34),(side*.62,-.11,-.34),.024,.024,wood,rider)
spear=pivot('Rider wooden spear',(.36,-.32,1.05),rider)
rod('Long wood shaft',(0,0,-.50),(0,0,1.55),.038,.032,wood,spear)
rod('Wood spear point',(0,0,1.53),(0,0,1.85),.062,0,wood,spear)
panel('Blue spear ribbon',[(-.01,0,1.44),(-.01,0,1.24),(-.01,.26,1.08),(-.01,.20,1.37)],cloth,spear)
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
    rider.location=(0,.12,1.45);rider.rotation_euler=(0,0,0)
    arms[0].rotation_euler=( -.80,0,.15)
    arms[1].rotation_euler=(-.90,0,0);spear.rotation_euler=(.35,0,0)
    if action=='run':
        horse.location.z=.035*(1-math.cos(phase*2))
        rider.location.z+=.022*math.cos(phase*2)
        rider.rotation_euler.x=.07
        neck.rotation_euler.x=.035*math.sin(phase*2)
        arms[1].rotation_euler.x=-.90+.07*math.sin(phase)
    elif action=='attack':
        reach=[0,.22,.65,1.12,1.43,1.08,.50,.12][i]
        arms[1].rotation_euler.x=-.90+reach*.60
        spear.rotation_euler.x=.35+reach*.60
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
        a=horse.matrix_world.inverted() @ (head.matrix_world @ Vector((side*.15,-.49,-.24)))
        b=hand
        rein.location=(a+b)/2;rein.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();rein.scale.z=(b-a).length/length

scene.render.resolution_x=192;scene.render.resolution_y=192
scene.camera.data.ortho_scale=6.0
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
(OUT/'manifest.json').write_text(json.dumps({'size':192,'frames':8,'directions':list(DIRECTIONS),'actions':actions,'ground_anchor':[ground.x,1-ground.y],'render_scale':6.0/4.1},indent=2))
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

if preview:
    scene.frame_set(1);root.rotation_euler.z=math.radians(90)
    scene.camera.location=(0,-9,1.85)
    scene.camera.rotation_euler=(Vector((0,0,1.85))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=768;scene.render.resolution_y=512
    scene.camera.data.ortho_scale=6.0
    scene.render.filepath=str(OUT/'reference-side.png')
    bpy.ops.render.render(write_still=True)

if preview:
    root.rotation_euler.z=math.radians(315)
    scene.camera.location=(0,-7,5.6)
    scene.camera.rotation_euler=(Vector((0,0,1.40))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.resolution_x=640;scene.render.resolution_y=640
    scene.camera.data.ortho_scale=6.0
    scene.render.filepath=str(OUT/'decorated-detail.png')
    bpy.ops.render.render(write_still=True)
