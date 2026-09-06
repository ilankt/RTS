"""Compare the transverse sword cut with the worker's downward strike."""
from pathlib import Path
import json
import sys
from PIL import Image,ImageDraw,ImageFont

OUT=Path(__file__).resolve().parent
source='motion-previews' if '--preview' in sys.argv else 'frames'
cases=[('bronze_worker','gather','SE','Worker / downward strike','frames'),
       ('bronze_swordsman','attack','SE','Sword / diagonal slash',source),
       ('bronze_swordsman','attack','S','Sword / front view',source)]
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',19)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',14)
def cell(case,i,size=320,show_label=True):
    unit,action,direction,label,folder=case
    meta=json.loads((OUT/'models'/f'{unit}.json').read_text())
    sprite=Image.open(OUT/folder/unit/action/direction/f'{i:02}.png').convert('RGBA')
    board=Image.new('RGB',(size,340),'#26362f')
    width=round(size*meta['render_scale'])
    sprite=sprite.resize((width,width),Image.Resampling.NEAREST)
    board.paste(sprite,(round(size/2-width*meta['ground_anchor'][0]),round(268-width*meta['ground_anchor'][1])),sprite)
    draw=ImageDraw.Draw(board)
    if show_label: draw.text((12,10),label,font=font,fill='#ecdfc4')
    draw.text((12,308),f'{direction} / frame {i+1:02} of 16',font=small,fill='#b5bdac')
    return board
frames=[]
for i in range(16):
    board=Image.new('RGB',(960,340),'#26362f')
    for col,case in enumerate(cases): board.paste(cell(case,i),(col*320,0))
    frames.append(board)
frames[0].save(OUT/'sword-slash-review.gif',save_all=True,append_images=frames[1:],duration=80,loop=0)
strip=Image.new('RGB',(8*240,3*340),'#26362f')
for row,case in enumerate(cases):
    for col in range(8): strip.paste(cell(case,col*2,240,False),(col*240,row*340))
    ImageDraw.Draw(strip).text((12,row*340+10),case[3],font=font,fill='#ecdfc4')
strip.save(OUT/'sword-slash-strip.png')
print('Sword/worker comparison saved.')
