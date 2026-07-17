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
- HUD cost glyphs: `assets/ui/Glyphs/gold_glyph.png`, `wood_glyph.png`, `stone_glyph.png`, `food_glyph.png`, `time_glyph.png`

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
  | stone | light cool gray `(185,190,196)` | 6.92 |
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
