"""Mechanical assertions for the four user-reported animation defects."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
OUT=Path(__file__).resolve().parent
results={}
def scene(unit,folder='remaining'):
    bpy.ops.wm.open_mainfile(filepath=str(OUT/folder/'models'/f'{unit}_option_b.blend'))
def point(o,z):
    depth=max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices)
    return o.matrix_world@Vector((0,0,z*depth/2))
def frame(t):bpy.context.scene.frame_set(int(t),subframe=t%1);bpy.context.view_layer.update()
scene('worker','workers');grips=0;alignments=[]
for start,name,marker in [(17,'Pickaxe','Pick cutting edge'),(25,'Building hammer','Hammer striking face')]:
    tool=bpy.data.objects[name]
    for i in range(57):
        t=start+i/8;frame(t)
        for suffix,offset in [('.001',0),('',-.19)]:
            error=((tool.matrix_world@Vector((0,0,offset)))-bpy.data.objects['Weapon grip hand'+suffix].matrix_world.translation).length
            assert error<.002,(name,t,suffix,error)
            grips+=1
    for t in [start+3,start+3.25,start+3.5,start+3.75]:
        frame(t-.01);before=bpy.data.objects[marker].matrix_world.translation.copy()
        frame(t+.01);after=bpy.data.objects[marker].matrix_world.translation.copy()
        frame(t);axis=tool.matrix_world.to_3x3()@Vector((0,-1,0));v=(after-before).normalized();score=axis.normalized().dot(v)
        assert score>.65,(name,t,score);alignments.append(score)
results['worker']=dict(two_hand_grip_checks=grips,min_working_face_velocity_alignment=min(alignments))
scene('archer');lengths=[];limbs=[];draw=[]
for i in range(257):
    t=35+i/16;frame(t);bow=bpy.data.objects['Bow'];inv=bow.matrix_world.inverted();strings=[bpy.data.objects[n] for n in ['Draw string','Draw string.001']]
    ends=[point(s,-1) for s in strings];nocks=[point(s,1) for s in strings]
    assert (nocks[0]-nocks[1]).length<1e-4
    lengths.append(sum((point(s,1)-point(s,-1)).length for s in strings))
    nock=inv@nocks[0];draw.append(nock.y)
    stave=bpy.data.objects['Continuous wooden bow'];pts=[stave.matrix_world@p.co.to_3d() for p in stave.data.splines[0].points]
    for half in [pts[:9],pts[8:]]:limbs.append(sum((b-a).length for a,b in zip(half,half[1:])))
    if t==35:assert (nocks[0]-(ends[0]+ends[1])/2).length<1e-4
    if t<=43:
        expected=bow.matrix_world@Vector((.035,nock.y+.01,0));assert (expected-bpy.data.objects['Weapon grip hand.001'].matrix_world.translation).length<.001
    if t==43:full_hand=bpy.data.objects['Weapon grip hand.001'].matrix_world.translation.copy()
    if t==43.25:
        assert (bpy.data.objects['Weapon grip hand.001'].matrix_world.translation-full_hand).length<.06
        assert nock.y<.221
assert max(lengths)-min(lengths)<.001 and max(limbs)-min(limbs)<.001
assert max(draw)-min(draw)>.47
results['archer']=dict(string_length_range=[min(lengths),max(lengths)],limb_length_range=[min(limbs),max(limbs)],draw_distance=max(draw)-min(draw),straight_braced_string=True,release_independent_of_hand=True)
scene('slinger');pull=[];hand=[]
for t in [17,18,19,20,21,21.25,22,23,24]:
    frame(t);root=bpy.data.objects['Forked wooden slingshot'];inv=root.matrix_world.inverted();p=inv@bpy.data.objects['Elastic pouch'].matrix_world.translation
    pull.append((t,p.y));hand.append((t,(inv@bpy.data.objects['Fist.001'].matrix_world.translation).y))
    assert abs(p.z-.47)<.001
    if t<=21:assert abs(hand[-1][1]-p.y-.015)<.001
assert dict(pull)[21]-dict(pull)[17]>.55
assert dict(pull)[21.25]<.04 and dict(hand)[21.25]>.70
results['slinger']=dict(pouch_path=pull,draw_hand_path=hand,backward_draw_and_independent_release=True)
scene('spearman');reference={}
names=['Body','Shoulder','Shoulder.001','Hip','Hip.001']
for a in range(3):
    for i in range(8):
        frame(a*8+i+1);reference[a,i]={n:(bpy.data.objects[n].location.copy(),bpy.data.objects[n].rotation_euler.to_quaternion()) for n in names}
checks=0
for unit in ['bronze_spearman','pikeman']:
    scene(unit)
    for (a,i),values in reference.items():
        frame(a*17+i*2+1)
        for n,(p,q) in values.items():
            o=bpy.data.objects[n];assert (o.location-p).length<1e-4 and abs(o.rotation_euler.to_quaternion().dot(q))>.99999,(unit,n,a,i)
            checks+=1
results['spears']=dict(copied_stone_pose_checks=checks)
(OUT/'motion-feedback').mkdir(exist_ok=True)
(OUT/'motion-feedback/mechanics.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
