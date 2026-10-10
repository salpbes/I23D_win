#!/usr/bin/env bash
# fix_background_remover.sh - make TRELLIS.2's background remover (BiRefNet) reliable on Apple Silicon.
#
# Problem: the free ZhengPeng7/BiRefNet weights are stored in half precision (F16), while
# pictures arrive in full precision on the Mac GPU -> "Input type ... should be the same".
# Fix: run the background remover on the CPU in full precision, and always match the
# picture to the model. Costs a few seconds per picture; nothing else changes.
#
#   bash fix_background_remover.sh
set -euo pipefail

ROOT="${TRELLIS_DIR:-$HOME/Documents/sources/trellis-mac}"
F="$ROOT/TRELLIS.2/trellis2/pipelines/rembg/BiRefNet.py"
[[ -f "$F" ]] || { echo "STOP  Not found: $F"; exit 1; }

cp "$F" "$F.bak"
echo "Backup saved: $F.bak"

cat > "$F" <<'PY'
from typing import *
from transformers import AutoModelForImageSegmentation
import torch
from torchvision import transforms
from PIL import Image


class BiRefNet:
    """Background remover, patched for Apple Silicon.

    Always uses the free, ungated ZhengPeng7/BiRefNet weights, kept on the CPU in
    float32. Its weights ship in float16, which clashes with float32 inputs on MPS.
    """

    def __init__(self, model_name: str = "ZhengPeng7/BiRefNet"):
        self.model = AutoModelForImageSegmentation.from_pretrained(
            "ZhengPeng7/BiRefNet", trust_remote_code=True
        )
        self.model.eval()
        self.model.to(device="cpu", dtype=torch.float32)
        self.transform_image = transforms.Compose(
            [
                transforms.Resize((1024, 1024)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    @property
    def device(self):
        return next(self.model.parameters()).device

    # The pipeline moves models between devices to save memory.
    # This one stays on the CPU on purpose, so these are no-ops.
    def to(self, device):
        return self

    def cuda(self):
        return self

    def cpu(self):
        return self

    def __call__(self, image: Image.Image) -> Image.Image:
        image_size = image.size
        param = next(self.model.parameters())
        input_images = self.transform_image(image.convert("RGB")).unsqueeze(0)
        input_images = input_images.to(device=param.device, dtype=param.dtype)
        with torch.no_grad():
            preds = self.model(input_images)[-1].sigmoid().float().cpu()
        pred = preds[0].squeeze()
        pred_pil = transforms.ToPILImage()(pred)
        mask = pred_pil.resize(image_size)
        image.putalpha(mask)
        return image
PY
echo "Background remover replaced."

echo "Self-test (first time downloads ~440 MB)..."
cd "$ROOT"
.venv/bin/python - "$F" <<'PY'
import importlib.util, sys, time
from PIL import Image
spec = importlib.util.spec_from_file_location("birefnet_patched", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
remover = mod.BiRefNet()
remover.to("mps")  # what the pipeline does; must be harmless now
t = time.time()
out = remover(Image.new("RGB", (640, 480), (200, 60, 60)))
assert out.mode == "RGBA" and out.size == (640, 480)
print(f"OK    Background remover works ({time.time() - t:.1f}s per picture)")
PY
echo "Done. Press Generate in Blender again."
