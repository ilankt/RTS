from core.config import HUMAN_STARTING_RESOURCES, AI_STARTING_RESOURCES


class Player:
    def __init__(self, name, human, color=(255, 255, 255)):
        self.name = name
        self.human = human
        self.color = color
        
        # Set starting resources based on player type
        if human:
            self.resources = HUMAN_STARTING_RESOURCES.copy()
        else:
            self.resources = AI_STARTING_RESOURCES.copy()
        
        # Player capacities and rates (for future tech tree upgrades)
        self.builder_capacity = 10  # Max number of builders that can work on a building
        self.gathering_rates = {
            "gold": 5.0,      # Multiplier for gathering rates
            "stone": 5.0,
            "wood": 5.0,
            "food": 5.0
        }
        
        # Technology and upgrade tracking (for future implementation)
        self.tech_level = 1
        self.upgrades = {}  # Track completed upgrades
        
        # Unit limits and production rates
        self.population_limit = 20  # Base population limit (increased by houses)
        self.unit_production_speed = 1.0  # Multiplier for unit production
        
        # Combat bonuses (for future implementation)
        self.attack_bonus = 1.0
        self.defense_bonus = 1.0
        
        # Economic bonuses
        self.build_speed_bonus = 1.0  # Multiplier for construction speed
        self.resource_storage_bonus = 1.0  # Multiplier for resource storage capacity
