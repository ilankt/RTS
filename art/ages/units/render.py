"""Build age variants from the approved editable cartoon rigs (Blender 5.2).

blender -b -t 4 --python art/ages/units/render.py -- --preview
blender -b -t 4 --python art/ages/units/render.py -- --unit bronze_swordsman
Without --preview, render all sixteen frames in all eight actual directions.
Existing Stone assets and gameplay configuration are never overwritten.
"""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DIRECTIONS = {'E':90,'SE':45,'S':0,'SW':315,'W':270,'NW':225,'N':180,'NE':135}
SPECS = {
 'bronze_worker': ('Bronze Worker','Bronze','worker', ['idle','run','gather','build']),
 'iron_worker': ('Iron Worker','Iron','worker', ['idle','run','gather','build']),
 'bronze_swordsman': ('Bronze Swordsman','Bronze','clubman', ['idle','run','attack']),
 'iron_swordsman': ('Iron Swordsman','Iron','clubman', ['idle','run','attack']),
 'archer': ('Archer','Bronze','slinger', ['idle','run','shoot']),
 'crossbowman': ('Crossbowman','Iron','slinger', ['idle','run','shoot']),
 'bronze_spearman': ('Bronze Spearman','Bronze','spearman', ['idle','run','attack']),
 'pikeman': ('Pikeman','Iron','spearman', ['idle','run','attack']),
 'mounted_spearman': ('Mounted Spearman','Bronze','mounted', ['idle','run','attack']),
 'heavy_cavalry': ('Heavy Cavalry','Iron','mounted', ['idle','run','attack']),
 'healer': ('Healer','Bronze','healer', ['idle','run','attack']),
 'priest': ('Priest','Iron','healer', ['idle','run','attack']),
 'ballista': ('Ballista','Bronze','siege', ['idle','run','attack']),
 'heavy_ballista': ('Heavy Ballista','Iron','siege', ['idle','run','attack']),
}

def descendants(obj):
    return [obj] + [nested for child in obj.children for nested in descendants(child)]

def remove(name):
    obj = bpy.data.objects.get(name)
    if obj:
        for child in reversed(descendants(obj)):
            bpy.data.objects.remove(child, do_unlink=True)

def material(name, color):
    result = bpy.data.materials['1_cartoon wood'].copy()
    result.name = name
    rgb = [int(color[i:i+2],16)/255 for i in (0,2,4)]
    rgb = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
    ramp = next(n for n in result.node_tree.nodes if n.type == 'VALTORGB')
    for element, factor in zip(ramp.color_ramp.elements,[.47,.82,1.14]):
        element.color = (*[min(1,c*factor) for c in rgb],1)
    return result

def pivot(name, loc, parent):
    obj = bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = loc
    return obj

def ball(name, loc, scale, mat, parent):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10)
    obj = bpy.context.object
    obj.name=name; obj.parent=parent; obj.location=loc; obj.scale=scale
    obj.data.materials.append(mat)
    for poly in obj.data.polygons: poly.use_smooth=True
    return obj

def rod(name,a,b,r1,r2,mat,parent):
    a,b = Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=12,radius1=r1,radius2=r2,depth=(b-a).length)
    obj=bpy.context.object; obj.name=name; obj.parent=parent; obj.location=(a+b)/2
    obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    obj.data.materials.append(mat)
    bevel=obj.modifiers.new('Crafted edge','BEVEL'); bevel.width=.012; bevel.segments=2
    for poly in obj.data.polygons: poly.use_smooth=True
    return obj

def box(name,loc,scale,mat,parent,bevel=.025):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj=bpy.context.object; obj.name=name; obj.parent=parent; obj.location=loc; obj.scale=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj.data.materials.append(mat)
    mod=obj.modifiers.new('Soft corners','BEVEL'); mod.width=bevel; mod.segments=2
    return obj

def mesh(name,vertices,faces,mat,parent):
    data=bpy.data.meshes.new(name); data.from_pydata(vertices,[],faces); data.update()
    obj=bpy.data.objects.new(name,data); bpy.context.collection.objects.link(obj)
    obj.parent=parent; obj.data.materials.append(mat)
    return obj

def blade(name,z0,z1,width,mat,parent):
    return mesh(name,[(-width,0,z0),(width,0,z0),(0,-width*.3,z0),(0,width*.3,z0),(0,0,z1)],
                [(0,2,4),(2,1,4),(1,3,4),(3,0,4),(0,3,1,2)],mat,parent)

def helmet(body,metal,iron=False):
    remove('Hair cap'); remove('Headband')
    vertices=[(0,.015,2.11)]; faces=[]; count=24
    for ring in range(1,7):
        theta=(math.pi/2)*ring/6
        for j in range(count):
            angle=math.tau*j/count
            vertices.append((.36*math.sin(theta)*math.cos(angle),.015+.325*math.sin(theta)*math.sin(angle),1.88+.23*math.cos(theta)))
    for j in range(count): faces.append((0,1+j,1+(j+1)%count))
    for ring in range(5):
        for j in range(count):
            a=1+ring*count+j; b=1+ring*count+(j+1)%count
            faces.append((a,b,b+count,a+count))
    mesh('Open-face helmet',vertices,faces,metal,body)
    rod('Helmet rim',(0,.015,1.86),(0,.015,1.90),.36,.36,metal,body)
    for a in [-.85,0,.85,math.pi]:
        ball('Helmet rivet',(.356*math.sin(a),.015-.33*math.cos(a),1.88),(.024,.024,.024),metal,body)
    if iron:
        for x in [-.305,.305]:
            ball('Helmet cheek guard',(x,.03,1.73),(.06,.17,.18),metal,body)
        box('Helmet ridge',(0,.02,2.06),(.055,.43,.075),metal,body)

def armor(body,metal,cloth,iron=False):
    ball('Back cuirass',(0,.17,1.02),(.31,.15,.25),metal,body)
    for side in [-1,1]:
        ball('Pauldron',(side*.31,0,1.235),(.17,.25,.095),metal,body)
        rod('Cuirass edging',(side*.23,-.255,.91),(side*.23,-.255,1.18),.028,.028,metal,body)
        for z in [.94,1.14]: ball('Armor fastening',(side*.23,-.279,z),(.026,.014,.026),metal,body)
    # Preserve a broad blue front panel for the existing team-color shader.
    if iron:
        ball('Mail collar',(0,.0,1.30),(.24,.22,.065),metal,body)
        for side in [-1,1]:
            for z in [.64,.70,.76]:
                box('Lamellar skirt',(side*.235,-.18,z),(.14,.12,.065),metal,body,.01)

def arm_rig(body,side,skin,linen):
    shoulder=sorted([o for o in body.children if o.type=='EMPTY' and o.name.startswith('Shoulder')],key=lambda o:o.location.x)[0 if side<0 else 1]
    for child in list(shoulder.children):
        for obj in reversed(descendants(child)): bpy.data.objects.remove(obj,do_unlink=True)
    parts=[rod('Articulated upper arm',(0,0,0),(0,0,1),.115,.097,skin,body),
           rod('Articulated forearm',(0,0,0),(0,0,1),.095,.082,skin,body),
           rod('Wrist wrap',(0,0,0),(0,0,1),.09,.09,linen,body),
           ball('Weapon grip hand',(0,0,0),(.095,.09,.10),skin,body)]
    return shoulder,parts,side

def aim_arm(rig,hand):
    shoulder,parts,side=rig
    a=Vector(shoulder.location); b=Vector(hand); delta=b-a; direction=delta.normalized()
    bend=Vector((side,0,0)); bend=(bend-direction*bend.dot(direction)).normalized()
    elbow=(a+b)/2+bend*math.sqrt(max(.004,.36**2-(delta.length/2)**2))
    for obj,start,end in [(parts[0],a,elbow),(parts[1],elbow,b),(parts[2],elbow.lerp(b,.78),b)]:
        obj.location=(start+end)/2; obj.rotation_euler=(end-start).to_track_quat('Z','Y').to_euler(); obj.scale.z=(end-start).length
    parts[3].location=b

def moving_line(name,mat,parent,radius=.014):
    return rod(name,(0,0,0),(0,0,1),radius,radius,mat,parent)

def line_between(obj,a,b):
    a,b=Vector(a),Vector(b)
    obj.location=(a+b)/2; obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler(); obj.scale.z=(b-a).length

def build(unit,spec):
    label,age,base,actions=spec
    source=ROOT/('art/mounted_units/mounted_spearman.blend' if base=='mounted' else f'art/outlined_units/{"clubman" if base=="siege" else base}.blend')
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene=bpy.context.scene; facing=bpy.data.objects['Facing']; body=bpy.data.objects['Body']
    scene.render.resolution_x=192; scene.render.resolution_y=192; scene.render.resolution_percentage=100
    scene.render.film_transparent=True; scene.render.image_settings.color_mode='RGBA'
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.compression=25
    iron=age=='Iron'
    metal=material('Age iron' if iron else 'Age bronze','A5ACA5' if iron else 'C78B47')
    leather=material('Age dark leather','65472F')
    wood=bpy.data.materials['1_cartoon wood']; linen=bpy.data.materials['1_cartoon linen']
    cloth=bpy.data.materials['1_cartoon blue cloth']; skin=bpy.data.materials['1_cartoon skin']
    animated=[]; pose=None; ortho=scene.camera.data.ortho_scale
    if base=='worker':
        for obj in scene.objects:
            if obj.type=='MESH':
                for slot in obj.material_slots:
                    if slot.material and slot.material.name=='Worker steel': slot.material=metal
        rod('Age apron belt',(0,0,.79),(0,0,.87),.32,.32,leather,body)
        ball('Metal belt clasp',(0,-.325,.83),(.07,.025,.045),metal,body)
        if iron:
            box('Spare hammer head',(-.34,.015,.98),(.19,.12,.09),metal,body)
            rod('Spare tool handle',(-.34,.015,.74),(-.34,.015,1.0),.027,.027,wood,body)
            bpy.data.objects['Apron bib'].data.materials[0]=leather
        else:
            bpy.data.objects['Apron bib'].data.materials[0]=linen
        box('Apron pocket',(.13,-.302,.99),(.17,.035,.13),leather,body,.014)
        rod('Pocket stitched lip',(.055,-.325,1.045),(.205,-.325,1.045),.012,.012,linen,body)
        for x in [-.13,.13]: ball('Apron strap button',(x,-.277,1.20),(.025,.018,.025),metal,body)
        # The original shoulder swing points the handle at the resource. Build
        # the tool around a real wrist grip, with its cutting edge across -Y.
        remove('Pickaxe'); remove('Building hammer')
        rig_l=arm_rig(body,-1,skin,linen); rig_r=arm_rig(body,1,skin,linen)
        animated+=rig_l[1]+rig_r[1]
        pick=pivot('Pickaxe',(0,-.30,1.10),body)
        rod('Pick handle',(0,0,-.20),(0,0,.65),.042,.045,wood,pick)
        rod('Pick cutting horn',(0,0,.65),(0,-.38,.70),.085,.006,metal,pick)
        rod('Pick rear horn',(0,0,.65),(0,.28,.60),.085,.015,metal,pick)
        pivot('Pick cutting edge',(0,-.38,.70),pick)
        rod('Pick head socket',(0,0,.55),(0,0,.68),.07,.07,metal,pick)
        for z in [-.19,-.13,-.07]: rod('Pick grip binding',(0,0,z),(0,0,z+.025),.046,.046,leather,pick)
        hammer=pivot('Building hammer',(0,-.30,1.10),body)
        rod('Hammer handle',(0,0,-.23),(0,0,.51),.042,.045,wood,hammer)
        box('Hammer head',(0,0,.54),(.16,.29,.17),metal,hammer)
        pivot('Hammer striking face',(0,-.145,.54),hammer)
        animated += [pick,hammer]
        def pose(action,i):
            body.rotation_euler=(0,0,0)
            tool=hammer if action=='build' else pick
            for candidate in [pick,hammer]:
                for obj in descendants(candidate):
                    obj.hide_render=candidate!=tool; obj.hide_viewport=obj.hide_render
                    obj.keyframe_insert('hide_render',frame=actions.index(action)*8+i+1)
                    obj.keyframe_insert('hide_viewport',frame=actions.index(action)*8+i+1)
            if action in ['gather','build']:
                tool.location=[(.20,-.43,1.10),(.32,-.38,1.23),(.38,-.34,1.28),(.20,-.46,1.25),
                               (0,-.56,.97),(.02,-.53,1.00),(.16,-.43,1.13),(.20,-.43,1.10)][i]
                tool.location.y-=.09
                tool.rotation_euler=([.18,-.35,-.50,.65,1.55,1.48,.60,.18][i],
                                     [.65,.85,.90,.45,0,.05,.40,.65][i],
                                     [0,-.12,-.18,0,0,0,0,0][i])
                aim_arm(rig_l,Vector(tool.location)+tool.rotation_euler.to_matrix()@Vector((0,0,-.19)))
            else:
                phase=math.tau*i/8
                tool.location=(.40,-.20+.04*math.sin(phase),.96)
                tool.rotation_euler=(.15,.24,-.10)
                aim_arm(rig_l,(-.40,-.13-.08*math.sin(phase) if action=='run' else -.13,.77))
            aim_arm(rig_r,tool.location)
            rig_r[1][3].rotation_euler=tool.rotation_euler
    elif base=='clubman':
        # Turn the shoulders independently of the planted legs. A sword cut
        # travels across the opponent; it does not repeat the worker's lift.
        stance=body
        hips=sorted([o for o in stance.children if o.name.startswith('Hip')],key=lambda o:o.location.x)
        hip_origins=[o.location.copy() for o in hips]
        body=pivot('Sword torso',(0,0,0),stance)
        for obj in list(stance.children):
            if obj!=body and obj not in hips: obj.parent=body
        animated += [stance,*hips]
        remove('Right-hand club'); helmet(body,metal,iron); armor(body,metal,cloth,iron)
        arms=sorted([o for o in body.children if o.type=='EMPTY' and o.name.startswith('Shoulder')],key=lambda o:o.location.x)
        animated.append(arms[0])
        rig=arm_rig(body,1,skin,linen); animated+=rig[1]
        sword=pivot('Sword grip',(.42,-.22,1.10),body); animated.append(sword)
        rod('Leather sword grip',(0,0,-.10),(0,0,.13),.043,.043,leather,sword)
        rod('Sword crossguard',(-.15,0,.14),(.15,0,.14),.037,.037,metal,sword)
        for side in [-1,1]:
            rod('Guard swept tip',(side*.15,0,.14),(side*.205,0,.10),.037,.024,metal,sword)
        for z in [-.07,-.02,.03,.08]:
            rod('Hilt leather wrap',(0,0,z),(0,0,z+.017),.047,.047,leather,sword)
        # A tapered diamond section gives the blade two cutting edges and a
        # light-catching central ridge, instead of a blunt rectangular bar.
        height=1.16 if iron else 1.00
        vertices=[]
        for z,w,d in [(.18,.095,.027),(.32,.105,.030),(height-.12,.060,.019)]:
            vertices += [(-w,0,z),(0,-d,z),(w,0,z),(0,d,z)]
        vertices.append((0,0,height+.20))
        faces=[(3,2,1,0)]
        for r in range(2):
            for j in range(4): faces.append((r*4+j,r*4+(j+1)%4,(r+1)*4+(j+1)%4,(r+1)*4+j))
        faces += [(8+j,8+(j+1)%4,12) for j in range(4)]
        mesh('Sword blade',vertices,faces,metal,sword)
        ball('Sword pommel',(0,0,-.12),(.065,.055,.05),metal,sword)
        pivot('Sword cutting tip',(0,0,height+.20),sword)
        shield=bpy.data.objects['Left-hand wooden buckler']
        for obj in descendants(shield):
            if obj.type=='MESH' and obj.data.materials: obj.data.materials[0]=metal
        if iron: shield.scale*=1.22
        def pose(action,i):
            body.rotation_euler=(0,0,0)
            if action=='attack':
                stance.rotation_euler=(0,0,0)
                stance.location=(0,[0,.025,.035,-.025,-.10,-.10,-.035,0][i],0)
                body.rotation_euler.z=[-.08,-.32,-.45,-.22,.10,.38,.20,-.08][i]
                sword.location=[(.46,-.27,1.14),(.59,-.04,1.24),(.63,.02,1.27),(.55,-.42,1.24),
                                (.18,-.65,1.16),(-.25,-.65,1.03),(.05,-.60,1.00),(.46,-.27,1.14)][i]
                direction=Vector([(.30,-.65,.70),(.96,.18,.22),(.94,.24,.25),(.74,-.67,.10),
                                  (-.30,-.95,-.04),(-.91,-.40,-.11),(-.65,-.35,.67),(.30,-.65,.70)][i]).normalized()
                # Local X is a sharp edge of the diamond-section blade. Keep
                # that edge facing the cut's tangent rather than slapping
                # with the broad face as the wrist turns.
                edge=Vector((-1,0,-.23))
                edge=(edge-direction*edge.dot(direction)).normalized()
                normal=direction.cross(edge).normalized()
                sword.rotation_euler=Matrix((edge,normal,direction)).transposed().to_euler()
                arms[0].rotation_euler=(-.20,0,-.12)
                for j,hip in enumerate(hips):
                    hip.location=hip_origins[j]
                    hip.rotation_euler=([-.05,-.05,-.05,-.25,-.30,-.27,-.14,-.05][i] if j==0 else [.06,.10,.12,.14,.17,.17,.10,.06][i],0,0)
                bpy.context.view_layer.update()
                for j,hip in enumerate(hips):
                    boots=[o for o in hip.children_recursive if o.name in ['Boot','Boot.001']]
                    bottom=min((o.matrix_world@Vector(c)).z for o in boots for c in o.bound_box)
                    hip.location.z+=(.055 if j==0 and i==3 else 0)-bottom
            else:
                sword.location=(.43,-.23+.04*math.sin(math.tau*i/8),1.08)
                direction=Vector((.12,-.38,.92))
                sword.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
            aim_arm(rig,sword.location)
            rig[1][3].rotation_euler=sword.rotation_euler
        ortho=4.8
    elif base=='spearman':
        remove('Wooden spear'); helmet(body,metal,iron); armor(body,metal,cloth,iron)
        rig=arm_rig(body,1,skin,linen); animated+=rig[1]
        spear=pivot('Pike' if iron else 'Bronze spear',(.42,-.30,1.05),body)
        length=1.85 if iron else 1.40
        rod('Spear shaft',(0,0,-.58),(0,0,length),.033,.028,wood,spear)
        blade('Metal spearhead',length,length+.29,.078,metal,spear)
        rod('Spear socket',(0,0,length-.08),(0,0,length+.04),.044,.044,metal,spear)
        rod('Spear ferrule',(0,0,-.60),(0,0,-.48),.039,.039,metal,spear)
        for z in [-.14,-.08,-.02,.04]: rod('Spear grip binding',(0,0,z),(0,0,z+.022),.038,.038,leather,spear)
        pivot('Spear cutting tip',(0,0,length+.29),spear)
        animated.append(spear)
        def pose(action,i):
            spear.location=(.42,-.30,1.07); spear.rotation_euler=(.17,0,0)
            if action=='attack':
                spear.location=[(.44,-.23,1.02),(.46,-.14,1.03),(.49,-.07,1.00),(.38,-.42,1.04),
                                (.30,-.64,1.02),(.32,-.52,1.03),(.40,-.32,1.02),(.44,-.23,1.02)][i]
                # Side-held grip aims inward and slightly upward. At extension
                # the point meets the center of the enemy's lane, not a parallel
                # line offset by the width of our right shoulder.
                tip_height=[1.27,1.36,1.40,1.24,1.14,1.18,1.24,1.27][i]
                dx=-spear.location.x; dz=tip_height-spear.location.z
                dy=-math.sqrt((length+.29)**2-dx*dx-dz*dz)
                spear.rotation_euler=Vector((dx,dy,dz)).to_track_quat('Z','Y').to_euler()
                body.rotation_euler=(0,0,0)
            aim_arm(rig,spear.location)
            rig[1][3].rotation_euler=spear.rotation_euler
        # Reserve room for a fully extended east/west thrust. Render scale in
        # the manifest compensates, keeping bodies the same world-space size.
        ortho=6.2 if iron else 5.2
    elif base=='slinger':
        remove('Forked wooden slingshot'); remove('Draw hand'); remove('Stone pouch'); remove('Pouch strap')
        if iron: helmet(body,metal,True)
        else:
            rod('Leather shoulder strap',(-.25,-.29,.84),(.23,-.25,1.22),.04,.04,leather,body)
        rig_l=arm_rig(body,-1,skin,linen); rig_r=arm_rig(body,1,skin,linen)
        animated+=rig_l[1]+rig_r[1]
        weapon=pivot('Crossbow' if iron else 'Bow',(0,-.50,1.20),body); animated.append(weapon)
        string=[moving_line('Draw string',linen,weapon,.018) for _ in range(2)]; animated+=string
        bow_segments=[]
        if iron:
            box('Crossbow stock',(0,-.12,0),(.105,.60,.11),wood,weapon)
            rod('Bolt rail',(0,.33,.065),(0,-.62,.065),.022,.022,metal,weapon)
            ends=[Vector((-.48,-.26,0)),Vector((.48,-.26,0))]
            for side in [-1,1]:
                rod('Steel bow limb',(0,-.30,0),(side*.26,-.38,0),.043,.038,metal,weapon)
                rod('Steel bow tip',(side*.26,-.38,0),(side*.48,-.26,0),.038,.020,metal,weapon)
            rod('Trigger lever',(0,.14,-.03),(0,.16,-.15),.025,.025,metal,weapon)
        else:
            ends=[Vector((0,-.13,-.64)),Vector((0,-.13,.64))]
            for side in [-1,1]:
                points=[(0,0,0),(0,-.10,side*.27),(0,-.17,side*.49),(0,-.13,side*.64)]
                for j in range(3):
                    segment=moving_line('Curved wooden bow',wood,weapon,.033-j*.006)
                    bow_segments.append((side,j,segment)); animated.append(segment)
            rod('Bow grip',(0,0,-.10),(0,0,.10),.045,.045,leather,weapon)
        arrow=pivot('Loaded bolt' if iron else 'Nocked arrow',(0,0,.07 if iron else .03),weapon)
        rod('Projectile shaft',(0,.16,0),(0,-.66,0),.012,.012,wood,arrow)
        tip=rod('Projectile point',(0,-.66,0),(0,-.79,0),.042,0,metal,arrow)
        for side in [-1,1]: rod('Projectile fletching',(0,.10,0),(side*.05,.19,0),.023,.005,linen,arrow)
        animated.append(arrow)
        quiver=rod('Back quiver',(.20,.23,.71),(.25,.24,1.33),.105,.13,leather,body)
        for z in [.78,1.25]: rod('Quiver binding',(.20+(z-.71)*.08,.24,z),(.20+(z-.71)*.08,.24,z+.04),.134,.134,linen,body)
        for x in [.17,.25,.32]:
            rod('Spare arrow',(x,.25,1.22),(x,.25,1.54 if not iron else 1.45),.014,.014,wood,body)
            ball('Quiver fletching',(x,.25,1.51 if not iron else 1.43),(.032,.025,.065),linen,body)
        def pose(action,i):
            body.rotation_euler=(0,0,0)
            weapon.location=(.35,-.48,1.43) if not iron else (0,-.60,1.25)
            weapon.rotation_euler=(0,0,0)
            if iron:
                # Fire, lower, reach the relaxed string, pull to the latch,
                # retrieve a bolt, seat it on the rail, then aim again.
                draw=[.27,.27,-.22,-.22,.04,.27,.27,.27][i] if action=='shoot' else .27
                if action=='shoot':
                    weapon.rotation_euler.x=[0,0,.10,.48,.48,.42,.28,.12][i]
                    weapon.location.z=[1.25,1.25,1.24,1.07,1.07,1.08,1.12,1.18][i]
                    weapon.location.y=[-.60,-.60,-.60,-.62,-.62,-.62,-.60,-.60][i]
                hidden=action=='shoot' and i in [2,3,4,5,6]
            else:
                draw=[.06,.14,.28,.42,.42,0,.02,.06][i] if action=='shoot' else .06
                hidden=action=='shoot' and i in [5,6]
                for side,j,segment in bow_segments:
                    points=[(0,0,0),(0,-.10+draw*.15,side*.27),
                            (0,-.17+draw*.30,side*.49),(0,-.13+draw*.55,side*(.64-.08*draw))]
                    line_between(segment,points[j],points[j+1])
                ends[:]=[Vector((0,-.13+draw*.55,side*(.64-.08*draw))) for side in [-1,1]]
            nock=Vector((0,draw,.065 if iron else .03))
            for obj,end in zip(string,ends): line_between(obj,end,nock)
            arrow.location.y=draw-.16
            arrow.hide_render=hidden
            arrow.hide_viewport=arrow.hide_render
            for obj in descendants(arrow):
                obj.hide_render=arrow.hide_render; obj.hide_viewport=arrow.hide_viewport
                obj.keyframe_insert('hide_render',frame=actions.index(action)*8+i+1)
                obj.keyframe_insert('hide_viewport',frame=actions.index(action)*8+i+1)
            rotation=weapon.rotation_euler.to_matrix()
            aim_arm(rig_l,weapon.location+rotation@Vector((-.03,-.02,-.08 if iron else 0)))
            if iron:
                hand_local=nock+Vector((.035,0,0)) if action=='shoot' and i in [3,4,5] else Vector((.035,.23,-.12))
                hand=weapon.location+rotation@hand_local
                if action=='shoot' and i==6: hand=Vector((.40,.22,1.32))
                if action=='shoot' and i==7: hand=weapon.location+rotation@Vector((.035,.06,.13))
            else:
                hand=weapon.location+nock+Vector((.035,.01,0))
                if action=='shoot' and i==5: hand=Vector((.43,-.04,1.40))
                if action=='shoot' and i==6: hand=Vector((.40,.22,1.32))
            aim_arm(rig_r,hand)
    elif base=='mounted':
        helmet(body,metal,iron)
        horse=bpy.data.objects['Horse body suspension']
        for side in [-1,1]:
            box('Saddle pouch',(side*.39,.43,1.62),(.14,.28,.22),leather,horse,.035)
            ball('Saddle pouch clasp',(side*.467,.39,1.64),(.018,.028,.032),metal,horse)
        if iron:
            armor(body,metal,cloth,True)
            horse=bpy.data.objects['Horse body suspension']
            ball('Light chest barding',(0,-.67,1.43),(.36,.14,.33),metal,horse)
            for side in [-1,1]:
                ball('Armored saddle flank',(side*.36,.40,1.46),(.055,.43,.25),metal,horse)
            head=bpy.data.objects['Head']
            ball('Horse forehead plate',(0,-.16,.02),(.13,.17,.12),metal,head)
        point=bpy.data.objects['Wood spear point']; point.data.materials[0]=metal
        spear=bpy.data.objects['Rider wooden spear']
        rod('Metal spear socket',(0,0,1.47),(0,0,1.59),.048,.048,metal,spear)
    elif base=='healer':
        staff=bpy.data.objects['Healing staff']
        # Keep the staff outside the hood through the walking/casting motion.
        # The original shoulder-driven rotation swept its finial through it.
        staff.parent=body; staff.animation_data_clear()
        rig=arm_rig(body,1,skin,linen); animated+=rig[1]+[staff]
        def pose(action,i):
            phase=math.tau*i/8
            staff.location=(.48,-.27,1.00+.025*math.sin(phase) if action=='run' else 1.00)
            staff.rotation_euler=(.18 if action=='attack' else .08,.19,0)
            aim_arm(rig,staff.location)
            rig[1][3].rotation_euler=staff.rotation_euler
        for z in [.05,.11,.17]: rod('Staff grip binding',(0,0,z),(0,0,z+.025),.065,.065,leather,staff)
        for x in [-.15,.15]: rod('Robe embroidered trim',(x,-.277,.73),(x,-.255,1.15),.012,.012,metal,body)
        box('Herb satchel',(.31,.04,.73),(.17,.22,.20),leather,body,.035)
        ball('Satchel clasp',(.39,-.01,.77),(.026,.033,.026),metal,body)
        if iron:
            robe=bpy.data.objects['Cream robe']; robe.scale.x*=1.07
            rod('Priest robe hem',(0,0,.27),(0,0,.35),.385,.385,metal,body)
            ball('Priest mantle',(0,.11,1.27),(.34,.24,.09),cloth,body)
            ball('Priest clasp',(0,-.26,1.23),(.07,.025,.06),metal,body)
            staff=bpy.data.objects['Healing staff']
            for side in [-1,1]:
                rod('Ornate staff crown',(side*.17,0,1.15),(side*.20,0,1.41),.027,.020,metal,staff)
            ball('Staff crown jewel',(0,0,1.31),(.10,.07,.12),cloth,staff)
            box('Prayer book',(-.30,.04,.77),(.14,.19,.23),leather,body)
        # Bronze Healer deliberately retains its already-approved source model.
    else:
        remove('Body')
        body=pivot('Siege chassis',(0,0,0),facing)
        wheels=[]
        for x in [-.58,.58]:
            box('Timber chassis runner',(x,0,.52),(.15,1.85,.17),wood,body)
        for y in [-.64,.64]:
            rod('Axle',(-.90,y,.33),(.90,y,.33),.07,.07,metal,body)
            for side in [-1,1]:
                wheel=pivot('Wheel',(side*.78,y,.33),body); wheels.append(wheel)
                bpy.ops.mesh.primitive_torus_add(major_radius=.27,minor_radius=.060,major_segments=20,minor_segments=8)
                ring=bpy.context.object; ring.name='Wheel rim'; ring.parent=wheel; ring.location=(0,0,0); ring.rotation_euler.y=math.pi/2; ring.data.materials.append(metal if iron else wood)
                rod('Wheel hub',(-.09,0,0),(.09,0,0),.095,.095,metal,wheel)
                for a in range(6):
                    angle=math.tau*a/6
                    rod('Wheel spoke',(0,0,0),(0,.25*math.sin(angle),.25*math.cos(angle)),.026,.024,wood,wheel)
        turret=pivot('Siege firing frame',(0,0,0),body)
        box('Bolt bed',(0,.05,.99),(.24,2.00,.18),wood,turret)
        for side in [-1,1]:
            rod('Frame diagonal',(side*.57,.56,.57),(side*.30,-.36,1.10),.08,.08,wood,body)
        box('Torsion crossbeam',(0,-.53,.99),(1.64,.22,.20),wood,turret)
        for side in [-1,1]:
            rod('Torsion bundle',(side*.65,-.53,.87),(side*.65,-.53,1.31),.115,.115,linen,turret)
            for z in [.89,1.26]: box('Torsion cap',(side*.65,-.53,z),(.27,.28,.085),metal,turret)
        limb_pivots=[]
        for side in [-1,1]:
            limb=pivot('Torsion arm',(side*.65,-.53,1.10),turret)
            rod('Throwing arm',(0,0,0),(side*.57,.20,0),.075,.050,wood,limb)
            limb_pivots.append(limb)
        strings=[moving_line('Siege bowstring',linen,turret,.025) for _ in range(2)]
        bolt=pivot('Siege bolt',(0,0,1.14),turret)
        rod('Siege bolt shaft',(0,.56,0),(0,-1.0,0),.032,.032,wood,bolt)
        rod('Siege bolt head',(0,-1.0,0),(0,-1.26,0),.11,0,metal,bolt)
        for side in [-1,1]:
            mesh('Bolt vanes',[(0,.47,0),(side*.14,.69,0),(0,.71,0)],[(0,1,2)],linen,bolt)
        rod('Winch spindle',(-.25,.85,.97),(.25,.85,.97),.11,.11,metal,turret)
        crank=pivot('Winch crank',(.26,.85,.97),turret)
        rod('Crank arm',(0,0,0),(0,0,.20),.027,.027,metal,crank)
        rod('Crank handle',(0,0,.20),(.14,0,.20),.035,.035,wood,crank)
        box('Team panel',(0,-.69,.81),(.48,.055,.25),cloth,body)
        for side in [-1,1]:
            for y in [-.65,.64]:
                ball('Chassis joinery peg',(side*.58,y,.615),(.037,.037,.024),metal,body)
            box('Bolt guide rail',(side*.095,-.13,1.095),(.024,1.75,.04),metal,turret,.006)
        if iron:
            for side in [-1,1]:
                box('Iron chassis reinforcement',(side*.59,0,.60),(.17,1.88,.05),metal,body)
                box('Heavy frame cheek',(side*.19,-.07,1.01),(.08,1.65,.27),metal,turret)
            box('Heavy rear shield',(0,.79,.72),(.96,.09,.32),cloth,body)
            for x in [-.39,0,.39]: ball('Shield rivet',(x,.73,.72),(.035,.025,.035),metal,body)
            body.scale=(1.08,1.08,1.08)
        animated=[body,turret,bolt,crank]+wheels+limb_pivots+strings
        def pose(action,i):
            draw=[.05,.14,.27,.42,.45,.00,.015,.05][i] if action=='attack' else .05
            turret.location.y=[0,0,0,0,0,.10,.035,0][i] if action=='attack' else 0
            for wheel in wheels: wheel.rotation_euler.x=-math.tau*i/8 if action=='run' else 0
            body.location.z=.008*math.sin(math.tau*i/8*2) if action=='run' else 0
            crank.rotation_euler.x=math.tau*min(i,4)/4 if action=='attack' else 0
            nock=Vector((0,draw,1.14))
            for side,limb,line in zip([-1,1],limb_pivots,strings):
                limb.rotation_euler.z=side*draw*.45
                end=Vector(limb.location)+limb.rotation_euler.to_matrix()@Vector((side*.57,.20,0))
                line_between(line,end,nock)
            # The bowstring bears on the rear of the bolt, not its middle.
            bolt.location.y=draw-.56
            for obj in descendants(bolt):
                obj.hide_render=action=='attack' and i in [5,6]
                obj.hide_viewport=obj.hide_render
                obj.keyframe_insert('hide_render',frame=actions.index(action)*8+i+1)
                obj.keyframe_insert('hide_viewport',frame=actions.index(action)*8+i+1)
        ortho=5.2 if iron else 4.8
        scene.camera.location=(0,-7,5.6)
        scene.camera.rotation_euler=(Vector((0,0,.80))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.ortho_scale=ortho
    if pose:
        for a,action in enumerate(actions):
            for i in range(8):
                frame=a*8+i+1; scene.frame_set(frame); pose(action,i)
                for obj in [body]+animated:
                    for prop in ['location','rotation_euler','scale']: obj.keyframe_insert(prop,frame=frame)
    # Resample each action separately. Quaternion interpolation avoids the
    # long-way rotation of a wrist; a closing pose prevents blending into the
    # next action. Re-solve arms after interpolation so grips stay attached.
    objects=[o for o in scene.objects if o.animation_data and o!=facing]
    samples=[]
    for a,action in enumerate(actions):
        cycle=[]
        for i in range(8):
            scene.frame_set(a*8+i+1)
            cycle.append({o:(o.location.copy(),o.rotation_euler.to_quaternion(),o.scale.copy(),o.hide_render,o.hide_viewport) for o in objects})
        samples.append(cycle)
    for obj in objects: obj.animation_data_clear()
    for a,action in enumerate(actions):
        previous={}
        for i in range(17):
            j=(i//2)%8; t=(i%2)*.5
            first=samples[a][j]; second=samples[a][(j+1)%8]
            for obj in objects:
                p,q=first[obj],second[obj]
                obj.location=p[0].lerp(q[0],t)
                obj.rotation_euler=p[1].slerp(q[1],t).to_euler()
                obj.scale=p[2].lerp(q[2],t)
                obj.hide_render=p[3]; obj.hide_viewport=p[4]
                if obj.name.startswith(('Draw string','Curved wooden bow','Siege bowstring')):
                    def endpoint(s,sign): return s[0]+s[1]@Vector((0,0,sign*s[2].z*.5))
                    line_between(obj,endpoint(p,-1).lerp(endpoint(q,-1),t),endpoint(p,1).lerp(endpoint(q,1),t))
            if base=='worker':
                tool=hammer if action=='build' else pick
                aim_arm(rig_r,tool.location); rig_r[1][3].rotation_euler=tool.rotation_euler
                left=(tool.location+tool.rotation_euler.to_matrix()@Vector((0,0,-.19))) if action in ['gather','build'] else rig_l[1][3].location.copy()
                aim_arm(rig_l,left)
            elif base in ['clubman','spearman','healer']:
                tool=sword if base=='clubman' else spear if base=='spearman' else staff
                aim_arm(rig,tool.location); rig[1][3].rotation_euler=tool.rotation_euler
            elif base=='slinger':
                rotation=weapon.rotation_euler.to_matrix()
                aim_arm(rig_l,weapon.location+rotation@Vector((-.03,-.02,-.08 if iron else 0)))
                hand=rig_r[1][3].location.copy()
                pulling=(j in [3,4] or (j==5 and t==0)) if iron else (j<4 or (j==4 and t==0))
                if action=='shoot' and pulling:
                    nock=string[0].location+string[0].rotation_euler.to_matrix()@Vector((0,0,string[0].scale.z*.5))
                    hand=weapon.location+rotation@(nock+Vector((.035,0 if iron else .01,0)))
                aim_arm(rig_r,hand)
            frame=a*17+i+1
            for obj in objects:
                if obj in previous: obj.rotation_euler.make_compatible(previous[obj])
                previous[obj]=obj.rotation_euler.copy()
                for prop in ['location','rotation_euler','scale','hide_render','hide_viewport']: obj.keyframe_insert(prop,frame=frame)
    # Linear interpolation between the dense, resolved poses keeps Blender
    # playback from overshooting into the face between exported frames.
    for obj in objects:
        for layer in obj.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:
                            key.interpolation='CONSTANT' if curve.data_path.startswith('hide_') else 'LINEAR'
    scene.timeline_markers.clear()
    for a,action in enumerate(actions): scene.timeline_markers.new(action,frame=a*17+1)
    scene.frame_start=1; scene.frame_end=len(actions)*17; scene.render.fps=20
    scene.frame_set(1); facing.rotation_euler.z=math.radians(45)
    ground=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
    metadata=dict(name=label,age=age,base=base,actions=actions,frames_per_direction=16,fps=20,timeline_stride=17,ground_anchor=[round(ground.x,6),round(1-ground.y,6)],render_scale=ortho/4.1)
    if base in ['clubman','spearman']: metadata['action_events']={'attack':{'impact_frame':8}}
    if base=='worker': metadata['action_events']={a:{'impact_frame':8} for a in ['gather','build']}
    if base=='slinger': metadata['action_events']={'shoot':{'release_frame':4 if iron else 10}}
    folder=OUT/'models'; folder.mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/f'{unit}.blend'))
    (folder/f'{unit}.json').write_text(json.dumps(metadata,indent=2))
    if '--models-only' in sys.argv: return
    preview='--preview' in sys.argv
    motion_preview='--motion-preview' in sys.argv
    for a,action in enumerate(actions):
        if motion_preview and action in ['idle','run']: continue
        for direction,angle in DIRECTIONS.items():
            if preview and direction not in ['SE','NW']: continue
            if motion_preview and direction not in ['E','SE','S','NW']: continue
            facing.rotation_euler.z=math.radians(angle)
            folder=OUT/('motion-previews' if motion_preview else 'previews' if preview else 'frames')/unit/action/direction
            folder.mkdir(parents=True,exist_ok=True)
            for i in ([0,8] if preview else range(16)):
                target=folder/f'{i:02}.png'
                if '--resume' in sys.argv and target.exists(): continue
                scene.frame_set(a*17+i+1); scene.render.filepath=str(target)
                bpy.ops.render.render(write_still=True)
        print(f'AGE_RENDER {unit} {action}',flush=True)

if __name__=='__main__':
    for unit,spec in SPECS.items():
        if '--shard' in sys.argv:
            shard,count=map(int,sys.argv[sys.argv.index('--shard')+1].split('/'))
            if list(SPECS).index(unit)%count!=shard: continue
        if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]: continue
        if '--affected' in sys.argv and unit not in list(SPECS)[:8]: continue
        if '--from' in sys.argv and list(SPECS).index(unit)<list(SPECS).index(sys.argv[sys.argv.index('--from')+1]): continue
        build(unit,spec)
