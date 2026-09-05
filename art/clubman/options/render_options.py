"""Three Blender art-direction studies; does not replace the playable sprite sheets."""
import bpy
import math
from pathlib import Path
from mathutils import Vector

OUT = Path(__file__).resolve().parent
DIRECTIONS = {'E':90, 'SE':45, 'S':0, 'SW':315, 'W':270, 'NW':225, 'N':180, 'NE':135}
STYLES = {
 '1_cartoon': dict(title='Outlined cartoon', head=.34, head_z=1.72, shoulder=1.30, hip=.64, width=.34, size=192, outline=1.35, texture=False),
 '2_illustrated': dict(title='Textured illustration', head=.265, head_z=1.94, shoulder=1.57, hip=.83, width=.35, size=192, outline=.8, texture=True),
 '3_pixel': dict(title='Crisp pixel sprite', head=.32, head_z=1.72, shoulder=1.32, hip=.66, width=.37, size=96, outline=.7, texture=False),
}

def linear(hexcolor):
    channels = [int(hexcolor[i:i+2],16)/255 for i in (0,2,4)]
    return [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]

for style, cfg in STYLES.items():
    folder=OUT/style
    folder.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE'
    scene.render.resolution_x=cfg['size']
    scene.render.resolution_y=cfg['size']
    scene.render.resolution_percentage=100
    scene.render.film_transparent=True
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGBA'
    scene.render.use_freestyle=True
    scene.render.line_thickness=cfg['outline']
    fs=bpy.context.view_layer.freestyle_settings
    lines=fs.linesets[0]
    lines.select_crease=False
    lines.linestyle.color=(.035,.043,.067) if not cfg['texture'] else (.05,.032,.015)
    lines.linestyle.thickness=cfg['outline']
    scene.view_settings.view_transform='Standard'
    scene.world.color=(.12,.12,.12)

    def mat(name, color, grain=False):
        m=bpy.data.materials.new(style+' '+name)
        m.use_nodes=True
        nodes=m.node_tree.nodes
        links=m.node_tree.links
        nodes.clear()
        output=nodes.new('ShaderNodeOutputMaterial')
        rgb=linear(color)
        if cfg['texture']:
            shader=nodes.new('ShaderNodeBsdfPrincipled')
            shader.inputs['Roughness'].default_value=.95
            shader.inputs['Specular IOR Level'].default_value=.1
            if grain:
                noise=nodes.new('ShaderNodeTexNoise')
                noise.inputs['Scale'].default_value=45
                noise.inputs['Detail'].default_value=2
                ramp=nodes.new('ShaderNodeValToRGB')
                ramp.color_ramp.elements[0].color=(*[c*.55 for c in rgb],1)
                ramp.color_ramp.elements[1].color=(*[min(1,c*1.3) for c in rgb],1)
                links.new(noise.outputs['Fac'],ramp.inputs[0])
                links.new(ramp.outputs['Color'],shader.inputs['Base Color'])
                bump=nodes.new('ShaderNodeBump')
                bump.inputs['Strength'].default_value=.12
                bump.inputs['Distance'].default_value=.025
                links.new(noise.outputs['Fac'],bump.inputs['Height'])
                links.new(bump.outputs[0],shader.inputs['Normal'])
            else:
                shader.inputs['Base Color'].default_value=(*rgb,1)
        else:
            diffuse=nodes.new('ShaderNodeBsdfDiffuse')
            diffuse.inputs['Color'].default_value=(.8,.8,.8,1)
            light=nodes.new('ShaderNodeShaderToRGB')
            links.new(diffuse.outputs[0],light.inputs[0])
            ramp=nodes.new('ShaderNodeValToRGB')
            ramp.color_ramp.interpolation='CONSTANT'
            for element,position,factor in [(ramp.color_ramp.elements[0],.0,.47),(ramp.color_ramp.elements[1],.35,.82)]:
                element.position=position
                element.color=(*[c*factor for c in rgb],1)
            e=ramp.color_ramp.elements.new(.68)
            e.color=(*[min(1,c*1.14) for c in rgb],1)
            links.new(light.outputs[0],ramp.inputs[0])
            shader=nodes.new('ShaderNodeEmission')
            links.new(ramp.outputs[0],shader.inputs['Color'])
        links.new(shader.outputs[0],output.inputs[0])
        return m

    skin=mat('skin','E5B875' if style!='2_illustrated' else 'D7A66B')
    cloth=mat('blue cloth','4693AF' if style!='2_illustrated' else '447F99',True)
    leather=mat('ochre hide','A57840',True)
    dark=mat('dark seam','463728')
    hair=mat('hair','55412A',True)
    linen=mat('linen','E6D4A0',True)
    wood=mat('wood','A4793F',True)
    gold=mat('buckle','C9AF61')
    eye=mat('eyes','20273C')
    white=mat('eye highlights','F7E5B3')

    def pivot(name,loc,parent=None):
        obj=bpy.data.objects.new(name,None)
        bpy.context.collection.objects.link(obj)
        obj.parent=parent
        obj.location=loc
        return obj

    def ball(name,loc,scale,material,parent):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16,ring_count=10,radius=1)
        obj=bpy.context.object
        obj.name=name
        obj.parent=parent
        obj.location=loc
        obj.scale=scale
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth=True
        return obj

    def rod(name,a,b,r1,r2,material,parent,vertices=12):
        a,b=Vector(a),Vector(b)
        bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=r1,radius2=r2,depth=(b-a).length)
        obj=bpy.context.object
        obj.name=name
        obj.parent=parent
        obj.location=(a+b)/2
        obj.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
        obj.data.materials.append(material)
        bevel=obj.modifiers.new('Soft crafted edges','BEVEL')
        bevel.width=.017
        bevel.segments=2
        for polygon in obj.data.polygons:
            polygon.use_smooth=True
        return obj

    root=pivot('Facing',(0,0,0))
    body=pivot('Body',(0,0,0),root)
    hip=cfg['hip']; shoulder=cfg['shoulder']; width=cfg['width']; hz=cfg['head_z']; hs=cfg['head']
    rod('Blue sleeveless tunic',(0,0,hip-.04),(0,0,shoulder-.10),width*.82,width,cloth,body)
    rod('Tunic hem',(0,0,hip-.08),(0,0,hip-.025),width*.84,width*.85,linen,body)
    rod('Wide hide belt',(0,0,hip+.10),(0,0,hip+.22),width*.85,width*.86,dark,body)
    ball('Belt buckle',(0,-width*.87,hip+.16),(.08,.027,.067),gold,body)
    rod('Neck',(0,0,shoulder-.07),(0,0,hz-hs*.65),.13,.13,skin,body)
    ball('Face',(0,-.025,hz),(hs,hs*.87,hs),skin,body)
    ball('Hair cap',(0,.025,hz+hs*.68),(hs*1.015,hs*.89,hs*.49),hair,body)
    for side in [-1,1]:
        ball('Ear',(side*hs*.98,0,hz-.015),(.065,.07,.09),skin,body)
        ball('Sideburn',(side*hs*.84,-.008,hz+hs*.22),(.06,.14,.15),hair,body)
        ball('Eye white',(side*hs*.34,-hs*.842,hz+.03),(.037,.026,.048),white,body)
        ball('Pupil',(side*hs*.34,-hs*.905,hz+.028),(.018,.015,.029),eye,body)
        rod('Brow',(side*hs*.34-.045,-hs*.85,hz+.09),(side*hs*.34+.045,-hs*.85,hz+.09),.023,.023,hair,body)
    ball('Nose',(0,-hs*.88,hz-.035),(.067,.072,.075),skin,body)
    # A shaped short beard avoids the faceted caveman muzzle of the first prototype.
    ball('Short beard',(0,-hs*.50,hz-hs*.68),(hs*.72,hs*.53,hs*.42),hair,body)
    rod('Headband',(0,0,hz+hs*.40),(0,0,hz+hs*.55),hs*1.01,hs*.985,cloth if style!='2_illustrated' else leather,body,24)
    if style=='2_illustrated':
        ball('Single hide shoulder pad',(-width*.83,0,shoulder-.015),(.24,.26,.15),leather,body)
        for z in [hip+.33,hip+.43,hip+.53]:
            rod('Front tunic stitching',(-.03,-width*.92,z),(.04,-width*.92,z+.02),.009,.009,linen,body,6)
        # A diagonal leather baldric gives the taller version a different silhouette and construction.
        rod('Diagonal strap',(-width*.55,-width*.81,shoulder-.12),(width*.55,-width*.81,hip+.23),.045,.045,leather,body,8)
    elif style=='3_pixel':
        ball('Broad hide collar',(0,.025,shoulder-.04),(width*1.06,.245,.13),leather,body)

    legs=[];arms=[]
    for side in [-1,1]:
        leg=pivot('Hip', (side*.15,0,hip),body)
        rod('Trouser leg',(0,0,-.035),(0,0,-hip*.62),.13,.11,leather if cfg['texture'] else cloth,leg)
        rod('Boot cuff',(0,0,-hip*.52),(0,0,-hip*.7),.14,.14,linen if not cfg['texture'] else leather,leg)
        ball('Boot',(0,-.06,-hip+.10),(.15,.215,.13),dark,leg)
        legs.append(leg)
        arm=pivot('Shoulder',(side*(width+.015),0,shoulder-.10),body)
        length=.47 if cfg['texture'] else .40
        rod('Upper arm',(0,0,0),(side*.055,-.025,-length*.50),.135,.105,skin,arm)
        rod('Forearm',(side*.055,-.025,-length*.50),(side*.07,-.14,-length),.11,.09,skin,arm)
        rod('Wrist binding',(side*.07,-.125,-length*.86),(side*.07,-.15,-length),.107,.10,linen,arm)
        ball('Fist',(side*.07,-.17,-length-.045),(.115,.115,.12),skin,arm)
        arms.append(arm)
    length=.47 if cfg['texture'] else .40
    weapon=pivot('Right-hand club',(.07,-.17,-length-.045),arms[1])
    rod('Club haft',(0,0,-.12),(0,-.10,.34),.050,.065,wood,weapon)
    rod('Knotted club head',(0,-.10,.26),(0,-.21,.72),.12,.18,wood,weapon,10)
    ball('Club end',(0,-.21,.72),(.18,.17,.12),wood,weapon)
    for z in [.30,.35]:
        rod('Club binding',(0,-.11,z),(0,-.12,z+.028),.135,.139,linen,weapon)
    if cfg['texture']:
        for x in [-.065,.06]:
            rod('Wood grain groove',(x,-.245,.40),(x+.02,-.345,.70),.009,.009,dark,weapon,6)
    shield=pivot('Left-hand wooden buckler',(-.07,-.23,-length*.66),arms[0])
    radius=.24 if cfg['texture'] else .25
    rod('Buckler dark rim',(0,.035,0),(0,-.04,0),radius,radius,dark,shield,20)
    rod('Buckler wood',(0,-.045,0),(0,-.06,0),radius*.88,radius*.88,wood,shield,20)
    ball('Buckler boss',(0,-.073,0),(.068,.034,.068),gold,shield)
    for x in [-.09,.09]:
        rod('Plank joint',(x,-.071,-.17),(x,-.071,.17),.009,.009,dark,shield,6)
    if style=='1_cartoon':
        rod('Shield blue stripe',(-.05,-.077,-.17),(-.05,-.077,.17),.021,.021,cloth,shield,6)

    for name,loc,power,size in [('Key',(-3,-4,7),800,3),('Fill',(4,-1,4),120,4)]:
        light=bpy.data.lights.new(name,'AREA')
        obj=bpy.data.objects.new(name,light)
        bpy.context.collection.objects.link(obj)
        obj.location=loc
        obj.rotation_euler=(Vector((0,0,1))-obj.location).to_track_quat('-Z','Y').to_euler()
        light.energy=power
        light.size=size
    bpy.ops.object.camera_add(location=(0,-7,5.3))
    cam=bpy.context.object
    cam.rotation_euler=(Vector((0,0,1.1))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO'
    cam.data.ortho_scale=4.1 if style!='2_illustrated' else 4.5
    scene.camera=cam
    root.rotation_euler.z=math.radians(45)
    scene.render.fps=10
    scene.frame_start=1;scene.frame_end=8
    for i in range(8):
        phase=i*math.tau/8
        body.location.z=.025*(1-math.cos(2*phase))
        body.keyframe_insert('location',frame=i+1)
        for j,side in enumerate([-1,1]):
            legs[j].rotation_euler.x=side*.45*math.sin(phase)
            arms[j].rotation_euler.x=-side*.35*math.sin(phase)
            legs[j].keyframe_insert('rotation_euler',frame=i+1)
            arms[j].keyframe_insert('rotation_euler',frame=i+1)
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(folder/'clubman.blend'))
    for direction,angle in DIRECTIONS.items():
        root.rotation_euler.z=math.radians(angle)
        scene.render.filepath=str(folder/f'idle_{direction}.png')
        bpy.ops.render.render(write_still=True)
    root.rotation_euler.z=math.radians(45)
    for i in range(8):
        scene.frame_set(i+1)
        scene.render.filepath=str(folder/f'walk_{i:02}.png')
        bpy.ops.render.render(write_still=True)
    print('DONE '+style,flush=True)
