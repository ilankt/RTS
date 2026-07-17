# Required Visual Asset Prompts For RTS Strategy Slice

This file lists the visual assets needed to replace missing or reused placeholder art in the strategy-depth slice.

The prompts are written for AI image generation. Generate one asset per prompt, then verify dimensions, transparency, frame count, and readability in-game.

## Existing Style Reference

Use the current game assets as the style anchor:

- Buildings: `assets/sprites/Buildings/Barracks.png`, `Castle.png`, `Lumbermill.png`, `Watchtower.png`
- Unit sheets: `assets/sprites/Units/Warrior/Warrior_Idle.png`, `Warrior_Run.png`, `Warrior_Attack.png`, `assets/sprites/Units/Archer/Archer_Shoot.png`
- UI icons: `assets/ui/Units/warrior_icon.png`, `archer_icon.png`, `worker_icon.png`, `assets/ui/build_mil_icon.png`

## Shared Style Guide

Use this style guide for every asset unless an individual prompt overrides it.

### Building Sprites

- Output: transparent PNG.
- Size: 1000x1000 px, unless the prompt says otherwise.
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

### UI Icons

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
blitted straight onto whatever is behind it, at roughly **14x14 px**. Everything below
follows from those two facts; the current `assets/ui/*_icon.png` set violates all of it
(measured 2026-07-17: 1000-1024 px, alpha 255 on every single pixel, a rounded plate and
bronze border baked in, corners ~RGB(32,20,8) — at 14 px on a tile they render as opaque
dark-brown squares, and gold/lumber/stone blur into unidentifiable smears).

- Output: transparent PNG with **true alpha**, not a keyed or matted background.
- Size: 1024x1024 px.
- Background: **fully transparent, alpha 0.** No plate, no rounded panel, no border, no
  off-white fill, no drop shadow. Anything baked behind the subject becomes an opaque
  square in-game.
- Composition: **exactly ONE object**, centered, filling ~90 percent of the canvas with a
  ~5 percent transparent margin. No piles, stacks, clusters, or paired props — at 14 px a
  cluster averages into a blob. (This is the single most common failure: today's gold is
  an ingot plus four coins, lumber is three logs plus two planks. Both are mush.)
- Outline: uniform, very dark, **3-4 percent of canvas width (roughly 30-40 px at 1024)**.
  A 2 px outline at 1024 is invisible at 14 px; a 6 percent one eats the tiny glyph's
  bright core. The outline is for house-style consistency and internal definition — it is
  **not** what separates the glyph from the background (see below).
- **Every surface a glyph touches is dark.** This is the fact that drives the palette, and
  it is easy to get wrong: the command card's tile fills are dark olive `(42,52,42)` when
  affordable, `(45,42,32)` locked, `(50,38,38)` unaffordable, `(67,77,67)` hovered, and the
  tooltip is near-black `(10,10,14)`. So a **bright, high-value fill** is what makes a glyph
  readable — a dark outline on a dark tile just merges with it.
- Fill values (measured 2026-07-17 against the real tile colors; WCAG contrast, ≥3.0
  required on the worst surface, which is always the affordable-tile olive):

  | Glyph | Fill | Worst-surface contrast |
  |---|---|---|
  | gold | bright yellow-gold `(245,200,60)` | 8.14 |
  | wood | **light** warm brown `(196,142,92)` | 4.54 |
  | stone | light cool gray `(185,190,196)` | 6.92 |
  | food | **bright** warm red `(230,125,95)` | 4.60 |
  | time | pale gray-blue `(170,196,214)` | 7.13 |

  The two traps: a natural mid-brown log `(120,80,50)` scores **1.84** and a natural
  roast-red `(120,45,40)` scores **1.36** — both are invisible on the tile. Wood and food
  must be pushed lighter than the subject "wants" to be.
- Detail budget: **at most 2 internal details**, two-step shading. No fine engraving, no
  thin lines, no gradients, no texture noise.
- Readability bar: **must be identifiable at 14x14 px.** Judge it by silhouette plus one
  dominant hue — that is all that survives. If it needs its details to read, it fails.
- Hue separation (**mandatory** — these glyphs sit side by side on one tile row): gold,
  wood and food are all warm and blur into each other at 14 px (today's gold and lumber
  icons are already indistinguishable there). Keep gold clearly yellow, wood clearly tan,
  and food clearly red.
- Avoid: text, numbers, watermark, background scenery, photorealism, and every framed-icon
  convention from the UI Icons section.

## Required Now

### 1. Ram Unit Icon

Target path:

`assets/ui/Units/ram_icon.png`

Reason:

The ram unit already references this icon. The file is missing, so the UI falls back to a placeholder.

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS unit: a battering ram. Match the existing game unit icon style: off-white background, thin gold square border near the edge, bold dark navy/black outlines, clean stylized shapes, slightly playful but still medieval strategy-game readable. The battering ram should be centered and fill about 80 percent of the canvas. Show a compact wooden siege ram with four small wheels, a heavy horizontal log body, iron-banded ram head, reinforced wooden roof or hide covering, rope bindings, and subtle metal studs. Use warm brown wood, muted gray metal, and a small blue cloth accent that harmonizes with the existing warrior/archer icons. The silhouette must be instantly recognizable as a siege ram at small size. No rider, no text, no letters, no numbers, no watermark, no photorealism, no background scenery. Keep the icon crisp, polished, and readable at 32x32.
```

## Required To Replace Placeholder Unit Art

### 2. Spearman Unit Icon

Target path:

`assets/ui/Units/spearman_icon.png`

Reason:

Spearman currently reuses the warrior icon, making unit composition hard to read.

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS unit: a spearman. Match the existing unit icon style used by warrior_icon.png: off-white background, thin gold square border near the edge, bold dark navy outlines, simple stylized chibi proportions, clean readable silhouette, polished vector-like painterly finish. The spearman should be centered, facing slightly right, holding a long spear diagonally upward with a clear metal spear tip. Use a simple helmet, small round or kite shield, blue and gold cloth accents, leather boots, and light armor. The spear must be the dominant identifier and remain visible without touching the icon border. Make the character distinct from the sword warrior: no sword, no large sword blade, no archer bow. No text, no watermark, no realistic portrait, no background scenery.
```

### 3. Spearman Idle Sprite Sheet

Target path:

`assets/sprites/Units/Spearman/Spearman_Idle.png`

Required dimensions:

1536x192 px, 8 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS spearman idle animation. Exact output size 1536x192 px, one row of 8 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing Warrior_Idle.png style: compact stylized small unit, slightly top-down 3/4 view, facing right/front-right, dark navy outlines, simplified medieval armor, blue and gold accents, transparent background. The spearman holds a long spear upright or slightly diagonal, with a small shield and light armor. Animate subtle idle breathing and tiny spear sway across 8 frames. Keep feet planted on the same baseline, same scale, same facing, same body proportions in every frame. The spear tip must remain inside each 192x192 frame. No ground, no shadow, no text, no UI border, no extra characters.
```

### 4. Spearman Run Sprite Sheet

Target path:

`assets/sprites/Units/Spearman/Spearman_Run.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS spearman running animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing Warrior_Run.png style: small stylized unit, slightly top-down 3/4 view, facing right/front-right, dark outlines, blue and gold cloth, simple helmet and light armor. The spearman runs forward with a long spear angled backward or forward in a controlled formation pose, shield close to body. Show a clear 6-frame run cycle with alternating legs and subtle body bob, but keep the same size and baseline across frames. Weapon tips must not be cropped. Transparent background only. No motion blur, no text, no shadows, no UI border.
```

### 5. Spearman Attack Sprite Sheet

Target path:

`assets/sprites/Units/Spearman/Spearman_Attack.png`

Required dimensions:

768x192 px, 4 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS spearman attack animation. Exact output size 768x192 px, one row of 4 frames, each frame exactly 192x192 px with no gutters and no grid. Match the current Warrior_Attack.png style: compact stylized unit, slightly top-down 3/4 view, facing right/front-right, dark navy outlines, readable at small size. The action is a spear thrust: frame 1 ready stance, frame 2 wind-up, frame 3 full forward thrust with spear extended, frame 4 recoil back toward guard. Keep the feet aligned to a stable baseline, same character scale, same outfit colors, transparent background. Spear tip must remain within frame and clearly visible. No hit effects, no enemy, no text, no ground, no UI frame.
```

### 6. Spearman Guard Sprite Sheet

Target path:

`assets/sprites/Units/Spearman/Spearman_Guard.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS spearman guard animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing Warrior_Guard.png style: compact stylized unit, slightly top-down 3/4 view, facing right/front-right, dark outlines, simple helmet, small shield, blue and gold accents. The spearman braces defensively with spear angled forward and shield held close, suitable as an anti-cavalry stance. Animate a subtle breathing/ready shift across 6 frames, not a full attack. Keep frame alignment, baseline, and scale consistent. Transparent background only. No text, no enemy, no ground.
```

### 7. Cavalry Unit Icon

Target path:

`assets/ui/Units/cavalry_icon.png`

Reason:

Cavalry currently reuses the warrior icon.

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS cavalry unit. Match the existing unit icon style: off-white background, thin gold square border, bold dark navy outlines, clean stylized chibi proportions, polished readable game UI art. Show a mounted knight or scout on a compact horse, facing slightly right. The rider wears a simple helmet and blue/gold cloth accents, carrying a short lance or saber. The horse should be readable but simplified, with warm brown coat, dark mane, small saddle, and minimal armor. The icon must clearly communicate "fast cavalry" at small size and be distinct from infantry icons. No text, no numbers, no watermark, no realistic background, no full landscape.
```

### 8. Cavalry Idle Sprite Sheet

Target path:

`assets/sprites/Units/Cavalry/Cavalry_Idle.png`

Required dimensions:

1536x192 px, 8 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS cavalry idle animation. Exact output size 1536x192 px, one row of 8 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing small unit sprite style: stylized, compact, slightly top-down 3/4 view, facing right/front-right, dark navy outlines, blue and gold accents, simplified medieval fantasy. Show a rider on a small horse, with the rider holding a short lance or saber. The idle animation should include subtle horse breathing, tiny head movement, and rider bob. Keep the horse and rider centered in every frame with the same baseline and scale. Fit the full horse and weapon inside each 192x192 frame. Transparent background only. No ground shadow, no text, no UI frame.
```

### 9. Cavalry Run Sprite Sheet

Target path:

`assets/sprites/Units/Cavalry/Cavalry_Run.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS cavalry run animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing Warrior_Run.png and Archer_Run.png small stylized sprite style: dark outlines, compact forms, slightly top-down 3/4 view, facing right/front-right, blue/gold team-neutral accents. Show a small horse galloping with a rider leaning forward, short lance or saber held safely within the frame. Make the motion readable as fast cavalry: alternating leg positions, body bob, rider bounce. Keep the same scale, anchor point, and baseline across all frames. Transparent background. No motion blur, no dust trail, no text, no cropping.
```

### 10. Cavalry Attack Sprite Sheet

Target path:

`assets/sprites/Units/Cavalry/Cavalry_Attack.png`

Required dimensions:

768x192 px, 4 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS cavalry attack animation. Exact output size 768x192 px, one row of 4 frames, each frame exactly 192x192 px with no gutters and no grid. Style must match the existing Warrior_Attack.png: compact stylized small unit, dark navy outlines, readable at small scale, slightly top-down 3/4 view, facing right/front-right. Show a mounted rider performing a quick lance jab or saber slash from horseback: frame 1 ready, frame 2 wind-up, frame 3 strike, frame 4 recover. Keep the horse and rider centered, consistent baseline, same scale, transparent background. Weapon must be fully visible and not cropped. No enemy, no hit flash, no text, no ground.
```

### 11. Cavalry Guard Sprite Sheet

Target path:

`assets/sprites/Units/Cavalry/Cavalry_Guard.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS cavalry guard animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing Warrior_Guard.png style: small stylized unit, dark outlines, blue/gold accents, slightly top-down 3/4 view, facing right/front-right. Show the horse standing alert while the mounted rider holds a lance or saber in a defensive ready pose. Animate slight horse breathing and rider posture shift across 6 frames. Keep all frames aligned to the same baseline with no camera changes. Transparent background. No text, no UI border, no enemy.
```

### 12. Ram Idle Sprite Sheet

Target path:

`assets/sprites/Units/Ram/Ram_Idle.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS battering ram idle animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing small RTS unit sprite style: stylized, compact, dark outlines, slightly top-down 3/4 view, facing right/front-right. The ram is a squat wooden siege machine with four wheels, a heavy horizontal log ram, iron bands, rope bindings, and a simple hide or wooden roof cover. It should be clearly different from infantry. Idle animation should be subtle: tiny wheel jiggle, slight roof/rope sway, barely shifting body weight. Keep same scale and baseline in every frame. Transparent background only. No crew, no ground shadow, no text, no UI border.
```

### 13. Ram Roll Sprite Sheet

Target path:

`assets/sprites/Units/Ram/Ram_Run.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS battering ram moving animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing unit sprite style: compact stylized forms, dark outlines, slight top-down 3/4 view, facing right/front-right, transparent background. Show a wooden battering ram slowly rolling forward on wheels, with the log and roof cover bobbing slightly. Animate wheel rotation and heavy slow movement across 6 frames. Keep the asset centered, same baseline, same scale, no camera changes. The ram must fit fully inside each 192x192 frame. No people, no dust trail, no background, no text.
```

### 14. Ram Attack Sprite Sheet

Target path:

`assets/sprites/Units/Ram/Ram_Attack.png`

Required dimensions:

768x192 px, 4 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS battering ram attack animation. Exact output size 768x192 px, one row of 4 frames, each frame exactly 192x192 px with no gutters and no grid. Match the existing unit sprite style: stylized compact siege unit, dark outlines, slightly top-down 3/4 view, facing right/front-right, transparent background. The ram performs a heavy building-hit motion: frame 1 braced, frame 2 log pulls slightly backward, frame 3 log thrusts forward, frame 4 recoil/settle. Show a wooden ram on wheels with iron bands and rope bindings. Keep frame alignment, baseline, and scale stable. No target building, no impact particles, no ground, no text, no cropped log.
```

### 15. Ram Guard Sprite Sheet

Target path:

`assets/sprites/Units/Ram/Ram_Guard.png`

Required dimensions:

1152x192 px, 6 frames, each frame 192x192 px.

Prompt:

```text
Create a transparent PNG horizontal sprite sheet for a medieval RTS battering ram guard/ready animation. Exact output size 1152x192 px, one row of 6 frames, each frame exactly 192x192 px with no gutters and no grid. Match the current unit sprite style: stylized, compact, dark outlines, slight top-down 3/4 view, facing right/front-right. Show the ram stationary in a ready state with wheels locked, roof cover and ropes subtly swaying. This is not an attack animation. Keep all frames centered, same scale, same baseline, transparent background. No crew, no enemy, no ground, no text.
```

## Required To Replace Placeholder Building Art

### 16. Stable Building Sprite

Target path:

`assets/sprites/Buildings/Stable.png`

Reason:

Stable currently reuses the barracks sprite.

Prompt:

```text
Create a 1000x1000 transparent PNG isometric building sprite for a medieval RTS stable. Match the existing building style from Barracks.png, Farm.png, House.png, and Lumbermill.png: hand-painted stylized medieval, crisp dark outlines, warm wood, pale roof tiles or thatch, stone foundation blocks, soft upper-left lighting, irregular dirt/moss footprint shadow, transparent background. The stable should be a wooden horse stable with an open front stall, visible hay bales, a simple fenced paddock, a saddle rack, horseshoe sign, and maybe one horse head peeking from a stall. Use a compact footprint similar to the barracks, about 1.5x1.5 building size in-game. Include a plain white flag or small cloth banner if appropriate, matching existing faction-neutral flags. It must be visually distinct from the barracks: no weapon racks, no shields, no spear stands. Keep full object visible with padding, no text, no watermark, no photorealism, no background scenery.
```

### 17. Blacksmith Building Sprite

Target path:

`assets/sprites/Buildings/Blacksmith.png`

Reason:

Blacksmith currently reuses the lumbermill sprite.

Prompt:

```text
Create a 1000x1000 transparent PNG isometric building sprite for a medieval RTS blacksmith. Match the existing building style from Lumbermill.png and Barracks.png: stylized hand-painted, crisp dark outlines, warm wooden beams, stone base, pale roof tiles or dark workshop roof, soft upper-left lighting, transparent background, irregular dirt/moss footprint shadow. The blacksmith should be a compact forge workshop with a stone chimney, glowing orange forge opening, anvil outside, hammer and tongs, stacked coal or charcoal, metal bars, water barrel, and a simple workbench. Use restrained warm orange glow from the forge but keep it consistent with the game's painterly style. Include a plain white flag or small cloth marker only if it fits the existing building language. It must be clearly different from lumbermill: no saw wheel, no cut logs as the main feature. Full object visible, centered, 8-12 percent padding. No text, no logo, no watermark, no photorealism.
```

### 18. Siege Workshop Building Sprite

Target path:

`assets/sprites/Buildings/SiegeWorkshop.png`

Reason:

Siege workshop currently reuses the barracks sprite.

Prompt:

```text
Create a 1000x1000 transparent PNG isometric building sprite for a medieval RTS siege workshop. Match the existing building style from Barracks.png, Lumbermill.png, and Watchtower.png: hand-painted stylized medieval, thick readable outlines, warm brown wood, stone block supports, soft upper-left lighting, transparent background, irregular dirt/moss footprint shadow. The siege workshop should look like a heavy timber construction yard for siege engines: large open-sided wooden shed, reinforced beams, simple crane or pulley, spare wheels, stacked logs, iron bands, rope coils, and a half-built battering ram or ram head visible near the front. Keep the footprint similar to a 1.5x1.5 building but visually heavier than barracks. It must be instantly recognizable as siege production and not just another house or barracks. Optional plain white flag/banner allowed, no colored faction mark. No text, no watermark, no photorealism, no background landscape, no cropped props.
```

## Required Research/Tech Icons

These are not fully wired into the UI yet, but they are required for a polished blacksmith research panel. Recommended target folder:

`assets/ui/Techs/`

### 19. Improved Tools Tech Icon

Target path:

`assets/ui/Techs/improved_tools_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS blacksmith upgrade named Improved Tools. Match the existing UI icon style: off-white background, thin gold square border, bold dark navy/black outlines, clean symbolic composition, readable at 32x32. Show crossed worker tools: a small pickaxe and wood axe or hammer, with subtle warm wood handles and gray metal heads. Add a small golden sparkle or polished edge highlight to suggest improvement, but keep it simple. No text, no letters, no numbers, no watermark, no character, no landscape.
```

### 20. Reinforced Frames Tech Icon

Target path:

`assets/ui/Techs/reinforced_frames_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS upgrade named Reinforced Frames. Match the existing UI style: off-white background, thin gold border, bold dark navy outlines, simple readable symbol. Show a sturdy wooden building frame or wall corner reinforced with metal brackets and rivets, plus one stone block base. Use warm brown wood, muted gray metal, and small gold highlights. The icon should communicate stronger buildings and reinforced structure. No text, no numbers, no watermark, no full building scene, no photorealism.
```

### 21. Forged Blades Tech Icon

Target path:

`assets/ui/Techs/forged_blades_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS upgrade named Forged Blades. Match the existing UI icon style: off-white background, thin gold square border, bold dark outlines, clean symbolic medieval look. Show two crossed freshly forged swords or one sword over a small anvil, with bright silver-green blade highlights matching the existing warrior sword color. Add a subtle orange forge glow near the base, but keep the design simple and readable. No text, no letters, no numbers, no watermark, no character portrait.
```

### 22. Fletching Tech Icon

Target path:

`assets/ui/Techs/fletching_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS upgrade named Fletching. Match the existing UI style: off-white background, thin gold border, bold dark navy outlines, clean high-resolution symbolic icon. Show a bundle of arrows with clearly visible feather fletching, perhaps crossing a small bow. Use tan wood shafts, white/blue feathers, and gray metal arrowheads. The icon should communicate improved archery range and accuracy. No text, no numbers, no watermark, no archer character, no scenery.
```

### 23. Padded Armor Tech Icon

Target path:

`assets/ui/Techs/padded_armor_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS upgrade named Padded Armor. Match the existing UI style: off-white background, thin gold border, bold dark outlines, simple readable medieval symbol. Show a quilted padded gambeson or armor vest with blue/gold trim and a small shield shape behind it. Use soft cloth texture, simple stitched panels, and dark outline. The icon must communicate defensive armor for infantry. No text, no letters, no numbers, no watermark, no full person, no realistic mannequin.
```

### 24. Siege Engineering Tech Icon

Target path:

`assets/ui/Techs/siege_engineering_icon.png`

Prompt:

```text
Create a 1024x1024 PNG tech icon for an RTS upgrade named Siege Engineering. Match the existing UI style: off-white background, thin gold border, bold dark outlines, clean symbolic medieval look. Show a small battering ram wheel, gear, and reinforced ram head, arranged as one central readable symbol. Use warm wood, gray metal, rope detail, and a tiny blueprint-like parchment corner if it stays simple. The icon should communicate stronger siege machinery. No text, no letters, no numbers, no watermark, no full building, no busy workshop background.
```

## Optional But Useful Visual Polish

### 25. Stable Build Menu Icon Override

Target path:

`assets/ui/Buildings/stable_icon.png`

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS stable building. Use the game's icon style: off-white background, thin gold square border, bold dark outlines, simple centered object. Show a stylized stable front with a horse head, hay bale, and horseshoe sign. Use warm wood and muted gold/brown colors. Make it readable at 32x32. No text, no watermark, no background scenery.
```

### 26. Blacksmith Build Menu Icon Override

Target path:

`assets/ui/Buildings/blacksmith_icon.png`

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS blacksmith building. Use the existing UI icon language: off-white background, thin gold border, bold dark outlines. Show an anvil, hammer, and small orange forge flame as a centered symbol. Warm brown and gray palette, simple silhouette, readable at 32x32. No text, no watermark, no full scene.
```

### 27. Siege Workshop Build Menu Icon Override

Target path:

`assets/ui/Buildings/siege_workshop_icon.png`

Prompt:

```text
Create a 1024x1024 PNG UI icon for a medieval RTS siege workshop. Match the game's UI icon style: off-white background, thin gold square border, bold dark outlines, clean symbolic art. Show a battering ram under construction with a wheel, log ram, rope, and hammer. Centered, readable at small size, warm wood and gray metal. No text, no watermark, no landscape.
```

## Required For The Command Card Cost Row (§8.2.2)

User request: *"Mostly I want to see the cost (with icons, not text or abbreviation) and
duration (also an icon)."* The card replaces its `"150G 100W"` text with icon+number pairs
on each tile, and the hover tooltip gains a duration row.

**These are new files, not replacements.** The existing `assets/ui/*_icon.png` set stays
exactly as it is: those framed plates are drawn at 48 px onto the dark top banner, where
they look correct and nobody has complained. Overwriting them to serve the cost row would
restyle the top bar as a side effect. A framed plate in the banner and a bare glyph inline
is a normal HUD split — keep both.

Follow the **HUD Cost Glyphs** style guide above; it overrides the UI Icons rules.

After generating, wire up: `ui/components/icon_loader.py` has no path to resource art at
all (resource icons load ad hoc in `core/game.py:208-223`), so add a `_load_cost_glyphs`
there and pin all five in `tools/verify_visual_assets.py`'s `EXPECTED_DIMS`.

### 28. Gold Cost Glyph

Target path:

`assets/ui/Glyphs/gold_glyph.png`

Prompt:

```text
Create a 1024x1024 transparent PNG inline HUD glyph representing the resource Gold in a stylized medieval RTS. This is a bare cut-out, NOT a framed icon: the background must be fully transparent alpha 0, with no plate, no rounded panel, no border, no off-white fill, and no drop shadow, because the glyph is drawn directly onto a dark olive tile and a dark wooden banner. Show exactly ONE single gold coin, face-on, as a bold simple disc with one small embossed crown mark in the center. Do not draw a pile, a stack, an ingot, or any cluster of coins: one object only. The coin fills about 90 percent of the canvas with a 5 percent transparent margin. Use one bright saturated yellow-gold fill, around RGB 245,200,60, with simple two-step shading: the glyph sits on dark backgrounds, so the bright fill is what makes it readable and it must not be dulled or darkened. Add a uniform very dark brown outline about 3 to 4 percent of the canvas width, roughly 30 to 40 px, for style consistency only. The glyph must stay instantly recognizable as money when scaled to 14x14 px, so keep the silhouette bold and use at most two internal details. Keep the hue clearly yellow so it cannot be confused with the tan wood glyph or the red food glyph it sits beside. No pile, no cluster, no fine engraving, no thin lines, no gradients, no text, no numbers, no watermark, no background scenery, no photorealism.
```

### 29. Wood Cost Glyph

Target path:

`assets/ui/Glyphs/wood_glyph.png`

Prompt:

```text
Create a 1024x1024 transparent PNG inline HUD glyph representing the resource Wood in a stylized medieval RTS. This is a bare cut-out, NOT a framed icon: fully transparent background, alpha 0, no plate, no rounded panel, no border, no off-white fill, no drop shadow. Show exactly ONE single wooden log lying horizontally, turned slightly so one circular cut end is visible with two or three simple growth rings. Do not draw a stack of logs, planks, boards, a woodpile, or an axe: one log only. The log fills about 90 percent of the canvas with a 5 percent transparent margin. Use a LIGHT warm tan-brown fill, around RGB 196,142,92, with a slightly paler cut end and simple two-step shading. This is important and counterintuitive: do not use a natural mid or dark brown, because the glyph is drawn on a dark olive background where dark brown disappears completely. Err on the side of too light. Add a uniform very dark brown outline about 3 to 4 percent of the canvas width, roughly 30 to 40 px, for style consistency only. Keep the tan clearly less yellow than a gold coin glyph and clearly less red than a roast-meat glyph, since all three sit side by side and blur together at small size. The glyph must stay recognizable as timber at 14x14 px: bold horizontal silhouette, at most two internal details. No stack, no planks, no bark texture noise, no thin lines, no text, no numbers, no watermark, no background, no photorealism.
```

### 30. Stone Cost Glyph

Target path:

`assets/ui/Glyphs/stone_glyph.png`

Prompt:

```text
Create a 1024x1024 transparent PNG inline HUD glyph representing the resource Stone in a stylized medieval RTS. This is a bare cut-out, NOT a framed icon: fully transparent background, alpha 0, no plate, no rounded panel, no border, no off-white fill, no drop shadow. Show exactly ONE single cut stone block, a chunky angular quarried cube seen in slight three-quarter view with clean chiseled faces. Do not draw a pile of rubble, scattered rocks, or a boulder cluster: one block only. The block fills about 90 percent of the canvas with a 5 percent transparent margin. Use a LIGHT cool gray fill, around RGB 185,190,196, with clear value contrast between the lit top face and the shaded side face. Do not use mid gray, dark gray, or charcoal: the glyph is drawn on dark backgrounds, where a dark stone vanishes entirely. Apply simple two-step shading and a uniform very dark outline about 3 to 4 percent of the canvas width, roughly 30 to 40 px, for style consistency only. The glyph must read as masonry at 14x14 px: strong blocky silhouette, at most two internal details. Its cool gray keeps it distinct from the warm gold, wood and food glyphs beside it, so do not warm it up with brown or tan tints. No rubble, no scattered rocks, no speckle texture, no cracks, no moss, no thin lines, no text, no numbers, no watermark, no background, no photorealism.
```

### 31. Food Cost Glyph

Target path:

`assets/ui/Glyphs/food_glyph.png`

Prompt:

```text
Create a 1024x1024 transparent PNG inline HUD glyph representing the resource Food in a stylized medieval RTS. This is a bare cut-out, NOT a framed icon: fully transparent background, alpha 0, no plate, no rounded panel, no border, no off-white fill, no drop shadow. Show exactly ONE single roasted meat drumstick standing upright with the bone at the bottom, the classic bold game-food silhouette. Do not draw a platter, a plate, bread, fruit, or a group of items: one drumstick only. It fills about 90 percent of the canvas with a 5 percent transparent margin. Use a BRIGHT warm red roasted fill, around RGB 230,125,95, with an off-white bone. Two requirements pull the same way here: the glyph sits on a dark olive background, so a natural dark roast-brown would disappear, and it also sits beside a yellow gold glyph and a tan wood glyph, which it must not blur into. So push the meat clearly toward bright red and keep it well lit. The off-white bone is a useful bright anchor: keep it clearly visible. Apply simple two-step shading and a uniform very dark outline about 3 to 4 percent of the canvas width, roughly 30 to 40 px, for style consistency only. Must read as food at 14x14 px: bold vertical silhouette with the narrow bone clearly separated from the wide meat, at most two internal details. No plate, no garnish, no steam, no grill marks, no thin lines, no text, no numbers, no watermark, no background, no photorealism.
```

### 32. Duration/Time Glyph

Target path:

`assets/ui/Glyphs/time_glyph.png`

Reason:

No clock, hourglass, or duration art exists anywhere in the project. The tooltip's
build/research duration row has nothing to draw.

Prompt:

```text
Create a 1024x1024 transparent PNG inline HUD glyph representing Time or Duration in a stylized medieval RTS. This is a bare cut-out, NOT a framed icon: fully transparent background, alpha 0, no plate, no rounded panel, no border, no off-white fill, no drop shadow. Show exactly ONE single hourglass, front-on and symmetrical, with a heavy top and bottom cap, two chunky corner posts, and a clear pinched waist. Choose an hourglass rather than a clock face: it suits the medieval setting, and its narrow-waisted silhouette is the most readable shape available when tiny. The hourglass fills about 90 percent of the canvas with a 5 percent transparent margin. Use a LIGHT cool gray-blue fill, around RGB 170,196,214, for the frame, with pale white-blue sand in the lower bulb. Keep the whole glyph cool, light and desaturated: it is drawn on dark backgrounds, so it must stay bright, and it sits beside a warm yellow gold glyph, which it must never be mistaken for. Apply simple two-step shading and a uniform very dark outline about 3 to 4 percent of the canvas width, roughly 30 to 40 px, for style consistency only. Must read as elapsed time at 14x14 px: keep the two triangular bulbs and the pinched waist bold and obvious, at most two internal details. No falling sand stream, no numerals, no clock hands, no wings, no thin lines, no text, no numbers, no watermark, no background, no photorealism.
```

## Post-Generation Verification Checklist

After generating assets:

1. Confirm paths and casing match data exactly.
2. Confirm dimensions:
   - Building sprites: 1000x1000 PNG, transparent background.
   - Unit icons and tech icons: 1024x1024 PNG.
   - Unit sprite sheets: width equals frame_count * 192, height equals 192.
   - HUD cost glyphs: 1024x1024 PNG.
3. Open each image against a dark and light background to catch bad alpha edges.
3a. **HUD cost glyphs — run the checker, then look at what it draws:**

```powershell
python tools\preview_cost_glyphs.py
```

   It fails the batch on the two things a generator will silently get wrong — a painted
   background instead of real alpha (`alpha_min=255`; exactly how the current
   `assets/ui/*_icon.png` set became unusable), and a fill too dark for the tile — and it
   writes `cost_glyph_preview.png`: every glyph at **14 px**, magnified, on all five real
   surfaces. **Judge the glyphs there, never at full size.** If you cannot name the
   resource from a 14 px cell, or gold/wood/food read as three similar warm blobs,
   regenerate with a bolder silhouette and stronger hue separation. Run it with `--old` to
   see the legacy icons fail, which is a useful calibration of what "too dark" looks like.
4. Run:

```powershell
python -m compileall -q core entities managers systems ui world screens tests tools main.py
python tools\smoke_strategy_slice.py --mode human_1v1 --seconds 45 --speed 5
```

5. Manually launch:

```powershell
python main.py
```

6. Verify in-game:
   - Build menu icons are readable.
   - Selected unit panel shows distinct icons.
   - Spearman, cavalry, and ram are distinguishable on the map.
   - Building silhouettes are distinct at gameplay zoom.
   - Animations do not jitter, crop, change size, or drift between frames.
   - Transparent backgrounds render cleanly with no black or white boxes.

## Data Wiring Notes

After adding generated assets, update data references where needed:

- Spearman:
  - `icon`: `assets/ui/Units/spearman_icon.png`
  - animations under `assets/sprites/Units/Spearman/`
- Cavalry:
  - `icon`: `assets/ui/Units/cavalry_icon.png`
  - animations under `assets/sprites/Units/Cavalry/`
- Ram:
  - `icon`: `assets/ui/Units/ram_icon.png`
  - animations under `assets/sprites/Units/Ram/`
- Stable:
  - `sprite`: `assets/sprites/Buildings/Stable.png`
- Blacksmith:
  - `sprite`: `assets/sprites/Buildings/Blacksmith.png`
- Siege workshop:
  - `sprite`: `assets/sprites/Buildings/SiegeWorkshop.png`
- Quarry:
  - fix `assets/sprites/Buildings/Quarry.png` vs existing `assets/sprites/Buildings/quarry.png` casing.
