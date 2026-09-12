import bpy, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
result={}
for unit,path in {'archer':'art/readability/remaining/models/archer_option_b.blend','axeman':'art/readability/models/clubman_option_b.blend','horse':'art/ages/units/models/mounted_spearman.blend'}.items():
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/path))
    result[unit]={'render':bpy.context.scene.render.engine,'objects':[{'name':o.name,'parent':o.parent.name if o.parent else None,'loc':list(o.location),'scale':list(o.scale),'animated':bool(o.animation_data)} for o in bpy.context.scene.objects if o.type!='LIGHT']}
(ROOT/'art/factions/source-inspection.json').write_text(json.dumps(result,indent=2))
