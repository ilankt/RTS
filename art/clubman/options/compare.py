"""Build comparison images from real Blender renders and the game's renderer."""
from pathlib import Path
import copy
import os
import random
import sys

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from PIL import Image, ImageDraw, ImageFont
from core.game import Game
from core.config import MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT
from systems.animation import Animation
from managers.sprite_manager import tint_surface_blue

STYLES=[('1_cartoon','Outlined cartoon','Closest to the current units','Big head, short limbs, flat colour and navy ink.'),('2_illustrated','Textured illustration','Closer to the buildings','Taller stance, fine edges, grain and leather detail.'),('3_pixel','Crisp pixel sprite','The strongest retro direction','Chunkier shapes and deliberate pixel edges.')]
random.seed(4321)
game=Game(mode='ai_spectator',player_count=2)
castle=next(b for b in game.buildings if b.name=='castle' and b.player is game.players[0])
player=castle.player
worker=next(u for u in game.units if u.player is player)
worker.x,worker.y=castle.x+120,castle.y+40
worker.status='idle'
old=copy.deepcopy(game.game_data['units']['warrior'])
old.player=player
old.x,old.y=castle.x+173,castle.y+40
old.status='idle'
old.facing_left=False
old.animations={'idle':Animation(tint_surface_blue(pygame.image.load('assets/sprites/Units/Warrior/Warrior_Idle.png').convert_alpha(),player.color),192,192,100)}
game.units.append(old)
new=copy.deepcopy(game.game_data['units']['warrior'])
new.player=player
new.x,new.y=castle.x+146,castle.y-13
new.status='idle';new.facing_left=False
game.units.append(new)
game.camera.zoom=1.0
game.game_map.scale_tiles(game.camera.zoom)
game.camera.x=MAP_VIEW_WIDTH/2-(castle.x+60)
game.camera.y=MAP_VIEW_HEIGHT/2-castle.y
for key,*_ in STYLES:
    surface=pygame.image.load(str(OUT/key/'idle_SE.png')).convert_alpha()
    size=surface.get_width()
    new.animations={'idle':Animation(surface,size,size,100)}
    game.rendering_system.draw_frame(game.screen,game.map_surface,game.camera,1/60)
    pygame.image.save(game.screen,str(OUT/key/'gameplay.png'))
    pygame.image.save(game.map_surface,str(OUT/key/'map.png'))
pygame.quit()

# The only image operations below arrange/export review boards. Character style
# comes from Blender geometry, materials, outlines and render resolution.
BG='#182321';PANEL='#24312d';INK='#f0e4c8';MUTED='#b3baaa';ACCENT='#d9b77b'
fontpath='C:/Windows/Fonts/'
def font(size,bold=False):
    return ImageFont.truetype(fontpath+('segoeuib.ttf' if bold else 'segoeui.ttf'),size)
def label(draw,xy,text,size=18,fill=INK,bold=False):
    draw.text(xy,text,font=font(size,bold),fill=fill)
def put(canvas,im,box,resample=Image.Resampling.NEAREST,trim=False):
    im=im.convert('RGBA')
    if trim: im=im.crop(im.getbbox())
    x,y,w,h=box
    im.thumbnail((w,h),resample=resample)
    canvas.paste(im,(int(x+(w-im.width)/2),int(y+h-im.height)),im)
def enlarged(im,factor=3):
    return im.resize((im.width*factor,im.height*factor),Image.Resampling.NEAREST)

board=Image.new('RGB',(1440,1080),BG)
d=ImageDraw.Draw(board)
label(d,(38,24),'CLUBMAN / THREE ART DIRECTIONS',16,ACCENT,True)
label(d,(38,51),'Same world. Three ways to belong.',38,INK,True)
label(d,(38,106),'All three are actual Blender renders. Compare shape, shading and detail; the weapon stays a wooden club.',18,MUTED)
# Reference strip: authentic existing art, enlarged equally for the two units.
d.rounded_rectangle((34,149,1406,328),radius=8,fill='#30392f')
label(d,(52,161),'EXISTING GAME ART',14,ACCENT,True)
for path,x,name in [('assets/sprites/Units/Worker/Idle.png',80,'Worker'),('assets/sprites/Units/Warrior/Warrior_Idle.png',272,'Warrior')]:
    im=Image.open(ROOT/path).crop((0,0,192,192))
    put(board,enlarged(im.crop(im.getbbox()),2),(x,190,160,100))
    label(d,(x+38,300),name,15,MUTED)
for path,x,name in [('assets/sprites/Buildings/Barracks.png',510,'Barracks'),('assets/sprites/Buildings/Castle.png',760,'Castle')]:
    put(board,Image.open(ROOT/path),(x,176,210,125),Image.Resampling.LANCZOS,True)
    label(d,(x+70,300),name,15,MUTED)
label(d,(1030,187),'Shared visual language',20,INK,True)
for n,text in enumerate(['Dark edges and warm colours','Compact, readable silhouettes','Blue cloth; grain in buildings']):
    label(d,(1030,223+n*25),text,16,MUTED)

for idx,(key,title,subtitle,description) in enumerate(STYLES):
    x=34+idx*468
    d.rounded_rectangle((x,349,x+436,1031),radius=7,fill=PANEL)
    label(d,(x+18,364),f'{idx+1:02}  {title}',27,INK,True)
    label(d,(x+18,403),subtitle,16,ACCENT)
    source=Image.open(OUT/key/'idle_SE.png').convert('RGBA')
    bbox=source.getbbox()
    assert bbox and min(bbox[:2])>0 and bbox[2]<source.width and bbox[3]<source.height
    crop=source.crop(bbox)
    scaled=crop.resize((int(crop.width*232/crop.height),232),Image.Resampling.NEAREST)
    put(board,scaled,(x+20,439,396,232))
    label(d,(x+18,689),'FRONT / SIDE / BACK',12,MUTED,True)
    for j,view in enumerate(['S','E','NW']):
        src=Image.open(OUT/key/f'idle_{view}.png')
        cr=src.crop(src.getbbox())
        target=cr.resize((int(cr.width*85/cr.height),85),Image.Resampling.NEAREST)
        put(board,target,(x+24+j*130,716,115,85))
    label(d,(x+18,815),'IN THE GAME  /  SAME CAMERA & SCALE',12,MUTED,True)
    scene=Image.open(OUT/key/'map.png')
    # Same untouched game-renderer crop in every card; central upper unit is the candidate.
    cx=MAP_VIEW_WIDTH//2;cy=MAP_VIEW_HEIGHT//2
    scene=scene.crop((cx-163,cy-90,cx+253,cy+100))
    board.paste(scene,(x+10,839))
label(d,(40,1047),'Scene: new clubman above; existing worker and warrior below. Enlarged character views show the rendered pixels.',17,MUTED)
board.save(OUT/'three-options.png')

# Animated comparison, with identical walk phase and apparent character height.
frames=[]
for i in range(8):
    canvas=Image.new('RGB',(1140,380),BG)
    draw=ImageDraw.Draw(canvas)
    for idx,(key,title,*_) in enumerate(STYLES):
        x=idx*380
        label(draw,(x+23,18),f'{idx+1}. {title}',22,INK,True)
        im=Image.open(OUT/key/f'walk_{i:02}.png').convert('RGBA')
        # Keep the entire frame and anchor constant across animation to avoid bob/pivot drift.
        scale=3 if im.width==192 else 6
        im=enlarged(im,scale)
        canvas.paste(im,(x+(380-im.width)//2,45+(300-im.height)//2),im)
        label(draw,(x+23,349),'BLENDER WALK / 8 FRAMES',12,MUTED)
    frames.append(canvas)
frames[0].save(OUT/'walk-comparison.gif',save_all=True,append_images=frames[1:],duration=110,loop=0)
print('Created three-options.png and walk-comparison.gif, plus three actual game screenshots.')
