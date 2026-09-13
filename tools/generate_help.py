"""Generate the in-game Help page (§ Help).

Reads the game's own data (data/*.json, keybindings, config) and the unit
sprite sheets, and emits ONE self-contained help/index.html:
- every image (unit GIFs, building stills, tech icons) inlined as a data URI
- inline CSS + a tiny search/filter JS
- no external requests, so it opens straight from file:// in any browser

Regenerate whenever unit/building stats or art change:
    python tools/generate_help.py

Uses Pillow for images and imports the game configuration for current rules.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import copy
from pathlib import Path
from urllib.parse import quote

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAME = 192                      # sprite-sheet cell size
CARD_BG = (30, 33, 44)           # unit/building art matte == card colour

# Which building trains each unit (Building.get_production_options, stable
# content). Empty prereq -> the castle.
TRAINED_AT = {
    "worker": "Town Center / Town Hall / Castle", "warrior": "Barracks", "archer": "Barracks",
    "spearman": "Barracks", "cavalry": "Stable", "ram": "Siege Workshop",
    "healer": "Temple", "horse_archer": "Stable (Steppe)", "axeman": "Barracks (Highland)",
}
PRODUCES = {
    "castle": ["Worker"], "barracks": ["Clubman / Swordsman", "Slinger / Archer / Crossbowman", "Spearman / Pikeman", "Axeman (Highland)"],
    "stable": ["Mounted Spearman / Heavy Cavalry", "Horse Archer (Steppe)"], "siege_workshop": ["Ballista / Heavy Ballista"], "temple": ["Healer / Priest"], "blacksmith": [],
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


def _unit_gif(animations, frame_size=FRAME, fps=20):
    """A looping GIF from a unit's idle sheet (falls back to run). None if the
    sheet is missing."""
    path = animations.get("idle") or animations.get("run")
    if not path:
        return None
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return None
    sheet = Image.open(full).convert("RGBA")
    count = max(1, sheet.width // frame_size)
    frames = [sheet.crop((i * frame_size, 0, (i + 1) * frame_size, frame_size)) for i in range(count)]

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
                   duration=round(1000 / fps), loop=0, optimize=True, disposal=1)
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
            .replace(">", "&gt;").replace('"', '&quot;'))


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
    labels = {'ram':'Ballista line','warrior':'Sword infantry','archer':'Ranged infantry','cavalry':'Cavalry','spearman':'Spearman line','horse_archer':'Horse Archer','watchtower':'Watchtower','castle':'Civic buildings','building':'Buildings','worker':'Worker','axeman':'Axeman'}
    chips = "".join(f'<span class="tag {kind}">{_esc(labels.get(x,x.replace("_"," ").title()))}</span>' for x in items)
    return f'<div class="tags"><span class="tag-label">{label}</span>{chips}</div>'


def _stat(label, value):
    return f'<div class="stat"><span>{label}</span><b>{_esc(value)}</b></div>'


def _unit_card(unit):
    gif = _unit_gif(unit.get("animations", {}), unit.get('frame_size', FRAME), unit.get('animation_fps', 20))
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
    stats += _stat("Training", str(unit['build_time']) + ' s')
    trained = TRAINED_AT.get(unit["name"], "Castle")
    search = f'{unit["display_name"]} {unit.get("role","")} {unit.get("progression","")} {trained}'.lower()
    return f'''<article class="card" data-search="{_esc(search)}">
  {art}
  <div class="body">
    <h3>{_esc(unit["display_name"])}</h3>
    <p class="role">{_esc(unit.get("role",""))}</p>
    <p class="progression">{_esc(unit.get('progression', ''))}</p>
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
            + ", ".join(produces) + '</div>') if produces else ""
    req = b.get("requires") or []
    req_txt = f'<span class="from">{_esc(b["availability"])}' + (f' · Needs {_esc(req[0].replace("_"," ").title())}' if req else '') + '</span>'
    stats = _stat("HP", b["hp"]) + _stat("Armor", f'{b.get("armor_type","").title()} {b.get("armor_value",0)}')
    stats += _stat('Build time', str(b['build_duration']) + ' s')
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

PROGRESSIONS = {
    'worker': 'Worker → Bronze Worker → Iron Worker (automatic with age)',
    'warrior': 'Clubman → Bronze Swordsman → Iron Swordsman',
    'archer': 'Slinger → Archer → Crossbowman',
    'spearman': 'Wooden Spearman → Bronze Spearman → Pikeman',
    'cavalry': 'Bronze: Mounted Spearman → Iron: Heavy Cavalry',
    'ram': 'Bronze: Ballista → Iron: Heavy Ballista',
    'healer': 'Bronze: Healer → Iron: Priest',
    'horse_archer': 'Bronze Age · Steppe Clans only',
    'axeman': 'Bronze Age · Highland Clans only',
}

CONTROL_LABELS = [
    ('idle_worker', 'Select / cycle idle Workers'), ('select_all_production', 'Select all military production buildings'),
    ('jump_to_base', 'Jump to your main base'), ('cycle_army', 'Cycle army units (or swap Worker build tabs)'),
    ('cycle_stance', 'Cycle stance'), ('cycle_formation', 'Cycle formation'),
    ('camera_bookmark_set', 'Set camera bookmark'), ('camera_bookmark_jump', 'Cycle camera bookmarks'),
    ('toggle_event_log', 'Open event log'), ('quick_save', 'Quick-save to slot 0'), ('quick_load', 'Load slot 0'),
    ('speed_down', 'Reduce game speed'), ('speed_up', 'Increase game speed'),
]


def _content():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from core import config
    from core.keybindings import DEFAULT_BINDINGS
    from core.version import GAME_VERSION
    from systems.ages import BRONZE_BUILDINGS, BUILDING_ART, UNIT_ART
    from systems.population import POP_BASE, POP_PER_HOUSE

    units = [copy.deepcopy(u) for u in _load_json('units.json') if u.get('buildable', True)]
    for u in units:
        u['progression'] = PROGRESSIONS[u['name']]
        variant = {'cavalry': 'mounted_spearman', 'ram': 'ballista', 'healer': 'healer'}.get(u['name'])
        if variant:
            meta = UNIT_ART[variant]
            u['animations'] = meta['animations']
            u['icon'] = meta['icon']
            u['frame_size'] = meta['frame_size']
            u['animation_fps'] = meta['fps']
    buildings = [copy.deepcopy(b) for b in _load_json('buildings.json') if b.get('buildable', True)]
    for b in buildings:
        age = 2 if b['name'] in BRONZE_BUILDINGS else 1
        b['availability'] = 'Bronze Age' if age == 2 else 'Stone Age'
        b['sprite'] = BUILDING_ART.get(f'{age}_{b["name"]}', {}).get('sprite', b['sprite'])
        if b['name'] == 'castle':
            b['display_name'] = 'Town Center / Town Hall / Castle'
    vals = dict(economic_target=config.ECONOMIC_VICTORY_TARGET, timed_minutes=config.TIMED_VICTORY_MINUTES,
                farm_amount=config.FARM_FOOD_AMOUNT, farm_interval=f'{config.FARM_FOOD_INTERVAL:g}',
                farm_rate=f'{config.FARM_FOOD_AMOUNT / config.FARM_FOOD_INTERVAL:g}',
                wood_rate=f'{config.GATHERING_RATES["wood"] * config.PLAYER_GATHERING_MULTIPLIER:g}',
                gold_rate=f'{config.GATHERING_RATES["gold"] * config.PLAYER_GATHERING_MULTIPLIER:g}',
                node_capacity=config.WORKER_SATURATION_CAP, base_population=POP_BASE, house_population=POP_PER_HOUSE,
                market_lot=config.MARKET_TRADE_LOT, market_buy=config.MARKET_BUY_GOLD, market_sell=config.MARKET_SELL_GOLD,
                heal_amount=config.HEALER_HEAL_AMOUNT, heal_interval=f'{config.HEALER_HEAL_INTERVAL:g}',
                heal_range=f'{config.HEALER_HEAL_RANGE:g}', ballista_hp=next(u['hp'] for u in units if u['name']=='ram'))
    topics = json.loads((Path(ROOT)/'help/topics.json').read_text(encoding='utf-8'))
    for topic in topics:
        for panel in topic['panels']:
            for key in ('paragraphs', 'bullets', 'steps'):
                if key in panel:
                    panel[key] = [p.format(**vals) for p in panel[key]]
    return units, buildings, _load_json('techs.json'), topics, GAME_VERSION, DEFAULT_BINDINGS


def _topic_html(topic):
    panels = []
    for panel in topic['panels']:
        body = ''.join(f'<p>{_esc(p)}</p>' for p in panel.get('paragraphs', []))
        for key, tag in [('bullets', 'ul'), ('steps', 'ol')]:
            if key in panel:
                body += f'<{tag}>' + ''.join(f'<li>{_esc(x)}</li>' for x in panel[key]) + f'</{tag}>'
        panels.append(f'<article class="panel"><h3>{_esc(panel["title"])}</h3>{body}</article>')
    return f'<section id="{topic["id"]}"><h2>{topic["title"]}</h2><p class="lede">{_esc(topic["intro"])}</p><div class="cols">{"".join(panels)}</div></section>'


def _tech_table(techs):
    rows = []
    for tech in techs:
        building = 'Town Center / Town Hall' if tech['building']=='castle' else tech['building'].replace('_',' ').title()
        age = {1:'Stone', 2:'Bronze', 3:'Iron'}.get(tech.get('required_age', 2 if tech['building']=='blacksmith' else 1))
        rows.append(f'<tr><th scope="row">{_esc(tech["display_name"])}</th><td>{_esc(building)}<br><small>{age} Age</small></td><td>{_esc(tech.get("tooltip",""))}</td><td>{_cost_chips(tech.get("costs",{}))}<br>{tech["research_time"]} s</td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>Research</th><th>Where</th><th>Effect / requirement</th><th>Cost / time</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def _art_gallery():
    from systems.ages import BUILDING_ART, UNIT_ART
    pictures = []
    for age, name in [(1,'Town Center'), (2,'Town Hall'), (3,'Castle')]:
        src = _still(BUILDING_ART[f'{age}_castle']['sprite'], (280,240))
        pictures.append(f'<figure><img src="{src}" alt="{name}"><figcaption>{name}<small>{["Stone", "Bronze", "Iron"][age-1]} Age</small></figcaption></figure>')
    civic = '<div class="age-gallery">' + ''.join(pictures) + '</div>'
    pictures = []
    for key, meta in UNIT_ART.items():
        src = _still(meta['icon'], (96,96))
        pictures.append(f'<figure data-search="{_esc(meta["name"].lower())}"><img loading="lazy" src="{src}" alt="{_esc(meta["name"])}"><figcaption>{_esc(meta["name"])}</figcaption></figure>')
    return civic, '<div class="portraits">' + ''.join(pictures) + '</div>'


def build(output_path=None):
    units, buildings, techs, topics, version, bindings = _content()
    sections = {t['id']: _topic_html(t) for t in topics}
    civic, portraits = _art_gallery()
    sections['ages'] = sections['ages'].replace('</section>', civic + _tech_table([t for t in techs if t['building']!='blacksmith']) + '</section>')
    sections['economy'] = sections['economy'].replace('</section>', '<h3>Blacksmith research</h3>' + _tech_table([t for t in techs if t['building']=='blacksmith']) + '</section>')
    rows = ''.join(f'<tr><th scope="row"><kbd>{_esc(bindings[k].upper())}</kbd></th><td>{_esc(v)}</td></tr>' for k,v in CONTROL_LABELS)
    sections['controls'] = sections['controls'].replace('</section>', '<h3>Default hotkeys</h3><div class="table-wrap"><table>' + rows + '</table></div></section>')
    sections['units'] = '<section id="units"><h2>Unit roster</h2><p class="lede">Base values before research. Each player has seven shared unit lines plus their faction\'s exclusive unit. Distances and speed use world units; all durations use game seconds. Military transformations require paid line research.</p><div class="grid">' + ''.join(_unit_card(u) for u in units) + '</div><h3>Age and faction portraits</h3>' + portraits + '</section>'
    sections['buildings'] = '<section id="buildings"><h2>Buildings</h2><p class="lede">These are the earliest available appearances and base values. Buildings already standing change artwork when your civilization advances. Requirements refer to completed buildings.</p><div class="grid">' + ''.join(_building_card(b) for b in buildings) + '</div></section>'
    order = ['basics','ages','factions','units','buildings','economy','combat','controls','troubleshooting']
    labels = ['Start here','Ages','Factions','Units','Buildings','Economy','Combat','Controls','Help & fixes']
    nav = ''.join(f'<a href="#{key}">{label}</a>' for key,label in zip(order,labels))
    html = _PAGE.replace('@@VERSION@@', _esc(version)).replace('@@NAV@@',nav).replace('@@SECTIONS@@',''.join(sections[x] for x in order)).replace('@@CSS@@',_CSS).replace('@@JS@@',_JS)
    output = Path(output_path or Path(ROOT)/'help/index.html')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(line.rstrip() for line in html.splitlines()) + '\n', encoding='utf-8')
    return str(output)


def _cost_text(costs):
    return ', '.join(f'{costs[r]} {r}' for r in ('food','wood','gold') if costs.get(r)) or 'None'


def build_wiki(output_path=None):
    """Repository-readable Markdown; strip .md link suffixes for a native wiki."""
    units, buildings, techs, topics, version, bindings = _content()
    output = Path(output_path or Path(ROOT)/'docs/wiki');output.mkdir(parents=True, exist_ok=True)
    root_url = 'https://github.com/ilankt/RTS'
    raw_url = 'https://raw.githubusercontent.com/ilankt/RTS/main/'
    pages = {}
    for topic in topics:
        parts = [f'# {topic["title"]}', topic['intro']]
        for panel in topic['panels']:
            parts.append('## ' + panel['title'])
            parts.extend(panel.get('paragraphs', []))
            if 'bullets' in panel: parts.append('\n'.join('- '+x for x in panel['bullets']))
            if 'steps' in panel: parts.append('\n'.join(f'{i}. {x}' for i,x in enumerate(panel['steps'],1)))
        pages[topic['page']] = '\n\n'.join(parts)
    def research_md(group):
        result = ['| Research | Building | Cost | Time | Effect / requirement |','|---|---|---|---|---|']
        for t in group:
            name = 'Town Center / Town Hall' if t['building']=='castle' else t['building'].replace('_',' ').title()
            result.append(f'| {t["display_name"]} | {name} | {_cost_text(t.get("costs",{}))} | {t["research_time"]} s | {t.get("tooltip", "")} |')
        return '\n'.join(result)
    pages['Ages-and-Upgrades'] += '\n\n## Research reference\n\n' + research_md([t for t in techs if t['building']!='blacksmith'])
    pages['Economy'] += '\n\n## Blacksmith research\n\n' + research_md([t for t in techs if t['building']=='blacksmith'])
    pages['Controls-and-Saving'] += '\n\n## Default hotkeys\n\n| Key | Action |\n|---|---|\n' + '\n'.join(f'| {bindings[k].upper()} | {v} |' for k,v in CONTROL_LABELS)
    parts = ['# Unit roster', 'Base values before upgrades. Distances and speed use world units; training and combat use game seconds. Each faction has seven shared lines and one exclusive unit.']
    for u in units:
        parts += ['## ' + u['display_name'], f'<img src="{raw_url + quote(u["icon"],safe="/")}" alt="{u["display_name"]}" width="100">', u['role'], f'**Progression:** {u["progression"]}', f'**Trained at:** {TRAINED_AT[u["name"]]} · **Cost:** {_cost_text(u["costs"])} · **Time:** {u["build_time"]} s', f'**Base stats:** {u["hp"]} HP · {u["min_damage"]}–{u["max_damage"]} damage · {u["armor_value"]} {u["armor_type"]} armor · {u["movement_speed"]} movement speed · {u["attack_range"]} attack range']
    pages['Units'] = '\n\n'.join(parts)
    parts = ['# Buildings', 'Base values and earliest available appearance. Civic buildings are named Town Center, Town Hall and Castle in Stone, Bronze and Iron Age.']
    for b in buildings:
        requirement = b['availability'] + ('; ' + ', '.join(x.replace('_',' ').title() for x in b.get('requires',[])) if b.get('requires') else '')
        parts += ['## '+b['display_name'], f'<img src="{raw_url + quote(b["sprite"],safe="/")}" alt="{b["display_name"]}" width="150">', b['role'], f'**Requires:** {requirement} · **Cost:** {_cost_text(b["costs"])} · **Build time:** {b["build_duration"]} s', f'**Base stats:** {b["hp"]} HP · {b.get("armor_value",0)} {b.get("armor_type", "")} armor']
        if PRODUCES.get(b['name']):parts.append('**Trains:** '+', '.join(PRODUCES[b['name']]))
    pages['Buildings'] = '\n\n'.join(parts)
    nav = '\n'.join(f'- [{name.replace("-"," ")}]({name}.md)' for name in ['Getting-Started','Ages-and-Upgrades','Factions','Units','Buildings','Economy','Combat-and-Worker-Safety','Controls-and-Saving','Troubleshooting'])
    pages['Home'] = f'''# RTS player wiki

The player guide for **RTS {version}**: build your economy, advance through three ages, and fight with Steppe or Highland armies.

**[Download the Windows beta]({root_url}/releases/latest)** · **[Watch the gameplay trailer](https://www.youtube.com/watch?v=9bWxDqkOkM8)** · **[Report a bug]({root_url}/issues)**

[![Watch the 42-second gameplay trailer]({raw_url}docs/media/trailer-preview.jpg)](https://www.youtube.com/watch?v=9bWxDqkOkM8)

## Find your way

{nav}

## About this guide

The in-game Help button opens a self-contained, illustrated version of this manual that works offline. These wiki pages and the manual share the same explanations and draw costs, stats and hotkeys from the game data.

The Windows beta includes the current unit animations, both factions and age-specific building graphics. AI-assisted development and artwork are part of the project; see the [credits]({root_url}/blob/main/CREDITS.md).
'''
    for name, body in pages.items():
        if name!='Home': body += f'\n\n---\n\n[Player wiki](Home.md) · [Download]({root_url}/releases/latest) · RTS {version}\n'
        (output/(name+'.md')).write_text(body.rstrip()+'\n',encoding='utf-8')
    (output/'_Sidebar.md').write_text('[RTS player wiki](Home.md)\n\n'+nav+'\n',encoding='utf-8')
    return str(output)


def sync_native_wiki(checkout):
    """Copy generated pages to an existing wiki checkout without committing."""
    import re

    destination = Path(checkout)
    if not (destination / '.git').is_dir():
        raise ValueError('The wiki destination must be an existing Git checkout.')
    for source in (Path(ROOT) / 'docs/wiki').glob('*.md'):
        body = re.sub(r'\]\(([A-Za-z-]+)\.md\)', r'](\1)', source.read_text(encoding='utf-8'))
        (destination / source.name).write_text(body, encoding='utf-8')


_CSS = '''
:root{--bg:#151a18;--panel:#202722;--card:#1e212c;--txt:#eeeade;--mut:#bcc2b5;--gold:#e2c67d;--line:#414a3f;--good:#a1d391;--bad:#efb0a0}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.7 "Segoe UI",sans-serif}
a{color:var(--gold)}a:hover{color:#fff}a:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid var(--gold);outline-offset:4px}
header{border-bottom:1px solid var(--line);background:#111711;padding:48px max(24px,calc((100vw - 1180px)/2)) 36px}
.eyebrow{color:var(--gold);letter-spacing:.16em;text-transform:uppercase;font-size:12px}h1,h2{font-family:Georgia,serif;font-weight:400}h1{font-size:clamp(36px,5vw,62px);line-height:1.1;margin:12px 0 18px}header p{max-width:760px;color:var(--mut)}
.toolbar{position:sticky;top:0;z-index:3;border-bottom:1px solid var(--line);background:#151a18f5;backdrop-filter:blur(8px)}.bar{max-width:1228px;margin:auto;padding:12px 24px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
nav{display:flex;gap:16px;flex-wrap:wrap;flex:1}nav a{font-size:14px;text-decoration:none;white-space:nowrap}#search{background:#101510;color:var(--txt);border:1px solid var(--line);border-radius:4px;padding:9px 12px;width:230px;max-width:100%;font:inherit;font-size:14px}
main{max-width:1228px;margin:auto;padding:38px 24px 70px}section{margin:0 0 64px;scroll-margin-top:150px}h2{font-size:34px;color:var(--gold);margin:0 0 10px;border-bottom:1px solid var(--line);padding-bottom:14px}h3{font-size:19px;line-height:1.4;margin:0 0 12px}section>h3{margin:28px 0 15px}.lede{max-width:86ch;color:var(--mut);margin-bottom:24px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:18px}.panel{background:var(--panel);padding:22px;border-top:2px solid #6e794f}.panel p:last-child{margin-bottom:0}p{margin-top:0}li{margin-bottom:10px}ol,ul{padding-left:22px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,270px),1fr));gap:18px}.card{border:1px solid var(--line);background:var(--card);border-radius:6px;overflow:hidden;min-width:0}.art{display:block;width:100%;height:170px;object-fit:contain;background:var(--card)}.body{padding:18px}.role{color:var(--mut);font-size:14px}.progression{font-size:13px;color:var(--gold);min-height:42px}.meta{display:flex;gap:6px;flex-wrap:wrap;font-size:13px;margin:10px 0}.from{flex-basis:100%;color:var(--mut)}.cost{display:inline-block;padding:2px 6px;border:1px solid #59604f;border-radius:3px;font-size:12px;margin:2px}.food{color:#f3be8b}.gold{color:#f0d989}.wood{color:#b4d799}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:4px 14px}.stat{display:flex;gap:8px;justify-content:space-between;font-size:12px;border-bottom:1px solid #ffffff1a}.stat span{color:var(--mut)}.stat b{text-align:right;overflow-wrap:anywhere}.tags{font-size:12px;display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}.tag-label{color:var(--mut)}.good{color:var(--good)}.bad{color:var(--bad)}.tag{border:1px solid #ffffff22;padding:0 5px}.produces{font-size:13px;color:var(--mut);margin-top:12px}
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:5px;margin-top:20px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:14px;border-bottom:1px solid var(--line);min-width:100px;overflow-wrap:anywhere}thead th{background:#283127;color:var(--gold);font-size:12px}tbody th{font-weight:600;min-width:175px}td small{color:var(--mut)}kbd{font:13px Consolas,monospace;color:var(--gold)}
.age-gallery{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:25px 0}.age-gallery figure{margin:0;background:var(--card);padding:15px;text-align:center}.age-gallery img{width:100%;height:200px;object-fit:contain}.age-gallery small{display:block;color:var(--gold)}.portraits{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:12px}.portraits figure{margin:0;padding:12px;text-align:center;background:var(--card);font-size:12px}.portraits img{width:90px;height:90px;object-fit:contain}.hidden{display:none!important}#search-status{margin:0 0 20px;color:var(--gold)}footer{text-align:center;color:var(--mut);border-top:1px solid var(--line);padding:24px;font-size:13px}.top{float:right;font:14px "Segoe UI",sans-serif}
@media(max-width:700px){header{padding:28px 20px}.bar{padding:10px 20px;gap:10px}.toolbar{position:static}nav{gap:10px 16px}#search{width:100%}main{padding:26px 20px}section{scroll-margin-top:20px}h2{font-size:29px}.age-gallery{gap:6px}.age-gallery figure{padding:5px}.age-gallery img{height:110px}.age-gallery figcaption{font-size:12px}.table-wrap table{min-width:620px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
'''

_JS = '''
const box=document.getElementById('search');
const status=document.getElementById('search-status');
const cards=[...document.querySelectorAll('.card')];
box.addEventListener('input',()=>{
  const query=box.value.trim().toLowerCase();let count=0;
  cards.forEach(card=>{const show=!query||card.dataset.search.includes(query);card.classList.toggle('hidden',!show);if(show)count++;});
  status.textContent=query?count+' matching units and buildings. Clear search to show the full roster.':'';
});
'''

_PAGE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RTS Field Manual · @@VERSION@@</title><style>@@CSS@@</style></head>
<body id="top"><header><div class="eyebrow">RTS GAME · @@VERSION@@ · PLAYER GUIDE</div><h1>The Field Manual</h1><p>From your first Farm to an Iron Age army. Learn the rules, choose your faction, and find the right unit for the fight. Available offline from the game's Help menu.</p></header>
<div class="toolbar"><div class="bar"><nav aria-label="Manual sections">@@NAV@@</nav><label><span class="eyebrow">Find a unit or building</span><br><input id="search" type="search" aria-label="Search units and buildings" placeholder="Try healer, cavalry, temple…"></label></div></div>
<main><p id="search-status" role="status" aria-live="polite"></p>@@SECTIONS@@</main>
<footer>RTS @@VERSION@@ · Costs, stats and default hotkeys generated from game data. <a href="#top">Back to top</a></footer><script>@@JS@@</script></body></html>'''


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Build the offline manual and player wiki.')
    parser.add_argument('--wiki-dir', help='Also copy pages into an existing native GitHub wiki checkout.')
    args = parser.parse_args()
    print('Built manual:', build())
    print('Built wiki:', build_wiki())
    if args.wiki_dir:
        sync_native_wiki(args.wiki_dir)
        print('Prepared native wiki:', args.wiki_dir)
