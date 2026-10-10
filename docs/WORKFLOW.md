# How the workflow works

Picture → **TRELLIS.2** (AI makes a detailed 3D model) → **Clean** (light, solid game mesh) →
**Colours** (TRELLIS.2's colours baked into one texture) → **Export** (`.glb` for three.js, Godot,
Unity, …).

## The three steps in the panel (3D View › press **N** › **Image→3D**)

### 1. Picture → 3D model
- **What:** runs TRELLIS.2 on your picture in the background and imports the result into the
  hidden collection *Image→3D Originals*.
- **When:** for every new picture.
- **Why in the background:** it takes 5–10 minutes on an M4 (Fast). Blender stays usable, and a
  progress bar plus "last output Xs ago" line show it's alive.
- **How:** pick the picture, press **Generate**. *Random seed* is on by default, so every run gives
  a different guess for parts the picture can't show (e.g. the back). If a result looks wrong,
  just run it again.

### 2. Clean for games
- **What:** makes a light copy of the original (e.g. `soldier_15k`) and keeps the original hidden.
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
- **TRELLIS colours** (default): the colours TRELLIS.2 generated are **baked** (copied with ray
  tracing) from the detailed original onto a texture of the light model.
  *Match photo colours* slider: 0 = pure TRELLIS colours, 1 = brightness/tint pulled toward the
  picture (TRELLIS colours often look washed-out).
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
| Detail (Fast/High) | TRELLIS.2 512 or 1024 cascade | High needs much more memory; on 24 GB it can take 1 h+ or stall |
| Seed | Fixed seed for repeatable results | To reproduce a result you liked |
| Fix orientation | Rotates trellis-mac output upright | Off only if your model already stands up |
| Bake textures | Use trellis-mac's own texture baking | Usually off: slow (~25 min) and noisy on Mac |
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

## Folder layout created on the Mac
```
~/Documents/sources/
  trellis-mac/            TRELLIS.2 for Apple Silicon (made by scripts/install_trellis.sh)
  trellis-output/         <name>.glb originals + <name>_log.txt
    game-ready/           exported game models
```
