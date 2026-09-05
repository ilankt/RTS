from pathlib import Path
from PIL import Image, ImageDraw
import json, base64
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
DIRECTIONS=['E','SE','S','SW','W','NW','N','NE']
ACTIONS=['idle','run','attack']
TARGET=ROOT/'assets/sprites/Units/Clubman'
TARGET.mkdir(parents=True,exist_ok=True)
manifest=json.loads((OUT/'manifest.json').read_text())
size=manifest['size']; frames=manifest['frames']
embedded={}
for action in ACTIONS:
    sheet=Image.new('RGBA',(size*frames,size*8))
    for row,direction in enumerate(DIRECTIONS):
        for frame in range(frames):
            im=Image.open(ROOT/'art/outlined_units/frames/clubman'/action/direction/f'{frame:02}.png').convert('RGBA')
            bbox=im.getbbox()
            assert bbox and min(bbox[:2])>0 and bbox[2]<size and bbox[3]<size, (action,direction,frame,bbox)
            sheet.paste(im,(size*frame,size*row))
    path=TARGET/f'{action}.png'
    sheet.save(path)
    embedded[action]='data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()
# Overview with all directions; animated walk exported for quick review.
contact_frames=[]
for frame in range(frames):
    contact=Image.new('RGB',(768,444),'#27312d')
    d=ImageDraw.Draw(contact)
    for n,direction in enumerate(DIRECTIONS):
        x=(n%4)*192; y=(n//4)*222
        im=Image.open(ROOT/'art/outlined_units/frames/clubman'/'run'/direction/f'{frame:02}.png')
        contact.paste(im,(x,y),im)
        d.text((x+86,y+194),direction,fill='#e5d4aa')
    contact_frames.append(contact)
contact_frames[0].save(OUT/'eight-directions.png')
contact_frames[0].save(OUT/'walk.gif',save_all=True,append_images=contact_frames[1:],duration=100,loop=0)
html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clubman / First age</title>
<style>*{box-sizing:border-box}body{margin:0;background:#17211e;color:#f0e6ce;font:16px Georgia,serif}main{max-width:1120px;margin:auto;padding:44px 30px}header{border-top:1px solid #788276;padding-top:22px;display:flex;justify-content:space-between;align-items:end}.eyebrow,button,label,footer,.caption{font:12px Consolas,monospace;letter-spacing:.07em}.eyebrow{color:#c4aa70}h1{font-size:68px;font-weight:400;margin:10px 0}p{color:#c6c9bd;line-height:1.6;max-width:470px}nav{display:flex;gap:8px;flex-wrap:wrap;margin:28px 0}button{padding:12px 20px;color:inherit;background:transparent;border:1px solid #697364;cursor:pointer}button[aria-pressed=true]{background:#d3b87b;color:#17211e;border-color:#d3b87b}button:focus-visible,input:focus-visible{outline:3px solid #fff;outline-offset:3px}label{margin-left:auto;display:flex;align-items:center;gap:10px}.grid{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #596458;border-left:1px solid #596458}.view{position:relative;border-right:1px solid #596458;border-bottom:1px solid #596458;background:radial-gradient(ellipse at 50% 72%,#4c594740,transparent 60%);text-align:center;padding-bottom:16px}.view:before{content:'';position:absolute;left:28%;right:28%;top:68%;height:10%;border:1px solid #8d96753b;border-radius:50%}canvas{position:relative;width:100%;height:auto;display:block}.caption{color:#c4aa70}footer{display:flex;justify-content:space-between;margin-top:24px;color:#98a28e;font-size:11px;line-height:1.7}@media(max-width:650px){main{padding:24px 16px}header{display:block}h1{font-size:52px}.grid{grid-template-columns:repeat(2,1fr)}label{margin-left:0}footer{display:block}}</style>
<main><header><div><div class="eyebrow">RTS / CHARACTER STUDY 001</div><h1>The clubman.</h1></div><p>Hide, linen, hardwood. A first-age fighter, sculpted in 3D and rendered from eight directions.</p></header>
<nav aria-label="Animation"><button data-action="idle" aria-pressed="false">Idle</button><button data-action="run" aria-pressed="true">Walk</button><button data-action="attack" aria-pressed="false">Attack</button><button id="pause" aria-pressed="false">Pause</button><label>Scale <input aria-label="Character scale" id="scale" type="range" min="0.33" max="1.3" step="0.01" value="1"></label></nav><div class="grid" id="grid"></div><footer><span>8 VIEWS / 3 ACTIONS / 192 RENDERED FRAMES<br>Orthographic Blender renders · prototype proportions</span><span>FIRST AGE → CLUBMAN<br>Future evolution: swordsman</span></footer></main>
<script>const sources=__IMAGES__;const directions=['E','SE','S','SW','W','NW','N','NE'];const sheets={};let action='run',paused=false,frame=0,last=0;const canvases=directions.map(d=>{let cell=document.createElement('div');cell.className='view';cell.innerHTML='<canvas width="192" height="192" aria-label="'+d+' view"></canvas><span class="caption">'+d+'</span>';grid.append(cell);return cell.querySelector('canvas')});let scale=1;document.querySelector('#scale').oninput=e=>scale=Number(e.target.value);document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{action=b.dataset.action;frame=0;document.querySelectorAll('[data-action]').forEach(x=>x.setAttribute('aria-pressed',x===b))});document.querySelector('#pause').onclick=e=>{paused=!paused;e.target.textContent=paused?'Play':'Pause';e.target.setAttribute('aria-pressed',paused)};function draw(now){if(!paused&&now-last>=100){frame=(frame+1)%8;last=now}const im=sheets[action];canvases.forEach((c,row)=>{const ctx=c.getContext('2d');ctx.clearRect(0,0,192,192);let s=192*scale;ctx.drawImage(im,frame*192,row*192,192,192,(192-s)/2,(192-s)/2,s,s)});requestAnimationFrame(draw)}Promise.all(Object.entries(sources).map(([k,src])=>new Promise(resolve=>{let im=new Image;im.onload=()=>{sheets[k]=im;resolve()};im.src=src}))).then(()=>requestAnimationFrame(draw));</script></html>'''
(OUT/'preview.html').write_text(html.replace('__IMAGES__',json.dumps(embedded)),encoding='utf-8')
print('Packed 192 frames into three 8-row sheets; no clipping. Preview and GIF ready.')
