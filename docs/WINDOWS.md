# Using this on Windows: findings and plan

> **Short answer:** the Blender add-on itself is plain Python and would run on Windows Blender with
> a few small changes. The hard part is **TRELLIS.2** (the AI that makes the 3D model). On Windows it
> needs a **strong NVIDIA graphics card**. This repo has **only been tested on a Mac (Apple M4, 24 GB)**.
> Nothing below has been tested on a Windows PC yet.

Status: research notes, October 2026.

## Update for I23D_win (2026-10-10)

**Target PC:** NVIDIA RTX 5060 Ti, 16 GB VRAM, compute capability 12.0 (Blackwell, driver 617.42),
Ryzen 9 3900X, 64 GB memory, Windows 11, Blender 5.2.2 LTS. No WSL, CUDA toolkit or Visual Studio
C++ tools installed yet.

- **Blackwell catch:** the official `setup.sh` installs PyTorch 2.6 + CUDA 12.4 and a prebuilt
  flash-attn. None of these support RTX 50 cards (sm_120), so the official install won't run as-is.
  Blackwell needs CUDA 12.8 or newer (CUDA 13 builds are common).
- **16 GB catch:** below the official 24 GB. Plan for 512 detail first; 1024 is uncertain.
- **New Option D: ComfyUI's built-in TRELLIS.2 (now the first choice).** Since ComfyUI 0.34
  (August 2026) TRELLIS.2 runs in ComfyUI without compiled CUDA extensions, on current PyTorch,
  with a ready-made workflow template (`3d_pixal3d_trellis2_image_to_model`). The add-on would send
  jobs to ComfyUI's local web interface (`http://127.0.0.1:8188`) instead of starting
  `generate.py`. Not yet tested on Windows or on a 16 GB card.
  Source: https://blog.comfy.org/p/trellis2-and-pixal3d-are-now-native
- **Option A (WSL2) for Blackwell:** https://github.com/Creepybits/trellis2-blackwell-wsl
  (CUDA 13, xformers, tested only on an RTX 5090 32 GB; known WSL memory crashes). Fallback.

---

## 1. What runs where

| Part | What it is | Mac (tested) | Windows (not yet) |
|---|---|---|---|
| Blender add-on (`addon/`) | Panel, cleaning, colour baking, `.glb` export | ✅ works | 🟡 needs 3 small code changes (see §4) |
| TRELLIS.2 | The AI that turns a picture into 3D | ✅ via **trellis-mac** (Apple Silicon port) | 🟡 needs the **official** version + NVIDIA GPU |
| Install scripts (`scripts/*.sh`) | Set up trellis-mac and patch it | ✅ | ❌ Mac only (bash, Homebrew, `textutil`, `caffeinate`) |
| Photo tools (`tools/`) | Experimental photo-fitting helpers | ✅ | ✅ plain Python (numpy, OpenCV, Pillow, SciPy) |

**Why is the Mac version not usable on Windows?** trellis-mac replaces NVIDIA-only parts of TRELLIS.2
with Apple "Metal" (MPS) code. Windows PCs don't have Metal, so on Windows you use Microsoft's
**official TRELLIS.2**, which is built for NVIDIA graphics cards (CUDA).

---

## 2. What the official TRELLIS.2 asks for

From the official page (github.com/microsoft/TRELLIS.2), checked October 2026:

- **System:** "currently tested only on Linux". Windows is not mentioned.
- **Graphics card:** NVIDIA, **at least 24 GB of video memory (VRAM)**. Verified on A100 and H100
  (data-centre cards).
- **CUDA:** 12.4 recommended (PyTorch 2.6.0 + CUDA 12.4).
- **Python:** 3.8 or newer.
- **Output:** a `.glb` with **real PBR textures** already inside (the Mac version only gives
  colours stored on the points; see §5).
- **Sizes:** 512³, 1024³ and 1536³ detail (about 3 s, 17 s and 60 s on an H100).

**What this means in plain words:** a home PC with a 24 GB card (e.g. RTX 3090 / 4090 / 5090)
is the "safe" setup. Cards with 8–16 GB *might* work with community versions at the lowest
detail (512), but that is a community claim, not something we have checked.

---

## 3. Three ways to run TRELLIS.2 on Windows

### Option A: WSL2 (Linux inside Windows), the recommended route
**What:** Windows' built-in Linux (WSL2) with Ubuntu. NVIDIA drivers on Windows pass the GPU through.
**Why:** the official code is only tested on Linux, so this is the closest match.
**How (outline):**
1. Install the latest NVIDIA Windows driver (it includes WSL GPU support).
2. In PowerShell (admin): `wsl --install -d Ubuntu`
3. Inside Ubuntu: install the CUDA 12.4 toolkit for WSL, then follow the official TRELLIS.2
   install steps (`git clone --recursive …`, `setup.sh`).
4. Log in to Hugging Face (`hf auth login`) and request access to the gated models
   (DINOv3, and RMBG-2.0 or swap to BiRefNet like the Mac script does).

**Catch:** the add-on runs in *Windows* Blender, but TRELLIS.2 lives *inside WSL*. The add-on would
start it through `wsl.exe` (see §4, change 4).

### Option B: Community Windows installers
- **trellis2.app** guide: a Windows install walkthrough. It claims 6–8 GB VRAM can work at 512 detail.
  *Not verified by us.*
- **IgorAherne/trellis-stable-projectorz** (GitHub): a Windows-friendly packaging of TRELLIS with a
  one-click style installer.

**Why consider it:** easiest to install, runs natively in Windows.
**Catch:** unofficial, versions change, and the command-line arguments may differ from
`generate.py` that the add-on expects. Check before relying on it.

### Option C: Native Windows with the official code
Possible in principle (PyTorch with CUDA runs on Windows), but several of TRELLIS.2's compiled
GPU extensions are built and tested for Linux. Expect build errors (Visual Studio C++ tools,
CUDA toolkit versions). **Only for people comfortable fixing compiler problems.**

### No suitable GPU?
Use the free online TRELLIS.2 page on Hugging Face Spaces, download the `.glb`, and use only
**step 2 (Clean)** and **step 3 (Export)** of the add-on (select the imported model, press
*Clean Selected*). Those steps don't need TRELLIS.2 at all.

---

## 4. Changes the add-on needs for Windows

All of them are in `addon/image_to_game_asset/trellis_runner.py` (the only file that starts
programs), plus one in `preferences.py`. The rest of the add-on (cleaning, baking, export,
panel) uses only Blender's own Python and is already cross-platform.

| # | What | Why | How |
|---|---|---|---|
| 1 | Python path | Windows virtual environments use `.venv\Scripts\python.exe`, not `.venv/bin/python` | In `build_command` and `check_setup`: pick `Scripts/python.exe` when `sys.platform == "win32"` |
| 2 | Stopping a run (Cancel) | `start_new_session=True` and `os.killpg` don't exist on Windows | On Windows start with `creationflags=subprocess.CREATE_NEW_PROCESS_GROUP` and stop with `proc.terminate()` / `taskkill /T /F /PID <pid>` (kills the child processes too) |
| 3 | Default folders | `~/Documents/sources/trellis-mac` is a Mac default | Default to the official `TRELLIS.2` folder and a Windows output folder; let *Check Setup* explain what is missing |
| 4 | WSL option (if Option A) | TRELLIS.2 lives inside Linux | A preference "Run through WSL"; the command becomes `wsl.exe -d Ubuntu -- bash -lc "cd … && python …"`, and Windows paths are converted with `wslpath` |
| 5 | Script arguments | Official TRELLIS.2 has no `generate.py` with the same options as trellis-mac | Ship a small `generate.py` wrapper for the official pipeline that accepts the same options (`--seed`, `--output`, `--pipeline-type`, `--no-texture`) and prints the same progress words the add-on listens for ("Sampling sparse structure", "Saved: …glb") |
| 6 | Keep-awake | `caffeinate` is Mac only | Already handled: it is only used when `sys.platform == "darwin"` |

Rough size of the work: changes 1–3 and 6 are small (an hour or two). Changes 4–5 are a small
project of their own and need a Windows PC with an NVIDIA card to test.

---

## 5. Colours work differently on Windows (important)

- **Mac (trellis-mac):** texture baking is slow and noisy, so we run shape-only (`--no-texture`)
  and our patch (`scripts/add_vertex_colours.sh`) copies TRELLIS.2's colours onto the model's points.
  The add-on then bakes those point colours into a clean texture for the light game model.
- **Windows (official TRELLIS.2):** the `.glb` comes with **real textures** (colour, roughness,
  metal). So the add-on needs a second bake path: **"bake from the original's material/texture"**
  instead of "bake from the colour layer". Blender's bake can do this (bake *Diffuse colour* from
  selected to active), so it's a change in `baking.py`, not a new tool.

Until that exists, on Windows choose a plain material preset (Clay, Gold, …) instead of
*TRELLIS colours*; the add-on falls back to Clay automatically when there's no colour layer.

---

## 6. Suggested order to make Windows work

1. **Check the hardware:** which NVIDIA card and how much VRAM? (Task Manager › Performance › GPU.)
2. Get TRELLIS.2 running **by itself** (Option A or B) and make one `.glb` from a test picture.
3. Use the add-on's **Clean** and **Export** on that `.glb`. This already works today.
4. Add changes 1–3 (+4 if WSL) so the **Generate** button works.
5. Add the "bake from texture" path (§5) so *TRELLIS colours* works with real textures.
