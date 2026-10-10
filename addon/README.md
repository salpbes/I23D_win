# Image to Game Asset (Blender add-on)

Picture → TRELLIS.2 3D model → clean, light game mesh → `.glb`, from one Blender panel.

## Install
1. Blender: **Edit › Preferences › Get Extensions** › ⌄ menu (top right) › **Install from Disk…**
2. Pick `image_to_game_asset-1.1.0.zip` (build it with `bash scripts/build_addon.sh`).
3. In the add-on's preferences, check the two folders and click **Check Setup**.
   Defaults: `~/Documents/sources/trellis-mac` and `~/Documents/sources/trellis-output`.
   (TRELLIS.2 for Mac is installed by `scripts/install_trellis.sh`.)

## Use (3D View › press **N** › **Image→3D** tab)
1. **Picture → 3D model** – pick a picture, press **Generate** (≈5–10 min on an M4; Blender stays usable).
2. **Clean for games** – choose a triangle budget, press **Clean Selected**.
   Colours default to **TRELLIS colours**: the colours TRELLIS.2 generated are baked into a texture
   (needs *Bake textures* off and the colour patch, which the installer adds).
   **Match photo colours**: 0 = pure TRELLIS colours, 1 = brightness/tint matched to the picture.
   Plain presets (Clay, Gold, …) are still there.
   To see textures, switch the viewport to **Material Preview**.
   The original is kept hidden, so you can re-clean at another size (e.g. `crown_15k`, `crown_5k`).
3. **Export** – press **Export .glb** (one file per selected model).

Tick *Clean automatically* and *Export .glb automatically* for a one-click run.

## How cleaning works
AI meshes are paper-thin, tangled shells. The add-on: thickens them slightly → rebuilds as one
closed solid (voxel remesh) → removes floating bits → simplifies to the budget → smooth shading,
optional resize, base on the ground. Result: watertight and light.

## Files
Generated models and a `<name>_log.txt` go to the output folder; exports go to
`<output folder>/game-ready` unless you choose another folder.

## Tips
- One object, plain or transparent background, seen slightly from the side and above.
- Close heavy apps while generating; TRELLIS.2 needs most of 24 GB.
- If cleaning loses thin parts, set **Advanced › Rebuild detail** to *Fine* or raise **Thicken**.
