# Problems we hit on the Mac, and the fixes

| Problem (what you see) | Why | Fix |
|---|---|---|
| Hugging Face asks for a company website / Discord for **briaai/RMBG-2.0** | That background remover is gated | The installer swaps it for **ZhengPeng7/BiRefNet** (MIT, no form) |
| `ModuleNotFoundError: einops` | BiRefNet needs it; trellis-mac's setup doesn't install it | `uv pip install --python .venv/bin/python einops` (installer step 7) |
| `RuntimeError: Input type (MPSFloatType) and weight type (MPSHalfType) should be the same` | BiRefNet's weights are half precision; the Mac GPU path mixes types | `scripts/fix_background_remover.sh`: runs it on the CPU in full precision |
| Why DINOv3? | TRELLIS.2 uses it to "understand" the picture. It's gated: click *Agree* on its Hugging Face page | Wait for approval, then re-run the installer |
| Shape-only models have **no colours** although the log says "Exporting with vertex colors" | trellis-mac bug: colours aren't saved in `--no-texture` mode | `scripts/add_vertex_colours.sh` (also inside the installer) copies TRELLIS.2's colours onto the points |
| Local result differs from the online demo | Different **seed** (not a bug). `scripts/diagnose_picture.sh` proved the background removal was fine | Random seed is on by default; run 2–3 times |
| "High" detail: 100% progress, then nothing for 50+ minutes | Out of memory on 24 GB while building the mesh | Use Fast (512). The panel shows "last output Xs ago" and warns when it looks stuck |
| Exit code 2 / GPU watchdog | macOS stopped a long GPU job | Close other apps, unplug extra displays, run again |
| "No textures" on the cleaned model | Viewport is in *Solid* mode | Switch to **Material Preview** |
| Model lies on its back | trellis-mac output is rotated | *Fix orientation* (Advanced, on by default) |
| Washed-out colours | TRELLIS.2 colours are pale | *Match photo colours* slider |
| Thin parts vanish after cleaning | Voxel rebuild too coarse | *Rebuild detail: Fine* or raise *Thicken* |

## Useful commands (Mac Terminal)
```bash
bash scripts/install_trellis.sh --check     # checks the Mac, installs nothing
bash scripts/diagnose_picture.sh photo.jpg  # what TRELLIS.2 "sees" after background removal
```
Each run writes `<name>_log.txt` next to the model; the panel's **Open Log** button opens it.
