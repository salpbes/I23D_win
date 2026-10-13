# How the workflow works

Picture → **TRELLIS.2** (AI makes a detailed 3D model) → **Clean** (light, solid game mesh) →
**Colours** (TRELLIS.2's colours baked into one texture) → **Export** (`.glb` for three.js, Godot,
Unity, …).

## Setting up (once)
First time? [GETTING_STARTED.md](GETTING_STARTED.md) shows every step with screenshots.

1. Download `image_to_game_asset-2.3.0.zip` from the
   [latest release](https://github.com/salpbes/I23D_win/releases/latest). Don't unzip it.
2. Blender › Edit › Preferences › Get Extensions › ⌄ (top right) › **Install from Disk…** › pick
   the zip.
3. 3D View › press **N** › **Image→3D** tab. While ComfyUI or a TRELLIS.2 file is missing, the
   panel starts with a **One-time setup** box. Press **Install ComfyUI + TRELLIS.2** there (or in
   the add-on's preferences) and say yes.
   - **What:** downloads ComfyUI (about 2 GB) and the TRELLIS.2 model files (about 9 GB) into
     `%USERPROFILE%\I23D`. No account needed.
   - **Why a separate window:** the download can take an hour on a slow connection. The window
     shows each file as it arrives; the panel shows one progress bar for all of it (the
     installer writes `install_progress.json` for that). Blender stays usable.
   - **Safe to press again:** finished files are skipped and stopped downloads continue. Use it
     after an interrupted download too. If the window is closed early, the panel says so.
4. At the end Blender runs **Check Setup** by itself and says **Setup finished**. If something is
   missing, it says what, with the Install button next to it. Already run your own ComfyUI? Press
   *Already have it? Check Setup* in the setup box instead.

## The three steps in the panel (3D View › press **N** › **Image→3D**)

### 1. Picture → 3D model
- **What:** sends your picture to TRELLIS.2 in a local ComfyUI and imports the textured result
  into the hidden collection *Image→3D Originals*.
- **When:** for every new picture.
- **Why in the background:** it takes under 3 minutes on an RTX 5060 Ti 16 GB, including starting
  ComfyUI the first time. Blender stays usable, and a progress bar ("Step 2 of 4: detailed
  shape (45%)") plus a "last news Xs ago" line show it's alive.
- **Picture check:** as soon as you pick a picture, the panel shows it with its background
  removed, cropped exactly as TRELLIS.2 will see it, and says in plain words if something may go
  wrong: no object found, several separate pieces, the object touching the edge of the picture,
  a small object or a small picture. **View Larger** opens it in its own window. It runs only
  ComfyUI's background-removal step, so it takes seconds once ComfyUI is running. The files go
  to `<output folder>\previews`. Turn it off with *Advanced › Check the picture when chosen*;
  the **Check Picture** button still works.
- **How:** pick the picture, press **Generate**. *Random seed* is on by default, so every run gives
  a different guess for parts the picture can't show (e.g. the back). If a result looks wrong,
  just run it again.
- **Steps you'll see:** removing the background → reading the picture → four TRELLIS.2 steps
  (rough shape, detailed shape, finer shape, surface colours) → building, tidying and unwrapping
  the mesh → baking its textures → saving. TRELLIS.2 itself takes under a minute; ComfyUI's
  mesh tidying and texture baking take most of the time.
- **Afterwards:** the 3D view switches from plain grey to Material Preview, so you see the
  colours, and turns to the new model. Don't want that? Untick *Show the new model in colour* above
  the Generate button. (It leaves wireframe and rendered views alone.)

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
  ComfyUI_windows_portable\   ComfyUI + its Python + TRELLIS.2 models (Install ComfyUI + TRELLIS.2)
  install_log.txt             what the installer did
  output\                     <name>.glb originals, <name>_log.txt, comfyui_log.txt
    game-ready\               exported game models
    textures\                 baked textures (.png): _basecolor, _metallicroughness, _normal
```
