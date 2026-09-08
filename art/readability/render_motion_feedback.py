import bpy,math,json,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
UNITS={'worker':('workers',['gather','build'],8,8),'slinger':('remaining',['shoot'],8,8),'archer':('remaining',['shoot'],16,17),'spearman':('remaining',['attack'],8,8),'bronze_spearman':('remaining',['attack'],16,17),'pikeman':('remaining',['attack'],16,17)}
SETS={'worker':['worker'],'ranged':['archer','slinger'],'spears':['bronze_spearman','pikeman']}
full='--full' in sys.argv
for unit,(folder,actions,count,stride) in UNITS.items():
    if '--set' in sys.argv and unit not in SETS[sys.argv[sys.argv.index('--set')+1]]:continue
    if '--unit' in sys.argv and unit!=sys.argv[sys.argv.index('--unit')+1]:continue
    bpy.ops.wm.open_mainfile(filepath=str(OUT/folder/'models'/f'{unit}_option_b.blend'))
    scene=bpy.context.scene;scene.render.resolution_x=scene.render.resolution_y=192 if full else 384
    all_actions=['idle','run','gather','build'] if unit=='worker' else ['idle','run','shoot' if unit in ['archer','slinger'] else 'attack']
    for action in all_actions if full else actions:
        a=all_actions.index(action)
        for d,angle in (dict(E=90,SE=45,S=0,SW=315,W=270,NW=225,N=180,NE=135) if full else dict(E=90,SE=45)).items():
            bpy.data.objects['Facing'].rotation_euler.z=math.radians(angle)
            for n in range(count if full else 16):
                f=a*stride+1+(n if full else n*count/16);scene.frame_set(int(f),subframe=f%1)
                target=OUT/folder/'frames'/unit/action/d if full else OUT/'motion-feedback/frames'/unit/action/d
                target.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(target/f'{n:02}.png');bpy.ops.render.render(write_still=True)
        print('FEEDBACK_RENDERED',unit,action,flush=True)
