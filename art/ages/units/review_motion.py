"""Build frame-by-frame action strips and a focused animation review."""
from pathlib import Path
import sys
from PIL import Image,ImageDraw,ImageFont

OUT=Path(__file__).resolve().parent
SOURCE=OUT/('motion-previews' if '--preview' in sys.argv else 'frames')
CASES=[('bronze_worker','gather','Worker / pickaxe'),('bronze_swordsman','attack','Swordsman / cut'),
       ('archer','shoot','Archer / draw and release'),('crossbowman','shoot','Crossbow / cock and load'),
       ('bronze_spearman','attack','Spearman / inward thrust')]
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',17)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',14)
for direction in ['SE','E']:
    sheet=Image.new('RGB',(1536,5*215),'#26362f');draw=ImageDraw.Draw(sheet)
    for row,(unit,action,label) in enumerate(CASES):
        draw.text((12,row*215+5),label+' / '+direction,font=font,fill='#eddfbe')
        for i in range(8):
            frame=Image.open(SOURCE/unit/action/direction/f'{i*2:02}.png').convert('RGBA')
            sheet.paste(frame,(i*192,row*215+22),frame)
            draw.text((i*192+12,row*215+188),str(i*2+1),font=small,fill='#bbc3af')
    sheet.save(OUT/f'motion-strip-{direction.lower()}.png')
frames=[]
for i in range(16):
    board=Image.new('RGB',(5*270,310),'#26362f');draw=ImageDraw.Draw(board)
    for col,(unit,action,label) in enumerate(CASES):
        frame=Image.open(SOURCE/unit/action/'SE'/f'{i:02}.png').convert('RGBA').resize((270,270),Image.Resampling.NEAREST)
        board.paste(frame,(col*270,0),frame)
        draw.text((col*270+10,268),label,font=font,fill='#eddfbe')
    frames.append(board)
frames[0].save(OUT/'revised-actions.gif',save_all=True,append_images=frames[1:],duration=70,loop=0)
print('Saved revised action strips and GIF.')
