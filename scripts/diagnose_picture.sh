#!/usr/bin/env bash
# diagnose_picture.sh - show exactly what TRELLIS.2 "sees" after background removal.
#   bash scripts/diagnose_picture.sh /path/to/picture.jpg
# Writes into ~/Downloads/trellis-debug/:
#   <name>_mask.png        white = kept as the object, black = removed as background
#   <name>_trellis_sees.png the exact cropped picture TRELLIS.2 builds the 3D model from
#   <name>_report.txt      numbers + any model-loading warnings
set -uo pipefail
IMG="${1:?Usage: bash diagnose_picture.sh /path/to/picture}"
ROOT="${TRELLIS_DIR:-$HOME/Documents/sources/trellis-mac}"
OUT="${DEBUG_DIR:-$HOME/Downloads/trellis-debug}"
mkdir -p "$OUT"
cd "$ROOT" || exit 1
.venv/bin/python - "$IMG" "$OUT" "$ROOT/TRELLIS.2/trellis2/pipelines/rembg/BiRefNet.py" <<'PY' 2>&1 | tee "$OUT/$(basename "${IMG%.*}")_report.txt"
import importlib.util, sys, time, logging
import numpy as np
from PIL import Image
from transformers.utils import logging as hf_logging
hf_logging.set_verbosity_warning()

img_path, out_dir, remover_file = sys.argv[1:4]
name = img_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

spec = importlib.util.spec_from_file_location("birefnet_patched", remover_file)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
remover = mod.BiRefNet()
p = next(remover.model.parameters())
print(f"Remover on {p.device}, {p.dtype}, {sum(x.numel() for x in remover.model.parameters())/1e6:.0f}M params")

img = Image.open(img_path)
print(f"Picture: {img.mode} {img.size}")
# --- same steps as TRELLIS.2 preprocess_image ---
scale = min(1, 1024 / max(img.size))
if scale < 1:
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
t = time.time()
out = remover(img.convert("RGB"))
print(f"Background removal took {time.time() - t:.1f}s")
alpha = np.array(out)[:, :, 3]
Image.fromarray(alpha).save(f"{out_dir}/{name}_mask.png")
kept = (alpha > 0.8 * 255).mean()
print(f"Mask: min {alpha.min()} max {alpha.max()} mean {alpha.mean():.0f} | kept as object: {kept:.1%} of the picture")
ys, xs = np.nonzero(alpha > 0.8 * 255)
if len(xs) == 0:
    print("PROBLEM: nothing was kept as the object"); sys.exit(0)
x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
print(f"Object box: x {x0}-{x1}, y {y0}-{y1} of {alpha.shape[1]}x{alpha.shape[0]}")
cx, cy, size = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)
crop = out.crop((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2))
arr = np.array(crop).astype(np.float32) / 255
Image.fromarray((arr[:, :, :3] * arr[:, :, 3:4] * 255).astype(np.uint8)).save(f"{out_dir}/{name}_trellis_sees.png")
print(f"Saved to {out_dir}")
PY
