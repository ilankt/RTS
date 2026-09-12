"""Faction identity and exclusive roster rules shared by UI, production and AI."""
FACTIONS = {
    'steppe': {'name': 'Steppe Clans', 'unit': 'horse_archer'},
    'highland': {'name': 'Highland Clans', 'unit': 'axeman'},
}
UNIT_FACTIONS = {meta['unit']: key for key, meta in FACTIONS.items()}


def normalize_faction(value):
    return value if value in FACTIONS else 'steppe'


def faction_allows(player, unit_name):
    required = UNIT_FACTIONS.get(unit_name)
    return required is None or normalize_faction(getattr(player, 'faction', None)) == required


def army_composition(player):
    """Keep personality, allocating part of its shared roster to the signature unit."""
    from systems.ai.utility.personality import COMPOSITION_TARGETS
    from systems.ages import current_age
    base = dict(COMPOSITION_TARGETS.get(getattr(player, 'ai_personality', 'balanced'),
                                        COMPOSITION_TARGETS['balanced']))
    if current_age(player) >= 2:
        unit = FACTIONS[normalize_faction(getattr(player, 'faction', None))]['unit']
        base = {name: share * .75 for name, share in base.items()}
        base[unit] = .25
    return base
