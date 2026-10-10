#!/usr/bin/env bash
# =============================================================================
# install_trellis.sh  -  sets up TRELLIS.2 (trellis-mac) on an Apple Silicon Mac
#
#   bash install_trellis.sh --check   -> only checks this Mac, installs nothing
#   bash install_trellis.sh           -> check + full install + one test model
#
# Everything goes into ~/Documents/sources (change it with I23D_HOME=/some/folder):
#   trellis-mac/           the program
#   trellis-output/        generated 3D models (.glb)
#   trellis-install.log    full log of this script
#
# Hugging Face login - the first one that exists is used, the token is never printed:
#   1. a token file:  HF_TOKEN_FILE=/path/to/token.txt   (.txt or .rtf; default
#                     ~/Documents/sources/hf_tokens/trellis.rtf)
#   2. the HF_TOKEN environment variable
#   3. a login you already made with:  hf auth login
# =============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${I23D_HOME:-$HOME/Documents/sources}"
REPO_DIR="$INSTALL_DIR/trellis-mac"
OUT_DIR="$INSTALL_DIR/trellis-output"
TOKEN_FILE="${HF_TOKEN_FILE:-$INSTALL_DIR/hf_tokens/trellis.rtf}"
LOG="$INSTALL_DIR/trellis-install.log"
CHECK_ONLY=0; [[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

ok()   { printf '  OK    %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; }
fail() { printf '  STOP  %s\n' "$*"; exit 1; }
step() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$INSTALL_DIR"
exec > >(tee -a "$LOG") 2>&1
echo; echo "----- $(date) -----"

# Keep the Mac awake while this script runs.
caffeinate -i -w $$ &

# -----------------------------------------------------------------------------
step "1. Checking this Mac"
ARCH=$(uname -m)
CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo unknown)
MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
FREE_GB=$(df -g "$INSTALL_DIR" | awk 'NR==2 {print $4}')
echo "  Chip:      $CHIP ($ARCH)"
echo "  Memory:    ${MEM_GB} GB"
echo "  Free disk: ${FREE_GB} GB"
echo "  macOS:     $(sw_vers -productVersion)"
echo

[[ "$ARCH" == "arm64" ]] && ok "Apple Silicon" || fail "Needs an Apple Silicon (M-series) Mac."

if   (( MEM_GB >= 24 )); then ok "Memory is enough (${MEM_GB} GB)"
elif (( MEM_GB >= 16 )); then warn "Memory is tight (${MEM_GB} GB). Shape-only models should work; close other apps first."
else fail "Under 16 GB memory is too little for TRELLIS.2. Use the free online page instead."
fi

(( FREE_GB >= 30 )) && ok "Disk space is enough" || fail "Need about 30 GB free disk (you have ${FREE_GB} GB)."

command -v git >/dev/null && ok "git found" || fail "git missing. Run:  xcode-select --install   then re-run this script."

if   command -v uv   >/dev/null; then ok "uv found"
elif command -v brew >/dev/null; then warn "uv missing - will install it with Homebrew"
else                                  warn "uv missing - will install it with uv's official installer"
fi

if xcodebuild -version >/dev/null 2>&1; then ok "Full Xcode found (faster texturing possible)"
else warn "Full Xcode not found - texturing will use the slower fallback. Fine for shapes."
fi

if   [[ -f "$TOKEN_FILE" ]];   then ok "Token file found"
elif [[ -n "${HF_TOKEN:-}" ]]; then ok "HF_TOKEN is set"
else warn "No token file at $TOKEN_FILE and no HF_TOKEN - this only works if you already ran: hf auth login"
fi

if (( CHECK_ONLY )); then echo; echo "Check finished. Nothing was installed."; exit 0; fi

# -----------------------------------------------------------------------------
step "2. Installing uv (Python helper)"
if ! command -v uv >/dev/null; then
  if command -v brew >/dev/null; then brew install uv
  else curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"
  fi
fi
command -v uv >/dev/null && ok "uv ready" || fail "uv install failed."

# -----------------------------------------------------------------------------
step "3. Downloading trellis-mac"
if [[ -d "$REPO_DIR/.git" ]]; then ok "Already downloaded"
else git clone https://github.com/shivampkumar/trellis-mac.git "$REPO_DIR" || fail "Download failed."
fi
cd "$REPO_DIR" || fail "Cannot open $REPO_DIR"

# -----------------------------------------------------------------------------
step "4. Metal toolchain (optional, for faster texturing)"
if xcodebuild -version >/dev/null 2>&1; then
  xcodebuild -downloadComponent MetalToolchain && ok "Installed" || warn "Skipped (not required)"
else
  warn "Skipped (no full Xcode, not required)"
fi

# -----------------------------------------------------------------------------
step "5. Running trellis-mac setup (10-20 minutes)"
bash setup.sh || fail "setup.sh failed - see the lines above."
# shellcheck disable=SC1091
source .venv/bin/activate || fail "Could not activate the Python environment."
python -c 'import sys; assert sys.version_info >= (3, 11)' \
  && ok "Python $(python -c 'import platform; print(platform.python_version())')" \
  || fail "Python 3.11+ needed in .venv. Delete $REPO_DIR/.venv and re-run."

# -----------------------------------------------------------------------------
step "6. Logging in to Hugging Face"
HF_TOKEN_VALUE=""
if [[ -f "$TOKEN_FILE" ]]; then
  # textutil turns .rtf into plain text; plain .txt files pass straight through
  HF_TOKEN_VALUE=$( (textutil -convert txt -stdout "$TOKEN_FILE" 2>/dev/null || cat "$TOKEN_FILE") | grep -oE 'hf_[A-Za-z0-9]+' | head -1)
  [[ -n "$HF_TOKEN_VALUE" ]] || fail "No token starting with hf_ found inside $TOKEN_FILE"
elif [[ -n "${HF_TOKEN:-}" ]]; then
  HF_TOKEN_VALUE="$HF_TOKEN"
fi
if [[ -n "$HF_TOKEN_VALUE" ]]; then
  HF_TOKEN_VALUE="$HF_TOKEN_VALUE" python - <<'PY' >/dev/null 2>&1 || fail "Login failed - the token may be wrong or expired."
import os
from huggingface_hub import login
login(token=os.environ["HF_TOKEN_VALUE"], add_to_git_credential=False)
PY
  unset HF_TOKEN_VALUE
  ok "Logged in (token not shown)"
else
  python -c 'from huggingface_hub import whoami; whoami()' >/dev/null 2>&1 \
    && ok "Using your existing Hugging Face login" \
    || fail "Not logged in to Hugging Face. Set HF_TOKEN_FILE or HF_TOKEN, or run: hf auth login"
fi

python - <<'PY' || fail "No access to DINOv3 yet - check the approval on huggingface.co."
from huggingface_hub import hf_hub_download
hf_hub_download("facebook/dinov3-vitl16-pretrain-lvd1689m", "config.json")
print("  OK    DINOv3 access confirmed")
PY

# -----------------------------------------------------------------------------
step "7. Swapping background remover to BiRefNet (free, MIT licence, no form)"
F="TRELLIS.2/trellis2/pipelines/rembg/BiRefNet.py"
PATTERN='"ZhengPeng7/BiRefNet", trust_remote_code'
if grep -q "$PATTERN" "$F"; then ok "Already swapped"
else
  sed -i '' 's/model_name, trust_remote_code=True/"ZhengPeng7\/BiRefNet", trust_remote_code=True/' "$F"
  grep -q "$PATTERN" "$F" && ok "Swapped" || fail "Swap failed - $F looks different than expected."
fi
# BiRefNet needs one extra package that setup.sh doesn't install.
uv pip install --python .venv/bin/python einops && ok "einops installed" || fail "Could not install einops."
# BiRefNet's weights are half precision; run it on the CPU in full precision instead.
FIX="$SCRIPT_DIR/fix_background_remover.sh"
if [[ -f "$FIX" ]]; then bash "$FIX" || fail "Background remover fix failed"
else warn "fix_background_remover.sh not found next to this script - run it before using pictures without transparency"; fi


# TRELLIS.2 colours: shape-only runs claim to save colours but don't; copy them onto the model's points.
G="generate.py"
if grep -q "I23D vertex colours" "$G"; then ok "Colour patch already in place"
else
  cp "$G" "$G.bak"
python3 - "$G" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = "        tm = trimesh.Trimesh(vertices=verts, faces=faces)\n"
new = '''        tm = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        if has_voxels:  # I23D vertex colours
            import numpy as _np
            from scipy.spatial import cKDTree
            _vc = mesh_out.coords.cpu().numpy().astype(_np.float32)
            _va = mesh_out.attrs.cpu().float().numpy()
            _org = _np.asarray(mesh_out.origin.cpu().numpy(), dtype=_np.float32)
            _vs = float(mesh_out.voxel_size)
            _centres = _vc * _vs + _org + _vs * 0.5
            print(f"  Colour grid: {len(_vc):,} voxels, size {_vs:.5f}, spans {_centres.min(0).round(3)} .. {_centres.max(0).round(3)}")
            print(f"  Shape spans: {verts.min(0).round(3)} .. {verts.max(0).round(3)}")
            _d, _i = cKDTree(_centres).query(verts, k=4, workers=-1)
            print(f"  Typical vertex-to-colour distance: {_np.median(_d[:, 0]) / _vs:.2f} voxels")
            _w = 1.0 / (_d + _vs * 0.1); _w /= _w.sum(1, keepdims=True)
            _rgb = _np.clip((_va[_i][..., 0:3] * _w[..., None]).sum(1), 0, 1)
            tm.visual.vertex_colors = _np.concatenate(
                [(_rgb * 255).astype(_np.uint8), _np.full((len(_rgb), 1), 255, _np.uint8)], 1)
            print("  Vertex colours added")
'''
assert old in s, "generate.py looks different than expected"
open(p, "w").write(s.replace(old, new, 1))
PY

  grep -q "I23D vertex colours" "$G" && ok "Colour patch added" || fail "Colour patch failed"
fi

# -----------------------------------------------------------------------------
step "8. Test model (first run downloads ~15 GB, then ~5 minutes)"
mkdir -p "$OUT_DIR"
TEST_IMG=$(ls TRELLIS.2/assets/example_image/*.webp 2>/dev/null | head -1)
[[ -n "$TEST_IMG" ]] || fail "No example picture found."
cp "$TEST_IMG" "$OUT_DIR/test_input.webp"
echo "  Test picture copied to: $OUT_DIR/test_input.webp"
python generate.py "$TEST_IMG" --output "$OUT_DIR/test_model" --no-texture
RC=$?
if [[ -f "$OUT_DIR/test_model.glb" ]]; then
  ok "Test model saved: $OUT_DIR/test_model.glb"
elif (( RC == 2 )); then
  fail "macOS stopped the graphics step (GPU watchdog). Close other apps / unplug external displays and re-run."
else
  fail "No test model was made - see the error above."
fi

# -----------------------------------------------------------------------------
step "Done"
cat <<EOF
  Next time, to make a model from your own picture:

    cd "$REPO_DIR"
    source .venv/bin/activate
    python generate.py /path/to/picture.png --output "$OUT_DIR/my_model" --no-texture

  Full log: $LOG
EOF
