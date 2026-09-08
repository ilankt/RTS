from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
GROUPS={'ranged':['slinger','archer','crossbowman'],'spears':['spearman','bronze_spearman','pikeman'],'healers':['healer','priest']}
DIRS=['E','SE','S','SW','W','NW','N','NE'];BG='#23312d';INK='#eee2c6'
META={p.stem:json.loads(p.read_text()) for p in (OUT/'models').glob('*.json')}
ORIGINAL={u:json.loads((ROOT/'art/ages/units/models'/f'{u}.json').read_text()) if u not in ['slinger','spearman'] else dict(ground_anchor=[.5,.730059],render_scale=1) for u in META}
def text(im,xy,value,size=20,bold=False):
    ImageDraw.Draw(im).text(xy,value,font=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size),fill=INK)
def frame(unit,variant,action='idle',direction='SE',index=0):
    root=OUT/'frames' if variant=='B' else ROOT/('art/outlined_units/frames' if unit in ['slinger','spearman'] else 'art/ages/units/frames')
    return Image.open(root/unit/action/direction/f'{index:02}.png').convert('RGBA')
def place(im,unit,variant,sprite,foot,zoom):
    meta=META[unit] if variant=='B' else ORIGINAL[unit];size=round(64*zoom*meta['render_scale']);anchor=meta['ground_anchor']
    sprite=sprite.resize((size,size),Image.Resampling.NEAREST)
    im.paste(sprite,(round(foot[0]-size*anchor[0]),round(foot[1]-size*anchor[1])),sprite)
def terrain(im,box):
    tile=Image.open(ROOT/'assets/tiles/source_textures/desert.png').convert('RGB').resize((256,256));patch=Image.new('RGB',(box[2]-box[0],box[3]-box[1]))
    for y in range(0,patch.height,256):
        for x in range(0,patch.width,256):patch.paste(tile,(x,y))
    im.paste(patch,box[:2])
checks=[]
for unit,meta in META.items():
    for action in meta['actions']:
        for d in DIRS:
            poses=[]
            for n in range(meta['count']):
                im=frame(unit,'B',action,d,n);bounds=im.getbbox()
                assert im.size==(192,192) and bounds
                assert min(bounds[0],bounds[1],192-bounds[2],192-bounds[3])>=2,(unit,action,d,n,bounds)
                poses.append(im.tobytes());checks.append(dict(unit=unit,action=action,direction=d,frame=n,bounds=bounds))
            if action!='idle':assert len(set(poses))>=4,(unit,action,d)
    assert len({frame(unit,'B',direction=d).tobytes() for d in DIRS})==8
clearance=json.loads((OUT/'clearance.json').read_text());assert len(clearance)==8 and not any(r['collisions'] or r['connection_errors'] for r in clearance)
(OUT/'verification.json').write_text(json.dumps(dict(frames=len(checks),mesh_pair_checks=sum(r['pair_checks'] for r in clearance),grip_checks=sum(r['grip_checks'] for r in clearance),connection_checks=sum(r['connection_checks'] for r in clearance),unintended_intersections=0,frame_checks=checks),indent=2))
for group,units in GROUPS.items():
    board=Image.new('RGB',(512*len(units),1000),BG);text(board,(24,18),group.upper()+' / BLENDER READABILITY REVIEW',29,True)
    text(board,(24,64),'Original left; revised right. Matching world scale.',20)
    for col,unit in enumerate(units):
        left=col*512;text(board,(left+24,108),unit.replace('_',' ').title(),26,True)
        for side,variant in enumerate(['original','B']):
            x=left+128+side*244;text(board,(x-80,150),'Original' if side==0 else 'Revised',20,True)
            for d,y,z in [('SE',422,5.2),('NW',635,4.0)]:place(board,unit,variant,Image.open(OUT/'details'/unit/variant/f'{d}.png').convert('RGBA'),(x,y),z)
        for row,(zoom,label) in enumerate([(1,'Actual size: zoom 1.0'),(.65,'Distant size: zoom 0.65')]):
            y=655+row*160;text(board,(left+24,y),label,20,True);terrain(board,(left+16,y+38,left+496,y+148))
            for side,variant in enumerate(['original','B']):
                for k,d in enumerate(['SE','NW']):place(board,unit,variant,frame(unit,variant,direction=d),(left+96+side*244+k*63,y+116),zoom)
    board.save(OUT/f'{group}-comparison.png')
    for action in ['run','shoot' if group=='ranged' else 'attack']:
        movie=[]
        for n in range(16):
            im=Image.new('RGB',(480*len(units),750),BG);text(im,(24,15),group.upper()+' / '+action.upper()+' / ORIGINAL LEFT, REVISED RIGHT',24,True)
            for col,unit in enumerate(units):
                text(im,(col*480+24,65),unit.replace('_',' ').title(),23,True);index=n//2 if META[unit]['count']==8 else n
                for row,d in enumerate(['SE','NW']):
                    for side,v in enumerate(['original','B']):place(im,unit,v,frame(unit,v,action,d,index),(col*480+120+side*235,355+row*300),4.8)
            movie.append(im)
        movie[0].save(OUT/f'{group}-{action}.gif',save_all=True,append_images=movie[1:],duration=50,loop=0)
        if action!='run':
            strip=Image.new('RGB',(1600,90+410*len(units)),BG);text(strip,(24,12),group.upper()+' / '+action.upper()+' / KEY POSES',28,True)
            for row,(unit,d) in enumerate((u,d) for u in units for d in ['SE','NW']):
                text(strip,(24,58+row*205),unit+' / '+d,19,True)
                for n in range(8):place(strip,unit,'B',frame(unit,'B',action,d,n if META[unit]['count']==8 else n*2),(n*200+100,245+row*205),3.5)
            strip.save(OUT/f'{group}-poses.png')
print('Validated',len(checks),'frames; built all group reviews.')
