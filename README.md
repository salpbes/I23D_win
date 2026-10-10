# I23D_win: Image to Game Asset (Blender + TRELLIS.2 on Windows)

Turn **one picture** into a **game-ready 3D model** (`.glb`) from a single Blender panel, running
everything **locally** on a Windows PC with an NVIDIA graphics card and Microsoft's open-source
**TRELLIS.2** AI. Windows port of [I23D_mac](https://github.com/salpbes/I23D_mac).

```
picture ──► TRELLIS.2 in a local ComfyUI (detailed, textured model)
        ──► Clean (5k / 15k / 60k triangles, closed solid)
        ──► TRELLIS colours, metal/roughness + normal maps baked ──► .glb for three.js / Godot / Unity
```

| | |
|---|---|
| **Tested on** | Windows 11, NVIDIA RTX 5060 Ti 16 GB, Ryzen 9 3900X, 64 GB memory, Blender 5.2.2 LTS |
| **How TRELLIS.2 runs** | ComfyUI v0.39.0 portable, started by the add-on with `--offline`, listening on 127.0.0.1 only |
| **Time per model** | under 3 minutes at Standard detail (1024), including starting ComfyUI; peak graphics memory 11.5 GB |
| **Needs** | NVIDIA card with 16 GB (12 GB may work), ~25 GB free disk, no Hugging Face account |

## Quick start (Windows)

1. **Get this repo** (or download it as a zip from GitHub):
   ```bash
   git clone https://github.com/salpbes/I23D_win.git
   ```
2. **Install ComfyUI + TRELLIS.2** (PowerShell, in the repo folder; ~11 GB download, first time only):
   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\install_comfyui.ps1 -Check
   ```
   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\install_comfyui.ps1
   ```
   The first checks your PC and installs nothing. Everything goes into `%USERPROFILE%\I23D`.
3. **Build and install the add-on:**
   ```bash
   powershell -ExecutionPolicy Bypass -File scripts\build_addon.ps1
   ```
   Blender › Edit › Preferences › Get Extensions › ⌄ (top right) › **Install from Disk…** ›
   pick `dist\image_to_game_asset-2.1.1.zip`. In its preferences press **Check Setup**.
4. In Blender: 3D View › press **N** › **Image→3D** tab › pick a picture › **Generate**.

Full guide: [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Is anything sent online?
No. The picture, the AI work and the model all stay on your PC. The add-on talks to ComfyUI at
`http://127.0.0.1:8188`, which other computers can't reach, and starts it with `--offline`
(no paid online "partner" nodes, no web requests from its page). Internet is used only by the
installer, to download ComfyUI and the model files once.

## What's in this repo

```
addon/image_to_game_asset/   the Blender add-on (one job per file, see __init__.py)
  trellis_runner.py            start ComfyUI, send the TRELLIS.2 job, read progress (no Blender code)
  workflows/                   the TRELLIS.2 ComfyUI workflow + the model files it needs
  cleanup.py                   messy AI mesh → light, closed game mesh
  baking.py                    bake TRELLIS.2's colours, metal/roughness + normal maps onto the game mesh (+ photo colour match)
  materials.py / exporter.py   material presets / .glb export
  pipeline.py                  glue used by the buttons
  properties.py / preferences.py / operators.py / ui.py   settings, buttons, panel
scripts/
  install_comfyui.ps1          one-shot installer: ComfyUI portable + TRELLIS.2 models
  build_addon.ps1              packs the add-on into an installable zip
  make_addon_workflow.py       rebuilds workflows/ from ComfyUI's TRELLIS.2 template
  comfy_workflow_to_api.py     turns a ComfyUI editor workflow into the API format
tools/photo_texture/         experimental photo-fitting helpers (see its README)
tests/                       automatic tests with a fake ComfyUI, plus a real end-to-end test
docs/                        workflow, Windows findings, detailed characters, troubleshooting
```

## Documentation
- [WORKFLOW.md](docs/WORKFLOW.md): every step and setting, in plain words
- [WINDOWS.md](docs/WINDOWS.md): how the Windows route was chosen and tested
- [DETAILED_CHARACTERS.md](docs/DETAILED_CHARACTERS.md): better faces and feet with zoom-in crops
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): problems and their fixes

## Tests
```bash
powershell -ExecutionPolicy Bypass -File tests\run_tests.ps1
```
No graphics card needed: a fake ComfyUI stands in. They check progress, error messages, Cancel,
starting/stopping ComfyUI, cleaning to budget, watertight results, colour baking accuracy (from
colour layers and from textures), photo colour matching and `.glb` export with texture.

With the real ComfyUI and TRELLIS.2 (about 4 minutes, uses the graphics card):
```bash
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b --factory-startup -P tests\e2e_real_bpy.py -- picture.png out_folder
```

## Credits and licences
- **TRELLIS.2** by Microsoft (MIT): https://github.com/microsoft/TRELLIS.2
- **ComfyUI** by Comfy Org (GPL-3.0), with its native TRELLIS.2 nodes and model files:
  https://github.com/Comfy-Org/ComfyUI (downloaded by the installer, not part of this repo)
- **BiRefNet** by ZhengPeng7 (MIT): background removal
- **DINOv3** by Meta: picture understanding (its own licence; check before commercial use)
- Built with help from Claude (Anthropic).

Licences in this repo:
- Scripts, tools, tests, docs: **MIT** (see `LICENSE`).
- Blender add-on (`addon/image_to_game_asset/`): **GPL-3.0-or-later** (see its own `LICENSE`).
  Blender add-ons must use a GPL-compatible licence because they use Blender's Python API.

Third-party models have their own licences and terms.
