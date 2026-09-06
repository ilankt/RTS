"""Check actual grip/contact trajectories and distinct ranged action phases."""
import bpy
from pathlib import Path
from mathutils import Vector

OUT=Path(__file__).resolve().parent
checks=0

def at(frame):
    """Map original pose numbers to the 16-frame action timeline."""
    index=frame-1
    bpy.context.scene.frame_set((index//8)*17+(index%8)*2+1)

def local_point(obj, point=(0,0,0)):
    return bpy.data.objects['Facing'].matrix_world.inverted() @ (obj.matrix_world @ Vector(point))

for unit in ['bronze_worker','iron_worker','bronze_swordsman','iron_swordsman',
             'bronze_spearman','pikeman','archer','crossbowman','ballista','heavy_ballista']:
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'models'/f'{unit}.blend'))
    scene=bpy.context.scene
    if unit.endswith('worker'):
        pick=bpy.data.objects['Pickaxe']; tip=bpy.data.objects['Pick cutting edge']
        hand=bpy.data.objects['Weapon grip hand.001']
        for frame in range(17,25):
            at(frame)
            assert (pick.matrix_world.translation-hand.matrix_world.translation).length<.001
            assert not tip.hide_render
            checks+=2
        at(19); raised=local_point(tip)
        at(21); contact=local_point(tip)
        assert raised.z>1.65 and contact.z<.65 and contact.y<raised.y-.7,(raised,contact)
        assert (contact.x/.35)**2+((contact.y+1.32)/.4)**2+((contact.z-.30)/.33)**2<1.05,contact
        assert contact.z<local_point(pick,(0,0,.65)).z-.30
        checks+=3
    elif unit.endswith('swordsman'):
        sword=bpy.data.objects['Sword grip']; tip=bpy.data.objects['Sword cutting tip']
        hand=bpy.data.objects['Weapon grip hand']
        assert sword.parent.name=='Sword torso'
        for frame in range(17,25):
            at(frame)
            assert (sword.matrix_world.translation-hand.matrix_world.translation).length<.001
            checks+=1
        at(19); windup=local_point(tip)
        at(21); contact=local_point(tip); pommel=local_point(sword,(0,0,-.12))
        assert windup.y-contact.y>.8,(windup,contact)
        assert contact.y<-1.5 and .6<contact.z<1.4
        assert contact.y<pommel.y-1.0
        checks+=4
        at(20); before=local_point(tip)
        at(22); after=local_point(tip)
        assert windup.x>.8 and after.x<-.6,(windup,after)
        assert abs(after.x-before.x)>2*abs(after.z-before.z),(before,after)
        at(19); coil=bpy.data.objects['Sword torso'].rotation_euler.z
        at(22); assert bpy.data.objects['Sword torso'].rotation_euler.z-coil>.65
        at(21)
        facing_inverse=bpy.data.objects['Facing'].matrix_world.inverted().to_3x3()
        axis=(facing_inverse@sword.matrix_world.to_3x3()@Vector((0,0,1))).normalized()
        edge=(facing_inverse@sword.matrix_world.to_3x3()@Vector((1,0,0))).normalized()
        travel=after-before; tangent=(travel-axis*travel.dot(axis)).normalized()
        assert abs(edge.dot(tangent))>.85,edge.dot(tangent)
        checks+=4
    elif unit in ['bronze_spearman','pikeman']:
        spear=bpy.data.objects['Pike' if unit=='pikeman' else 'Bronze spear']
        tip=bpy.data.objects['Spear cutting tip']; hand=bpy.data.objects['Weapon grip hand']
        for frame in range(17,25):
            at(frame)
            assert (spear.matrix_world.translation-hand.matrix_world.translation).length<.001
            assert abs(local_point(tip).x)<.002
            checks+=2
        at(19); cocked=local_point(tip)
        at(21); contact=local_point(tip); grip=local_point(spear)
        assert contact.y<cocked.y-.45
        assert grip.x-contact.x>.25 and contact.z-grip.z>.10
        checks+=2
    elif unit in ['archer','crossbowman']:
        weapon=bpy.data.objects['Crossbow' if unit=='crossbowman' else 'Bow']
        arrow=bpy.data.objects['Loaded bolt' if unit=='crossbowman' else 'Nocked arrow']
        hand=bpy.data.objects['Weapon grip hand.001']; string=bpy.data.objects['Draw string']
        hide_frames=[19,20,21,22,23] if unit=='crossbowman' else [22,23]
        for frame in range(17,25):
            at(frame); assert arrow.hide_render==(frame in hide_frames); checks+=1
        for frame in ([20,21,22] if unit=='crossbowman' else [18,19,20,21]):
            at(frame); nock=string.matrix_world@Vector((0,0,.5))
            assert (hand.matrix_world.translation-nock).length<.055
            checks+=1
        if unit=='crossbowman':
            at(20); loose=weapon.matrix_world.inverted()@hand.matrix_world.translation
            assert weapon.rotation_euler.x>.4
            at(22); cocked=weapon.matrix_world.inverted()@hand.matrix_world.translation
            assert cocked.y-loose.y>.45
            at(23); assert local_point(hand).y>.1
            checks+=3
        else:
            at(17); ready=weapon.matrix_world.inverted()@hand.matrix_world.translation
            at(21); drawn=weapon.matrix_world.inverted()@hand.matrix_world.translation
            assert drawn.y-ready.y>.3
            at(22)
            assert (hand.matrix_world.translation-(string.matrix_world@Vector((0,0,.5)))).length>.25
            checks+=2
    else:
        projectile=bpy.data.objects['Siege bolt']
        for frame in range(17,25):
            at(frame); assert projectile.hide_render==(frame in [22,23]); checks+=1
            if not projectile.hide_render:
                rear=projectile.matrix_world@Vector((0,.56,0))
                nock=bpy.data.objects['Siege bowstring'].matrix_world@Vector((0,0,.5))
                assert (rear-nock).length<.001,(unit,frame,rear,nock)
                checks+=1
        angles=[]
        for frame in range(17,22):
            at(frame); angles.append(bpy.data.objects['Winch crank'].rotation_euler.x)
        assert all(b>a for a,b in zip(angles,angles[1:])),angles
        checks+=1
print(f'PASS: {checks} grip, forward cutting-edge contact, angled thrust and reload phase checks.')
