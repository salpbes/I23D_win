# Image to Game Asset (Blender add-on, Windows)

Picture → TRELLIS.2 3D model → clean, light game mesh → `.glb`, from one Blender panel.
Everything runs on your own PC: TRELLIS.2 runs inside a local ComfyUI that only listens to this
computer (127.0.0.1) and is started with `--offline`.

## Install
Step by step with screenshots: https://github.com/salpbes/I23D_win/blob/main/docs/GETTING_STARTED.md

1. Download `image_to_game_asset-2.5.0.zip` from the
   [latest release](https://github.com/salpbes/I23D_win/releases/latest). Don't unzip it.
2. Blender: **Edit › Preferences › Get Extensions** › ⌄ menu (top right) › **Install from Disk…**
   and pick the zip.
3. 3D View › press **N** › **Image→3D** tab › **One-time setup** › **Install ComfyUI + TRELLIS.2**
   (also in the add-on's preferences), and say yes. A window opens and downloads ComfyUI and the
   TRELLIS.2 models (about 11 GB, first time only); the panel shows its progress. Blender stays
   usable. It is safe to press again: finished files are skipped, stopped downloads continue.
   Front + back pictures need one more file (Pixal3D, about 6 GB): the panel offers it when you
   choose **Front + back**.
4. At the end Blender checks the setup by itself and says **Setup finished**. Defaults:
   ComfyUI folder `%USERPROFILE%\I23D\ComfyUI_windows_portable`, output `%USERPROFILE%\I23D\output`.

The installer is `install\install_comfyui.ps1` inside the add-on folder. You can also run it
yourself: `powershell -ExecutionPolicy Bypass -File install_comfyui.ps1` (add `-Check` to only
check your PC, `-FrontBack` for the front + back model too, or `-InstallDir <folder>` to install
somewhere else).

## Use (3D View › press **N** › **Image→3D** tab)
1. **Picture → 3D model** – pick a picture. The panel shows it with its background removed, as
   TRELLIS.2 will see it, and says if something may go wrong (several pieces, cut off at the
   edge, too small); **View Larger** opens it in its own window. Press **Generate**.
   **Front + back**: choose it at the top, then pick one picture with the front and back side by
   side (the add-on splits it), or the front and the back as two pictures. Pixal3D then makes
   the model from both, so the back isn't guessed. Best with straight-on views, level camera,
   the object the same size in both. Long objects (vehicles, animals): add a **Side** picture
   (front pointing left or right, as set in the panel), or set **Length** to how many times
   longer than wide it is. *Paint the pictures onto the model* (on) then copies the
   pictures' real colours onto the parts they show clearly: sharper faces and details. The first time, the add-on starts
   ComfyUI in the background (about 30 s). A model takes under 3 minutes on an RTX 5060 Ti 16 GB.
   Blender stays usable; the bar shows each step. When it's done, the view switches to colour
   (Material Preview) and turns to the new model; turn that off with *Show the new model in
   colour* above the Generate button.
2. **Clean for games** – choose a triangle budget, press **Clean Selected**.
   Colours default to **TRELLIS colours**: TRELLIS.2's colour texture is baked onto the light model.
   **Match photo colours**: 0 = pure TRELLIS colours, 1 = brightness/tint matched to the picture.
   **Metal, roughness & bumps** (on by default): also bakes the original's metal/roughness texture
   and a normal map of its fine detail, so metal parts keep their shine in the exported .glb.
   Plain presets (Clay, Gold, …) are still there.
   To see textures, switch the viewport to **Material Preview**.
   The original is kept hidden, so you can re-clean at another size (e.g. `axe_15k`, `axe_5k`).
3. **Export** – press **Export .glb** (one file per selected model). Next to each `.glb`,
   `<name>.licences.json` lists the models that made it and their licences.

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

## Disclaimer
Provided "as is", without warranty of any kind (see `LICENSE`, sections 15 and 16). You are
responsible for how you use the add-on, the AI models it runs and the 3D models it makes: use
only pictures you have the right to use, follow the law and the third-party licences (TRELLIS.2,
Pixal3D, ComfyUI, BiRefNet, DINOv3), and check every model before you rely on it. The authors are not
liable for any misuse or for any loss or damage from using it. Full text:
https://github.com/salpbes/I23D_win#disclaimer
