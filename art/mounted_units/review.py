"""Pack and review mounted unit frames without installing them in gameplay."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent
meta=json.loads((OUT/'manifest.json').read_text())
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',20)
for action in meta['actions']:
    frames=[]
    for i in range(8):
        board=Image.new('RGB',(1100,410),'#29362f');d=ImageDraw.Draw(board)
        d.text((20,12),f'Mounted spearman / {action} / decorated horse',font=font,fill='#efdfbe')
        for n,direction in enumerate(['E','SE','S','NW']):
            im=Image.open(OUT/'frames'/action/direction/f'{i:02}.png').convert('RGBA')
            im=im.resize((384,384),Image.Resampling.NEAREST)
            board.paste(im,(n*275-55,5),im)
            d.text((n*275+100,374),direction,font=font,fill='#efdfbe')
        frames.append(board)
    frames[4].save(OUT/f'{action}-pose-check.png')
    frames[0].save(OUT/f'{action}-preview.gif',save_all=True,append_images=frames[1:],duration=110,loop=0)
for action in meta['actions']:
    for direction in meta['directions']:
        unique_frames=set()
        for i in range(8):
            im=Image.open(OUT/'frames'/action/direction/f'{i:02}.png')
            unique_frames.add(im.tobytes())
            bounds=im.getbbox()
            assert bounds and min(bounds[:2])>0 and max(bounds[2:])<192,(action,direction,i,bounds)
        assert len(unique_frames)>=4,(action,direction,'insufficient motion')
print('PASS: 192 mounted-unit frames, all directions/actions, no clipping.')
