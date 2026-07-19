# Visual Asset Style Guide For RTS

The project's art-direction reference for generating new game art (AI image
generation or hand-made) so it matches what already ships.

> **History (2026-07-17):** this file used to also carry ~32 numbered
> "generate this missing asset" prompts. Every one of them is now done — the
> unit icons, sprite sheets, building sprites, tech icons, and the HUD cost
> glyphs (`assets/ui/Glyphs/`) all exist and are wired in — so the prompts were
> removed as stale. What remains is the reusable style guide the rest of the
> plan points at (MASTER_PLAN §11's art direction, the wall/gate re-enable, and
> Track D's tileset/props/tree work). Asset geometry is pinned by
> `tools/verify_visual_assets.py`; the HUD glyphs are gated by
> `tools/preview_cost_glyphs.py`.

## Existing Style Reference

Use the current game assets as the style anchor:

- Buildings: `assets/sprites/Buildings/Barracks.png`, `Castle.png`, `Lumbermill.png`, `Watchtower.png`
- Unit sheets: `assets/sprites/Units/Warrior/Warrior_Idle.png`, `Warrior_Run.png`, `Warrior_Attack.png`, `assets/sprites/Units/Archer/Archer_Shoot.png`
- UI icons: `assets/ui/Units/warrior_icon.png`, `archer_icon.png`, `worker_icon.png`, `assets/ui/build_mil_icon.png`
- HUD cost glyphs: `assets/ui/Glyphs/gold_glyph.png`, `wood_glyph.png`, `food_glyph.png`, `time_glyph.png`
  *(`stone_glyph.png` is no longer used — the stone resource was removed 2026-07-19.)*

## Shared Style Guide

Use this style guide for every asset unless a specific need overrides it.

### Building Sprites

- Output: transparent PNG.
- Size: 1000x1000 px, unless stated otherwise.
- Camera: isometric 3/4 top-down game asset, object centered, camera angle matching the existing barracks and lumbermill.
- Composition: full object visible, no cropping, 8-12 percent transparent padding around the object.
- Style: stylized medieval RTS game art, hand-painted, crisp ink-like dark outlines, warm wood tones, stone block bases, clean readable silhouette.
- Lighting: soft light from upper-left, gentle shading, ambient occlusion under roof eaves and props.
- Ground: include a small irregular dirt/moss footprint shadow like existing buildings, but keep the background transparent.
- Team color: if flags, banners, or cloth are included, make them plain white so the game can tint or visually distinguish them later.
- Avoid: photorealism, modern materials, text labels, logos, watermarks, UI frames, perspective distortion, extreme detail that becomes unreadable when scaled down.

### Unit Sprite Sheets

- Output: transparent PNG sprite sheet, one horizontal row only.
- Frame size: exactly 192x192 px per frame.
- Frame layout: evenly spaced frames with no gutter, no margins, no grid lines.
- Camera: small RTS unit view, slightly top-down 3/4, facing right/front-right, matching the warrior and archer sheets.
- Scale: unit should fit inside each 192x192 frame with 10-20 px padding; feet/wheels must stay aligned on the same baseline across all frames.
- Style: stylized compact medieval fantasy, chunky readable silhouette, dark navy/black outlines, simplified shapes, limited palette.
- Animation: each frame should show a clear progression but preserve the same character design, size, facing, and anchor point.
- Avoid: changing camera angle between frames, different character proportions per frame, background, shadows that extend outside the frame, text, UI border, motion blur, cropped weapon tips.
- Pipeline: generated sheets are **not** drop-in — run `tools/normalize_team_color.py` then `tools/reanchor_sprite_frames.py` (team-color keying is a ±25 match on two exact shades). See MEMORY / CLAUDE.md.

### UI Icons (framed plates)

For the framed icons that sit on the dark top banner and in the unit panel.

- Output: PNG.
- Size: 1024x1024 px.
- Background: off-white or very light warm background matching existing unit icons.
- Border: thin gold square border near the edge, matching `assets/ui/Units/warrior_icon.png`.
- Style: clean high-resolution icon, bold dark navy outlines, simple readable shape, polished but slightly playful RTS UI look.
- Composition: centered object or character, fills 70-85 percent of the icon area, no cropping.
- Avoid: text, letters, numbers, watermark, busy background, realistic render, black background.

### Tech Icons

- Output: PNG.
- Size: 1024x1024 px.
- Background: off-white or very light warm background.
- Border: thin gold square border near the edge, consistent with the existing UI icon set.
- Style: bold symbolic icon, dark navy or black silhouette with 1-3 accent colors, readable at 32x32.
- Composition: one central symbol, no text.

### HUD Cost Glyphs

**This section deliberately overrides the UI Icons rules above — do not apply them here.**
A UI icon is a framed plate that owns its own background. A glyph is a bare cut-out
blitted straight onto whatever is behind it, at roughly **14x14 px**. The shipped set in
`assets/ui/Glyphs/` follows every rule below; a replacement or a new glyph (e.g. a housing
glyph) must too. Verify with `python tools/preview_cost_glyphs.py`, which draws each glyph
at 14 px on the real tile surfaces and fails on a painted background or a too-dark fill.
(If a generator returns an opaque canvas with a flat backdrop — common — fix it up with
`tools/cutout_glyph_background.py`, which flood-fills the background off from the border and
so cannot punch through a subject enclosed by its own outline.)

- Output: transparent PNG with **true alpha**, not a keyed or matted background.
- Size: 1024x1024 px.
- Background: **fully transparent, alpha 0.** No plate, no rounded panel, no border, no
  off-white fill, no drop shadow. Anything baked behind the subject becomes an opaque
  square in-game.
- Composition: **exactly ONE object**, centered, filling ~90 percent of the canvas with a
  ~5 percent transparent margin. No piles, stacks, clusters, or paired props — at 14 px a
  cluster averages into a blob.
- Outline: uniform, very dark, **3-4 percent of canvas width (roughly 30-40 px at 1024)**.
  A 2 px outline at 1024 is invisible at 14 px; a 6 percent one eats the tiny glyph's
  bright core. The outline is for house-style consistency and internal definition — it is
  **not** what separates the glyph from the background.
- **Every surface a glyph touches is dark.** This drives the palette and is easy to get
  wrong: the command card's tile fills are dark olive `(42,52,42)` when affordable,
  `(45,42,32)` locked, `(50,38,38)` unaffordable, `(67,77,67)` hovered, and the tooltip is
  near-black `(10,10,14)`. So a **bright, high-value fill** is what makes a glyph readable —
  a dark outline on a dark tile just merges with it.
- Fill values (measured against the real tile colors; WCAG contrast, ≥3.0 required on the
  worst surface, always the affordable-tile olive):

  | Glyph | Fill | Worst-surface contrast |
  |---|---|---|
  | gold | bright yellow-gold `(245,200,60)` | 8.14 |
  | wood | **light** warm brown `(196,142,92)` | 4.54 |
  | food | **bright** warm red `(230,125,95)` | 4.60 |
  | time | pale gray-blue `(170,196,214)` | 7.13 |

  The two traps: a natural mid-brown log `(120,80,50)` scores **1.84** and a natural
  roast-red `(120,45,40)` scores **1.36** — both invisible on the tile. Wood and food must
  be pushed lighter than the subject "wants" to be.
- Detail budget: **at most 2 internal details**, two-step shading. No fine engraving, no
  thin lines, no gradients, no texture noise.
- Readability bar: **must be identifiable at 14x14 px.** Judge it by silhouette plus one
  dominant hue — that is all that survives. If it needs its details to read, it fails.
- Hue separation (**mandatory** — these glyphs sit side by side on one cost row): gold,
  wood and food are all warm and blur into each other at 14 px. Keep gold clearly yellow,
  wood clearly tan, food clearly red.
- Avoid: text, numbers, watermark, background scenery, photorealism, and every framed-icon
  convention from the UI Icons section.

## Terrain & World Props (§11.1 / §11.2) — FULL PROMPTS

Two different pipelines, chosen around what image generators actually get
wrong:

- **Ground tiles**: generators cannot draw pixel-exact interlocking hexagons
  and cannot do transparency. So we never ask: each terrain is generated as a
  **flat seamless SQUARE texture** filling the whole canvas (no background at
  all), and `tools/build_tileset_from_textures.py` cuts the exact hex masks
  AND mints 4 variants per terrain from different crop offsets of the same
  image. Save each result as
  `assets/tiles/source_textures/<name>.png`, then run the tool.
- **Props** (mountain, trees): single object on a **solid pure magenta
  (#FF00FF) background** as the transparency key — magenta never occurs in
  rock/wood/foliage art, and `tools/cutout_glyph_background.py` flood-fills
  the flat backdrop off from the border into true alpha without punching
  holes in the subject.

**No transition art is needed, ever**: biome borders (grass-desert,
land-water, all 6 hex directions) are blended IN-GAME by feathering the
actual tile textures across shared edges (`Map.build_transitions`), so the
transitions always match whatever sheet is installed. Generate only the six
flat textures below.

### Ground texture prompts — one per file, copy-paste verbatim

Shared tail — append to every ground prompt below:

> hand-painted stylized medieval fantasy RTS terrain, soft painterly
> brushwork, mid-saturation natural colors, even diffuse overhead lighting
> with NO directional shadows, top-down view straight from above, perfectly
> seamless tileable texture that repeats on all four edges with no visible
> seam, uniform detail density with no focal point, no vignette, no border,
> no objects, no creatures, no buildings, no text, no watermark, square
> image, 1024x1024

**grass.png**
> Lush green grassland meadow ground texture: short dense grass in soft
> tonal patches of fresh green and deeper olive, a few tiny lighter tufts
> and sparse minuscule white-yellow wildflower dots, gentle organic
> variation, nothing taller than grass, +shared tail

**desert.png**
> Warm sandy desert ground texture: fine golden-beige sand with soft wind
> ripples, subtle darker undulations, a few tiny scattered pebbles and
> faint dry cracks, sun-warmed tones from pale cream to amber, +shared tail

**swamp.png**
> Murky swamp bog ground texture: wet brown-green marsh mud interlaced with
> patches of dark stagnant water, thin films of algae, small moss clumps and
> sparse short reed stubble, oily green-brown palette with faint teal water
> glints, +shared tail

**dirt.png**
> Bare packed earth ground texture: dry brown soil with subtle footworn
> compression marks, small embedded pebbles, faint patches of lighter dust
> and darker damp earth, neutral warm browns, +shared tail

**water_shallow.png** *(revised 2026-07-18: tuned as a PAIR with deep —
the old versions were too far apart and the coast read as a cliff)*
> Sunlit shallow coastal water texture: clear bright turquoise-cyan water
> with soft ripple highlights, the sandy bottom faintly visible through the
> surface as a warm golden tint, delicate light caustic patterns, fresh and
> readable, the LIGHTEST water in the set, +shared tail

**water_deep.png** *(revised: only 2-3 shades darker than shallow — the
in-engine preview `transitions_v2_coast_lighter_deep.png` is the target)*
> Open sea water texture: medium-deep vivid sea-blue water, only two or
> three shades darker than bright turquoise shallows, clearly blue and
> alive, never black, never near-black navy, never murky, calm surface with
> sparse subtle wave crests and a few faint foam flecks, no visible bottom,
> +shared tail

Processing:

    # drop the six PNGs into assets/tiles/source_textures/  then:
    python tools/build_tileset_from_textures.py
    python tools/verify_visual_assets.py

Missing textures keep their current tile, so the set can land one biome at
a time. Judge in-game (tiles read at 64x56): detail that vanishes at that
scale is wasted; detail that strobes when tiled is worse.

### Mountain prop — assets/sprites/Props/Mountain.png

Drop-in: the renderer loads this path automatically over the procedural
placeholder. In game it spans 3-5 tiles — it must read as a LANDMARK.

**Mountain.png** (generate at 1024x1024)
> A single massive rocky mountain massif with three jagged stone peaks of
> different heights, light snow caps on the two tallest, stylized medieval
> fantasy RTS game art, hand-painted with crisp dark ink-like outlines,
> isometric three-quarter top-down view matching a strategy game building
> sprite, cool stone gray cliffs with warm earthy brown scree at the base,
> soft light from the upper left, gentle ambient occlusion in the crevices,
> a small irregular rocky footprint skirt at the bottom, the mountain
> centered and filling about 85 percent of the frame, THE ENTIRE BACKGROUND
> IS ONE SOLID FLAT PURE MAGENTA COLOR hex FF00FF with no gradient, no
> shadow cast onto the background, no vignette, no horizon, no sky, no
> clouds, no text, no watermark, square image, 1024x1024

For VARIANTS (ridges stop reading as clones): re-run the same prompt changing ONLY the peak clause - 'two jagged stone peaks' / 'one single dominant jagged peak' / 'four stepped jagged peaks of ascending height'. Save as Mountain_2.png, Mountain_3.png, ... in assets/sprites/Props/ - the renderer auto-loads any count and each placed mountain picks one deterministically.

Processing:

    python tools/cutout_glyph_background.py --out-dir assets/sprites/Props <generated>.png
    # rename/move the result to assets/sprites/Props/Mountain.png (or Mountain_N.png)
    # then check the silhouette for leftover magenta fringe pixels

### Tree props — assets/sprites/Resources/TREE.png / TREE_DESERT.png

Both are live: every wood resource renders TREE.png, and any wood standing
on desert terrain automatically renders TREE_DESERT.png. Regenerate them in
house style whenever ready (current desert palm is serviceable).

**TREE.png** (generate at 1000x1000)
> A single broadleaf fantasy tree with a full rounded canopy in two or three
> clumps, visible sturdy trunk, stylized medieval RTS game art, hand-painted
> with crisp dark outlines, isometric three-quarter top-down view, rich
> living greens with warm brown bark, soft light from the upper left, small
> grassy root footprint, tree centered filling about 80 percent of the
> frame, THE ENTIRE BACKGROUND IS ONE SOLID FLAT PURE MAGENTA COLOR hex
> FF00FF with no gradient, no cast shadow on the background, no other
> plants, no text, no watermark, square image, 1000x1000

**TREE_DESERT.png** (generate at 1000x1000)
> A single desert palm tree with a slightly curved trunk and a crown of arcs
> of fronds, a few coconuts, stylized medieval RTS game art, hand-painted
> with crisp dark outlines, isometric three-quarter top-down view, dusty
> green fronds and sun-bleached tan trunk, small sandy footprint with a
> couple of tiny stones, soft light from the upper left, tree centered
> filling about 80 percent of the frame, THE ENTIRE BACKGROUND IS ONE SOLID
> FLAT PURE MAGENTA COLOR hex FF00FF with no gradient, no cast shadow on the
> background, no text, no watermark, square image, 1000x1000

Processing: same magenta cutout as the mountain, then overwrite the file in
`assets/sprites/Resources/`.

### World prop prompts (§11.2 follow-ups) — magenta-keyed, like the mountain

Not yet wired in code — generate freely; each gets its entity/placement pass
when the art lands. Same processing as the mountain (magenta cutout, then
check the silhouette for pink fringe). The no-ground-patch rule applies to
ALL of them: these sit on several biomes, so any baked soil mound will clash
with one of them.

**Rocks.png — rock outcrop (small blocking prop)** (1000x1000)
> A single cluster of three to five weathered gray granite boulders of
> varying sizes leaning together as one rocky outcrop, stylized medieval
> fantasy RTS game art, hand-painted with crisp dark ink-like outlines,
> isometric three-quarter top-down view matching a strategy game building
> sprite, cool stone grays with subtle warm lichen accents, soft light from
> the upper left, gentle ambient occlusion between the boulders, NO ground
> patch beneath it - the boulder bases fade directly out with no soil, no
> grass and no sand, the cluster centered filling about 70 percent of the
> frame, THE ENTIRE BACKGROUND IS ONE SOLID FLAT PURE MAGENTA COLOR hex
> FF00FF with no gradient, no shadow cast onto the background, no vignette,
> no text, no watermark, square image, 1000x1000

**DeadTree.png — swamp dead tree (non-blocking atmosphere)** (1000x1000)
> A single gnarled dead swamp tree with a twisted bare trunk, a few crooked
> leafless branches and thin strands of hanging moss, stylized medieval
> fantasy RTS game art, hand-painted with crisp dark ink-like outlines,
> isometric three-quarter top-down view, weathered gray-brown bark with
> faint green moss accents, soft light from the upper left, NO ground patch
> beneath it - the roots fade directly out with no soil mound and no water,
> the tree centered filling about 75 percent of the frame, THE ENTIRE
> BACKGROUND IS ONE SOLID FLAT PURE MAGENTA COLOR hex FF00FF with no
> gradient, no shadow cast onto the background, no vignette, no text, no
> watermark, square image, 1000x1000

**Reeds.png — marsh reed clump (non-blocking, swamp & shorelines)** (1000x1000)
> A single small clump of tall marsh reeds and cattails with slender
> green-brown stalks and two or three dark brown cattail heads, stylized
> medieval fantasy RTS game art, hand-painted with crisp dark ink-like
> outlines, isometric three-quarter top-down view, muted wetland greens and
> tans, soft light from the upper left, NO ground patch beneath it - the
> stalks fade directly out at the base with no soil and no water, the clump
> centered filling about 60 percent of the frame, THE ENTIRE BACKGROUND IS
> ONE SOLID FLAT PURE MAGENTA COLOR hex FF00FF with no gradient, no shadow
> cast onto the background, no vignette, no text, no watermark, square
> image, 1000x1000

**Ruins.png — crumbled watchtower (blocking landmark, story flavor)** (1000x1000)
> The crumbling ruin of a single small round medieval stone watchtower,
> broken off at half height with a jagged top edge, a few scattered fallen
> stone blocks around its foot, an empty dark doorway, stylized medieval
> fantasy RTS game art, hand-painted with crisp dark ink-like outlines
> matching a strategy game building sprite, isometric three-quarter
> top-down view, weathered gray stone with moss accents, soft light from
> the upper left, gentle ambient occlusion, minimal ground contact - the
> fallen blocks sit directly on the background with no soil patch, the ruin
> centered filling about 75 percent of the frame, THE ENTIRE BACKGROUND IS
> ONE SOLID FLAT PURE MAGENTA COLOR hex FF00FF with no gradient, no shadow
> cast onto the background, no vignette, no text, no watermark, square
> image, 1000x1000

**Oasis: no new art needed** — it will be generated as a shallow-water
pocket stamped into desert during map generation, ringed by the existing
desert palms (TREE_DESERT). Reeds.png above is its optional garnish.
