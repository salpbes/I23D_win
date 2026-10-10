#!/usr/bin/env bash
# add_vertex_colours.sh - make trellis-mac's shape-only mode (--no-texture) actually save
# TRELLIS.2's own colours on the model.
#
# Why: generate.py prints "Exporting with vertex colors" but saves a mesh with NO colours.
# The colours are computed anyway (the "surface" step), so we just copy them onto the
# vertices. No extra AI work, no slow texture baking. Also prints a size check so we can
# see whether the colour grid and the shape line up.
#
#   bash scripts/add_vertex_colours.sh
set -euo pipefail
F="${TRELLIS_DIR:-$HOME/Documents/sources/trellis-mac}/generate.py"
[[ -f "$F" ]] || { echo "STOP  Not found: $F"; exit 1; }
if grep -q "I23D vertex colours" "$F"; then echo "Already patched."; exit 0; fi
cp "$F" "$F.bak"; echo "Backup: $F.bak"
python3 - "$F" <<'PY'
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
echo "Patched. Shape-only runs now keep TRELLIS.2's colours."
