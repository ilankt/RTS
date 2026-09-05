from pathlib import Path
import os,sys
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import pygame
from PIL import Image,ImageDraw,ImageFont
from managers.sprite_manager import tint_directional_team
OUT=Path(__file__).resolve().parent
pygame.init();pygame.display.set_mode((1,1))
board=Image.new('RGB',(1120,500),'#29362f');draw=ImageDraw.Draw(board)
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',21)
draw.text((18,14),'Decorated mounted spearman / player-color study',font=font,fill='#efdfbe')
for i,(color,label,direction) in enumerate([((40,100,220),'Blue player','SW'),((210,55,45),'Red player','SE'),((70,170,75),'Green player','E')]):
    surface=pygame.image.load(str(OUT/'decorated-detail.png')).convert_alpha()
    tinted=tint_directional_team(surface,color)
    assert pygame.image.tobytes(surface,'RGBA')!=pygame.image.tobytes(tinted,'RGBA')
    assert (pygame.surfarray.array_alpha(surface)==pygame.surfarray.array_alpha(tinted)).all()
    im=Image.frombytes('RGBA',tinted.get_size(),pygame.image.tobytes(tinted,'RGBA'))
    im=im.crop(im.getbbox());im.thumbnail((330,375),Image.Resampling.NEAREST)
    im=im.resize((round(im.width*min(330/im.width,375/im.height)),round(im.height*min(330/im.width,375/im.height))),Image.Resampling.NEAREST)
    board.paste(im,(i*370+(370-im.width)//2,60+(375-im.height)//2),im)
    draw.text((i*370+118,459),label,font=font,fill='#efdfbe')
board.save(OUT/'decorated-review.png')
pygame.quit()
print('PASS: actual game team tint changes cloth and preserves transparency in three player colors.')
