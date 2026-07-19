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

# --- Terrain categories (§11.4/§11.1) — THE definition of what terrain is.
# Every system asks these sets, never a local literal. Roster simplified
# 2026-07-18 (user decision): 4 grounds + 2 waters. Everything that used to
# be a special tile (forest, mountains, lava) is a PROP placed on these
# grounds — trees are choppable resources with biome sprites, mountains are
# huge impassable objects (§11.2). Adding a terrain type — or changing what
# blocks/spawns/builds — is a one-line change here.
TERRAIN_TYPES = {
    "grass", "desert", "swamp", "dirt", "water_shallow", "water_deep",
}
WATER_TERRAIN = {"water_shallow", "water_deep"}
# Units cannot walk here, buildings cannot stand here (nav bitmap, collision,
# placement, spawn probes, and the watchdog all key off this ONE set).
BLOCKED_TERRAIN = set(WATER_TERRAIN)
BUILDABLE_TERRAIN = TERRAIN_TYPES - BLOCKED_TERRAIN
# Where castles/spawns may generate (map.py start-location search) — no
# castles in the bog.
SPAWN_SAFE_TERRAIN = {"grass", "desert", "dirt"}
# Where each resource type may be placed by world generation. Swamps are
# wood-rich, mineral deposits favor open/dry ground; desert wood uses the
# TREE_DESERT sprite.
RESOURCE_TERRAIN = {
    "gold": {"grass", "desert", "dirt"},
    "wood": {"grass", "swamp", "desert"},
}
# Old-roster names found in pre-simplification saves map onto the new
# roster on load (blocked stays blocked, walkable stays walkable).
LEGACY_TERRAIN = {
    "plains": "grass", "forest": "grass", "cracked_dirt": "dirt",
    "desert_hills": "desert", "stone": "dirt", "rocky": "dirt",
    "dark_stone": "dirt", "lava": "water_deep", "water": "water_shallow",
}

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

CAMERA_SPEED = 10

# Zoom range tightened + higher start (2026-07-18 playtest): 1.0 felt too
# far out as an opener, 0.5 showed half the map, and 2.5 was closer than
# anyone ever plays. DEFAULT_ZOOM is the human match opener; the spectator
# start below stays its own (wider) setting.
MIN_ZOOM = 0.75
MAX_ZOOM = 2.0
ZOOM_STEP = 0.25
DEFAULT_ZOOM = 1.25

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
SPECTATOR_START_ZOOM = 0.75  # never below MIN_ZOOM or zooming can't recover
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
# Time slice per queue-drained attempt. An over-budget search suspends its
# frontier and resumes on the next retry, so a genuinely long path (cross-map
# scout/army order) completes across several slices without any single frame
# ever paying more than one slice for it.
PATHFINDING_QUEUE_REQUEST_MS = 20
PATHFINDING_QUEUE_MAX_PER_FRAME = 8
# Ceiling for ALL queue work in one frame: slices shrink to fit what is left
# of it, and the drain stops once less than the minimum useful slice remains.
# Sized so drain + a worst-case AI tick (~11 ms) still fits a ~23 ms frame.
PATHFINDING_QUEUE_FRAME_MS = 10
PATHFINDING_QUEUE_MIN_SLICE_MS = 5
# Cumulative capacity = inline attempt + retries * slice — covers the worst
# corner-to-corner search on a 70x70 map (~80 ms of JPS). Even past the
# ladder the suspended frontier survives the drop, so a reissued command
# resumes instead of starting over.
PATHFINDING_QUEUE_MAX_RETRIES = 10
PATH_CACHE_MAX_ENTRIES = 4096

# Resource Gathering Configuration
# Stone was removed 2026-07-19 (user decision): three resources carry the
# whole economy. Its costs folded into WOOD (see data/buildings.json), so
# defense and siege still avoid competing with army gold.
GATHERING_RATES = {
    "gold": 1,     # Resources per second
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
    "wood": 20
}

# Drop-off delay configuration
DROP_OFF_DELAY = 0.5  # Seconds to wait during resource drop-off

# Farm food generation configuration
FARM_FOOD_AMOUNT = 10  # Amount of food generated per cycle
FARM_FOOD_INTERVAL = 10.0  # Seconds between food generation

RESOURCE_LIMITS = {
    "gold": 1000,
    "wood": 600
}

# Drop-off buildings for each resource type
DROP_OFF_BUILDINGS = {
    "gold": ["mine", "castle"],
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
TOP_BAR_ITEMS = ["food", "gold", "wood", "house"]
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
# worker 25f, house 50w, farm/lumbermill/mine 75w, barracks 100g/100w,
# warrior 80g/50f. Gold (100) is exactly a barracks and nothing else, so the
# first military push still requires gathering first.
#
# The 75 starting stone was dropped 2026-07-19 with the resource. It bought
# nothing in the opening (the cheapest stone item was a 125-stone tower), so
# it is NOT compensated in wood — starting wood is a balance-pass dial.

HUMAN_STARTING_RESOURCES = {
    "food": 200,      # Starting food for human player
    "gold": 100,      # Starting gold for human player
    "wood": 200       # Starting wood for human player
}

AI_STARTING_RESOURCES = {
    "food": 200,      # Starting food for AI players
    "gold": 100,      # Starting gold for AI players
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

# §8.9 market: all trades route through gold, always at a loss — the spread
# makes the market a strategic release valve, never a money machine
# (a full round trip keeps ~33% of the original resource).
MARKET_TRADE_LOT = 100      # resources moved per trade
MARKET_SELL_GOLD = 50       # gold received for selling one lot
MARKET_BUY_GOLD = 150       # gold paid to buy one lot
MARKET_TRADEABLE = ("wood", "food")

# Combat counter model (§8.4, prototyped behind a flag): attackers deal bonus
# damage to targets listed in their strong_against tags, making e.g.
# spearman-vs-cavalry distinctly stronger than archer-vs-cavalry.
COMBAT_BONUS_VS_TAGS_ENABLED = True
COMBAT_BONUS_VS_TAG_MULTIPLIER = 1.5

# (§8.4 forest cover removed 2026-07-18: the forest tile left the roster —
# forests are tree props now — and the user dropped the cover mechanic
# with it. See PLAN_ARCHIVE §8.4 for the old cover-on evidence.)

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
