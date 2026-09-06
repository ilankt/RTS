"""Package the review proposal and existing art into one offline HTML file."""
from pathlib import Path
import base64
import io
import json
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
assets = {}
def asset(key, path):
    image = Image.open(ROOT/path).convert('RGBA')
    image.thumbnail((360, 360), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, 'WEBP', quality=88)
    assets[key] = 'data:image/webp;base64,' + base64.b64encode(output.getvalue()).decode()

units = json.loads((ROOT/'data/units.json').read_text())
buildings = json.loads((ROOT/'data/buildings.json').read_text())
for u in units: asset(u['name'], u['icon'])
for b in buildings: asset(b['name'], b['sprite'])
asset('town_stone', 'assets/sprites/Buildings/TownCenterStone.png')
asset('barracks_stone', 'assets/sprites/Buildings/BarracksStone.png')
asset('swordsman', 'assets/ui/Units/warrior_icon.png')
asset('bowman', 'assets/ui/Units/archer_icon.png')
asset('ballista', 'art/ages/proposal/ballista-concept.png')

rows = []
def n(name, image, role, unlock, status, art, strengths, weakness, look, cost, extra=''):
    return dict(name=name,image=image,role=role,unlock=unlock,status=status,art=art,strong=strengths,weak=weakness,look=look,cost=cost,extra=extra)
def row(code, family, kind, *nodes):
    rows.append(dict(code=code,family=family,kind=kind,nodes=list(nodes)))

LIVE='Existing base'
UPGRADE='Proposed upgrade'
NEW='New unit type'
EXACT='Current game artwork'
REF='Existing art reference; new age model needed'
CONCEPT='New concept illustration; no game animation yet'

row('U01','Workers & economy','unit',
 n('Worker','worker','Builds and gathers. Your only civilian unit.','Town Center · available at start',LIVE,EXACT,'Economy and construction','Every military unit','Simple cloth, primitive hand tools.','Food · inexpensive'),
 n('Worker','worker','Same worker; improved economic tools.','Settlement center · carried forward',LIVE,REF,'Economy and construction','Raids; never an army substitute','Bronze tools, woven apron, same readable silhouette.','Food · inexpensive','Appearance changes with age. Gathering bonuses require the Tools I technology at the Town Hall.'),
 n('Worker','worker','Same worker; efficient late-game economy.','Settlement center · carried forward',UPGRADE,REF,'Economy and construction','Raids','Iron tools, leather work belt.','Food · inexpensive','Tools II at the Castle improves gathering. No separate expensive worker class.'))

row('U02','Front-line infantry','unit',
 n('Clubman','warrior','Durable opening melee fighter.','Barracks · train directly',LIVE,EXACT,'Slingers caught in melee; exposed workers','Ranged focus fire and kiting','Hide tunic, wooden club and buckler.','Food + wood · inexpensive','Proposal: make Stone Age military gold-free. This changes current costs and needs a balance pass.'),
 n('Bronze Swordsman','swordsman','The main infantry line; protects fragile ranged units.','Barracks · paid Clubman → Swordsman upgrade',LIVE,REF,'Spearmen and exposed siege','Archers behind a screen; cavalry flanks','Bronze sword and helmet, round shield, linen armor.','Food + gold · standard','Swordsman upgrade mechanics already exist. Bronze-specific name/model are proposed. Initial upgrade: 180 food + 120 gold, 35s.'),
 n('Iron Swordsman','swordsman','Stronger infantry that can hold a battle line.','Barracks · paid Swordsman → Iron Swordsman upgrade',UPGRADE,REF,'Light infantry and exposed siege','Massed archers; ballista fire','Iron sword and helmet, mail details, larger shield.','Food + gold · standard','Better armor and melee damage. Still needs ranged support; no free power jump on age completion.'))

row('U03','Main ranged line','unit',
 n('Slinger','archer','Opening ranged support; fragile in melee.','Barracks · train directly',LIVE,EXACT,'Clubmen at range; exposed workers','Melee contact','Current slingshot character retained.','Food + wood · inexpensive','Display-name cleanup from “Slingshot Man” to “Slinger” is proposed; keep the current visual weapon for now.'),
 n('Archer','bowman','Reliable damage from behind the infantry.','Barracks · paid Slinger → Archer upgrade',LIVE,REF,'Slow infantry at range','Mounted raids; melee contact','Simple bow, bronze arrowheads, cloth and leather.','Wood + gold · standard','Archer upgrade mechanics already exist. Initial upgrade: 180 wood + 120 gold, 35s. Replaces the slinger recruitment button.'),
 n('Crossbowman','bowman','Powerful ranged shots, with a slower reload.','Barracks · paid Archer → Crossbowman upgrade',UPGRADE,REF,'Armored infantry and exposed support units','Cavalry flanks; melee pressure during reload','Wooden crossbow with iron fittings, bolt quiver and light helmet.','Wood + gold · standard','Replaces Composite Bowman in the accepted ranged line: Slinger → Archer → Crossbowman. The portrait is an Archer reference; a crossbow model and firing animation are needed.'))

row('U04','Spear infantry','unit',
 n('Wooden Spearman','spearman','Cheap reach support for the opening army.','Barracks · Stone Age; train directly',UPGRADE,REF,'Supporting Clubmen; later enemy cavalry','Slingers; Clubmen in a direct melee trade','Fire-hardened wooden spear, hide clothing and a small wooden shield.','Food + wood · inexpensive','New Stone Age variant of the existing spear unit. Its reach gives it an opening role before cavalry appears; Clubmen remain the main front line. The current metal-tipped portrait is a reference only.'),
 n('Bronze Spearman','spearman','Affordable protection against mounted attacks.','Barracks · paid Wooden Spearman → Bronze Spearman upgrade',UPGRADE,REF,'Mounted Spearmen','Swordsmen and archers','Bronze spear tip, simple shield, light armor.','Food + wood · inexpensive','The spear unit already works. This replaces its current Bronze direct unlock with a paid upgrade from Wooden Spearman; retain affordable food + wood recruitment.'),
 n('Pikeman','spearman','A longer spear and a stronger cavalry counter.','Barracks · paid Spearman → Pikeman upgrade',UPGRADE,REF,'Heavy cavalry','Ranged fire and swordsmen','Long iron-tipped pike, helmet and modest body armor.','Food + wood · inexpensive','Use passive reach and anti-cavalry damage first. A manual brace ability can be considered separately.'))

row('U06','Mounted raiders','unit',None,
 n('Mounted Spearman','cavalry','Fast raids and flanks; expensive to lose.','Stable · Bronze Age + completed Barracks',LIVE,EXACT,'Archers and exposed workers','Spearmen; concentrated tower fire','Use the current approved horse/rider and blue saddle cloth.','Food + gold · expensive','Keep its current eight-direction animation. Bronze equipment refinements can follow without rebuilding the horse.'),
 n('Heavy Cavalry','cavalry','A stronger mounted line for decisive flanks.','Stable · paid Mounted Spearman → Heavy Cavalry upgrade',UPGRADE,REF,'Ranged lines and exposed siege','Pikemen; costly trades into defended positions','Armored rider, iron spear, light horse protection; same horse proportions.','Food + gold · expensive','More durability and melee power with a small speed tradeoff. No separate cavalry branch in this first tree.'))

row('U07','Healing support','unit',None,
 n('Healer','healer','Sustains an army between engagements.','Temple · Bronze Age + completed Barracks',LIVE,EXACT,'Healing damaged friendly units','Ranged fire and flanking cavalry','Existing robe, staff and satchel.','Food + gold · specialist','Healing already works. Keep automatic single-target healing; no conversion or damage spell.'),
 n('Priest','healer','Improved single-target healing and support reach.','Temple · paid Healer → Priest upgrade',UPGRADE,REF,'Sustaining expensive late-game armies','Any combat unit that reaches it','Layered robes, more ornate staff, clear team-color trim.','Food + gold · specialist','No resurrection, army conversion or area healing in the initial proposal.'))

row('U09','Long-range siege','unit',None,
 n('Ballista','ballista','Escorted ranged siege for breaking defended bases.','Siege Workshop · Bronze Age + completed Blacksmith; train directly',NEW,CONCEPT,'Buildings and towers; exposed enemy siege','Cavalry flanks; minimum-range dead zone','Timber torsion frame, bronze fittings and wooden wheels.','Wood + gold · expensive','Approved Bronze unlock. Replaces the Ram as the primary building counter: strong structure damage and enough reach to pressure towers. Slow single-target bolts, long reload and minimum range; no splash or piercing initially. Current concept is a silhouette reference, with Bronze fittings still to design.'),
 n('Heavy Ballista','ballista','Stronger siege for fortified late-game bases.','Siege Workshop · paid Ballista → Heavy Ballista upgrade',UPGRADE,CONCEPT,'Fortified buildings, armored infantry and exposed siege','Cavalry and close-range attacks','Larger torsion arms, reinforced bolt rail, iron bands and heavy wheels.','Wood + gold · very expensive','Same siege line, with improved damage and durability. Requires a protective screen. Concept shows the base silhouette; the Heavy variant needs distinct art.'))

def bn(name,image,role,unlock,status,art,look,extra='',cost='Wood · varies by building'):
    return n(name,image,role,unlock,status,art,'See function and unlocks','Enemy siege; most buildings cannot fight',look,cost,extra)

row('B01','Settlement center','building',
 bn('Town Center','town_stone','Trains Workers; researches Bronze Age.','Starting building; workers can rebuild it',LIVE,EXACT,'Round thatched communal hall, timber, hide banners.','Excluded from the three-building age requirement. Existing worker garrison and drop-off functions remain.'),
 bn('Town Hall','town_stone','Trains Workers; researches Iron Age and Tools I.','Town Center evolves automatically on Bronze completion',UPGRADE,REF,'Larger mudbrick hall, timber pillars, bronze trim.','Same settlement-center building, renamed Town Hall. Preserve worker production, garrison and drop-off functions. Stone portrait is a reference; Bronze artwork is needed.'),
 bn('Castle','castle','Trains Workers; researches Tools II.','Town Hall evolves automatically on Iron completion',UPGRADE,REF,'Fortified stone keep, iron fittings and prominent team banners.','Final form of the settlement center, retaining its civic functions. No separate Castle construction branch or automatic combat bonus. Existing castle art is a reference for the final model.'))

row('B02','Infantry & ranged training','building',
 bn('Barracks','barracks_stone','Trains Clubmen, Slingers and Wooden Spearmen.','Stone Age · build directly',LIVE,EXACT,'Thatched training lodge, wooden weapons and practice target.','Counts toward Bronze advancement.'),
 bn('Barracks','barracks','Trains Swordsmen, Archers and Bronze Spearmen after their paid line upgrades.','Same building · Bronze Age unlocks new options',LIVE,REF,'Mudbrick training yard, bronze weapon racks, cloth awning.','All three Stone lines continue here. Keep the name Barracks in every age; only its appearance evolves automatically. No separate archery building.'),
 bn('Barracks','barracks','Trains Iron Swordsmen, Crossbowmen and Pikemen after paid line upgrades.','Same building · Iron Age',UPGRADE,REF,'Stone training yard, iron racks and reinforced gate.','Unpurchased line upgrades leave the earlier unit available. Building appearance itself upgrades automatically.'))

row('B03','Population','building',
 bn('House','house','Adds population capacity.','Stone Age · build directly',LIVE,REF,'Small thatched family hut.','Counts toward Bronze advancement. Current function is +5 capacity.'),
 bn('House','house','Adds the same population capacity.','Existing houses remain usable',LIVE,REF,'Mudbrick home with woven awning.','Cosmetic change only; no free capacity boost on age-up.'),
 bn('House','house','Adds the same population capacity.','Existing houses remain usable',UPGRADE,REF,'Stone-and-timber family home.','Keep one House button and the same capacity rule across all three ages.'))

row('B04','Food production','building',
 bn('Farm','farm','Generates food over time.','Stone Age · build directly',LIVE,REF,'Small hand-tended plots and a rough fence.','Counts toward Bronze advancement. Preserve the current passive-food model.'),
 bn('Farm','farm','Food production; benefits from paid economic research.','Existing farms remain usable',LIVE,REF,'Larger-looking field rows, irrigation channels and tool shed.','Visual irrigation does not introduce a water resource or a new worker assignment system.'),
 bn('Farm','farm','Late-game food production.','Existing farms remain usable',UPGRADE,REF,'Well-kept field, improved tools and grain store.','Avoid silently increasing income on age-up; tie gains to economic research.'))

row('B05','Wood logistics','building',
 bn('Lumbermill','lumbermill','Nearby wood drop-off.','Stone Age · build directly',LIVE,REF,'Log piles, chopping block and rough shelter.','Keep the name Lumbermill in every age; vary the artwork. Counts toward Bronze advancement.'),
 bn('Lumbermill','lumbermill','Nearby wood drop-off.','Same building · automatic appearance',LIVE,REF,'Covered timber yard and bronze saws.','Settlement-center economic research improves gathering; no additional research building needed.'),
 bn('Lumbermill','lumbermill','Nearby wood drop-off.','Same building · automatic appearance',UPGRADE,REF,'Framed timber mill with iron tools.','Keep the same placement and drop-off rules.'))

row('B06','Gold logistics','building',
 bn('Mine','mine','Nearby gold drop-off.','Stone Age · build directly',LIVE,REF,'Surface gold workings, baskets and simple tools.','Keep the name Mine in every age. Counts toward Bronze advancement. Gold still exists in Stone Age even if opening military costs become gold-free.'),
 bn('Mine','mine','Gold drop-off for a growing army economy.','Same building · automatic appearance',LIVE,REF,'Shored entrance, bronze tools and ore baskets.','Bronze is an age label, not a new collectible metal.'),
 bn('Mine','mine','Gold drop-off for expensive late-game units.','Same building · automatic appearance',UPGRADE,REF,'Reinforced mine entrance and iron tools.','Keep exactly three resources: food, wood and gold. No iron resource.'))

row('B07','Mounted training','building',None,
 bn('Stable','stable','Trains Mounted Spearmen.','Bronze Age + completed Barracks',LIVE,REF,'Timber paddock, shade canopy and tack rack.','Counts as one distinct Bronze specialist for Iron advancement.'),
 bn('Stable','stable','Trains Heavy Cavalry after its paid line upgrade.','Existing Stable · Iron Age',UPGRADE,REF,'Reinforced stable, armored tack and training enclosure.','One mounted line keeps army composition readable.'))

row('B08','Military research','building',None,
 bn('Blacksmith','blacksmith','Blades I, Bowcraft I, Armor I; unlocks Siege Workshop.','Bronze Age + completed Barracks',LIVE,REF,'Open charcoal forge, clay furnace and bronze tools.','Mandatory for Iron advancement. Proposal: move economy research to the settlement center and give each military family one Bronze level.'),
 bn('Blacksmith','blacksmith','Blades II, Bowcraft II, Armor II, Masonry and Siege Engineering.','Existing Blacksmith · Iron Age',UPGRADE,REF,'Stone furnace, bellows, iron anvil and chimney.','Simplifies the current three-level tech families into one Bronze and one Iron level. Line upgrades stay at the building that trains the unit. Masonry is paid building durability; no automatic health refill.'))

row('B09','Support training','building',None,
 bn('Temple','temple','Trains Healers.','Bronze Age + completed Barracks',LIVE,REF,'Simple columned sanctuary, cloth banners and herb pots.','Counts as a distinct Bronze specialist for Iron advancement.'),
 bn('Temple','temple','Trains Priests after the paid support upgrade.','Existing Temple · Iron Age',UPGRADE,REF,'Stone sanctuary with decorated entrance.','Healing stays automatic and single-target.'))

row('B10','Siege production','building',None,
 bn('Siege Workshop','siege_workshop','Builds Ballistae.','Bronze Age + completed Blacksmith',LIVE,REF,'Open carpentry shelter, timber torsion frames and bolt racks.','Counts as a distinct Bronze specialist for Iron advancement.'),
 bn('Siege Workshop','siege_workshop','Builds Heavy Ballistae after the paid siege-line upgrade.','Existing Workshop · Iron Age',UPGRADE,REF,'Reinforced workshop with torsion frames and iron fittings.','One siege line across Bronze and Iron. Ballista replaces the Ram for structure damage and protected long-range pressure.'))

row('B11','Resource exchange','building',None,
 bn('Market','market','Trades food and wood for gold, and back.','Bronze Age · build directly',LIVE,REF,'Cloth-covered stalls, baskets and scales.','Counts as a distinct Bronze specialist for Iron advancement. Keep current exchange mechanics.'),
 bn('Market','market','Same resource exchange.','Existing Market · Iron Age',UPGRADE,REF,'Larger stone-paved market with permanent stalls.','No trade carts or new economy subsystem in this proposal.'))

row('B12','Static defense','building',None,
 bn('Watchtower','watchtower','Defends a local area; shelters workers.','Bronze Age · build directly',LIVE,REF,'Wooden lookout on rough stone footings, blue banner.','Counts as a distinct Bronze specialist for Iron advancement. Escorted Ballistae must be an effective answer.'),
 bn('Watchtower','watchtower','Improved tower through a paid global defense upgrade.','Watchtower · Iron Age + Tower Reinforcement research at Blacksmith',UPGRADE,REF,'Stone lower structure, protected firing platform and iron braces.','At age-up, the structure gains its new visual style. Keep the name Watchtower. Combat improvement waits for paid Tower Reinforcement research. No new standalone fortress or wall system.'))

# Use the generated age portraits when the complete, validated pack exists.
age_manifest = ROOT/'art/ages/units/manifest.json'
if age_manifest.exists():
    age_units = json.loads(age_manifest.read_text())['units']
    variants = {
        'U01': ('bronze_worker', 'iron_worker'),
        'U02': ('bronze_swordsman', 'iron_swordsman'),
        'U03': ('archer', 'crossbowman'),
        'U04': ('bronze_spearman', 'pikeman'),
        'U06': ('mounted_spearman', 'heavy_cavalry'),
        'U07': ('healer', 'priest'),
        'U09': ('ballista', 'heavy_ballista'),
    }
    for item in rows:
        if item['code'] not in variants:
            continue
        for age, unit_id in enumerate(variants[item['code']], start=1):
            key = 'age_' + unit_id
            asset(key, age_units[unit_id]['icon'])
            node = item['nodes'][age]
            node['image'] = key
            node['art'] = 'Generated Blender artwork; eight-direction animations ready for review'
            # The art description must reflect the actual delivered asset.
            node['extra'] = node['extra'].replace('The portrait is an Archer reference; a crossbow model and firing animation are needed.', 'Crossbow model and firing animation are available in the unit art gallery.')
            node['extra'] = node['extra'].replace('Current concept is a silhouette reference, with Bronze fittings still to design.', 'Bronze model and rolling/firing animations are available in the unit art gallery.')
            node['extra'] = node['extra'].replace('Concept shows the base silhouette; the Heavy variant needs distinct art.', 'A distinct reinforced Heavy model and animations are available in the unit art gallery.')
            node['extra'] = node['extra'].replace('Bronze-specific name/model are proposed.', 'Bronze-specific name is proposed; its matching model and animations are ready for review.')
    wooden = next(item for item in rows if item['code']=='U04')['nodes'][0]
    wooden['art'] = EXACT
    wooden['extra'] = wooden['extra'].replace('The current metal-tipped portrait is a reference only.', 'The approved all-wood spear model already exists; this adds its Stone Age recruitment unlock.')

payload = dict(rows=rows,assets=assets)
template = (HERE/'template.html').read_text(encoding='utf-8')
target = HERE.parent/'advancement-tree.html'
target.write_text(template.replace('__DATA__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
print(f'Built {target}: {len(rows)} lines, {sum(bool(n) for r in rows for n in r["nodes"])} entries, {target.stat().st_size:,} bytes')
