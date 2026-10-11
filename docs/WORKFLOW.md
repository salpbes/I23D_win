# How the workflow works

Picture → **TRELLIS.2** (AI makes a detailed 3D model) → **Clean** (light, solid game mesh) →
**Colours** (TRELLIS.2's colours baked into one texture) → **Export** (`.glb` for three.js, Godot,
Unity, …).

## The three steps in the panel (3D View › press **N** › **Image→3D**)

### 1. Picture → 3D model
- **What:** sends your picture to TRELLIS.2 in a local ComfyUI and imports the textured result
  into the hidden collection *Image→3D Originals*.
- **When:** for every new picture.
- **Why in the background:** it takes under 3 minutes on an RTX 5060 Ti 16 GB, including starting
  ComfyUI the first time. Blender stays usable, and a progress bar ("Step 2 of 4: detailed
  shape (45%)") plus a "last news Xs ago" line show it's alive.
- **How:** pick the picture, press **Generate**. *Random seed* is on by default, so every run gives
  a different guess for parts the picture can't show (e.g. the back). If a result looks wrong,
  just run it again.
- **Steps you'll see:** removing the background → reading the picture → four TRELLIS.2 steps
  (rough shape, detailed shape, finer shape, surface colours) → building, tidying and unwrapping
  the mesh → baking its textures → saving. TRELLIS.2 itself takes under a minute; ComfyUI's
  mesh tidying and texture baking take most of the time.

### 2. Clean for games
- **What:** makes a light copy of the original (e.g. `soldier_15k`) and puts the detailed original
  away: it stays in the .blend file, but out of the scene, so Blender's own File › Export can't
  add it to your `.glb`. Tick *Show detailed originals* to bring the originals back into view.
- **When:** automatically after Generate (if *Clean automatically* is ticked), or press
  **Clean Selected** any time, e.g. to make a second size.
- **Why:** AI models are huge (often 1–3 million triangles) and made of paper-thin, tangled shells.
  Games need a few thousand triangles and a closed surface.
- **How it works inside:**
  1. thicken slightly (so thin parts survive),
  2. rebuild as one closed solid (voxel remesh),
  3. remove small floating bits,
  4. simplify down to the triangle budget,
  5. smooth shading, optional resize, stand it on the ground.

**Triangle budgets:** *Hero* 60k (main character, close-ups), *Standard* 15k (most objects),
*Light* 5k (props, crowds), or *Custom*. The budget is a **target you choose**. Nothing changes
it automatically. You can clean the same original several times at different sizes; each gets its
own object (`name_60k`, `name_15k`, `name_5k`).

### Colours
- **TRELLIS colours** (default): the colour texture TRELLIS.2 made for the detailed original is
  **baked** (copied with ray tracing) onto a new texture of the light model.
  *Match photo colours* slider: 0 = pure TRELLIS colours, 1 = brightness/tint pulled toward the
  picture (TRELLIS colours often look washed-out).
  *Metal, roughness & bumps* (on by default): the original from ComfyUI also has a
  metal/roughness texture and far more surface detail than the light model. Both are baked too:
  a metallicRoughness texture and a normal map (the small bumps the light model can't hold as
  triangles). The .glb then has three textures instead of one. Untick it for a single colour
  texture and a plain, non-metal surface.
- **Plain presets:** Clay, Gold, Silver, Bronze, Stone, Wood, Plastic.
- The 🎨 button next to *Clean Selected* re-applies colours without re-cleaning.
- **Tip:** Blender's *Solid* view hides textures. Switch the viewport to **Material Preview**
  (Z › Material Preview) to see them.

### 3. Export
- **What:** writes one `.glb` per selected model (texture packed inside).
- **Where:** `<output folder>/game-ready` unless you choose a folder.
- *Draco* compression (Advanced) makes files smaller; three.js needs the Draco loader for those.

## Advanced settings (only when needed)
| Setting | What it does | When to change |
|---|---|---|
| Detail (Standard/High) | TRELLIS.2's finer-shape step at 1024 or 1536 | High needs more graphics memory and time; not yet tested on 16 GB |
| Seed | Fixed seed for repeatable results | To reproduce a result you liked |
| Rebuild detail | Fine / Normal / Coarse voxel size | *Fine* if thin parts (straps, rifle) disappear |
| Thicken | How much thin shells are thickened | Raise if parts break apart |
| Height / Ground | Resize to a height; stand on Z=0 | Match your game's units (three.js: 1 unit = 1 m) |
| Texture size | 1024 / 2048 / 4096 | 2048 is a good default |

## Settings that matter most for quality
1. **The picture.** One object, plain background, seen slightly from the side and above.
2. **The seed.** The same picture can give a great or a bad model. Try 2–3 runs.
3. **How big the object is in the picture.** TRELLIS.2 builds the rough shape on a 64×64×64 grid,
   so small parts (a face, boots) get only a few cells. Cropping in on them helps a lot; see
   [DETAILED_CHARACTERS.md](DETAILED_CHARACTERS.md).

## ComfyUI in the background
- The add-on starts ComfyUI when you press Generate and it isn't running (preference
  *Start ComfyUI when needed*). It runs hidden, offline, and only this PC can reach it.
- It stays running so the next model starts faster (*Keep ComfyUI running between models*).
  **Advanced › Stop ComfyUI** frees its memory; quitting Blender stops it too.
- Already use ComfyUI yourself? Start it at the same address and the add-on uses yours.
  It needs ComfyUI 0.34 or newer and the five model files listed in
  `addon/image_to_game_asset/workflows/trellis2_image_to_glb.json`.

## Folder layout created on Windows
```
%USERPROFILE%\I23D\
  ComfyUI_windows_portable\   ComfyUI + its Python + TRELLIS.2 models (scripts\install_comfyui.ps1)
  output\                     <name>.glb originals, <name>_log.txt, comfyui_log.txt
    game-ready\               exported game models
    textures\                 baked textures (.png): _basecolor, _metallicroughness, _normal
```
