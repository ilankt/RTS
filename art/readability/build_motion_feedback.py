from pathlib import Path
import json,sys
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent;DEST=OUT/'motion-feedback'
BG='#23312d';INK='#eee2c6'
GROUPS={'worker':[('worker','gather'),('worker','build')],'ranged':[('archer','shoot'),('slinger','shoot')],'spears':[(u,'attack') for u in ['spearman','bronze_spearman','pikeman']]}
def text(im,xy,s,size=20):ImageDraw.Draw(im).text(xy,s,font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size),fill=INK)
def place(im,u,a,d,n,foot,zoom):
    folder=OUT/('workers' if u=='worker' else 'remaining');meta=json.loads((folder/'models'/f'{u}.json').read_text())
    src=Image.open(DEST/'frames'/u/a/d/f'{n:02}.png').convert('RGBA');size=round(64*zoom*meta['render_scale']);anchor=meta['ground_anchor'];src=src.resize((size,size),Image.Resampling.LANCZOS)
    im.paste(src,(round(foot[0]-size*anchor[0]),round(foot[1]-size*anchor[1])),src)
for group,items in GROUPS.items():
    if '--group' in sys.argv and group!=sys.argv[sys.argv.index('--group')+1]:continue
    movie=[];w=600*len(items)
    for n in range(16):
        im=Image.new('RGB',(w,950),BG);text(im,(25,15),f'{group.upper()} / CORRECTED BLENDER ANIMATION / HALF SPEED',27)
        for col,(u,a) in enumerate(items):
            text(im,(col*600+25,65),u.replace('_',' ').title()+' / '+a,25)
            for row,d in enumerate(['SE','E']):
                text(im,(col*600+25,120+row*400),'Isometric' if row==0 else 'Side view',19)
                place(im,u,a,d,n,(col*600+300,480+row*400),7.0)
        movie.append(im)
    movie[0].save(DEST/f'{group}.gif',save_all=True,append_images=movie[1:],duration=100,loop=0)
    if group=='worker':
        assert movie[0].tobytes()==movie[-1].tobytes(),'Worker preview still changes pose at the loop seam'
    strip=Image.new('RGB',(1600,len(items)*260+80),BG);text(strip,(24,12),group.upper()+' / SIDE-VIEW KEY POSES',27)
    for row,(u,a) in enumerate(items):
        text(strip,(24,60+row*260),u.replace('_',' ').title()+' / '+a,22)
        for col,n in enumerate([0,2,4,6,8,9,12,15]):
            place(strip,u,a,'E',n,(col*200+90,300+row*260),4.4)
            if group=='ranged':text(strip,(col*200+25,95+row*260),['Ready','Draw','Draw','Full draw','Hold','Release','Reload','Ready'][col],17)
    strip.save(DEST/f'{group}-poses.png')
print('Built corrected side-view strips and half-speed GIFs.')
