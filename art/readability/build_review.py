"""Compose genuine Blender renders at unchanged camera/game scales."""
from pathlib import Path
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
UNITS = ['clubman', 'bronze_swordsman', 'iron_swordsman']
NAMES = ['Clubman', 'Bronze Swordsman', 'Iron Swordsman']
DIRECTIONS = ['E', 'SE', 'S', 'SW', 'W', 'NW', 'N', 'NE']
FONT = 'C:/Windows/Fonts/segoeui.ttf'
BOLD = 'C:/Windows/Fonts/segoeuib.ttf'
BG = '#23312d'
INK = '#eee2c6'
meta = {u: json.loads((OUT/'models'/f'{u}.json').read_text()) for u in UNITS}
original_meta={u:(json.loads((ROOT/'art/ages/units/models'/f'{u}.json').read_text()) if u!='clubman' else {'ground_anchor':[.5,.730059],'render_scale':1.0}) for u in UNITS}

def settings(unit,variant):
    return meta[unit] if variant=='B' else original_meta[unit]
if (OUT/'full-frames').exists():
    for unit in UNITS:
        count=8 if unit=='clubman' else 16
        for action in ['idle','run','attack']:
            for direction in DIRECTIONS:
                for n in range(count):
                    assert (OUT/'full-frames'/unit/action/direction/f'{n:02}.png').exists(), (unit,action,direction,n)
                if action=='idle' or direction in ['SE','NW']:
                    for n in ([0] if action=='idle' else range(8)):
                        index=n if unit=='clubman' else n*2
                        destination=OUT/'frames'/unit/action/direction/f'{n:02}.png'
                        destination.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(OUT/'full-frames'/unit/action/direction/f'{index:02}.png',destination)


def label(im, xy, text, size=20, bold=False):
    ImageDraw.Draw(im).text(xy, text, fill=INK, font=ImageFont.truetype(BOLD if bold else FONT, size))


def frame(unit, variant, action='idle', direction='SE', sample=0):
    if variant == 'B':
        index=sample if unit=='clubman' else sample*2
        path=OUT/'full-frames'/unit/action/direction/f'{index:02}.png'
        if not path.exists(): path = OUT/'frames'/unit/action/direction/f'{sample:02}.png'
    else:
        folder = ROOT/('art/outlined_units/frames' if unit == 'clubman' else 'art/ages/units/frames')
        index = sample if unit == 'clubman' else sample*2
        path = folder/unit/action/direction/f'{index:02}.png'
    return Image.open(path).convert('RGBA')


def place(im, sprite, foot, cell, anchor):
    sprite = sprite.resize((round(cell), round(cell)), Image.Resampling.NEAREST)
    im.paste(sprite, (round(foot[0]-cell*anchor[0]), round(foot[1]-cell*anchor[1])), sprite)


def terrain(im, box):
    tile = Image.open(ROOT/'assets/tiles/source_textures/desert.png').convert('RGB')
    tile = tile.resize((256, 256))
    patch = Image.new('RGB', (box[2]-box[0], box[3]-box[1]))
    for y in range(0, patch.height, 256):
        for x in range(0, patch.width, 256):
            patch.paste(tile, (x,y))
    im.paste(patch, box[:2])


board = Image.new('RGB', (1536, 1050), BG)
label(board, (28, 18), 'OPTION B / ACTUAL BLENDER MODEL REVIEW', 32, True)
label(board, (28, 64), 'Original vs corrected models. Same world scale, lighting and head size; corrected arm/grip motion. Review only.', 19)
for i, (unit, name) in enumerate(zip(UNITS, NAMES)):
    left = i*512
    label(board, (left+24, 110), name, 27, True)
    for j, variant in enumerate(['original', 'B']):
        x = left+128+j*244
        label(board, (x-85, 155), 'Original' if j == 0 else 'Option B', 22, True)
        for direction, y, cell in [('SE',423,380),('NW',630,270)]:
            detail=OUT/'details'/unit/variant/f'{direction}.png'
            sprite=Image.open(detail).convert('RGBA') if detail.exists() else frame(unit, variant,direction=direction)
            m=settings(unit,variant)
            place(board, sprite, (x,y), cell*m['render_scale'], m['ground_anchor'])
    label(board, (left+24, 659), 'Actual size: zoom 1.0', 20, True)
    terrain(board, (left+16, 698, left+496, 817))
    for j, variant in enumerate(['original', 'B']):
        for k, direction in enumerate(['SE', 'NW']):
            m=settings(unit,variant)
            place(board, frame(unit, variant, direction=direction), (left+96+j*244+k*63, 780), 64*m['render_scale'], m['ground_anchor'])
    label(board, (left+24, 834), 'Distant size: zoom 0.65', 20, True)
    terrain(board, (left+16, 873, left+496, 980))
    for j, variant in enumerate(['original', 'B']):
        for k, direction in enumerate(['SE', 'NW']):
            m=settings(unit,variant)
            place(board, frame(unit, variant, direction=direction), (left+96+j*244+k*63, 946), 64*.65*m['render_scale'], m['ground_anchor'])
label(board, (28, 1004), 'Top views enlarged for inspection. Small rows use the game renderer\'s 64 px unit-cell scale. Open at 100% to judge size.', 18)
board.save(OUT/'comparison.png')

directions = Image.new('RGB', (1440, 800), BG)
label(directions, (24, 15), 'OPTION B / EIGHT DIRECTIONS', 29, True)
for col, direction in enumerate(DIRECTIONS):
    label(directions, (col*180+65, 62), direction, 21, True)
for row, (unit, name) in enumerate(zip(UNITS, NAMES)):
    label(directions, (24, row*226+105), name, 21, True)
    for col, direction in enumerate(DIRECTIONS):
        place(directions, frame(unit, 'B', direction=direction), (col*180+90,row*226+292), 260*meta[unit]['render_scale'], meta[unit]['ground_anchor'])
directions.save(OUT/'eight-directions.png')

if (OUT/'full-frames').exists():
    movie=[]
    for n in range(16):
        im=Image.new('RGB',(1600,790),BG)
        label(im,(24,15),'CORRECTED ATTACK / ALL EIGHT DIRECTIONS',28,True)
        for col,direction in enumerate(DIRECTIONS): label(im,(col*200+80,60),direction,20,True)
        for row,(unit,name) in enumerate(zip(UNITS,NAMES)):
            label(im,(24,102+row*225),name,21,True)
            index=n//2 if unit=='clubman' else n
            for col,direction in enumerate(DIRECTIONS):
                sprite=Image.open(OUT/'full-frames'/unit/'attack'/direction/f'{index:02}.png').convert('RGBA')
                place(im,sprite,(col*200+100,295+row*225),235*meta[unit]['render_scale'],meta[unit]['ground_anchor'])
        movie.append(im)
    movie[0].save(OUT/'attack-all-directions.gif',save_all=True,append_images=movie[1:],duration=50,loop=0)
    swings=[]
    for n in range(16):
        im=Image.new('RGB',(1080,710),BG)
        label(im,(24,15),'CLUBMAN SWING / EDGE-FIRST SWORD STRIKE',28,True)
        for col,(unit,name) in enumerate(zip(UNITS,NAMES)):
            label(im,(col*360+24,68),name,23,True)
            for row,direction in enumerate(['SE','NW']):
                index=n//2 if unit=='clubman' else n
                sprite=Image.open(OUT/'full-frames'/unit/'attack'/direction/f'{index:02}.png').convert('RGBA')
                place(im,sprite,(col*360+180,350+row*295),340*meta[unit]['render_scale'],meta[unit]['ground_anchor'])
        swings.append(im)
    swings[0].save(OUT/'swing-comparison.gif',save_all=True,append_images=swings[1:],duration=50,loop=0)
    strip=Image.new('RGB',(1600,1320),BG)
    label(strip,(24,12),'CORRECTED ATTACK / KEY POSES',28,True)
    for row,(unit,direction) in enumerate((u,d) for u in UNITS for d in ['SE','NW']):
        label(strip,(24,58+row*205),f'{unit.replace("_"," ").title()} / {direction}',19,True)
        for n in range(8):
            place(strip,frame(unit,'B','attack',direction,n),(n*200+100,245+row*205),250*meta[unit]['render_scale'],meta[unit]['ground_anchor'])
    strip.save(OUT/'attack-key-poses.png')

for action in ['run', 'attack']:
    frames=[]
    for n in range(8):
        im = Image.new('RGB', (1440, 740), BG)
        label(im, (24, 15), f'OPTION B / {action.upper()} / ORIGINAL LEFT, OPTION B RIGHT', 26, True)
        for col, (unit, name) in enumerate(zip(UNITS, NAMES)):
            label(im, (col*480+24, 65), name, 23, True)
            for row, direction in enumerate(['SE', 'NW']):
                for side, variant in enumerate(['original','B']):
                    m=settings(unit,variant)
                    place(im, frame(unit, variant, action, direction,n), (col*480+122+side*232, 350+row*305), 350*m['render_scale'], m['ground_anchor'])
        frames.append(im)
    frames[0].save(OUT/f'{action}.gif', save_all=True, append_images=frames[1:], duration=100, loop=0)

# Identical crowd locations and facings on both halves. Other roles unchanged.
crowd = Image.new('RGB', (1400, 620), BG)
label(crowd, (24, 15), 'MIXED CROWD / ZOOM 1.0 / NO EMBLEMS', 28, True)
for side, variant in enumerate(['original', 'B']):
    label(crowd, (side*700+24, 66), 'Original melee units' if side == 0 else 'Option B melee units', 24, True)
    terrain(crowd, (side*700+16, 110, side*700+684, 575))
    for row in range(6):
        for col in range(7):
            index = row*7+col
            unit = ['worker', 'clubman', 'slinger', 'bronze_swordsman', 'spearman', 'iron_swordsman', 'healer'][index%7]
            direction = DIRECTIONS[(row*3+col)%8]
            if unit in UNITS:
                sprite = frame(unit, variant, direction=direction)
                m=settings(unit,variant)
                anchor = m['ground_anchor']; scale = m['render_scale']
            else:
                sprite = Image.open(ROOT/'art/outlined_units/frames'/unit/'idle'/direction/'00.png').convert('RGBA')
                anchor = [.5,.730059]; scale = 1
            place(crowd, sprite, (side*700+78+col*85+(row%2)*17, 173+row*72),64*scale,anchor)
label(crowd, (24, 588), '42 units per panel. Workers, ranged infantry, spearmen and healers are unchanged. Blender sprites composited on terrain.', 18)
crowd.save(OUT/'mixed-crowd.png')

checks=[]
for path in sorted((OUT/('full-frames' if (OUT/'full-frames').exists() else 'frames')).rglob('*.png')):
    im=Image.open(path)
    bounds=im.getbbox()
    assert im.mode == 'RGBA' and im.size == (192,192) and bounds, str(path)
    assert min(bounds[0],bounds[1],192-bounds[2],192-bounds[3]) >= 2, (str(path),bounds)
    checks.append({'frame':str(path.relative_to(OUT)), 'bounds':bounds})
for unit in UNITS:
    assert len({frame(unit,'B',direction=d).tobytes() for d in DIRECTIONS}) == 8
    for action in ['run','attack']:
        for direction in ['SE','NW']:
            assert len({frame(unit,'B',action,direction,n).tobytes() for n in range(8)}) > 4
(OUT/'validation.json').write_text(json.dumps({'frames_checked':len(checks),'checks':'RGBA, 192 px, margins >=2 px, eight distinct directions and active motion', 'frames':checks},indent=2))
if (OUT/'clearance.json').exists():
    clearance=json.loads((OUT/'clearance.json').read_text())
    assert len(clearance)==3 and not any(r['collisions'] for r in clearance)
    (OUT/'verification-summary.json').write_text(json.dumps({
        'sprite_frames':len(checks),'mesh_pair_checks':sum(r['pair_checks'] for r in clearance),
        'grip_checks':sum(r['grip_checks'] for r in clearance),
        'unintended_intersections':0,'subframe_interval':.125,
        'scope':'Three review models; idle, run and attack; all eight sprite facings; production assets unchanged'
    },indent=2))
print(f'Built review sheets and GIFs; {len(checks)} rendered frames validated.')
