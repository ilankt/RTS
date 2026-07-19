"""Generate the in-game Help page (§ Help).

Reads the game's own data (data/*.json, keybindings, config) and the unit
sprite sheets, and emits ONE self-contained help/index.html:
- every image (unit GIFs, building stills, tech icons) inlined as a data URI
- inline CSS + a tiny search/filter JS
- no external requests, so it opens straight from file:// in any browser

Regenerate whenever unit/building stats or art change:
    python tools/generate_help.py

Uses Pillow only (no pygame) so it runs anywhere the sprite PNGs exist.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = 192                      # sprite-sheet cell size
FRAME_MS = 100                   # matches systems/animation.py cadence
CARD_BG = (30, 33, 44)           # unit/building art matte == card colour

# Which building trains each unit (Building.get_production_options, stable
# content). Empty prereq -> the castle.
TRAINED_AT = {
    "worker": "Castle", "warrior": "Barracks", "archer": "Barracks",
    "spearman": "Barracks", "cavalry": "Stable", "ram": "Siege Workshop",
    "healer": "Temple",
}
PRODUCES = {
    "castle": ["worker"], "barracks": ["warrior", "archer", "spearman"],
    "stable": ["cavalry"], "siege_workshop": ["ram"], "blacksmith": [],
}
RES_NAME = {"gold": "Gold", "wood": "Wood", "food": "Food"}


# --------------------------------------------------------------------------- #
# data + image helpers
# --------------------------------------------------------------------------- #
def _load_json(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as handle:
        return json.load(handle)


def _fit(size, box_w, box_h):
    w, h = size
    scale = min(box_w / w, box_h / h)
    return max(1, round(w * scale)), max(1, round(h * scale))


def _matte(frame, size=None):
    """Flatten an RGBA frame onto the card colour (opaque)."""
    if size:
        frame = frame.resize(size, Image.LANCZOS)
    bg = Image.new("RGBA", frame.size, CARD_BG + (255,))
    bg.alpha_composite(frame)
    return bg.convert("RGB")


def _data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def _unit_gif(animations):
    """A looping GIF from a unit's idle sheet (falls back to run). None if the
    sheet is missing."""
    path = animations.get("idle") or animations.get("run")
    if not path:
        return None
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    sheet = Image.open(full).convert("RGBA")
    count = max(1, sheet.width // FRAME)
    frames = [sheet.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME)) for i in range(count)]

    # Stable crop: union of every frame's opaque bbox (no per-frame jitter)
    box = None
    for frame in frames:
        fb = frame.getchannel("A").getbbox()
        if fb is None:
            continue
        box = fb if box is None else (
            min(box[0], fb[0]), min(box[1], fb[1]),
            max(box[2], fb[2]), max(box[3], fb[3]))
    if box is None:
        return None
    cropped = [f.crop(box) for f in frames]
    target = _fit(cropped[0].size, 180, 150)
    matted = [_matte(f, target) for f in cropped]

    buf = io.BytesIO()
    matted[0].save(buf, format="GIF", save_all=True, append_images=matted[1:],
                   duration=FRAME_MS, loop=0, optimize=True, disposal=1)
    return _data_uri(buf.getvalue(), "image/gif")


def _still(sprite_path, box=(190, 160)):
    """A trimmed, matted PNG still (buildings). None if missing."""
    full = os.path.join(ROOT, sprite_path or "")
    if not sprite_path or not os.path.exists(full):
        return None
    img = Image.open(full).convert("RGBA")
    bb = img.getchannel("A").getbbox()
    if bb:
        img = img.crop(bb)
    matted = _matte(img, _fit(img.size, *box))
    buf = io.BytesIO()
    matted.save(buf, format="PNG", optimize=True)
    return _data_uri(buf.getvalue(), "image/png")


def _icon(path, size=(34, 34)):
    full = os.path.join(ROOT, path or "")
    if not path or not os.path.exists(full):
        return None
    img = Image.open(full).convert("RGBA")
    img.thumbnail(size, Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return _data_uri(buf.getvalue(), "image/png")


# --------------------------------------------------------------------------- #
# html fragments
# --------------------------------------------------------------------------- #
def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _cost_chips(costs):
    order = ["food", "gold", "wood"]
    chips = []
    for res in order:
        if costs.get(res):
            chips.append(f'<span class="cost {res}">{costs[res]} {RES_NAME[res]}</span>')
    return "".join(chips) or '<span class="cost free">Free</span>'


def _tag_row(label, items, kind):
    if not items:
        return ""
    chips = "".join(f'<span class="tag {kind}">{_esc(x.title())}</span>' for x in items)
    return f'<div class="tags"><span class="tag-label">{label}</span>{chips}</div>'


def _stat(label, value):
    return f'<div class="stat"><span>{label}</span><b>{_esc(value)}</b></div>'


def _unit_card(unit):
    gif = _unit_gif(unit.get("animations", {}))
    art = (f'<img class="art" loading="lazy" src="{gif}" alt="{_esc(unit["display_name"])}">'
           if gif else '<div class="art noart">no art</div>')
    dmg = f'{unit["min_damage"]}–{unit["max_damage"]}' if unit.get("max_damage") else "—"
    combat = unit.get("can_attack") and unit.get("max_damage")
    stats = _stat("HP", unit["hp"])
    if combat:
        stats += _stat("Damage", dmg)
        stats += _stat("Attack type", unit["attack_type"].title())
        stats += _stat("Range", unit["attack_range"])
    stats += _stat("Armor", f'{unit.get("armor_type","light").title()} {unit.get("armor_value",0)}')
    stats += _stat("Speed", unit["movement_speed"])
    trained = TRAINED_AT.get(unit["name"], "Castle")
    search = f'{unit["display_name"]} {unit.get("role","")}'.lower()
    return f'''<article class="card" data-search="{_esc(search)}">
  {art}
  <div class="body">
    <h3>{_esc(unit["display_name"])}</h3>
    <p class="role">{_esc(unit.get("role",""))}</p>
    <div class="meta"><span class="from">Trained at {_esc(trained)}</span>{_cost_chips(unit.get("costs",{}))}</div>
    <div class="stats">{stats}</div>
    {_tag_row("Strong vs", unit.get("strong_against"), "good")}
    {_tag_row("Weak vs", unit.get("weak_against"), "bad")}
  </div>
</article>'''


def _building_card(b):
    still = _still(b.get("sprite"))
    art = (f'<img class="art" loading="lazy" src="{still}" alt="{_esc(b["display_name"])}">'
           if still else '<div class="art noart">no art</div>')
    produces = PRODUCES.get(b["name"], [])
    prod = (f'<div class="produces">Trains: '
            + ", ".join(u.title() for u in produces) + '</div>') if produces else ""
    req = b.get("requires") or []
    req_txt = f'<span class="from">Needs {_esc(req[0].title())}</span>' if req else ""
    stats = _stat("HP", b["hp"]) + _stat("Armor", f'{b.get("armor_type","").title()} {b.get("armor_value",0)}')
    if b.get("can_attack"):
        stats += _stat("Damage", f'{b["min_damage"]}–{b["max_damage"]}')
        stats += _stat("Range", b.get("attack_range", 0))
    search = f'{b["display_name"]} {b.get("role","")}'.lower()
    return f'''<article class="card" data-search="{_esc(search)}">
  {art}
  <div class="body">
    <h3>{_esc(b["display_name"])}</h3>
    <p class="role">{_esc(b.get("role",""))}</p>
    <div class="meta">{req_txt}{_cost_chips(b.get("costs",{}))}</div>
    <div class="stats">{stats}</div>
    {prod}
  </div>
</article>'''


def _tech_row(tech):
    icon = _icon(tech.get("icon"))
    img = f'<img src="{icon}" alt="">' if icon else '<span class="ph"></span>'
    return f'''<tr>
  <td class="tech-name">{img}<b>{_esc(tech["display_name"])}</b></td>
  <td>{_esc(tech.get("tooltip",""))}</td>
  <td class="nowrap">{_cost_chips(tech.get("costs",{}))}</td>
</tr>'''


# --------------------------------------------------------------------------- #
# page
# --------------------------------------------------------------------------- #
def build(output_path=None):
    units = [u for u in _load_json("units.json")
             if u.get("buildable", True) and u.get("name") != "healer"]
    buildings = [b for b in _load_json("buildings.json")
                 if b.get("buildable", True)
                 and b["name"] not in ("wall", "wooden_wall", "gate")]
    techs = _load_json("techs.json")

    sys.path.insert(0, ROOT)
    from core import config
    from core.keybindings import DEFAULT_BINDINGS
    from core.version import GAME_VERSION

    unit_cards = "\n".join(_unit_card(u) for u in units)
    building_cards = "\n".join(_building_card(b) for b in buildings)
    tech_rows = "\n".join(_tech_row(t) for t in techs)

    fountain = _still("assets/sprites/Buildings/Fountain.png", box=(150, 120))
    fountain_img = f'<img src="{fountain}" alt="Healing Fountain">' if fountain else ""
    fountain_block = f'''<div class="panel fountain-note">
      {fountain_img}
      <div><h3>The Healing Fountain</h3>
      <p>A neutral fountain stands near the center of every map — you don't
      build it, and no one owns it. Any unit standing close slowly regains
      health, so both armies want it and the middle becomes contested ground.
      It's the ideal spot to regroup and mend a battered army mid-fight.</p></div>
    </div>'''

    # Economy numbers, pulled live so they never drift from balance
    mult = getattr(config, "PLAYER_GATHERING_MULTIPLIER", 5.0)
    rates = config.GATHERING_RATES
    econ_rates = "".join(
        f'<div class="stat"><span>{res.title()}</span>'
        f'<b>{rates[res]*mult:.0f}/s per worker</b></div>'
        for res in ("gold", "wood"))
    market = (f'Sell {config.MARKET_TRADE_LOT} → {config.MARKET_SELL_GOLD} gold '
              f'&nbsp;·&nbsp; Buy {config.MARKET_TRADE_LOT} ← {config.MARKET_BUY_GOLD} gold')

    # Controls — a curated subset of the rebindable actions
    control_labels = [
        ("idle_worker", "Select / cycle idle workers"),
        ("select_all_production", "Select all military buildings"),
        ("jump_to_base", "Jump camera to your castle"),
        ("cycle_army", "Select + center next army unit"),
        ("cycle_stance", "Cycle unit stance"),
        ("cycle_formation", "Cycle group formation"),
        ("toggle_gates", "Open / close selected gate"),
        ("camera_bookmark_set", "Save camera bookmark"),
        ("camera_bookmark_jump", "Jump between bookmarks"),
        ("toggle_event_log", "Toggle the event log"),
        ("quick_save", "Quick save"),
        ("quick_load", "Quick load"),
        ("speed_down", "Slow the game down"),
        ("speed_up", "Speed the game up"),
        ("toggle_fog", "Toggle fog of war"),
    ]
    control_rows = "".join(
        f'<tr><td><kbd>{_esc(DEFAULT_BINDINGS[a].upper())}</kbd></td><td>{_esc(label)}</td></tr>'
        for a, label in control_labels if a in DEFAULT_BINDINGS)
    control_rows += ('<tr><td><kbd>Right-click</kbd></td><td>Move · gather · attack · '
                     'build · garrison (context-aware)</td></tr>'
                     '<tr><td><kbd>Shift + Right-click</kbd></td><td>Queue commands</td></tr>'
                     '<tr><td><kbd>1–9</kbd></td><td>Assign / recall control groups</td></tr>'
                     '<tr><td><kbd>Esc</kbd></td><td>Pause menu</td></tr>')

    html = _PAGE.format(
        version=_esc(GAME_VERSION),
        unit_cards=unit_cards,
        building_cards=building_cards,
        tech_rows=tech_rows,
        econ_rates=econ_rates,
        market=market,
        control_rows=control_rows,
        fountain_block=fountain_block,
        css=_CSS,
        js=_JS,
    )

    if output_path is None:
        output_path = os.path.join(ROOT, "help", "index.html")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    return output_path


_CSS = """
:root{--bg:#14141e;--panel:#1e2230;--card:#1e212c;--line:#2c3040;
--gold:#c8b464;--txt:#d9dbe3;--mut:#8b90a2;--good:#6ac06a;--bad:#d97a7a;
--gold-r:#d4b43c;--wood-r:#5cb85c;--food-r:#e0863c;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:15px/1.55 system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
a{color:var(--gold);text-decoration:none}
header{position:sticky;top:0;z-index:10;background:rgba(20,20,30,.96);
border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.bar{max-width:1180px;margin:0 auto;padding:14px 22px;display:flex;
align-items:center;gap:20px;flex-wrap:wrap}
.bar h1{margin:0;font-size:22px;color:var(--gold);letter-spacing:.5px}
.bar h1 span{color:var(--mut);font-size:13px;font-weight:400}
nav{display:flex;gap:16px;flex-wrap:wrap;margin-left:auto}
nav a{color:var(--txt);font-size:14px;padding:4px 2px;border-bottom:2px solid transparent}
nav a:hover{color:var(--gold);border-color:var(--gold)}
#search{background:var(--card);border:1px solid var(--line);color:var(--txt);
border-radius:8px;padding:7px 12px;font-size:14px;min-width:180px}
main{max-width:1180px;margin:0 auto;padding:26px 22px 80px}
section{margin:0 0 46px;scroll-margin-top:74px}
h2{color:var(--gold);font-size:24px;margin:0 0 6px;
border-bottom:1px solid var(--line);padding-bottom:8px}
.lede{color:var(--mut);margin:0 0 18px;max-width:74ch}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
overflow:hidden;display:flex;flex-direction:column}
.card .art{width:100%;height:150px;object-fit:contain;background:var(--card);display:block}
.card .noart{display:flex;align-items:center;justify-content:center;color:var(--mut);font-size:13px}
.card .body{padding:12px 14px 14px}
.card h3{margin:0 0 2px;font-size:18px}
.role{margin:0 0 10px;color:var(--mut);font-size:13px;min-height:34px}
.meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.from{font-size:12px;color:var(--mut);margin-right:auto}
.cost{font-size:13px;font-weight:600;background:#0006;border:1px solid var(--line);
border-radius:6px;padding:2px 7px}
.cost em{font-style:normal;font-size:11px;opacity:.8;margin-left:2px}
.cost.gold{color:var(--gold-r)}.cost.wood{color:var(--wood-r)}
.cost.food{color:var(--food-r)}.cost.free{color:var(--mut)}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:2px 14px;margin-bottom:8px}
.stat{display:flex;justify-content:space-between;font-size:13px;
border-bottom:1px dotted #2c3040;padding:3px 0}
.stat span{color:var(--mut)}
.tags{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-top:8px}
.tag-label{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;margin-right:2px}
.tag{font-size:12px;border-radius:5px;padding:1px 7px}
.tag.good{background:#1e3320;color:var(--good);border:1px solid #2f5030}
.tag.bad{background:#331e1e;color:var(--bad);border:1px solid #503030}
.produces{font-size:13px;color:var(--mut);margin-top:6px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin-bottom:16px}
.panel h3{margin:0 0 10px;color:var(--gold);font-size:17px}
.cols{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}
.fountain-note{display:flex;gap:18px;align-items:center;margin-top:16px}
.fountain-note img{width:140px;height:118px;object-fit:contain;flex:none;
border-radius:8px;background:var(--card)}
.fountain-note h3{margin:0 0 6px}
.econ{display:grid;grid-template-columns:1fr 1fr;gap:2px 18px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.tech-name{display:flex;align-items:center;gap:9px;white-space:nowrap}
.tech-name img{width:28px;height:28px;border-radius:5px}
.tech-name .ph{width:28px;height:28px;border-radius:5px;background:#0004;display:inline-block}
.nowrap{white-space:nowrap}
kbd{background:#0006;border:1px solid var(--line);border-bottom-width:2px;border-radius:5px;
padding:2px 8px;font:13px ui-monospace,Consolas,monospace;color:var(--gold)}
ul.tips{margin:0;padding-left:20px}ul.tips li{margin:6px 0}
.hidden{display:none!important}
footer{color:var(--mut);font-size:12px;text-align:center;padding:24px}
"""

_JS = """
const box=document.getElementById('search');
box.addEventListener('input',()=>{
  const q=box.value.trim().toLowerCase();
  document.querySelectorAll('.card').forEach(c=>{
    c.classList.toggle('hidden', q && !c.dataset.search.includes(q));
  });
});
"""

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RTS Game — Help</title><style>{css}</style></head>
<body>
<header><div class="bar">
  <h1>RTS Game <span>Field Manual · v{version}</span></h1>
  <nav>
    <a href="#basics">Basics</a>
    <a href="#units">Units</a>
    <a href="#buildings">Buildings</a>
    <a href="#economy">Economy &amp; Tech</a>
    <a href="#controls">Controls</a>
  </nav>
  <input id="search" type="search" placeholder="Search units &amp; buildings…">
</div></header>
<main>

<section id="basics">
  <h2>Getting Started</h2>
  <p class="lede">Command a medieval army: gather resources, raise a base, train
  troops, and destroy the enemy castle before they destroy yours.</p>
  <div class="cols">
    <div class="panel"><h3>The goal</h3>
      <p>Win by <b>razing every enemy castle</b> (Annihilation). Some matches
      instead use <b>Economic</b> victory (first to a resource total) or
      <b>Timed</b> victory (highest score when the clock runs out). Lose your
      last castle with no workers or castle-in-progress and you're out.</p></div>
    <div class="panel"><h3>The loop</h3>
      <p><b>Gather → Build → Train → Fight.</b> Right-click resources with
      workers to gather, build production from the sidebar, train an army, then
      right-click an enemy to attack. Scout first — you can only see what your
      units reveal.</p></div>
    <div class="panel"><h3>First five minutes</h3>
      <p>Send every starting worker to gather. Build a <b>House</b> before you
      hit the population cap and a <b>Barracks</b> to unlock troops. Keep workers
      on gold — it pays for almost every soldier. Expand to a second resource
      cluster once your first is crowded (3 workers per node is the sweet spot).</p></div>
  </div>
  {fountain_block}
</section>

<section id="units">
  <h2>Units</h2>
  <p class="lede">Every unit counters something and folds to something else —
  the tags on each card tell you what. Damage also depends on armor type, so
  counters are strong but not absolute.</p>
  <div class="grid">{unit_cards}</div>
</section>

<section id="buildings">
  <h2>Buildings</h2>
  <p class="lede">Your base. Production buildings train units; the blacksmith
  researches upgrades; watchtowers defend; the market trades resources.</p>
  <div class="grid">{building_cards}</div>
</section>

<section id="economy">
  <h2>Economy &amp; Tech</h2>
  <div class="cols">
    <div class="panel"><h3>The three resources</h3>
      <p><b>Gold</b> — the army currency: nearly every soldier costs it. Scarce
      and contested.<br>
      <b>Wood</b> — everything you build: structures, defense and siege.
      Renewable and plentiful.<br>
      <b>Food</b> — labor: every unit needs it; farms produce it over time.</p></div>
    <div class="panel"><h3>Gathering</h3>
      <div class="econ">{econ_rates}</div>
      <p style="margin:10px 0 0;color:var(--mut)">A node supports 3 workers at
      full rate — pile on more and each gathers less, so spread out and expand.</p></div>
    <div class="panel"><h3>The Market</h3>
      <p>Trade surplus for what you're short on — always at a loss, so it's a
      release valve, not a money press.</p>
      <p style="color:var(--gold)">{market}</p></div>
  </div>
  <div class="panel"><h3>Blacksmith upgrades</h3>
    <table><thead><tr><th>Upgrade</th><th>Effect</th><th>Cost</th></tr></thead>
    <tbody>{tech_rows}</tbody></table></div>
</section>

<section id="controls">
  <h2>Controls &amp; Strategy</h2>
  <div class="cols">
    <div class="panel"><h3>Hotkeys</h3>
      <table><tbody>{control_rows}</tbody></table>
      <p style="color:var(--mut);margin:10px 0 0;font-size:13px">All keys are
      rebindable in <code>keybindings.json</code>.</p></div>
    <div class="panel"><h3>Stances</h3>
      <p><b>Aggressive</b> chases nearby enemies. <b>Defensive</b> fights back but
      stays near home. <b>Stand Ground</b> holds position and only hits what walks
      into range. <b>No Attack</b> never fights — good for scouts and fleeing
      workers. Cycle with the stance key.</p></div>
    <div class="panel"><h3>Tactics</h3>
      <ul class="tips">
        <li><b>Counters:</b> spearmen gut cavalry, cavalry run down archers,
        archers shred infantry, rams smash buildings (and die to any soldier).</li>
        <li><b>Towers out-range archers</b> — don't try to plink one down; bring
        a ram or overwhelm it.</li>
        <li><b>Raid the undefended:</b> forward mines and lumber camps are soft.
        Hit them before committing to the castle.</li>
        <li><b>Garrison</b> workers and troops in the castle or a tower to shelter
        them — each one inside a tower makes it fire faster.</li>
        <li><b>Hold the fountain:</b> the neutral healing fountain mends any unit
        nearby — great to regroup a wounded army on.</li>
      </ul></div>
  </div>
</section>

</main>
<footer>Generated from the game's own data — stats reflect the current
build. · RTS Game v{version}</footer>
<script>{js}</script>
</body></html>"""


if __name__ == "__main__":
    path = build()
    size_kb = os.path.getsize(path) // 1024
    print(f"wrote {path} ({size_kb} KB)")
