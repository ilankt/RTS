"""Validate renders and package age art; never edit gameplay data.

python art/ages/units/pack.py --preview : contact sheet only
python art/ages/units/pack.py : sprite sheets, portraits, metadata and gallery
"""
import base64
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
ORDER=['bronze_worker','iron_worker','bronze_swordsman','iron_swordsman','archer','crossbowman',
       'bronze_spearman','pikeman','mounted_spearman','heavy_cavalry','healer','priest','ballista','heavy_ballista']
DIRECTIONS=['E','SE','S','SW','W','NW','N','NE']
SIZE=192
FRAMES=16
FONT=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',18)
SMALL=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',14)
preview='--preview' in sys.argv
metadata={unit:json.loads((OUT/'models'/f'{unit}.json').read_text()) for unit in ORDER}
source=OUT/('previews' if preview else 'frames')

def board(action='idle',frame=0):
    image=Image.new('RGB',(7*250,2*320+62),'#26362f')
    draw=ImageDraw.Draw(image)
    draw.text((20,15),'THE THREE AGES / '+('MODEL REVIEW' if preview else action.upper()+' / EIGHT-DIRECTION SPRITES'),font=FONT,fill='#eaddbf')
    for index,unit in enumerate(ORDER):
        col=index//2; row=index%2; x=col*250; y=row*320+55
        meta=metadata[unit]; chosen=action if action in meta['actions'] else meta['actions'][-1]
        sprite=Image.open(source/unit/chosen/'SE'/f'{frame:02}.png').convert('RGBA')
        display_size=round(250*meta['render_scale'])
        sprite=sprite.resize((display_size,display_size),Image.Resampling.NEAREST)
        image.paste(sprite,(round(x+125-display_size*meta['ground_anchor'][0]),
                            round(y+195-display_size*meta['ground_anchor'][1])),sprite)
        draw.text((x+12,y+242),meta['name'],font=FONT,fill='#eee1c7')
        draw.text((x+12,y+267),meta['age']+' / '+chosen,font=SMALL,fill='#acb9ac')
    return image

board().save(OUT/('model-review.png' if preview else 'roster.png'))
board('attack',8).save(OUT/('action-review.png' if preview else 'action-roster.png'))
if preview:
    print('Preview boards saved.'); sys.exit()

# Validate every source image before exporting any sheet.
stats={}; prepared={}
for unit,meta in metadata.items():
    prepared[unit]={}; bounds_all=[]; motion={}
    for action in meta['actions']:
        sheet=Image.new('RGBA',(SIZE*FRAMES,SIZE*8)); direction_hashes=[]; counts=[]
        for row,direction in enumerate(DIRECTIONS):
            hashes=[]
            for frame in range(FRAMES):
                path=source/unit/action/direction/f'{frame:02}.png'
                with Image.open(path) as original:
                    assert original.mode=='RGBA' and original.size==(SIZE,SIZE),path
                    sprite=original.copy()
                bounds=sprite.getbbox()
                assert bounds and min(bounds[:2])>1 and max(bounds[2:])<SIZE-1,(path,bounds)
                assert sprite.getchannel('A').getextrema()==(0,255),path
                hashes.append(hashlib.sha256(sprite.tobytes()).hexdigest())
                bounds_all.append(bounds); sheet.paste(sprite,(frame*SIZE,row*SIZE))
            counts.append(len(set(hashes))); direction_hashes.append(hashes[0])
        # Siege idle is deliberately still; walking and firing must animate.
        if action!='idle': assert min(counts)>1,(unit,action,counts)
        assert len(set(direction_hashes))>=6,(unit,action,'Missing true facings')
        motion[action]=counts; prepared[unit][action]=sheet
    stats[unit]={'frame_count':len(meta['actions'])*FRAMES*8,'motion_unique_frames':motion,
                 'minimum_edge_margin':min(min(b[0],b[1],SIZE-b[2],SIZE-b[3]) for b in bounds_all)}

gallery=[]
for unit,meta in metadata.items():
    folder=ROOT/'assets/sprites/Units/Ages'/unit; folder.mkdir(parents=True,exist_ok=True)
    animations={}; embedded={}
    for action,sheet in prepared[unit].items():
        path=folder/f'{action}.png'; sheet.save(path)
        animations[action]=path.relative_to(ROOT).as_posix()
        embedded[action]='data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()
    portrait=Image.open(source/unit/'idle/SE/00.png').convert('RGBA')
    portrait=portrait.crop(portrait.getbbox()); portrait.thumbnail((112,112),Image.Resampling.LANCZOS)
    icon=Image.new('RGBA',(128,128)); icon.paste(portrait,((128-portrait.width)//2,(128-portrait.height)//2))
    icons=ROOT/'assets/ui/Units/Ages'; icons.mkdir(parents=True,exist_ok=True)
    icon.save(icons/f'{unit}.png')
    (OUT/'portraits').mkdir(exist_ok=True)
    icon.save(OUT/'portraits'/f'{unit}.png')
    meta.update(id=unit,animations=animations,icon=(icons/f'{unit}.png').relative_to(ROOT).as_posix(),
                animation_directions=8,frame_size=SIZE,frames_per_direction=FRAMES,fps=20,
                model=(OUT/'models'/f'{unit}.blend').relative_to(ROOT).as_posix())
    gallery.append({**meta,'sheets':embedded})

manifest={'style':'Approved outlined cartoon / option 1','directions':DIRECTIONS,
          'units':metadata,'validation':stats,'total_frames':sum(s['frame_count'] for s in stats.values())}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
template=(OUT/'gallery.html').read_text(encoding='utf-8')
(OUT/'index.html').write_text(template.replace('__ROSTER__',json.dumps(gallery).replace('</','<\\/')),encoding='utf-8')
frames=[board('attack',i) for i in range(FRAMES)]
frames[0].save(OUT/'actions.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
print(f'PASS: {len(metadata)} units, {sum(len(m["actions"]) for m in metadata.values())} sheets, {manifest["total_frames"]} transparent frames; bounds, directions and motion verified.')
