"""Validate review frames and create an offline gallery; never installs assets."""
from pathlib import Path
import base64,json,hashlib
from PIL import Image,ImageDraw,ImageFont
from pack_portraits import portrait
OUT=Path(__file__).resolve().parent
DIRS=['E','SE','S','SW','W','NW','N','NE']
UNITS=['horse_archer','axeman'];BG='#243630';INK='#F0E6CF'
def label(im,xy,s,size=22):
    ImageDraw.Draw(im).text(xy,s,fill=INK,font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size))
def cell(u,a,d,n):return Image.open(OUT/'frames'/u/a/d/f'{n:02}.png').convert('RGBA')
def paste(im,sprite,meta,foot,zoom):
    size=round(64*zoom*meta['render_scale']);sprite=sprite.resize((size,size),Image.Resampling.LANCZOS)
    im.paste(sprite,(round(foot[0]-size*meta['ground_anchor'][0]),round(foot[1]-size*meta['ground_anchor'][1])),sprite)
def data(path):return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()
meta={u:json.loads((OUT/'models'/f'{u}.json').read_text()) for u in UNITS}
payload={};checks=[]
for u in UNITS:
    payload[u]={**meta[u],'sheets':{},'detail':data(OUT/'details'/u/'idle/SE/00.png')}
    for a in meta[u]['actions']:
        sheet=Image.new('RGBA',(192*16,192*8));direction_hashes=[]
        for row,d in enumerate(DIRS):
            hashes=[]
            for n in range(16):
                im=cell(u,a,d,n);bounds=im.getbbox()
                assert im.size==(192,192) and bounds,(u,a,d,n)
                margin=min(bounds[0],bounds[1],192-bounds[2],192-bounds[3])
                assert margin>=3,(u,a,d,n,bounds)
                assert im.getextrema()[3][0]==0,(u,a,d,n,'no transparent pixels')
                hashes.append(hashlib.sha256(im.tobytes()).hexdigest())
                sheet.paste(im,(n*192,row*192));checks.append(dict(unit=u,action=a,direction=d,frame=n,margin=margin))
            if a!='idle':assert len(set(hashes))>=8,(u,a,d,'insufficient motion')
            direction_hashes.append(hashes[0])
        assert len(set(direction_hashes))==8,(u,a,'duplicate directions')
        folder=OUT/'sheets'/u;folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'{a}.png';sheet.save(path);payload[u]['sheets'][a]=data(path)
    (OUT/'portraits').mkdir(exist_ok=True)
    portrait(cell(u,'idle','SE',0)).save(OUT/'portraits'/f'{u}.png')
geometry=json.loads((OUT/'geometry-checks.json').read_text())
assert all(not r['collisions'] and r['max_grip_error']<.001 and max(r['loop_transform_errors'])<.001 for r in geometry)
(OUT/'verification.json').write_text(json.dumps(dict(frames=len(checks),min_margin=min(c['margin'] for c in checks),model_sha256={u:hashlib.sha256((OUT/'models'/f'{u}.blend').read_bytes()).hexdigest() for u in UNITS},geometry=geometry,frame_checks=checks),indent=2))
board=Image.new('RGB',(1200,680),BG)
label(board,(38,24),'FACTIONS / MODEL REVIEW 02',28)
label(board,(38,66),'Horse Archer approved. Axeman revised with a centered grip.',20)
for col,u in enumerate(UNITS):
    x=col*600;label(board,(x+40,121),u.replace('_',' ').title(),32)
    detail=Image.open(OUT/'details'/u/'idle/SE/00.png').convert('RGBA')
    paste(board,detail,meta[u],(x+300,570),6)
    label(board,(x+40,612),'Bow, quiver & seated rider' if col==0 else 'Two-handed axe & fur shoulders',20)
board.save(OUT/'roster.png')
grip=Image.new('RGB',(1440,620),BG)
label(grip,(30,20),'AXEMAN / CENTERED GRIP',28)
for col,(action,d,n,title) in enumerate([('idle','S',0,'Front / ready'),('idle','SE',0,'Three-quarter / ready'),('attack','SE',8,'Forward chop')]):
    label(grip,(col*480+30,75),title,22)
    detail=Image.open(OUT/'details/axeman'/action/d/f'{n:02}.png').convert('RGBA')
    paste(grip,detail,meta['axeman'],(col*480+230,540),8.5)
grip.save(OUT/'centered-grip.png')
for action in ['idle','run','attack']:
    movie=[]
    for n in range(16):
        im=Image.new('RGB',(1000,710),BG);label(im,(28,18),action.upper()+' / HALF SPEED / SE + NW',24)
        for col,u in enumerate(UNITS):
            a='shoot' if action=='attack' and u=='horse_archer' else action
            label(im,(col*500+28,58),u.replace('_',' ').title(),24)
            for row,d in enumerate(['SE','NW']):paste(im,cell(u,a,d,n),meta[u],(col*500+250,365+row*310),4.6)
        movie.append(im)
    movie[0].save(OUT/f'{action}.gif',save_all=True,append_images=movie[1:],duration=100,loop=0)
strip=Image.new('RGB',(1536,470),BG)
for row,u in enumerate(UNITS):
    label(strip,(18,row*235+5),u.replace('_',' ').upper(),18)
    for i,d in enumerate(DIRS):
        paste(strip,cell(u,'idle',d,0),meta[u],(i*192+96,row*235+199),2.7)
        label(strip,(i*192+80,row*235+207),d,17)
strip.save(OUT/'eight-directions.png')
template=(OUT/'gallery.html').read_text(encoding='utf-8')
(OUT/'index.html').write_text(template.replace('__PAYLOAD__',json.dumps(payload)),encoding='utf-8')
print('Validated',len(checks),'frames; generated gallery, 6 sheets, portraits and previews.')
