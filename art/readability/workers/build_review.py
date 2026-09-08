from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
UNITS=['worker','bronze_worker','iron_worker']
NAMES=['Stone Worker','Bronze Worker','Iron Worker']
DIRS=['E','SE','S','SW','W','NW','N','NE']
BG='#23312d';INK='#eee2c6'
META={u:json.loads((OUT/'models'/f'{u}.json').read_text()) for u in UNITS}
ORIGINAL={u:(json.loads((ROOT/'art/ages/units/models'/f'{u}.json').read_text()) if u!='worker' else dict(ground_anchor=[.5,.730059],render_scale=1)) for u in UNITS}

def text(im,xy,value,size=20,bold=False):
    ImageDraw.Draw(im).text(xy,value,font=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size),fill=INK)

def frame(unit,variant,action='idle',direction='SE',index=0):
    root=OUT/'frames' if variant=='B' else ROOT/('art/outlined_units/frames' if unit=='worker' else 'art/ages/units/frames')
    return Image.open(root/unit/action/direction/f'{index:02}.png').convert('RGBA')

def place(im,unit,variant,sprite,foot,zoom):
    meta=META[unit] if variant=='B' else ORIGINAL[unit]
    size=round(64*zoom*meta['render_scale']);anchor=meta['ground_anchor']
    sprite=sprite.resize((size,size),Image.Resampling.NEAREST)
    im.paste(sprite,(round(foot[0]-size*anchor[0]),round(foot[1]-size*anchor[1])),sprite)

def terrain(im,box):
    tile=Image.open(ROOT/'assets/tiles/source_textures/desert.png').convert('RGB').resize((256,256))
    patch=Image.new('RGB',(box[2]-box[0],box[3]-box[1]))
    for y in range(0,patch.height,256):
        for x in range(0,patch.width,256):patch.paste(tile,(x,y))
    im.paste(patch,box[:2])

checks=[]
for unit in UNITS:
    count=8 if unit=='worker' else 16
    for action in ['idle','run','gather','build']:
        for direction in DIRS:
            poses=[]
            for n in range(count):
                image=frame(unit,'B',action,direction,n);bounds=image.getbbox()
                assert image.size==(192,192) and bounds
                assert min(bounds[0],bounds[1],192-bounds[2],192-bounds[3])>=2,(unit,action,direction,n,bounds)
                poses.append(image.tobytes());checks.append(dict(unit=unit,action=action,direction=direction,frame=n,bounds=bounds))
            if action!='idle':assert len(set(poses))>=4,(unit,action,direction)
    assert len({frame(unit,'B',direction=d).tobytes() for d in DIRS})==8
clearance=json.loads((OUT/'clearance.json').read_text())
assert len(clearance)==3 and not any(r['collisions'] for r in clearance)
(OUT/'verification.json').write_text(json.dumps(dict(frames=len(checks),mesh_pair_checks=sum(r['pair_checks'] for r in clearance),grip_checks=sum(r['grip_checks'] for r in clearance),unintended_intersections=0,frame_checks=checks),indent=2))

board=Image.new('RGB',(1536,1050),BG)
text(board,(24,18),'WORKER / ACTUAL BLENDER READABILITY REVIEW',31,True)
text(board,(24,64),'Larger tool heads, pouch and apron. Original left; revised right. Same world scale and head size.',20)
for col,(unit,name) in enumerate(zip(UNITS,NAMES)):
    left=col*512;text(board,(left+24,110),name,27,True)
    for side,variant in enumerate(['original','B']):
        x=left+128+side*244;text(board,(x-84,155),'Original' if side==0 else 'Revised',22,True)
        for direction,y,zoom in [('SE',423,5.94),('NW',630,4.22)]:
            sprite=Image.open(OUT/'details'/unit/variant/f'{direction}.png').convert('RGBA')
            place(board,unit,variant,sprite,(x,y),zoom)
    for row,(zoom,label) in enumerate([(1,'Actual size: zoom 1.0'),(.65,'Distant size: zoom 0.65')]):
        y=660+row*175;text(board,(left+24,y),label,20,True)
        terrain(board,(left+16,y+38,left+496,y+153))
        for side,variant in enumerate(['original','B']):
            for k,direction in enumerate(['SE','NW']):place(board,unit,variant,frame(unit,variant,direction=direction),(left+96+side*244+k*63,y+119),zoom)
text(board,(24,1005),'Actual rendered sprites composited on terrain. Open at 100% to judge small rows. Review variants; no gameplay installation.',18)
board.save(OUT/'comparison.png')

for action in ['gather','build','run']:
    movie=[]
    for n in range(16):
        im=Image.new('RGB',(1440,750),BG)
        text(im,(24,15),f'WORKER / {action.upper()} / ORIGINAL LEFT, REVISED RIGHT',27,True)
        for col,(unit,name) in enumerate(zip(UNITS,NAMES)):
            text(im,(col*480+24,65),name,23,True)
            index=n//2 if unit=='worker' else n
            for row,direction in enumerate(['SE','NW']):
                for side,variant in enumerate(['original','B']):place(im,unit,variant,frame(unit,variant,action,direction,index),(col*480+120+side*235,355+row*300),5.47)
        movie.append(im)
    movie[0].save(OUT/f'{action}.gif',save_all=True,append_images=movie[1:],duration=50,loop=0)
    if action!='run':
        strip=Image.new('RGB',(1600,1320),BG);text(strip,(24,12),f'WORKER / {action.upper()} / KEY POSES',28,True)
        for row,(unit,direction) in enumerate((u,d) for u in UNITS for d in ['SE','NW']):
            text(strip,(24,58+row*205),f'{unit.replace("_"," ").title()} / {direction}',19,True)
            for n in range(8):place(strip,unit,'B',frame(unit,'B',action,direction,n if unit=='worker' else n*2),(n*200+100,245+row*205),3.90)
        strip.save(OUT/f'{action}-poses.png')
directions=Image.new('RGB',(1440,800),BG);text(directions,(24,15),'WORKER / EIGHT DIRECTIONS',29,True)
for col,d in enumerate(DIRS):text(directions,(col*180+65,62),d,21,True)
for row,(unit,name) in enumerate(zip(UNITS,NAMES)):
    text(directions,(24,105+row*226),name,21,True)
    for col,d in enumerate(DIRS):place(directions,unit,'B',frame(unit,'B',direction=d),(col*180+90,292+row*226),4.06)
directions.save(OUT/'eight-directions.png')
print(f'Validated {len(checks)} Worker frames and built review images.')
