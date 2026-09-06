"""Three ages and paid global unit lines, using stable entity/save IDs."""
import json
from pathlib import Path

STONE_AGE, BRONZE_AGE, IRON_AGE = 1, 2, 3
AGE_NAMES = {1: 'Stone Age', 2: 'Bronze Age', 3: 'Iron Age'}
TIER_ONE_BUILDINGS = frozenset({'barracks','farm','house','lumbermill','mine'})
BRONZE_BUILDINGS = frozenset({'stable','blacksmith','siege_workshop','market','temple','watchtower'})
BRONZE_UNITS = frozenset({'cavalry','ram','healer'})
IRON_SPECIALISTS = BRONZE_BUILDINGS - {'blacksmith'}
LINE_UPGRADES = {'warrior':'swordsman_training','archer':'archer_training','spearman':'bronze_spearman_training'}
UNIT_LINE_TECHS = {
    'warrior': ('swordsman_training','iron_swordsman_training'),
    'archer': ('archer_training','crossbow_training'),
    'spearman': ('bronze_spearman_training','pikeman_training'),
    'cavalry': ('heavy_cavalry_training',), 'healer': ('priest_training',),
    'ram': ('heavy_ballista_training',),
}
ROOT=Path(__file__).resolve().parents[1]
UNIT_ART=json.loads((ROOT/'data/age_units.json').read_text())
BUILDING_ART=json.loads((ROOT/'data/age_buildings.json').read_text())

def current_age(player):
    upgrades=getattr(player,'upgrades',{})
    return 3 if 'iron_age' in upgrades else 2 if 'bronze_age' in upgrades else 1

def age_name(player): return AGE_NAMES[current_age(player)]

def availability(player,name):
    if current_age(player)<2 and name in BRONZE_BUILDINGS | BRONZE_UNITS:
        return False,'Requires Bronze Age'
    return True,'Ready'

def completed_tier_one(buildings,player):
    return sum(1 for b in buildings if b.player is player and b.hp>0 and b.name in TIER_ONE_BUILDINGS)

def iron_requirement(buildings,player):
    owned={b.name for b in buildings if b.player is player and b.hp>0}
    return 'blacksmith' in owned and len(owned & IRON_SPECIALISTS)>=2

def unit_variant(name,player):
    age=current_age(player); upgrades=getattr(player,'upgrades',{})
    if name=='worker': return {2:'bronze_worker',3:'iron_worker'}.get(age)
    for tech,variant in {
        'warrior': [('iron_swordsman_training','iron_swordsman'),('swordsman_training','bronze_swordsman')],
        'archer': [('crossbow_training','crossbowman'),('archer_training','archer')],
        'spearman': [('pikeman_training','pikeman'),('bronze_spearman_training','bronze_spearman')],
        'cavalry': [('heavy_cavalry_training','heavy_cavalry')],
        'healer': [('priest_training','priest')],
        'ram': [('heavy_ballista_training','heavy_ballista')],
    }.get(name,[]):
        if tech in upgrades: return variant
    if age>=2: return {'cavalry':'mounted_spearman','healer':'healer','ram':'ballista'}.get(name)
    return None

def display_name(name,player,fallback=None):
    if name=='castle': return {1:'Town Center',2:'Town Hall',3:'Castle'}[current_age(player)]
    variant=unit_variant(name,player)
    if variant: return UNIT_ART[variant]['name']
    return {'barracks':'Barracks','archer':'Slinger','spearman':'Wooden Spearman','ram':'Ballista'}.get(name,fallback or name.replace('_',' ').title())

def unit_icon_path(name,player):
    variant=unit_variant(name,player)
    return UNIT_ART[variant]['icon'] if variant else None

def building_sprite_path(name,player,fallback):
    # Locked specialist portraits show their first available (Bronze) art.
    # Availability still controls construction; this also covers legacy saves.
    age = max(2 if name in BRONZE_BUILDINGS else 1, current_age(player))
    return BUILDING_ART.get(f'{age}_{name}', {}).get('sprite', fallback)

def apply_unit_appearance(game,unit):
    """Replace visuals only: preserve HP, orders, targets and combat cooldown."""
    variant=unit_variant(unit.name,unit.player)
    manager=getattr(game,'sprite_manager',None)
    if not variant or manager is None or getattr(unit, '_age_art', None) == variant: return
    from systems.animation import Animation
    meta=UNIT_ART[variant]
    sheets=manager.age_unit_sheets(variant,game.players.index(unit.player))
    old=unit.animations
    unit.animations={key:Animation(sheet,meta['frame_size'],meta['frame_size'],1000/meta['fps'],directions=8) for key,sheet in sheets.items()}
    for key,animation in unit.animations.items():
        previous=old.get(key)
        if hasattr(previous,'current_frame_index'):
            animation.current_frame_index=int(previous.current_frame_index/len(previous.frames)*len(animation.frames))%len(animation.frames)
            animation.time_accumulator = previous.time_accumulator
    unit._age_art=variant
    unit._art_render_scale=meta['render_scale']
    unit._art_ground_anchor=tuple(meta['ground_anchor'])
    idle = unit.animations.get('idle')
    unit._art_health_top = idle.frames[0].get_bounding_rect().top / meta['frame_size'] if idle else .2
    unit._legacy_age_art=False

def complete_age_research(game,player,tech):
    if tech['id'] in ('bronze_age','iron_age'): player.tech_level=current_age(player)
    if tech['id'] in ('bronze_age','iron_age') or any(tech['id'] in line for line in UNIT_LINE_TECHS.values()):
        for unit in game.units:
            if unit.player is player: apply_unit_appearance(game,unit)
        # Old tiers are no longer recruitable after a global upgrade. Release
        # their large sheets once no living unit uses them (death fades retain
        # their own frame reference until they expire).
        manager = getattr(game, 'sprite_manager', None)
        cache = getattr(manager, '_age_unit_cache', {})
        player_index = game.players.index(player)
        active = {getattr(unit, '_age_art', None) for unit in game.units
                  if unit.player is player and unit.hp > 0}
        for key in list(cache):
            if key[1] == player_index and key[0] not in active:
                del cache[key]
