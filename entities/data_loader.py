import json
from entities.building import Building
from entities.unit import Unit
from entities.resource import Resource
from core.config import TILE_WIDTH


def load_game_data():
    """Load game data from JSON files and create entity templates"""
    with open('data/buildings.json', 'r') as f:
        buildings_data = json.load(f)
    with open('data/units.json', 'r') as f:
        units_data = json.load(f)
    with open('data/resources.json', 'r') as f:
        resources_data = json.load(f)

    game_data = {
        "buildings": {},
        "units": {},
        "resources": {},
        "costs": {},
    }

    for u in units_data:
        game_data["costs"][u["name"]] = u.get("costs", {})
    for b in buildings_data:
        game_data["costs"][b["name"]] = b.get("costs", {})

    for b in buildings_data:
        # Calculate radius based on size[0] and TILE_WIDTH
        radius = b['size'][0] * TILE_WIDTH / 2
        game_data["buildings"][b['name']] = Building(
            name=b['name'],
            size=b['size'],
            hp=b['hp'],
            sprite=b['sprite'],
            build_duration=b['build_duration'],
            x=0, 
            y=0, 
            radius=radius,
            costs=b.get('costs', {}),
            armor_type=b.get('armor_type', 'fortified'),
            armor_value=b.get('armor_value', 0),
            can_attack=b.get('can_attack', False),
            min_damage=b.get('min_damage', 0),
            max_damage=b.get('max_damage', 0),
            attack_type=b.get('attack_type', 'slash'),
            attack_speed=b.get('attack_speed', 1.0),
            attack_range=b.get('attack_range', 0)
        )

    for u in units_data:
        # Calculate radius based on size[0] and TILE_WIDTH
        # Units should be smaller than tiles - use 1/8 tile width for radius
        # This gives workers/warriors/archers a 16-pixel diameter (8 radius)
        radius = u['size'][0] * TILE_WIDTH / 8
        game_data["units"][u['name']] = Unit(
            x=0, y=0, radius=radius, 
            name=u['name'], 
            size=u['size'], 
            hp=u['hp'], 
            movement_speed=u['movement_speed'], 
            attack=u.get('attack'), 
            animations=u['animations'], 
            can_build=u.get('can_build', False),
            can_attack=u.get('can_attack', False),
            min_damage=u.get('min_damage', 0),
            max_damage=u.get('max_damage', 0),
            attack_type=u.get('attack_type', 'slash'),
            armor_type=u.get('armor_type', 'light'),
            armor_value=u.get('armor_value', 0),
            attack_speed=u.get('attack_speed', 1.0),
            attack_range=u.get('attack_range', 32)
        )

    for r in resources_data:
        # Resources have a fixed size of [1,1] in the current Resource class, so radius will be TILE_WIDTH / 4 (reduced for better pathfinding)
        radius = TILE_WIDTH / 4
        game_data["resources"][r['name']] = Resource(x=0, y=0, radius=radius, **r)

    return game_data