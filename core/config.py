SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# Derived from the screen size by apply_resolution() (§8.2.1 Phase D) —
# the defaults below are the 720p values. The map view spans the screen
# minus the top bar, extending 22 px under the right sidebar so camera
# centering targets the visible area's middle.
MAP_VIEW_WIDTH = 1102
MAP_VIEW_HEIGHT = 620


MAP_WIDTH = 70
MAP_HEIGHT = 70

# Match-setup map sizes (§7.5): word -> (tiles per side, max total players).
# Small maps cap the player count — spawns need room to spread.
MAP_SIZES = {
    "tiny":   (45, 2),
    "small":  (60, 4),
    "medium": (70, 6),
    "large":  (85, 8),
    "huge":   (100, 8),
}

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
AI_ONLY_MODE = False  # Legacy fallback; Game() now defaults to human 1v1.
AI_ONLY_PLAYER_COUNT = 4
# §8.11 fair spectating: fog RULES always apply to AI players (they scout
# like anyone else); this only controls whether the spectator's DISPLAY
# reveals the whole map (True) or watches through player 1's fog (False).
SPECTATOR_REVEALED_DISPLAY = True
SPECTATOR_START_ZOOM = 0.5
NUM_PLAYERS = 4  # Configurable number of players (minimum 2)
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

# §8.7 accessibility: colorblind-safe team palette (Okabe-Ito) — swapped
# in-place over PLAYER_COLORS at startup when the settings toggle is on,
# so every by-value import sees it. Avoids red/green confusion pairs.
PLAYER_COLORS_COLORBLIND = [
    (0, 114, 178),    # Blue (Human player)
    (230, 159, 0),    # Orange
    (86, 180, 233),   # Sky blue
    (240, 228, 66),   # Yellow
    (204, 121, 167),  # Reddish purple
    (0, 158, 115),    # Bluish green
    (213, 94, 0),     # Vermillion
    (153, 153, 153),  # Grey
]

# Pathfinding Configuration
GRID_SIZE = 20  # World units per navigation cell (larger = faster but coarser)
PATHFINDING_MAX_EXPANSIONS = 12000
# Post-JPS budgets: a single request gets a few ms, a frame stays well under a
# 60 FPS tick. Over-budget commands are queued across frames (see
# Pathfinding.process_pending), never silently rejected.
PATHFINDING_MAX_REQUEST_MS = 12
PATHFINDING_FRAME_BUDGET_MS = 10
PATHFINDING_QUEUE_REQUEST_MS = 20   # base ceiling when drained from the queue; escalates per retry
PATHFINDING_QUEUE_REQUEST_MAX_MS = 80  # hard ceiling for the final retries of a long path
PATHFINDING_QUEUE_MAX_PER_FRAME = 8
PATHFINDING_QUEUE_MAX_RETRIES = 6
PATH_CACHE_MAX_ENTRIES = 4096

# Resource Gathering Configuration
GATHERING_RATES = {
    "gold": 1,     # Resources per second
    "stone": 1,
    "wood": 2,
    "food": 3      # Food per second from farms
}

# Gold 10→20 (2026-07-14 aggression re-tune, diagnosed via instrumented
# match): with one rich node per base, a 3-gatherer saturation cap, and a
# carry of 10, effective gold income was ~0.5/s per worker FOR EVERYONE —
# gold armies were tiny regardless of economy size, so the wood-priced ram
# became the de-facto army and the best wood economy (boomer) always won.
WORKER_CAPACITY = {
    "gold": 20,
    "stone": 10,
    "wood": 20
}

# Drop-off delay configuration
DROP_OFF_DELAY = 0.5  # Seconds to wait during resource drop-off

# Farm food generation configuration
FARM_FOOD_AMOUNT = 10  # Amount of food generated per cycle
FARM_FOOD_INTERVAL = 10.0  # Seconds between food generation

RESOURCE_LIMITS = {
    "gold": 1000,
    "stone": 1000,
    "wood": 600
}

# Drop-off buildings for each resource type
DROP_OFF_BUILDINGS = {
    "gold": ["mine", "castle"],
    "stone": ["quarry", "castle"],
    "wood": ["lumbermill", "castle"]
}

# (GATHERING_DISTANCE_MULTIPLIER removed 2026-07-13 — it was never read.
# Gather/drop-off proximity lives in gathering_manager.get_gathering_distance
# and get_drop_off_distance: combined radii + 10% + 5 px.)

# Top Bar UI Configuration
TOP_BAR_HEIGHT = 100
TOP_BAR_START_X = 48   # clears the framed banner's left end-cap
TOP_BAR_SPACING = 185  # keeps the 5th item clear of the right-side Idle badge
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
#
# Deliberately lean: enough to open (a couple of houses/farms, a few extra
# workers, and a down-payment toward the first barracks) but NOT enough to
# build everything at once — the player has to prioritise. For reference:
# worker 25f, house 50w, farm/lumbermill 75w, barracks 150g/100w/50s,
# warrior 100g/25w/50f. Gold (100) is intentionally short of a barracks so
# the first military push requires gathering first.

HUMAN_STARTING_RESOURCES = {
    "food": 200,      # Starting food for human player
    "gold": 100,      # Starting gold for human player
    "stone": 75,      # Starting stone for human player
    "wood": 200       # Starting wood for human player
}

AI_STARTING_RESOURCES = {
    "food": 200,      # Starting food for AI players
    "gold": 100,      # Starting gold for AI players
    "stone": 75,      # Starting stone for AI players
    "wood": 200       # Starting wood for AI players
}

# Victory conditions (§7.5)
ECONOMIC_VICTORY_TARGET = 5000   # cumulative resources gathered
TIMED_VICTORY_MINUTES = 20       # game-time minutes for "timed" mode

# Healer behavior (§9 backlog: "healer doesn't heal")
HEALER_HEAL_AMOUNT = 6      # hp restored per heal tick
HEALER_HEAL_INTERVAL = 1.0  # game-time seconds between heal ticks
HEALER_HEAL_RANGE = 110.0   # world px

# Worker saturation (§8.3, prototyped behind a flag): a resource node only
# supports WORKER_SATURATION_CAP gatherers at full rate; beyond that the
# node's total yield stays capped, so income growth requires expanding to
# fresh nodes instead of stacking one.
WORKER_SATURATION_ENABLED = True
WORKER_SATURATION_CAP = 3

# Every player's base gathering-rate multiplier (per resource). Effective
# income = GATHERING_RATES[type] * this (* upgrades). Shared by
# entities/player.py and the §8.3 balance tooling.
PLAYER_GATHERING_MULTIPLIER = 5.0

# Combat counter model (§8.4, prototyped behind a flag): attackers deal bonus
# damage to targets listed in their strong_against tags, making e.g.
# spearman-vs-cavalry distinctly stronger than archer-vs-cavalry.
COMBAT_BONUS_VS_TAGS_ENABLED = True
COMBAT_BONUS_VS_TAG_MULTIPLIER = 1.5

# §8.4 "position matters" — units standing in forest take reduced damage,
# making wooded ground a defensive lever. Default ON since the 2026-07-13
# same-seed A/B (tools/balance_12_cover_{off,on}.json): identical win rates,
# 0 timeouts, and ram reliance dropped 32%→20% with cover on.
# Override for A/B sim runs with the RTS_TERRAIN_COVER env var (1/0).
import os as _os

COMBAT_TERRAIN_COVER_ENABLED = _os.environ.get("RTS_TERRAIN_COVER", "1").strip().lower() in {"1", "true", "on", "yes"}
COMBAT_FOREST_COVER_MULTIPLIER = 0.85  # damage taken by a unit in forest

# Debug Configuration
DEBUG_PATHFINDING = False  # Enable/disable pathfinding debug output
DEBUG_MOVEMENT = False     # Enable/disable movement debug output
DEBUG_TO_FILE = True       # Enable/disable debug output to file
# Relative when run from source; under %LOCALAPPDATA%\RTS when frozen.
from core.app_paths import user_path as _user_path
DEBUG_FILE_PATH = _user_path("debug.dat")  # Path to debug output file
DEBUG_ENABLED_CATEGORIES = {
    "GENERAL",
    "ERROR",
    "WARNING",
    "BUILDING",
    "CONSTRUCTION",
    "PRODUCTION",
    "WATCHDOG",
    "UI",
}
DEBUG_FLUSH_INTERVAL = 1.0

# Performance instrumentation
# Toggle at runtime with the RTS_PERF_STATS env var (1/true/on) without editing this file.
import os as _os

PERF_STATS_ENABLED = _os.environ.get("RTS_PERF_STATS", "").strip().lower() in {"1", "true", "on", "yes"}
PERF_BENCHMARK_SECONDS = 600

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


def apply_resolution(width, height):
    """Set the screen size and recompute the derived layout constants
    (§8.2.1 Phase D resolution independence). Must run before the game/UI
    modules import these constants by value — main.py calls it at startup
    with the persisted settings resolution."""
    global SCREEN_WIDTH, SCREEN_HEIGHT, MAP_VIEW_WIDTH, MAP_VIEW_HEIGHT
    SCREEN_WIDTH = int(width)
    SCREEN_HEIGHT = int(height)
    MAP_VIEW_WIDTH = SCREEN_WIDTH - (MINIMAP_WIDTH - 22)
    MAP_VIEW_HEIGHT = SCREEN_HEIGHT - TOP_BAR_HEIGHT
