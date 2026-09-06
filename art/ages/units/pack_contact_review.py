from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

OUT=Path(__file__).resolve().parent
CASES=[('bronze_worker','Pickaxe edge → ore'),('bronze_swordsman','Sword blade → target'),('bronze_spearman','Side grip → target center')]
font=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',20)
frames=[]
for direction in ['E','SE']:
    for i in range(16):
        board=Image.new('RGB',(1260,440),'#26362f');draw=ImageDraw.Draw(board)
        draw.text((18,12),f'WORKING-EDGE REVIEW / {direction} / FRAME {i+1}',font=font,fill='#eddfbe')
        for column,(unit,label) in enumerate(CASES):
            frame=Image.open(OUT/'contact-frames'/unit/direction/f'{i:02}.png').convert('RGBA').resize((420,420),Image.Resampling.NEAREST)
            board.paste(frame,(column*420,-18),frame)
            draw.text((column*420+18,390),label,font=font,fill='#eddfbe')
        if i==8: board.save(OUT/f'contact-{direction.lower()}.png')
        frames.append(board)
frames[0].save(OUT/'contact-review.gif',save_all=True,append_images=frames[1:],duration=80,loop=0)
print('Contact GIF and frame-9 stills saved.')
