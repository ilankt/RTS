"""Assemble actual Blender results at consistent world sizes, including a crowd."""
from pathlib import Path
import json,random
from PIL import Image,ImageDraw,ImageFont
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
ROWS=[['worker','bronze_worker','iron_worker'],['slinger','archer','crossbowman'],['spearman','bronze_spearman','pikeman'],[None,'healer','priest']]
LABELS=['Workers: larger working tools, apron and pouch','Ranged: fork, tall bow and wide crossbow','Spears: stronger spearheads and tall oval shields','Healers: wider robe hems and larger staff finials']
BG='#23312d';INK='#eee2c6'
def text(im,xy,value,size=20,bold=False):
    ImageDraw.Draw(im).text(xy,value,font=ImageFont.truetype('C:/Windows/Fonts/'+('segoeuib.ttf' if bold else 'segoeui.ttf'),size),fill=INK)
def folder(u):return OUT/('workers' if 'worker' in u else 'remaining')
def sprite(u,v='B',d='SE',detail=False):
    if detail:return Image.open(folder(u)/'details'/u/v/f'{d}.png').convert('RGBA')
    root=folder(u)/'frames' if v=='B' else ROOT/('art/outlined_units/frames' if u in ['worker','slinger','spearman'] else 'art/ages/units/frames')
    return Image.open(root/u/'idle'/d/'00.png').convert('RGBA')
def place(im,u,foot,zoom=1,v='B',d='SE',detail=False):
    if v=='B':meta=json.loads((folder(u)/'models'/f'{u}.json').read_text())
    elif u in ['worker','slinger','spearman']:meta=dict(ground_anchor=[.5,.730059],render_scale=1)
    else:meta=json.loads((ROOT/'art/ages/units/models'/f'{u}.json').read_text())
    size=round(64*zoom*meta['render_scale']);anchor=meta['ground_anchor'];im2=sprite(u,v,d,detail).resize((size,size),Image.Resampling.LANCZOS if detail else Image.Resampling.NEAREST)
    im.paste(im2,(round(foot[0]-size*anchor[0]),round(foot[1]-size*anchor[1])),im2)
board=Image.new('RGB',(1440,1480),BG)
text(board,(30,20),'OPTION B / REMAINING FOOT UNITS',36,True)
text(board,(30,73),'Actual Blender models and renders. No emblems. Horses and ballistas unchanged.',21)
for col,age in enumerate(['STONE','BRONZE','IRON']):text(board,(col*480+30,120),age,24,True)
for row,units in enumerate(ROWS):
    y=165+row*310;text(board,(30,y),LABELS[row],21,True)
    for col,u in enumerate(units):
        if not u:continue
        text(board,(col*480+30,y+37),u.replace('_',' ').title(),22)
        place(board,u,(col*480+180,y+280),4.2,detail=True)
        place(board,u,(col*480+370,y+275),3.5,d='NW',detail=True)
text(board,(30,1430),'Review variants. Approved Clubman and Swordsmen preserved. Gameplay integration awaits review.',19)
board.save(OUT/'remaining-roster.png')
crowd=Image.new('RGB',(1440,1050),BG)
text(crowd,(25,18),'44 UNITS / ORIGINAL LEFT, OPTION B RIGHT',31,True)
text(crowd,(25,65),'Matching positions and world scale. Open at 100% to judge distant readability.',21)
tile=Image.open(ROOT/'assets/tiles/source_textures/desert.png').convert('RGB').resize((256,256))
units=[u for row in ROWS for u in row if u]*4;random.Random(31).shuffle(units)
for row,zoom in enumerate([1,.65]):
    y=115+row*455;text(crowd,(25,y),f'Zoom {zoom:.2f}',22,True)
    for side,v in enumerate(['original','B']):
        left=side*720+15;patch=Image.new('RGB',(690,380))
        for ty in range(0,380,256):
            for tx in range(0,690,256):patch.paste(tile,(tx,ty))
        crowd.paste(patch,(left,y+40))
        for i,u in enumerate(units):place(crowd,u,(left+55+(i%8)*82,y+104+(i//8)*54),zoom,v,['SE','S','SW','NW'][i%4])
crowd.save(OUT/'remaining-crowd.png')
print('Built 11-unit roster and matched 44-unit crowds.')
