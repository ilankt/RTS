"""Build review-only faction units from approved Blender sources.

blender -b -t 4 --python art/factions/build_models.py
No game data or installed assets are written.
"""
import bpy, math, json, sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/'art/ages/units'))
import render as geo

def delete(obj):
    for child in list(obj.children): delete(child)
    bpy.data.objects.remove(obj,do_unlink=True)

def linear():
    for o in bpy.context.scene.objects:
        if not o.animation_data or not o.animation_data.action: continue
        for layer in o.animation_data.action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for k in curve.keyframe_points:
                            k.interpolation='CONSTANT' if curve.data_path.startswith('hide_') else 'LINEAR'

def key(o,t):
    for p in ['location','rotation_euler','scale']:o.keyframe_insert(p,frame=t)

def finish(unit,actions,ortho,notes):
    s=bpy.context.scene
    s.camera.data.ortho_scale=ortho
    s.render.resolution_x=s.render.resolution_y=192
    s.render.resolution_percentage=100
    s.render.film_transparent=True
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGBA'
    s.timeline_markers.clear()
    for i,a in enumerate(actions):s.timeline_markers.new(a,frame=1+i*17)
    s.frame_start=1;s.frame_end=51;s.render.fps=20
    linear();s.frame_set(1)
    bpy.data.objects['Facing'].rotation_euler.z=math.radians(45)
    bpy.context.view_layer.update()
    anchor=world_to_camera_view(s,s.camera,Vector((0,0,0)))
    meta=dict(unit=unit,actions=actions,frames_per_direction=16,timeline_stride=17,fps=20,
              ground_anchor=[anchor.x,1-anchor.y],render_scale=ortho/4.1,notes=notes,
              action_events={actions[-1]:{'release_frame':10} if unit=='horse_archer' else {'impact_frame':8}})
    (OUT/'models').mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'models'/f'{unit}.blend'))
    (OUT/'models'/f'{unit}.json').write_text(json.dumps(meta,indent=2))

def horse_archer():
    source=ROOT/'art/readability/remaining/models/archer_option_b.blend'
    bpy.ops.wm.open_mainfile(filepath=str(source))
    names=[o.name for o in bpy.data.objects['Body'].children_recursive if not o.name.startswith(('Hip','Trouser leg','Boot'))]
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'art/ages/units/models/mounted_spearman.blend'))
    rider=bpy.data.objects['Body']
    # Keep the seated legs and the approved rider suspension, replacing the upper body.
    for c in list(rider.children):
        if not c.name.startswith(('Rider thigh','Rider shin','Rider boot','Stirrup strap','Wood stirrup')):delete(c)
    with bpy.data.libraries.load(str(source),link=False) as (src,dst):dst.objects=names
    imported=[o for o in dst.objects if o]
    upper=geo.pivot('Seated upper body clearance',(0,0,.23),rider)
    for o in imported:
        bpy.context.collection.objects.link(o)
        if o.parent not in imported:o.parent=upper
        o.name='HA '+o.name
    # A soft cap and leather vest distinguish the rider from the shared foot archer.
    leather=geo.material('Faction warm leather','805633')
    gold=geo.material('Faction brass fittings','C19A52')
    geo.ball('Rider leather cap',(0,.025,1.98),(.33,.29,.17),leather,upper)
    for side in [-1,1]:
        geo.rod('Vest front edging',(side*.23,-.275,.85),(side*.23,-.26,1.18),.025,.025,leather,upper)
        for z in [.9,1.05,1.17]:geo.ball('Vest fastening',(side*.23,-.285,z),(.024,.015,.024),gold,upper)
    # All source upper-body animations and the horse already use 17-frame sections.
    finish('horse_archer',['idle','run','shoot'],6.4,
           'Approved bay horse and trot; seated archer with leather cap, team cloth and quiver. Shooting stops the horse.')

def arm(body,side,skin,linen):
    shoulder=geo.pivot('Axe shoulder '+str(side),(side*.42,0,1.22),body)
    parts=[geo.rod('Axe upper arm '+str(side),(0,0,0),(0,0,1),.12,.10,skin,body),
           geo.rod('Axe forearm '+str(side),(0,0,0),(0,0,1),.10,.08,skin,body),
           geo.rod('Axe wrist '+str(side),(0,0,0),(0,0,1),.09,.09,linen,body),
           geo.ball('Axe hand '+str(side),(0,0,0),(.095,.095,.105),skin,body)]
    return shoulder,parts,side

def resolve_arm(rig,hand):
    # Fixed-length two-bone arms, with elbows below/outside the shoulders.
    # The old solver stretched an arm across the chest to an off-center weapon.
    shoulder=Vector(rig[0].location);hand=Vector(hand)
    delta=hand-shoulder;distance=delta.length;axis=delta.normalized()
    length=.43
    assert distance<2*length,(rig[2],distance)
    bend=Vector((rig[2]*.7,.1,-1))
    bend=(bend-axis*bend.dot(axis)).normalized()
    elbow=(shoulder+hand)/2+bend*math.sqrt(length*length-(distance/2)**2)
    fore,wrap=rig[1][1:3]
    direction=(Vector(hand)-elbow).normalized()
    wrist=Vector(hand)-direction*.20
    for obj,a,b in [(rig[1][0],Vector(rig[0].location),elbow),(fore,elbow,wrist),(wrap,wrist,Vector(hand)-direction*.085)]:
        obj.location=(a+b)/2;obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();obj.scale.z=(b-a).length
    rig[1][3].location=hand

def axeman():
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'art/readability/models/clubman_option_b.blend'))
    s=bpy.context.scene;body=bpy.data.objects['Body']
    # Resample the approved walk and idle into separately closed 16-frame cycles.
    objects=[o for o in s.objects if o.animation_data]
    poses=[]
    for a in range(3):
        cycle=[]
        for i in range(8):
            s.frame_set(a*8+i+1)
            cycle.append({o.name:(o.location.copy(),o.rotation_euler.to_quaternion(),o.scale.copy()) for o in objects})
        poses.append(cycle)
    for o in objects:o.animation_data_clear()
    for name in ['Shoulder','Shoulder.001','Right-hand club','Left-hand wooden buckler']:
        if bpy.data.objects.get(name):delete(bpy.data.objects[name])
    for a in range(3):
        for i in range(17):
            j=(i//2)%8;f=(i%2)*.5
            for name,p in poses[a][j].items():
                o=bpy.data.objects.get(name)
                if not o:continue
                q=poses[a][(j+1)%8][name]
                o.location=p[0].lerp(q[0],f);o.rotation_euler=p[1].slerp(q[1],f).to_euler();o.scale=p[2].lerp(q[2],f)
                key(o,a*17+i+1)
    skin=bpy.data.materials['1_cartoon skin'];linen=bpy.data.materials['1_cartoon linen']
    wood=bpy.data.materials['1_cartoon wood'];leather=geo.material('Axeman dark leather','644638')
    steel=geo.material('Forged axe iron','83919C');edge=geo.material('Sharpened axe edge','C5CFD1')
    fur=geo.material('Axeman fur mantle','978470')
    # Broad single-bit axe: the -Y cutting edge leads the forward/downward swing.
    axe=geo.pivot('Two handed axe',(.55,-.42,1.12),body)
    geo.rod('Axe haft',(0,0,-.30),(0,0,.81),.044,.034,wood,axe)
    for z in [-.28,-.23,-.18,-.13,.01,.06,.11]:
        geo.rod('Axe leather binding',(0,0,z),(0,0,z+.033),.049,.049,leather,axe)
    outline=[(.035,.51),(.035,.87),(-.16,.94),(-.49,1.04),(-.58,.91),(-.58,.48),(-.42,.38),(-.18,.52)]
    verts=[(x,y,z) for x in [-.065,.065] for y,z in outline];n=len(outline)
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    geo.mesh('Broad forged axe head',verts,faces,steel,axe)
    geo.mesh('Bright axe cutting bevel',[(-.066,-.49,1.04),(.066,-.49,1.04),(-.066,-.58,.48),(.066,-.58,.48),(0,-.625,.48),(0,-.625,.94)],[(0,1,5),(0,5,4,2),(1,3,4,5),(2,4,3)],edge,axe)
    geo.rod('Axe head socket',(0,0,.52),(0,0,.88),.082,.075,steel,axe)
    # Small fur shoulder pieces and a beard preserve broad team-color visibility.
    for side in [-1,1]:
        for k in range(4):geo.ball('Fur shoulder tuft',(side*(.23+k*.047),.04,1.29-.025*k),(.085,.19,.07),fur,body)
    beard=bpy.data.objects.get('Short beard')
    if beard:beard.scale.z*=1.4
    for z in [.72,.91,1.1]:geo.ball('Tunic leather toggle',(0,-.335,z),(.075,.022,.019),leather,body)
    left=arm(body,-1,skin,linen);right=arm(body,1,skin,linen)
    # Key dense analytic poses so hand attachment remains exact between export frames.
    points=[(0,.23,(.07,-.49,1.12)),(.25,-.20,(.13,-.49,1.45)),(.375,-.15,(.13,-.50,1.46)),(.50,1.25,(.05,-.71,1.10)),(.625,1.43,(.02,-.71,1.01)),(.80,.65,(.06,-.60,1.08)),(1,.23,(.07,-.49,1.12))]
    for a in range(3):
        for k in range(65):
            u=k/64;t=a*17+1+u*16;s.frame_set(int(t),subframe=t%1)
            if a==2:
                idx=next((j for j in range(len(points)-1) if points[j][0]<=u<=points[j+1][0]),len(points)-2)
                p,q=points[idx:idx+2];v=(u-p[0])/(q[0]-p[0]);v=v*v*(3-2*v)
                angle=p[1]+(q[1]-p[1])*v;pos=Vector(p[2]).lerp(Vector(q[2]),v)
            else:
                angle=.23+.025*math.sin(math.tau*u);pos=Vector((.07,-.49,1.12+.012*math.sin(math.tau*u)))
            axe.location=pos;axe.rotation_euler=(angle,.28,0)
            resolve_arm(right,pos)
            resolve_arm(left,pos+axe.rotation_euler.to_matrix()@Vector((0,0,-.24)))
            for rig in [left,right]:rig[1][3].rotation_euler=axe.rotation_euler
            for o in [axe]+left[1]+right[1]:key(o,t)
    finish('axeman',['idle','run','attack'],4.8,
           'Two-handed single-bit axe, exposed arms, fur shoulders and team-color tunic. Forward chopping edge and attached grips.')

if __name__=='__main__':
    for name,fn in [('horse_archer',horse_archer),('axeman',axeman)]:
        if '--unit' not in sys.argv or sys.argv[sys.argv.index('--unit')+1]==name:fn()
