"""Readability studies for remaining foot units; no mounted/siege changes."""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Matrix,Vector
from bpy_extras.object_utils import world_to_camera_view
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
import motion_corrections
ROOT=OUT.parents[2]
GROUPS={'ranged':['slinger','archer','crossbowman'],'spears':['spearman','bronze_spearman','pikeman'],'healers':['healer','priest']}
DIRECTIONS=dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135)

def reshape(obj,center,factors):
    matrix=Matrix.LocRotScale(obj.location,obj.rotation_euler.to_quaternion(),obj.scale);inverse=matrix.inverted();center=Vector(center)
    for v in obj.data.vertices:
        point=matrix@v.co-center
        v.co=inverse@(Vector(tuple(point[i]*factors[i] for i in range(3)))+center)

def wrapper(root,children,scale,name):
    helper=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(helper)
    helper.parent=root;helper.scale=scale
    for obj in children:obj.parent=helper
    return helper

def linear(objects):
    for obj in objects:
        if not obj.animation_data or not obj.animation_data.action:continue
        for layer in obj.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points:key.interpolation='LINEAR'

def enlarge_sling():
    scene=bpy.context.scene;sling=bpy.data.objects['Forked wooden slingshot']
    shoulder=bpy.data.objects['Shoulder']
    helper=bpy.data.objects.new('Sling arm clearance',None);bpy.context.collection.objects.link(helper)
    helper.parent=shoulder.parent;helper.location=(-.08,-.20,0);shoulder.parent=helper
    carry=[]
    for t in range(1,17):
        scene.frame_set(t);carry.append((t,-.70+shoulder.rotation_euler.x*.15))
    for t,angle in carry:
        shoulder.rotation_euler.x=angle;shoulder.keyframe_insert('rotation_euler',frame=t)
        sling.rotation_euler.x=-angle;sling.keyframe_insert('rotation_euler',frame=t)
    hand=bpy.data.objects['Fist'];elbow=hand.location+Vector((-.20,.06,.16));wrist=hand.location+(elbow-hand.location).normalized()*.16
    fore=bpy.data.objects['Forearm'];depth=max(v.co.z for v in fore.data.vertices)-min(v.co.z for v in fore.data.vertices)
    fore.location=(elbow+wrist)/2;fore.rotation_euler=(wrist-elbow).to_track_quat('Z','Y').to_euler();fore.scale.z=(wrist-elbow).length/depth
    upper=bpy.data.objects['Upper arm'];depth=max(v.co.z for v in upper.data.vertices)-min(v.co.z for v in upper.data.vertices)
    for i in range((scene.frame_end-1)*4+1):
        t=1+i/4;scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
        start=shoulder.matrix_world.inverted()@(helper.parent.matrix_world@shoulder.location)
        upper.location=(start+elbow)/2;upper.rotation_euler=(elbow-start).to_track_quat('Z','Y').to_euler();upper.scale.z=(elbow-start).length/depth
        for prop in ['location','rotation_euler','scale']:upper.keyframe_insert(prop,frame=t)
    for obj in sling.children:
        if obj.type=='MESH' and obj.name.startswith('Fork'):reshape(obj,(0,0,.17),(1.5,1.2,1.25))
    pouch=bpy.data.objects['Stone pouch'];pouch.scale*=1.35;pouch.location.x-=.035
    bands=sorted([o for o in sling.children if o.name.startswith('Sling band')],key=lambda o:o.name)
    depths={o:max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices) for o in bands}
    values=[]
    for i in range((scene.frame_end-1)*4+1):
        t=1+i/4;scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
        end=sling.matrix_world.inverted()@bpy.data.objects['Fist.001'].matrix_world.translation if t>=17 else Vector((0,.03,.36))
        for side,obj in zip([-1,1],bands):
            start=Vector((side*.24,0,.47));rot=(end-start).to_track_quat('Z','Y').to_euler()
            values.append((t,obj,(start+end)/2,rot,(end-start).length/depths[obj]))
    prev={}
    for t,obj,loc,rot,length in values:
        if obj in prev:rot.make_compatible(prev[obj])
        prev[obj]=rot.copy();obj.location=loc;obj.rotation_euler=rot;obj.scale.z=length
        for prop in ['location','rotation_euler','scale']:obj.keyframe_insert(prop,frame=t)
    linear(bands)

def ranged_grips(unit):
    if unit=='slinger':return
    scene=bpy.context.scene;bow=bpy.data.objects['Bow' if unit=='archer' else 'Crossbow']
    arrow=bpy.data.objects['Nocked arrow' if unit=='archer' else 'Loaded bolt']
    strings=[bpy.data.objects['Draw string'],bpy.data.objects['Draw string.001']]
    if unit=='archer':
        for obj in strings:obj.parent=bow
    samples=[]
    for i in range((scene.frame_end-1)*4+1):
        t=1+i/4;scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
        values=[];arrow_loc=arrow.location.copy();draw=arrow_loc.y+.16
        delta=max(.18-draw,0) if unit=='archer' else 0
        if unit=='archer':
            arrow_loc.y+=delta;values.append((arrow,'location',arrow_loc))
            nock=Vector((0,draw+delta,.03))
            for obj,name in zip(strings,['Curved wooden bow.002','Curved wooden bow.005']):
                end=bow.matrix_world.inverted()@(bpy.data.objects[name].matrix_world@Vector((0,0,.5)))
                values.extend([(obj,'location',(end+nock)/2),(obj,'rotation_euler',(nock-end).to_track_quat('Z','Y').to_euler()),(obj,'scale',Vector((1,1,(nock-end).length)))])
        for suffix in ['', '.001']:
            hand=bpy.data.objects['Weapon grip hand'+suffix];fore=bpy.data.objects['Articulated forearm'+suffix]
            upper=bpy.data.objects['Articulated upper arm'+suffix];wrap=bpy.data.objects['Wrist wrap'+suffix]
            shoulder=bpy.data.objects['Shoulder'+suffix].location
            old_hand=hand.location.copy();new_hand=old_hand.copy()
            if suffix:
                if unit=='archer':
                    expected=bow.location+Vector((.035,draw+.01,.03))
                    if (old_hand-expected).length<.12:new_hand.y+=delta
                else:new_hand+=bow.rotation_euler.to_matrix()@Vector((.055,.065,.085))
                retrieval=max(0,1-abs(t-47)/2) if 45<t<49 else 0
                new_hand+=Vector((0,.14,.10))*retrieval
            direction=fore.rotation_euler.to_matrix()@Vector((0,0,1));elbow=fore.location-direction*fore.scale.z/2+(new_hand-old_hand)*.5
            wrist=new_hand+(elbow-new_hand).normalized()*.16
            values.append((hand,'location',new_hand))
            for obj,a,b in [(upper,shoulder,elbow),(fore,elbow,wrist),(wrap,wrist,new_hand+(elbow-new_hand).normalized()*.075)]:
                values.extend([(obj,'location',(a+b)/2),(obj,'rotation_euler',(b-a).to_track_quat('Z','Y').to_euler()),(obj,'scale',Vector((obj.scale.x,obj.scale.y,(b-a).length)))])
        samples.append((t,values))
    previous={};changed=set()
    for t,values in samples:
        for obj,prop,value in values:
            if prop=='rotation_euler':
                if obj in previous:value.make_compatible(previous[obj])
                previous[obj]=value.copy()
            setattr(obj,prop,value);obj.keyframe_insert(prop,frame=t);changed.add(obj)
    linear(changed)

def enlarge_ranged(unit):
    if unit=='slinger':enlarge_sling();return
    bow=bpy.data.objects['Bow' if unit=='archer' else 'Crossbow']
    pieces=[o for o in bow.children if o.name.startswith(('Curved wooden bow','Steel bow','Draw string'))]
    wrapper(bow,pieces,(1.10,1,1.28) if unit=='archer' else (1.35,1,1),'Larger bow silhouette')
    if unit=='crossbowman':
        strings=[bpy.data.objects['Draw string'],bpy.data.objects['Draw string.001']]
        for obj in strings:obj.parent=bow
        scene=bpy.context.scene;values=[]
        for i in range((scene.frame_end-1)*4+1):
            t=1+i/4;scene.frame_set(int(t),subframe=t%1)
            nock=Vector((0,bpy.data.objects['Loaded bolt'].location.y+.16,.065))
            for side,obj in zip([-1,1],strings):
                start=Vector((side*.48*1.35,-.26,0))
                values.append((t,obj,(start+nock)/2,(nock-start).to_track_quat('Z','Y').to_euler(),(nock-start).length))
        prev={}
        for t,obj,loc,rot,length in values:
            if obj in prev:rot.make_compatible(prev[obj])
            prev[obj]=rot.copy();obj.location=loc;obj.rotation_euler=rot;obj.scale.z=length
            for prop in ['location','rotation_euler','scale']:obj.keyframe_insert(prop,frame=t)
        linear(strings)
    for obj in bpy.context.scene.objects:
        if obj.name.startswith(('Back quiver','Quiver binding','Spare arrow','Quiver fletching')):
            reshape(obj,(.20,.24,.74),(1.12,1.12,1.18))
            obj.location.y+=.14

def enlarge_spear(unit):
    root=bpy.data.objects['Wooden spear' if unit=='spearman' else 'Pike' if unit=='pikeman' else 'Bronze spear']
    for obj in root.children:
        if obj.type!='MESH':continue
        reshape(obj,(0,0,0),(1.65,1.65,1) if obj.name.startswith(('Metal spearhead','Sharpened wooden tip')) else (1.30,1.30,1))
    shield=bpy.data.objects['Left-hand wooden buckler'];shield.scale.x*=.95;shield.scale.z*=1.45

def enlarge_healer(unit):
    robe=bpy.data.objects['Cream robe']
    reshape(robe,(0,0,1.16),(1,1,1))
    # Widen only the robe hem; the upper body and hood keep their design.
    matrix=Matrix.LocRotScale(robe.location,robe.rotation_euler.to_quaternion(),robe.scale);inverse=matrix.inverted()
    for v in robe.data.vertices:
        p=matrix@v.co;factor=1+.15*max(0,min(1,(1.05-p.z)/.8));p.x*=factor;p.y*=factor;v.co=inverse@p
    for obj in bpy.data.objects['Healing staff'].children:
        if obj.type!='MESH':continue
        if obj.name.startswith(('Staff finial','Finial prong','Ornate staff crown','Staff crown jewel')):reshape(obj,(0,0,1.20),(1.50,1.35,1.20))
        elif obj.name=='Staff shaft':reshape(obj,(0,0,0),(1.15,1.15,1))
    if unit=='priest':
        bpy.data.objects['Priest robe hem'].scale.x*=1.15;bpy.data.objects['Priest robe hem'].scale.y*=1.15

def pole_grips(unit):
    scene=bpy.context.scene;stone=unit=='spearman';healing=unit in ['healer','priest']
    root=bpy.data.objects['Healing staff' if healing else 'Wooden spear' if stone else 'Pike' if unit=='pikeman' else 'Bronze spear']
    if not healing:
        shoulder=bpy.data.objects['Shoulder'];helper=bpy.data.objects.new('Shield clearance',None);bpy.context.collection.objects.link(helper)
        helper.parent=shoulder.parent;helper.location=(-.055,-.28,0);shoulder.parent=helper
    if stone:
        shoulder=bpy.data.objects['Shoulder.001'];helper=bpy.data.objects.new('Spear clearance',None);bpy.context.collection.objects.link(helper)
        helper.parent=shoulder.parent;helper.location=(.18,-.06,0);shoulder.parent=helper
        hand=bpy.data.objects['Fist.001'];elbow=hand.location+Vector((-.26,.16,-.06));wrist=hand.location+(elbow-hand.location).normalized()*.16
        fore=bpy.data.objects['Forearm.001'];depth=max(v.co.z for v in fore.data.vertices)-min(v.co.z for v in fore.data.vertices)
        fore.location=(elbow+wrist)/2;fore.rotation_euler=(wrist-elbow).to_track_quat('Z','Y').to_euler();fore.scale.z=(wrist-elbow).length/depth
    samples=[]
    for i in range((scene.frame_end-1)*4+1):
        t=1+i/4;scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update();values=[]
        for suffix in (['','.001'] if stone else [''] if not healing else []):
            shoulder=bpy.data.objects['Shoulder'+suffix];upper=bpy.data.objects['Upper arm'+suffix]
            start=shoulder.matrix_world.inverted()@(shoulder.parent.parent.matrix_world@shoulder.location)
            end=elbow if suffix else Vector((-.055,-.025,-.20))
            depth=max(v.co.z for v in upper.data.vertices)-min(v.co.z for v in upper.data.vertices)
            values.extend([(upper,'location',(start+end)/2),(upper,'rotation_euler',(end-start).to_track_quat('Z','Y').to_euler()),(upper,'scale',Vector((upper.scale.x,upper.scale.y,(end-start).length/depth)))])
        if not stone:
            hand=bpy.data.objects['Weapon grip hand'];fore=bpy.data.objects['Articulated forearm'];upper=bpy.data.objects['Articulated upper arm'];wrap=bpy.data.objects['Wrist wrap']
            h=hand.location.copy();r=root.location.copy()
            if healing:h.x+=.12;r.x+=.12;values.extend([(hand,'location',h),(root,'location',r)])
            axis=root.rotation_euler.to_matrix()@Vector((0,0,1));old=fore.location-(fore.rotation_euler.to_matrix()@Vector((0,0,1)))*fore.scale.z/2
            bend=old-h;bend-=axis*bend.dot(axis);e=h+bend.normalized()*.30
            wrist=h+(e-h).normalized()*.16;shoulder=bpy.data.objects['Shoulder.001'].location
            for obj,a,b in [(upper,shoulder,e),(fore,e,wrist),(wrap,wrist,h+(e-h).normalized()*.075)]:
                values.extend([(obj,'location',(a+b)/2),(obj,'rotation_euler',(b-a).to_track_quat('Z','Y').to_euler()),(obj,'scale',Vector((obj.scale.x,obj.scale.y,(b-a).length)))])
        samples.append((t,values))
    prev={};changed=set()
    for t,values in samples:
        for obj,prop,value in values:
            if prop=='rotation_euler':
                if obj in prev:value.make_compatible(prev[obj])
                prev[obj]=value.copy()
            setattr(obj,prop,value);obj.keyframe_insert(prop,frame=t);changed.add(obj)
    linear(changed)

def fit_camera(actions,count,stride):
    scene=bpy.context.scene;facing=bpy.data.objects['Facing'];facing.rotation_euler.z=0
    bpy.context.view_layer.update()
    graph=bpy.context.evaluated_depsgraph_get()
    view=scene.camera.calc_matrix_camera(graph,x=192,y=192)@scene.camera.matrix_world.inverted()
    projections=[view@Matrix.Rotation(math.radians(a),4,'Z') for a in DIRECTIONS.values()]
    extent=0
    for a in range(len(actions)):
        for n in range(count):
            scene.frame_set(a*stride+n+1);graph=bpy.context.evaluated_depsgraph_get()
            for obj in scene.objects:
                if obj.type not in ['MESH','CURVE'] or obj.hide_render:continue
                evaluated=obj.evaluated_get(graph)
                for corner in evaluated.bound_box:
                    world=(evaluated.matrix_world@Vector(corner)).to_4d();world.w=1
                    for projection in projections:
                        p=projection@world;extent=max(extent,abs(p.x/p.w),abs(p.y/p.w))
    if extent>.92:scene.camera.data.ortho_scale*=extent/.92
    scene.frame_set(1);facing.rotation_euler.z=math.radians(45)

for group,units in GROUPS.items():
    if '--group' in sys.argv and group!=sys.argv[sys.argv.index('--group')+1]:continue
    for unit in units:
        if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]:continue
        stone=unit in ['slinger','spearman']
        source=f'art/outlined_units/{unit}.blend' if stone else f'art/ages/units/models/{unit}.blend'
        bpy.ops.wm.open_mainfile(filepath=str(ROOT/source));scene=bpy.context.scene;scene.frame_set(1)
        if group=='ranged':enlarge_ranged(unit);ranged_grips(unit)
        elif group=='spears':enlarge_spear(unit);pole_grips(unit)
        else:enlarge_healer(unit);pole_grips(unit)
        if unit=='archer':motion_corrections.archer()
        elif unit=='slinger':motion_corrections.slinger()
        elif unit in ['bronze_spearman','pikeman']:motion_corrections.spears(unit)
        actions=['idle','run','shoot' if group=='ranged' else 'attack'];count=8 if stone else 16;stride=8 if stone else 17
        fit_camera(actions,count,stride)
        scene.render.resolution_x=scene.render.resolution_y=192;scene.render.resolution_percentage=100
        bpy.context.preferences.filepaths.save_version=0
        folder=OUT/'models';folder.mkdir(exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(folder/f'{unit}_option_b.blend'))
        bpy.context.view_layer.update();ground=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
        (folder/f'{unit}.json').write_text(json.dumps(dict(source=source,group=group,actions=actions,count=count,stride=stride,ground_anchor=[ground.x,1-ground.y],render_scale=scene.camera.data.ortho_scale/4.1),indent=2))
        if '--models-only' in sys.argv:continue
        for a,action in enumerate(actions):
            for direction,angle in DIRECTIONS.items():
                bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
                for n in range(count):
                    scene.frame_set(a*stride+n+1)
                    folder=OUT/'frames'/unit/action/direction;folder.mkdir(parents=True,exist_ok=True)
                    scene.render.filepath=str(folder/f'{n:02}.png');bpy.ops.render.render(write_still=True)
            print('UNIT_RENDERED',unit,action,flush=True)
