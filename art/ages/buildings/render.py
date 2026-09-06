"""Editable outlined buildings for the 30 available age/family combinations."""
import bpy
import sys
import math
import json
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'units'))
from render import box,rod,ball,mesh,pivot,material,remove

FAMILIES=['castle','barracks','house','farm','lumbermill','mine','stable','blacksmith','temple','siege_workshop','market','watchtower']
NAMES={'castle':['Town Center','Town Hall','Castle'],'lumbermill':'Lumbermill','siege_workshop':'Siege Workshop'}

def build(family,age):
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/'art/outlined_units/clubman.blend'))
    scene=bpy.context.scene
    remove('Body')
    facing=bpy.data.objects['Facing']; facing.animation_data_clear(); facing.rotation_euler.z=math.pi/4
    base=pivot('Building origin',(0,0,0),facing)
    wood=material('Timber','876047'); dark=material('Dark recess','303234')
    wall=material('Age wall',['AE8760','D8BF91','A6A79D'][age-1])
    roofmat=material('Roof',['BD9C58','A95D3F','626C69'][age-1])
    trim=material('Cut stone','BDB7A2'); metal=material('Metalwork','A2A69D')
    blue=bpy.data.materials['1_cartoon blue cloth']
    linen=bpy.data.materials['1_cartoon linen']
    soil=material('Earth','6F6346'); green=material('Leaves','71894C'); gold=material('Grain and ore','D4B263')
    def beam(name,a,b,r=.055,mat=wood): return rod(name,a,b,r,r,mat,base)
    def block(name,loc,scale,mat=wall,b=.035): return box(name,loc,scale,mat,base,b)
    def gable(x,y,w,d,z,h):
        vertices=[(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x,y-d/2,z+h),
                  (x-w/2,y+d/2,z),(x+w/2,y+d/2,z),(x,y+d/2,z+h)]
        mesh('Pitched roof',vertices,[(0,1,2),(5,4,3),(0,2,5,3),(2,1,4,5),(3,4,1,0)],roofmat,base)
        beam('Roof ridge',(x,y-d/2,z+h+.025),(x,y+d/2,z+h+.025),.045)
        for side in [-1,1]:
            for j in range(1,7):
                yy=y-d/2+d*j/7
                beam('Roof course',(x+side*.035,yy,z+h),(x+side*w*.49,yy,z+.025),.019,roofmat if age>1 else gold)
    def flag(x,y,z):
        beam('Banner pole',(x,y,z),(x,y,z+.77),.025)
        mesh('Team banner',[(x,y,z+.73),(x+.44,y,z+.68),(x+.39,y,z+.35),(x,y,z+.4)],[(0,1,2,3)],blue,base)
    def door(x,y,z=.12,w=.48,h=.80):
        block('Door recess',(x,y,z+h/2),(w,.035,h),dark,.025)
        for side in [-1,1]: block('Door jamb',(x+side*(w/2+.055),y-.015,z+h/2),(.08,.08,h+.08),wood)
        block('Door lintel',(x,y-.015,z+h+.03),(w+.20,.11,.1),wood)
    def shelter(x,y,w,d,h,closed=True):
        if closed:
            block('Building walls',(x,y,h/2+.13),(w,d,h),wall)
            door(x,y-d/2-.035)
            for side in [-1,1]:
                block('Window',(x+side*w*.32,y-d/2-.05,h*.67),(.24,.05,.30),dark)
                beam('Window mullion',(x+side*w*.32,y-d/2-.09,h*.53),(x+side*w*.32,y-d/2-.09,h*.83),.02)
        for xx in [-1,1]:
            for yy in [-1,1]:
                beam('Corner post',(x+xx*w*.47,y+yy*d*.47,.12),(x+xx*w*.47,y+yy*d*.47,h+.18),.075)
        gable(x,y,w+.32,d+.30,h+.16,.52 if age==1 else .67)
    def fence(x,y,w):
        for xx in [x-w/2,x,x+w/2]: beam('Fence post',(xx,y,.10),(xx,y,.65),.045)
        for z in [.32,.55]: beam('Fence rail',(x-w/2,y,z),(x+w/2,y,z),.03)
    def barrel(x,y,z=.12):
        rod('Barrel',(x,y,z),(x,y,z+.45),.18,.18,wood,base)
        for zz in [z+.07,z+.37]: rod('Barrel hoop',(x,y,zz),(x,y,zz+.035),.187,.187,metal,base)
    def logs(x,y):
        for j in range(3):
            beam('Stacked log',(x-.45,y+j*.16,.24),(x+.45,y+j*.16,.24),.10)
        beam('Stacked log',(x-.4,y+.17,.42),(x+.4,y+.17,.42),.1)
    block('Footing',(0,0,.07),(4.5,3.65,.14),soil if age==1 else trim,.16)
    if age>1:
        for xx in [-1.85,-1.20,-.55,.1,.75,1.40]:
            block('Paving joint',(xx,-1.70,.145),(.015,.17,.009),soil,.002)
    if family=='castle':
        if age<3:
            shelter(0,.12,2.6,2.1,1.30 if age==1 else 1.65)
            for x in [-.8,.8]: beam('Entrance canopy post',(x,-1.48,.13),(x,-1.48,1.20),.065)
            block('Civic canopy',(0,-1.25,1.19),(1.9,.9,.10),roofmat)
            barrel(-1.72,-.8); flag(1.5,.65,1.2)
            block('Entrance step',(0,-1.55,.17),(1.1,.45,.18),trim)
        else:
            block('Castle keep',(0,.45,1.28),(2.50,1.85,2.30),wall)
            door(0,-.51,.13,.72,1.12)
            for x in [-1.57,1.57]:
                block('Corner tower',(x,-.35,1.47),(.82,.94,2.72),wall)
                block('Tower crown',(x,-.35,2.78),(.97,1.08,.18),trim)
                for dx in [-.34,.34]:
                    for dy in [-.4,.4]: block('Battlement',(x+dx,-.35+dy,2.98),(.25,.25,.35),wall)
                block('Arrow slit',(x,-.831,1.94),(.065,.025,.4),dark)
            for x in [-.98,-.5,0,.5,.98]: block('Keep battlement',(x,-.38,2.57),(.26,.28,.30),wall)
            flag(0,.5,2.45)
    elif family=='barracks':
        shelter(-.25,.30,2.5,1.85,1.18+age*.10)
        for x in [1.35,1.67,1.98]:
            beam('Weapon rack spear',(x,.45,.16),(x,.45,1.50),.025)
            rod('Spear point',(x,.45,1.50),(x,.45,1.72),.075,0,wood if age==1 else metal,base)
        beam('Weapon rack bar',(1.2,.50,.8),(2.1,.50,.8),.045)
        for x in [-1.45,1.25]:
            beam('Practice post',(x,-1.22,.12),(x,-1.22,1.12),.07)
            ball('Practice shield',(x,-1.25,.88),(.27,.08,.31),wood if age==1 else metal,base)
        flag(.95,.5,1.8)
    elif family=='house':
        shelter(-.2,.15,2.15,1.75,1.05+age*.12)
        if age==3: block('Chimney',(.53,.45,2.05),(.32,.40,1.0),wall)
        barrel(1.48,-.5); fence(-1.2,-1.35,1.1)
        block('Door mat',(-.2,-1.13,.17),(.58,.32,.06),linen)
        flag(.78,.40,1.5)
    elif family=='farm':
        block('Cultivated earth',(0,-.35,.16),(3.65,2.10,.07),soil)
        for row in range(5):
            y=-1.18+row*.37
            block('Raised furrow',(0,y,.23),(3.28,.16,.10),soil)
            for j in range(10):
                x=-1.45+j*.32
                beam('Grain stalk',(x,y,.26),(x,y,.65+age*.03),.012,gold)
                ball('Grain head',(x,y,.69+age*.03),(.035,.06,.11),gold,base)
        shelter(-1.14,1.14,1.2,.68,.58+age*.12)
        fence(.65,1.48,2.2); barrel(1.52,1.15); flag(1.85,1.35,.5)
    elif family=='lumbermill':
        shelter(-.48,.5,2.45,1.30,1.22,False)
        logs(-.72,-1.20); logs(1.32,.78)
        block('Saw bench',(.9,-.72,.67),(1.48,.48,.16),wood)
        for x in [.30,1.50]: beam('Bench leg',(x,-.72,.13),(x,-.72,.65),.07)
        block('Saw blade',(1.12,-.72,.90),(.72,.025,.20),wood if age==1 else metal)
        flag(-1.4,.72,1.5)
    elif family=='mine':
        for x,y,z,s in [(-1,.5,.95,1.0),(.65,.6,1.0,1.2),(-.1,1.12,1.30,1.05)]:
            ball('Rock outcrop',(x,y,z),(s,.72,s),wall,base)
        block('Mine opening',(0,-.22,.68),(1.05,.045,1.25),dark)
        for x in [-.59,.59]: beam('Mine entrance upright',(x,-.30,.15),(x,-.30,1.50),.12,wood if age<3 else trim)
        beam('Mine crossbeam',(-.72,-.30,1.52),(.72,-.30,1.52),.13)
        for j in range(5): block('Mine rail sleeper',(0,-.55-j*.23,.18),(.85,.1,.07),wood)
        for x in [-.3,.3]: beam('Ore rails',(x,-1.58,.24),(x,-.45,.24),.025,wood if age==1 else metal)
        barrel(1.40,-.88)
        for x,y in [(1.2,-1.10),(1.45,-1.2),(1.7,-1.0)]: ball('Gold ore',(x,y,.25),(.17,.16,.13),gold,base)
        flag(-1.50,-.5,.55)
    elif family=='stable':
        shelter(0,.5,3.20,1.55,1.48,False)
        for x in [-1.1,0,1.1]:
            fence(x,-.32,.88)
            block('Stall back',(x,1.22,.68),(.96,.10,1.05),wood)
        block('Water trough',(1.25,-1.1,.40),(1.1,.5,.5),wood)
        block('Trough water',(1.25,-1.1,.66),(.92,.33,.015),blue)
        barrel(-1.55,-1.14);flag(1.8,.6,1.2)
    elif family=='blacksmith':
        shelter(-.70,.55,2.10,1.48,1.35,False)
        block('Forge furnace',(1.13,.55,.77),(.95,1.1,1.3),wall)
        block('Chimney',(1.13,.78,1.8),(.52,.58,1.75),wall)
        block('Forge mouth',(1.13,-.018,.76),(.56,.035,.57),dark)
        glow=material('Embers','E98D39')
        block('Glowing coals',(1.13,-.045,.54),(.43,.03,.13),glow)
        block('Anvil pedestal',(-.25,-.85,.44),(.48,.45,.65),wood)
        block('Anvil',(-.25,-.85,.84),(.73,.30,.18),metal)
        rod('Anvil horn',(.08,-.85,.87),(.50,-.85,.87),.11,.015,metal,base)
        barrel(-1.56,-1.05);flag(-1.6,.7,1.5)
    elif family=='temple':
        for j in range(3): block('Temple step',(0,-1.15+j*.25,.15+j*.10),(2.7,.48,.18),trim)
        block('Sanctuary',(0,.62,.90),(2.20,1.35,1.52),wall)
        for x in [-1.15,-.48,.48,1.15]:
            rod('Sanctuary column',(x,-.48,.42),(x,-.48,1.84),.11,.09,trim,base)
            block('Column capital',(x,-.48,1.85),(.29,.3,.15),trim)
        gable(0,.26,2.85,2.17,1.97,.42)
        door(0,-.08,.35,.57,1.15)
        for x in [-1.6,1.6]:
            barrel(x,-.85)
            ball('Herb pot foliage',(x,-.85,.68),(.25,.2,.22),green,base)
        flag(0,.75,2.2)
    elif family=='siege_workshop':
        shelter(-.80,.45,1.90,1.65,1.55,False)
        logs(-1.1,-1.12)
        block('Assembly bench',(.8,-.10,.58),(1.7,1.8,.15),wood)
        beam('Ballista stock',(.8,-1.25,.85),(.8,.9,.85),.11)
        beam('Ballista arms',(-.03,-.45,.92),(1.65,-.45,.92),.08)
        for x in [.15,1.45]: beam('Torsion bundle',(x,-.45,.68),(x,-.45,1.12),.09,linen)
        for x in [1.75,1.87,1.99]: beam('Bolt rack',(x,.4,.15),(x,.4,1.48),.022)
        flag(-1.6,.75,1.8)
    elif family=='market':
        for x in [-1.16,1.05]:
            block('Market counter',(x,-.15,.55),(1.45,.7,.75),wood)
            for xx in [x-.65,x+.65]: beam('Stall post',(xx,.18,.12),(xx,.18,1.56),.045)
            gable(x,-.05,1.75,1.38,1.45,.24)
            for j in range(4):
                ball('Basket goods',(x-.48+j*.31,-.20,1.01),(.12,.12,.13),gold if j%2 else green,base)
        barrel(-1.65,1.15);barrel(-1.18,1.15);flag(.0,1.25,1.05)
        block('Market sign',(0,1.15,1.10),(.72,.1,.45),blue)
    elif family=='watchtower':
        for x in [-.65,.65]:
            for y in [-.6,.6]: beam('Tower support',(x,y,.12),(x,y,2.15),.115,wood if age==2 else trim)
        if age==3: block('Stone tower base',(0,0,.99),(1.48,1.38,1.76),wall)
        else:
            for y in [-.60,.60]: beam('Tower cross brace',(-.65,y,.25),(.65,y,1.85),.07)
        block('Firing platform',(0,0,2.02),(1.85,1.75,.20),wood)
        for x in [-.84,.84]: block('Tower parapet',(x,0,2.37),(.14,1.75,.55),wall if age==3 else wood)
        block('Front parapet',(0,-.8,2.37),(1.75,.13,.55),wall if age==3 else wood)
        gable(0,0,2.05,1.94,2.70,.46)
        for j in range(7): beam('Ladder rung',(-.25,-.92,.25+j*.23),(.25,-.92,.25+j*.23),.022)
        for x in [-.29,.29]: beam('Ladder rail',(x,-.92,.15),(x,-.92,1.94),.025)
        flag(.9,.4,2.28)
    # Construction detail distinguishes the materials, not just their color.
    wall_parts=[o for o in base.children if o.name.startswith(('Building walls','Castle keep','Corner tower','Sanctuary','Forge furnace','Stone tower base')) and o.type=='MESH']
    for part in wall_parts:
        corners=[part.matrix_basis@Vector(v) for v in part.bound_box]
        x0,x1=min(v.x for v in corners),max(v.x for v in corners)
        y0,y1=min(v.y for v in corners),max(v.y for v in corners)
        z0,z1=min(v.z for v in corners),max(v.z for v in corners)
        if age==3:
            z=z0+.28;row=0
            while z<z1-.04:
                beam('Masonry course',(x0,y0-.009,z),(x1,y0-.009,z),.009,soil)
                beam('Side masonry course',(x1+.009,y0,z),(x1+.009,y1,z),.009,soil)
                xx=x0+.32+(row%2)*.30
                while xx<x1-.03:
                    beam('Staggered stone joint',(xx,y0-.009,z-.26),(xx,y0-.009,z),.007,soil)
                    xx+=.60
                z+=.28;row+=1
        elif age==2:
            beam('Timber sill',(x0,y0-.04,z0+.10),(x1,y0-.04,z0+.10),.035)
            beam('Side diagonal brace',(x1+.04,y0,z0+.10),(x1+.04,y1,z1-.10),.04)
        elif family!='mine':
            for xx in [x0+.12,x1-.12]:
                beam('Wattle wall upright',(xx,y0-.035,z0),(xx,y0-.035,z1),.045)
    # Deliberate age-specific masonry, even on shared functional silhouettes.
    if age==3 and family not in ['farm','mine']:
        for x in [-1.95,-1.45,-.95,-.45,.05,.55,1.05,1.55,1.95]:
            block('Stone edging',(x,1.70,.23),(.40,.13,.19),wall,.014)
    scene.camera.location=(0,-9,7)
    scene.camera.rotation_euler=(Vector((0,0,1.13))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera.data.ortho_scale=7.2
    scene.render.resolution_x=512;scene.render.resolution_y=512;scene.render.resolution_percentage=100
    scene.render.film_transparent=True;scene.render.image_settings.color_mode='RGBA'
    scene.frame_set(1)
    name=NAMES.get(family,family.title());name=name[age-1] if isinstance(name,list) else name
    key=f'{age}_{family}'
    for folder in ['models','sprites']: (OUT/folder).mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'models'/f'{key}.blend'))
    scene.render.filepath=str(OUT/'sprites'/f'{key}.png');bpy.ops.render.render(write_still=True)
    anchor=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
    return dict(id=key,family=family,age=age,name=name,ground_anchor=[anchor.x,1-anchor.y],sprite=f'sprites/{key}.png',model=f'models/{key}.blend')

manifest=[]
for family in FAMILIES:
    for age in [1,2,3]:
        if age==1 and family in FAMILIES[6:]: continue
        manifest.append(build(family,age))
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('BUILDINGS_COMPLETE',len(manifest),flush=True)
