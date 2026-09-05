from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent
board=Image.new('RGB',(1100,410),'#29362f');d=ImageDraw.Draw(board)
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',22)
d.text((20,15),'Mounted spearman / first model / no armor',font=font,fill='#efdfbe')
for n,(direction,label) in enumerate([('E','Side'),('SE','Front three-quarter'),('S','Front'),('NW','Rear three-quarter')]):
    im=Image.open(OUT/'frames/idle'/direction/'00.png').convert('RGBA')
    im=im.resize((384,384),Image.Resampling.NEAREST)
    board.paste(im,(n*275-55,5),im)
    d.text((n*275+14,367),label,font=font,fill='#efdfbe')
board.save(OUT/'first-model.png')
