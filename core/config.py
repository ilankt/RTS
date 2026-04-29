SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

MAP_VIEW_WIDTH = 1102
MAP_VIEW_HEIGHT = 620


MAP_WIDTH = 50
MAP_HEIGHT = 50

TILE_WIDTH = 64
TILE_HEIGHT = 56

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

CAMERA_SPEED = 10

MIN_ZOOM = 0.5
MAX_ZOOM = 2.5
ZOOM_STEP = 0.25

# Minimap
MINIMAP_WIDTH = 200
MINIMAP_HEIGHT = 200

# Players
NUM_PLAYERS = 2  # Configurable number of players (minimum 2)
PLAYER_COLORS = [
    (0, 100, 255),    # Blue (Human player)
    (255, 50, 50),    # Red
    (50, 200, 50),    # Green
    (255, 200, 0),    # Yellow
    (150, 50, 200),   # Purple
    (255, 100, 50),   # Orange
    (50, 200, 200),   # Cyan
    (200, 50, 150),   # Pink
]

# Pathfinding Configuration
GRID_SIZE = 20  # World units per navigation cell (larger = faster but coarser)

# Resource Gathering Configuration
GATHERING_RATES = {
    "gold": 1,     # Resources per second
    "stone": 1,
    "wood": 2,
    "food": 3      # Food per second from farms
}

WORKER_CAPACITY = {
    "gold": 10,
    "stone": 10,
    "wood": 20
}

# Drop-off delay configuration
DROP_OFF_DELAY = 0.5  # Seconds to wait during resource drop-off

# Farm food generation configuration
FARM_FOOD_AMOUNT = 10  # Amount of food generated per cycle
FARM_FOOD_INTERVAL = 10.0  # Seconds between food generation

RESOURCE_LIMITS = {
    "gold": 500,
    "stone": 500,
    "wood": 300
}

# Drop-off buildings for each resource type
DROP_OFF_BUILDINGS = {
    "gold": ["mine", "castle"],
    "stone": ["quarry", "castle"],  # Note: quarry not in buildings.json yet
    "wood": ["lumbermill", "castle"]
}

# Gathering distance multiplier (fraction of combined radii)
GATHERING_DISTANCE_MULTIPLIER = 0.5

# Top Bar UI Configuration
TOP_BAR_HEIGHT = 100
TOP_BAR_START_X = 20
TOP_BAR_SPACING = 200
TOP_BAR_ROW_Y = 25
TOP_BAR_ITEMS = ["food", "gold", "stone", "wood", "house"]
# Top bar width will be MAP_VIEW_WIDTH (to not overlap minimap)

# Building Menu Configuration
# Available height: SCREEN_HEIGHT - MINIMAP_HEIGHT = 720 - 200 = 520px
# 7 buildings + 1 cancel + title + padding = 9 elements
# Optimal button height calculation: (520 - 50 title - 30 cancel - 16 padding) / 7 = ~60px
BUILDING_BUTTON_HEIGHT = 60
BUILDING_ICON_SIZE = 48  # Button height - padding (60 - 12 = 48)

# Starting Resources Configuration
# Adjust these values to balance the game difficulty
# Higher values = easier start, lower values = more challenging

HUMAN_STARTING_RESOURCES = {
    "food": 100,        # Starting food for human player
    "gold": 200,        # Starting gold for human player
    "stone": 100,       # Starting stone for human player
    "wood": 200         # Starting wood for human player
}

AI_STARTING_RESOURCES = {
    "food": 100,        # Starting food for AI players
    "gold": 200,        # Starting gold for AI players  
    "stone": 100,       # Starting stone for AI players
    "wood": 200         # Starting wood for AI players
}

# Debug Configuration
DEBUG_PATHFINDING = False  # Enable/disable pathfinding debug output
DEBUG_MOVEMENT = False     # Enable/disable movement debug output
DEBUG_TO_FILE = True       # Enable/disable debug output to file
DEBUG_FILE_PATH = "debug.dat"  # Path to debug output file

# Cursor Configuration
CURSOR_SIZE = 48  # Size in pixels for command mode cursors (configurable)
SMART_CURSORS_ENABLED = True  # Enable automatic cursor switching based on context

# Ghosting duration for stuck units (in milliseconds)
GHOST_DURATION = 2000

# Game speed settings
DEFAULT_GAME_SPEED = 1.0
MIN_GAME_SPEED = 1.0
MAX_GAME_SPEED = 5.0
GAME_SPEED_INCREMENT = 1.0
