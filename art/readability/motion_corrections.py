"""User-directed mechanical animation corrections; review scenes only."""
import bpy,math
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent

def linear(objects):
    for o in objects:
        if not o.animation_data or not o.animation_data.action:continue
        for layer in o.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for c in bag.fcurves:
                        for k in c.keyframe_points:k.interpolation='CONSTANT' if c.data_path.startswith('hide_') else 'LINEAR'

def key(o,t):
    for p in ['location','rotation_euler','scale']:o.keyframe_insert(p,frame=t)

def remove(objects):
    for o in set(objects):
        if o.name in bpy.data.objects:bpy.data.objects.remove(o,do_unlink=True)

def imported(path):
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):
        names=list(src.objects);dst.objects=names.copy()
    result=dict(zip(names,dst.objects))
    for o in result.values():bpy.context.collection.objects.link(o)
    return result

def retime(objects,actions,old_stride,new_stride,old_count,new_count):
    scene=bpy.context.scene;samples=[]
    for a in range(actions):
        for s in range(new_count*4+1):
            phase=s/4*old_count/new_count;f=a*old_stride+1+min(phase,old_count-1)
            scene.frame_set(int(f),subframe=f%1)
            vals={o:(o.location.copy(),o.rotation_euler.to_quaternion(),o.scale.copy(),o.hide_render) for o in objects}
            if phase>old_count-1:
                scene.frame_set(a*old_stride+1);factor=phase-(old_count-1)
                vals={o:(p.lerp(o.location,factor),q.slerp(o.rotation_euler.to_quaternion(),factor),sc.lerp(o.scale,factor),hidden) for o,(p,q,sc,hidden) in vals.items()}
            samples.append((a*new_stride+1+s/4,vals))
    for o in objects:o.animation_data_clear()
    prev={}
    for t,vals in samples:
        for o,(p,q,sc,hidden) in vals.items():
            r=q.to_euler('XYZ',prev[o]) if o in prev else q.to_euler();prev[o]=r.copy()
            o.location=p;o.rotation_euler=r;o.scale=sc;o.hide_render=hidden;o.hide_viewport=hidden;key(o,t)
            for prop in ['hide_render','hide_viewport']:o.keyframe_insert(prop,frame=t)
    linear(objects)

def worker():
    body=bpy.data.objects['Body'];metal=bpy.data.objects['Hammer head'].data.materials[0]
    old=set()
    for n in ['Shoulder','Shoulder.001','Pickaxe','Building hammer']:
        o=bpy.data.objects.get(n)
        if o:old.update([o,*o.children_recursive])
    src=imported(OUT/'workers/models/bronze_worker_option_b.blend')
    keep=set()
    for n in ['Pickaxe','Building hammer']:
        o=src[n];keep.update([o,*o.children_recursive])
    keep.update(o for n,o in src.items() if n.startswith(('Articulated upper arm','Articulated forearm','Wrist wrap','Weapon grip hand')))
    retime([*keep,src['Body']],4,17,8,16,8)
    body.animation_data_clear();body.animation_data_create();body.animation_data.action=src['Body'].animation_data.action.copy()
    body.animation_data.action_slot=body.animation_data.action.slots[0]
    for o in keep:
        if o.parent not in keep:o.parent=body;o.matrix_parent_inverse.identity()
    remove(old)
    for n,o in src.items():
        if o in keep:
            o.name=n
            if n.startswith(('Pick cutting horn','Pick rear horn','Pick head socket','Hammer head')):o.data.materials[0]=metal
    remove(set(src.values())-keep)
    rig=[bpy.data.objects[n] for n in ['Articulated upper arm','Articulated forearm','Wrist wrap','Weapon grip hand']]
    samples=[]
    for a,name in [(2,'Pickaxe'),(3,'Building hammer')]:
        tool=bpy.data.objects[name]
        for i in range(113):
            t=a*8+1+i/16;bpy.context.scene.frame_set(int(t),subframe=t%1)
            hand=tool.location+tool.rotation_euler.to_matrix()@Vector((0,0,-.19))
            fore=rig[1];elbow=fore.location-(fore.rotation_euler.to_matrix()@Vector((0,0,1)))*fore.scale.z/2
            samples.append((t,hand,elbow))
    for t,hand,elbow in samples:arm_pose(rig,-1,hand,elbow,t)
    # Retiming left old quarter-frame keys beyond the final exported pose.
    # The stroke already rests in its first pose there; replace every leftover
    # return key, including the closing pose, with the corrected arm solution.
    closures=[]
    for start in [17,25]:
        bpy.context.scene.frame_set(start)
        closures.append((start,{o:(o.location.copy(),o.rotation_euler.copy(),o.scale.copy()) for o in rig}))
    for start,poses in closures:
        for i in range(17):
            t=start+7+i/16
            for o,(p,r,s) in poses.items():o.location=p;o.rotation_euler=r;o.scale=s;key(o,t)
    linear(rig)
    bpy.context.scene.frame_set(1)

def spears(unit):
    body=bpy.data.objects['Body'];root=bpy.data.objects['Pike' if unit=='pikeman' else 'Bronze spear']
    armor_prefix=('Open-face helmet','Helmet','Back cuirass','Pauldron','Cuirass edging','Armor fastening','Mail collar','Lamellar skirt')
    armor=[o for o in body.children_recursive if o.name.startswith(armor_prefix)]
    weapon=list(root.children_recursive)
    old=set([body,*body.children_recursive]);old-=set(armor+weapon)
    for o in armor+weapon:o.parent=None
    src=imported(OUT/'remaining/models/spearman_option_b.blend')
    newbody=src['Body'];keep=set([newbody,*newbody.children_recursive])
    retime(list(keep),3,8,17,8,16)
    newbody.parent=bpy.data.objects['Facing'];newbody.matrix_parent_inverse.identity()
    spear=src['Wooden spear'];discard=set(spear.children_recursive);keep-=discard;remove(discard)
    for o in weapon:o.parent=spear;o.matrix_parent_inverse.identity()
    for o in armor:o.parent=newbody;o.matrix_parent_inverse.identity()
    discard={src['Hair cap'],src['Headband']};keep-=discard;remove(discard)
    remove(old)
    for n,o in src.items():
        try:
            if o in keep:o.name=n
        except ReferenceError:pass
    for o in list(src.values()):
        try:
            if o not in keep:bpy.data.objects.remove(o,do_unlink=True)
        except ReferenceError:pass
    spear.name='Pike' if unit=='pikeman' else 'Bronze spear'
    bpy.data.objects['Fist.001'].name='Weapon grip hand';bpy.data.objects['Wrist binding.001'].name='Wrist wrap'
    scene=bpy.context.scene;scene.timeline_markers.clear()
    for a,name in enumerate(['idle','run','attack']):scene.timeline_markers.new(name,frame=a*17+1)
    scene.frame_end=51;scene.frame_set(1)

def line(o,a,b):
    a,b=Vector(a),Vector(b);depth=max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices)
    o.location=(a+b)/2;o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();o.scale.z=(b-a).length/depth

def sample(values,p):
    p=max(0,min(p,len(values)-1));i=min(int(p),len(values)-2);f=p-i
    return values[i]*(1-f)+values[i+1]*f

def path(keys,t):
    for (a,p),(b,q) in zip(keys,keys[1:]):
        if t<=b:return Vector(p).lerp(Vector(q),max(0,min(1,(t-a)/(b-a))))
    return Vector(keys[-1][1])

def arms(stone=False):
    body=bpy.data.objects['Body'];result=[]
    for suffix in ['','.001']:
        names=['Upper arm','Forearm','Wrist binding','Fist'] if stone else ['Articulated upper arm','Articulated forearm','Wrist wrap','Weapon grip hand']
        objs=[bpy.data.objects[n+suffix] for n in names]
        for o in objs:o.parent=body;o.matrix_parent_inverse.identity();o.animation_data_clear()
        result.append(objs)
    return result

def arm_pose(rig,side,hand,elbow,t,rotation=None):
    upper,fore,wrap,palm=rig;hand=Vector(hand);elbow=Vector(elbow);shoulder=Vector((side*.34,0,1.38))
    direction=(hand-elbow).normalized();wrist=hand-direction*.16
    for o,a,b in [(upper,shoulder,elbow),(fore,elbow,wrist),(wrap,wrist,hand-direction*.075)]:line(o,a,b);key(o,t)
    palm.location=hand
    if rotation is not None:palm.rotation_euler=rotation
    key(palm,t)

def archer():
    scene=bpy.context.scene;bow=bpy.data.objects['Bow'];bow.animation_data_clear();bow.location=(.60,-.68,1.43);bow.rotation_euler=(0,0,0)
    limbs=[o for o in bow.children_recursive if o.name.startswith('Curved wooden bow')]
    wood=limbs[0].data.materials[0];template=limbs[0];new=[]
    for side in [-1,1]:
        for i in range(8):
            o=template.copy();o.data=template.data.copy();o.animation_data_clear();bpy.context.collection.objects.link(o);o.parent=bow;o.matrix_parent_inverse.identity();o.scale=(1,1,1);o.name=f'Bow limb {side:+d} {i}';new.append(o)
    remove(limbs)
    curve=bpy.data.curves.new('Continuous bow stave','CURVE');curve.dimensions='3D';curve.bevel_depth=.036;curve.bevel_resolution=2;curve.use_fill_caps=True
    spline=curve.splines.new('POLY');spline.points.add(16)
    stave=bpy.data.objects.new('Continuous wooden bow',curve);bpy.context.collection.objects.link(stave);stave.parent=bow;curve.materials.append(wood)
    for j,p in enumerate(spline.points):p.radius=1-.45*abs(j-8)/8
    for o in new:o.hide_render=True;o.hide_viewport=True
    strings=[bpy.data.objects[n] for n in ['Draw string','Draw string.001']]
    for o in strings:o.parent=bow;o.animation_data_clear()
    arrow=bpy.data.objects['Nocked arrow'];arrow.animation_data_clear()
    rig=arms();objects=[bow,arrow,*new,*strings,*rig[0],*rig[1]]
    def points(ty,h):return [Vector((0,ty*(j/8)**2,h*j/8)) for j in range(9)]
    def length(pts):return sum((b-a).length for a,b in zip(pts,pts[1:]))
    half_string=.80;brace=.22;limb_length=length(points(brace,half_string))
    for i in range(801):
        t=1+i/16;scene.frame_set(int(t),subframe=t%1);shoot=t>=35;p=(t-35)/2
        draw=sample([0,.22,.62,1,1,0,0,0,0],p) if shoot else 0
        if shoot and 43.25<=t<49:draw=0
        nock_y=brace+.48*draw;lo=brace;hi=nock_y+.001
        for _ in range(35):
            ty=(lo+hi)/2;h=math.sqrt(max(.001,half_string**2-(nock_y-ty)**2))
            if length(points(ty,h))>limb_length:hi=ty
            else:lo=ty
        ty=(lo+hi)/2;h=math.sqrt(half_string**2-(nock_y-ty)**2)
        poly=list(reversed(points(ty,-h)))+points(ty,h)[1:]
        for p,v in zip(spline.points,poly):p.co=(*v,1);p.keyframe_insert('co',frame=t)
        for s,side in enumerate([-1,1]):
            pts=points(ty,side*h)
            for j in range(8):line(new[s*8+j],pts[j],pts[j+1]);key(new[s*8+j],t)
            line(strings[s],pts[-1],(0,nock_y,0));key(strings[s],t)
        nock=bow.location+Vector((0,nock_y,0));right=nock+Vector((.035,.01,0))
        released=shoot and 43.25<=t<49
        if released:
            right=path([(43.25,(.635,.03,1.43)),(45,(.66,.16,1.43)),(47,(.46,.36,1.43)),(49,(.635,-.45,1.43))],t)
        arrow.location=(0,nock_y-.16,0);key(arrow,t)
        for o in [arrow,*arrow.children_recursive]:
            o.hide_render=released;o.hide_viewport=released;o.keyframe_insert('hide_render',frame=t);o.keyframe_insert('hide_viewport',frame=t)
        arm_pose(rig[0],-1,bow.location+Vector((-.03,-.02,0)),(-.27,-.38,1.30),t)
        arm_pose(rig[1],1,right,(.76,.18+.24*draw,1.28),t)
    linear([*[o for o in objects if o not in new],curve]);remove(new)

def slinger():
    scene=bpy.context.scene;body=bpy.data.objects['Body'];root=bpy.data.objects['Forked wooden slingshot']
    root.parent=body;root.matrix_parent_inverse.identity();root.animation_data_clear()
    rig=arms(True);bands=[bpy.data.objects[n] for n in ['Sling band','Sling band.001']]
    for o in bands:o.animation_data_clear()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=1)
    pouch=bpy.context.object;pouch.name='Elastic pouch';pouch.parent=root;pouch.scale=(.06,.035,.045);pouch.data.materials.append(bpy.data.objects['Stone pouch'].data.materials[0])
    for i in range(369):
        t=1+i/16;scene.frame_set(int(t),subframe=t%1);shoot=t>=17;p=t-17
        root.location=(.46,-.73,1.08) if shoot else (.05,-.49,.95);root.rotation_euler=(0,0,0);key(root,t)
        pull=sample([.16,.30,.50,.72,.72,.16,.16,.16],p) if shoot else .03
        if shoot and 21.25<=t<23:pull=.03
        nock=root.location+Vector((0,pull,.47));right=nock+Vector((.035,.015,0))
        if shoot and 21.25<=t<23:
            right=root.location+path([(21.25,(.035,.735,.47)),(22,(.07,.77,.47)),(23,(.035,.175,.47))],t)
        if not shoot:right=Vector((.43,-.10,.85))
        for side,o in zip([-1,1],bands):line(o,(side*.24,0,.47),(0,pull,.47));key(o,t)
        pouch.location=(0,pull,.47);key(pouch,t)
        arm_pose(rig[0],-1,root.location,(-.24,-.45,1.06),t)
        arm_pose(rig[1],1,right,(.82,.03,1.30) if shoot else (.49,.04,1.1),t)
    linear([root,pouch,*bands,*rig[0],*rig[1]])
