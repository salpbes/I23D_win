# Image to Game Asset (Blender add-on, Windows)

Picture → TRELLIS.2 3D model → clean, light game mesh → `.glb`, from one Blender panel.
Everything runs on your own PC: TRELLIS.2 runs inside a local ComfyUI that only listens to this
computer (127.0.0.1) and is started with `--offline`.

## Install
1. Install ComfyUI and the TRELLIS.2 models once (about 11 GB of downloads):
   `powershell -ExecutionPolicy Bypass -File scripts\install_comfyui.ps1`
2. Build the add-on: `powershell -ExecutionPolicy Bypass -File scripts\build_addon.ps1`
3. Blender: **Edit › Preferences › Get Extensions** › ⌄ menu (top right) › **Install from Disk…**
   and pick `dist\image_to_game_asset-2.1.2.zip`.
4. In the add-on's preferences press **Check Setup**. Defaults:
   ComfyUI folder `%USERPROFILE%\I23D\ComfyUI_windows_portable`, output `%USERPROFILE%\I23D\output`.

## Use (3D View › press **N** › **Image→3D** tab)
1. **Picture → 3D model** – pick a picture, press **Generate**. The first time, the add-on starts
   ComfyUI in the background (about 30 s). A model takes under 3 minutes on an RTX 5060 Ti 16 GB.
   Blender stays usable; the bar shows each step.
2. **Clean for games** – choose a triangle budget, press **Clean Selected**.
   Colours default to **TRELLIS colours**: TRELLIS.2's colour texture is baked onto the light model.
   **Match photo colours**: 0 = pure TRELLIS colours, 1 = brightness/tint matched to the picture.
   **Metal, roughness & bumps** (on by default): also bakes the original's metal/roughness texture
   and a normal map of its fine detail, so metal parts keep their shine in the exported .glb.
   Plain presets (Clay, Gold, …) are still there.
   To see textures, switch the viewport to **Material Preview**.
   The original is kept hidden, so you can re-clean at another size (e.g. `axe_15k`, `axe_5k`).
3. **Export** – press **Export .glb** (one file per selected model).

Tick *Clean automatically* and *Export .glb automatically* for a one-click run.

## ComfyUI
- **Start ComfyUI when needed** (preferences, on): Generate starts it if it isn't running.
  If you already run ComfyUI yourself at the same address, the add-on just uses it.
- **Keep ComfyUI running between models** (on): the next model starts faster. Press
  **Advanced › Stop ComfyUI** to free its memory; it also stops when you quit Blender.
- **Cancel** stops the current model only.

## How cleaning works
AI meshes are huge and made of tangled shells. The add-on: thickens them slightly → rebuilds as one
closed solid (voxel remesh) → removes floating bits → simplifies to the budget → smooth shading,
optional resize, base on the ground. Result: watertight and light.

## Files
Generated models and a `<name>_log.txt` go to the output folder, with `comfyui_log.txt` when the
add-on started ComfyUI. Exports go to `<output folder>\game-ready` unless you choose another folder.

## Tips
- One object, plain or transparent background, seen slightly from the side and above.
- Close other programs that use the graphics card while generating (games, video editors).
- If cleaning loses thin parts, set **Advanced › Rebuild detail** to *Fine* or raise **Thicken**.
