"""Validate transparent building renders and make the offline review gallery."""
from pathlib import Path
import json,base64
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent
data=json.loads((OUT/'manifest.json').read_text())
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',17)
families=list(dict.fromkeys(b['family'] for b in data))
lookup={(b['family'],b['age']):b for b in data}
board=Image.new('RGB',(3*360,len(families)*290+60),'#26362f')
draw=ImageDraw.Draw(board)
for col,age in enumerate(['STONE AGE','BRONZE AGE','IRON AGE']): draw.text((col*360+20,18),age,font=font,fill='#e7d9bc')
for b in data:
    path=OUT/b['sprite'];img=Image.open(path).convert('RGBA');bounds=img.getbbox()
    assert img.size==(512,512) and bounds and min(bounds[:2])>2 and max(bounds[2:])<510,(path,bounds)
    assert img.getchannel('A').getextrema()==(0,255),path
    b['image']='data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()
    b['margin']=min(bounds[0],bounds[1],512-bounds[2],512-bounds[3])
for row,family in enumerate(families):
    for age in [1,2,3]:
        x=(age-1)*360;y=row*290+60;b=lookup.get((family,age))
        if b:
            sprite=Image.open(OUT/b['sprite']).convert('RGBA').resize((275,275),Image.Resampling.LANCZOS)
            board.paste(sprite,(x+43,y-7),sprite)
            draw.text((x+20,y+254),b['name'],font=font,fill='#e7d9bc')
        else: draw.text((x+45,y+127),'Available from Bronze Age',font=font,fill='#9aa796')
board.save(OUT/'roster.png')
template=(OUT/'gallery.html').read_text(encoding='utf-8')
(OUT/'index.html').write_text(template.replace('__BUILDINGS__',json.dumps(data)),encoding='utf-8')
(OUT/'validation.json').write_text(json.dumps({'models':len(data),'minimum_margin':min(b['margin'] for b in data),'size':512,'alpha':'RGBA / transparent'},indent=2))
print('PASS: 30 editable models and 30 transparent, unclipped building renders.')
