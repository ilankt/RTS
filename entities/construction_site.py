from entities.game_object import GameObject


class ConstructionSite(GameObject):
    """Construction site entity class"""
    def __init__(self, building_name, building_data, x, y, radius, player=None):
        # Use construction sprite and temporary HP
        super().__init__(f"{building_name}_construction", building_data['size'], 100, 
                         "assets/sprites/Buildings/Construction.png", x, y, radius, player)
        self.building_name = building_name
        self.building_data = building_data
        self.construction_progress = 0
        self.construction_duration = building_data['build_duration']
        self.builder = None  # The unit currently building this
        self.costs = building_data.get('costs', {})  # Resources spent on this construction

        # Store the building type for identification
        self.building_type = building_name

        # Combat: a foundation IS a legal target (razing an enemy's half-built
        # castle is fair play) and the damage math reads these off the target.
        # armor_value was missing entirely, so any attack on a site crashed the
        # match (user-reported). A site is deliberately soft — "light" armor
        # (what the damage math already defaulted to) and no armor value, so
        # anything can raze a foundation quickly.
        self.armor_type = "light"
        self.armor_value = 0