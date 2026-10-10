# I23D_win: Image to Game Asset (Blender + TRELLIS.2 on Windows)

> **Work in progress.** This is the Windows port of
> [I23D_mac](https://github.com/salpbes/I23D_mac). It starts as a copy of the Mac version; the
> Mac instructions below are kept until each part has a tested Windows replacement.

Turn **one picture** into a **game-ready 3D model** (`.glb`) from a single Blender panel, running
everything **locally** on a Windows PC with an NVIDIA graphics card and Microsoft's open-source
**TRELLIS.2** AI.

```
picture ──► TRELLIS.2 (detailed AI model) ──► Clean (5k / 15k / 60k triangles, closed solid)
        ──► TRELLIS colours baked into one texture ──► .glb for three.js / Godot / Unity
```

| | |
|---|---|
| **Target PC** | Windows 11, NVIDIA RTX 5060 Ti 16 GB (Blackwell), 64 GB memory, Blender 5.2 LTS |
| **Windows status** | Not working yet. Plan: [docs/WINDOWS.md](docs/WINDOWS.md) |
| **Planned TRELLIS.2 route** | ComfyUI's built-in TRELLIS.2 (no CUDA compiling); WSL2 as fallback |
| **Mac version** | Tested on Apple M4, 24 GB, macOS 27: see [I23D_mac](https://github.com/salpbes/I23D_mac) |

## Quick start (Mac)

1. **Hugging Face account:** request access to `facebook/dinov3-vitl16-pretrain-lvd1689m`
   and create a *read* token.
2. **Install TRELLIS.2 for Mac** (Terminal, ~30 min + ~15 GB download on first run):
   ```bash
   git clone https://github.com/salpbes/I23D_mac.git && cd I23D_mac
   bash scripts/install_trellis.sh --check          # checks your Mac, installs nothing
   HF_TOKEN_FILE=~/path/to/token.txt bash scripts/install_trellis.sh
   ```
   (or `export HF_TOKEN=hf_...` first, or log in once with `hf auth login`).
   The token is never printed or stored in this repo.
3. **Install the add-on:**
   ```bash
   bash scripts/build_addon.sh                      # makes dist/image_to_game_asset-1.1.0.zip
   ```
   Blender › Edit › Preferences › Get Extensions › ⌄ (top right) › **Install from Disk…** › pick the zip.
4. In Blender: 3D View › press **N** › **Image→3D** tab › pick a picture › **Generate**.

Full guide: [docs/WORKFLOW.md](docs/WORKFLOW.md).

## What's in this repo

```
addon/image_to_game_asset/   the Blender add-on (one job per file, see __init__.py)
  trellis_runner.py            start/stop TRELLIS.2, read its progress (no Blender code)
  cleanup.py                   messy AI mesh → light, closed game mesh
  baking.py                    bake TRELLIS.2's colours onto the game mesh (+ photo colour match)
  materials.py / exporter.py   material presets / .glb export
  pipeline.py                  glue used by the buttons
  properties.py / preferences.py / operators.py / ui.py   settings, buttons, panel
scripts/
  install_trellis.sh           one-shot Mac installer (trellis-mac + all fixes below)
  fix_background_remover.sh    BiRefNet on CPU in full precision (fixes an MPS type error)
  add_vertex_colours.sh        makes shape-only runs keep TRELLIS.2's colours
  diagnose_picture.sh          shows what TRELLIS.2 "sees" after background removal
  build_addon.sh               packs the add-on into an installable zip
tools/photo_texture/         experimental photo-fitting helpers (see its README)
tests/                       automatic tests with a fake TRELLIS.2 (bash tests/run_tests.sh)
docs/                        workflow, Windows findings, detailed characters, troubleshooting
```

## Documentation
- [WORKFLOW.md](docs/WORKFLOW.md): every step and setting, in plain words
- [WINDOWS.md](docs/WINDOWS.md): can it run on Windows? What's needed, three options, code changes
- [DETAILED_CHARACTERS.md](docs/DETAILED_CHARACTERS.md): better faces and feet with zoom-in crops
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): every problem we hit and its fix

## Tests
```bash
pip install bpy            # Blender as a Python module (needs the matching Python version)
bash tests/run_tests.sh
```
They use a fake TRELLIS.2 and check: progress parsing, cancel, cleaning to budget, watertight
result, colour baking accuracy, photo colour matching and `.glb` export with texture.

## Credits and licences
- **TRELLIS.2** by Microsoft (MIT): https://github.com/microsoft/TRELLIS.2
- **trellis-mac** (Apple Silicon port) by shivampkumar: https://github.com/shivampkumar/trellis-mac
- **BiRefNet** by ZhengPeng7 (MIT): background removal
- Built with help from Claude (Anthropic).

Licences in this repo:
- Scripts, tools, tests, docs: **MIT** (see `LICENSE`).
- Blender add-on (`addon/image_to_game_asset/`): **GPL-3.0-or-later** (see its own `LICENSE`).
  Blender add-ons must use a GPL-compatible licence because they use Blender's Python API.

Third-party models have their own licences and access terms (e.g. DINOv3 on Hugging Face).
