from entities.game_object import GameObject


class ConstructionSite(GameObject):
    """Construction site entity class"""

    # §8.17.2 progress-scaled hp: a fresh foundation is cheap to deny, a
    # nearly-finished castle is a real object. The old flat 100 hp meant a
    # castle site rendered 100/5000 (an empty-looking bar, user-reported as
    # "0 hp") and every foundation cost the same ~100 damage to raze.
    SITE_BASE_HP = 50

    def __init__(self, building_name, building_data, x, y, radius, player=None):
        super().__init__(f"{building_name}_construction", building_data['size'],
                         self.SITE_BASE_HP,
                         "assets/sprites/Buildings/Construction.png", x, y, radius, player)
        self.max_hp = self.SITE_BASE_HP
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

    def scaled_max_hp(self):
        """Max hp at the current progress: SITE_BASE_HP -> the building's
        final hp, linearly."""
        final_hp = self.building_data.get('hp', 100)
        fraction = 0.0
        if self.construction_duration > 0:
            fraction = min(1.0, self.construction_progress / self.construction_duration)
        return int(self.SITE_BASE_HP + (final_hp - self.SITE_BASE_HP) * fraction)

    def apply_progress_hp_growth(self):
        """Called by building_system after each progress tick: the max grows
        with progress and the growth is added to current hp, so damage
        already taken stays absolute (a hurt site doesn't heal by building)."""
        new_max = self.scaled_max_hp()
        if new_max > self.max_hp:
            self.hp += new_max - self.max_hp
            self.max_hp = new_max