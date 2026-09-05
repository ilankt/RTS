"""Pack all validated outlined-unit frames and update unit artwork metadata."""
from pathlib import Path
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
manifest=json.loads((OUT/'manifest.json').read_text())
size=manifest['size'];count=manifest['frames'];directions=manifest['directions']
paths={'clubman':ROOT/'assets/sprites/Units/Clubman','worker':ROOT/'assets/sprites/Units/WorkerOutlined','slinger':ROOT/'assets/sprites/Units/SlingerOutlined','spearman':ROOT/'assets/sprites/Units/SpearmanOutlined','healer':ROOT/'assets/sprites/Units/HealerOutlined'}
sheets={}
for unit,actions in manifest['units'].items():
    for action in actions:
        sheet=Image.new('RGBA',(size*count,size*8))
        for row,direction in enumerate(directions):
            for frame in range(count):
                image=Image.open(OUT/'frames'/unit/action/direction/f'{frame:02}.png').convert('RGBA')
                bounds=image.getbbox()
                assert bounds and bounds[0]>0 and bounds[1]>0 and bounds[2]<size and bounds[3]<size,(unit,action,direction,frame,bounds)
                sheet.paste(image,(frame*size,row*size))
        sheets[unit,action]=sheet
# Only export after every source frame passed the bounds check.
for (unit,action),sheet in sheets.items():
    paths[unit].mkdir(parents=True,exist_ok=True)
    sheet.save(paths[unit]/f'{action}.png')
shutil.copyfile(OUT/'clubman.blend',ROOT/'art/clubman/clubman.blend')
icons={'clubman':'clubman_icon.png','worker':'worker_outlined_icon.png','slinger':'slinger_outlined_icon.png','spearman':'spearman_outlined_icon.png','healer':'healer_outlined_icon.png'}
for unit,name in icons.items():
    image=Image.open(OUT/'frames'/unit/'idle'/'SE'/'00.png').convert('RGBA')
    image=image.crop(image.getbbox())
    image.thumbnail((108,112),Image.Resampling.NEAREST)
    portrait=Image.new('RGBA',(128,128))
    portrait.paste(image,((128-image.width)//2,8),image)
    portrait.save(ROOT/'assets/ui/Units'/name)
data_path=ROOT/'data/units.json'
data=json.loads(data_path.read_text())
for unit in data:
    art={'warrior':'clubman','worker':'worker','archer':'slinger','spearman':'spearman','healer':'healer'}.get(unit['name'])
    if art is None: continue
    unit['animation_directions']=8
    unit['ground_anchor']=manifest['ground_anchors'][art]
    unit['animations']={action:(paths[art]/f'{action}.png').relative_to(ROOT).as_posix() for action in manifest['units'][art]}
    if art=='slinger':
        unit['display_name']='Slingshot Man'
        unit['projectile_type']='stone'
    if art=='spearman': unit['render_scale']=1.0
    if art in ('clubman','spearman'): unit['animations']['guard']=unit['animations']['idle']
    unit['icon']='assets/ui/Units/'+icons[art]
data_path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')

font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',18)
frames=[]
cases=[('clubman','run','Clubman / walk'),('clubman','attack','Clubman / attack'),('worker','gather','Worker / gather'),('worker','build','Worker / build')]
for i in range(8):
    board=Image.new('RGB',(1040,310),'#23312d')
    draw=ImageDraw.Draw(board)
    for n,(unit,action,label) in enumerate(cases):
        image=Image.open(OUT/'frames'/unit/action/'SE'/f'{i:02}.png').convert('RGBA')
        image=image.resize((384,384),Image.Resampling.NEAREST)
        board.paste(image,(n*260-62,-34),image)
        draw.text((n*260+15,273),label,font=font,fill='#efdfbe')
    frames.append(board)
frames[0].save(OUT/'actions.gif',save_all=True,append_images=frames[1:],duration=100,loop=0)
print(f'Validated and packed {len(sheets)*count*8} Blender frames across {len(paths)} units.')
