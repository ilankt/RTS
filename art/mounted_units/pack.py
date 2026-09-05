"""Validate and install the approved mounted sprites into the cavalry slot."""
from pathlib import Path
import json
from PIL import Image
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
meta=json.loads((OUT/'manifest.json').read_text())
size=meta['size'];count=meta['frames'];sheets={}
for action in meta['actions']:
    sheet=Image.new('RGBA',(size*count,size*8))
    for row,direction in enumerate(meta['directions']):
        for i in range(count):
            im=Image.open(OUT/'frames'/action/direction/f'{i:02}.png').convert('RGBA')
            bounds=im.getbbox()
            assert bounds and min(bounds[:2])>0 and max(bounds[2:])<size,(action,direction,i,bounds)
            sheet.paste(im,(i*size,row*size))
    sheets[action]=sheet
asset=ROOT/'assets/sprites/Units/MountedSpearmanOutlined';asset.mkdir(parents=True,exist_ok=True)
for action,sheet in sheets.items():sheet.save(asset/f'{action}.png')
im=Image.open(OUT/'frames/idle/SE/00.png').convert('RGBA');im=im.crop(im.getbbox());im.thumbnail((112,112),Image.Resampling.LANCZOS)
icon=Image.new('RGBA',(128,128));icon.paste(im,((128-im.width)//2,(128-im.height)//2),im)
icon.save(ROOT/'assets/ui/Units/mounted_spearman_icon.png')
p=ROOT/'data/units.json';data=json.loads(p.read_text(encoding='utf-8'));unit=next(u for u in data if u['name']=='cavalry')
unit.update(display_name='Mounted Spearman',collision_radius=14,animation_directions=8,ground_anchor=meta['ground_anchor'],render_scale=meta['render_scale'],icon='assets/ui/Units/mounted_spearman_icon.png')
unit['animations']={action:(asset/f'{action}.png').relative_to(ROOT).as_posix() for action in meta['actions']}
unit['animations']['guard']=unit['animations']['idle']
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print('PASS: installed 192 validated mounted frames, portrait and camera-derived foot anchor.')
