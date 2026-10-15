"""Export objects as .glb files (one file per object) for three.js / game engines."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import bpy

# What made a model, for the licence record next to each .glb (see write_licences).
MODELS = {
    "TRELLIS.2": ("Microsoft", "MIT", "https://github.com/microsoft/TRELLIS.2",
                  "made the 3D model from the picture"),
    "Pixal3D": ("Tencent ARC Lab and Tsinghua University", "MIT (its third-party parts keep their own terms, see its NOTICE)",
                "https://huggingface.co/TencentARC/Pixal3D", "made the 3D model from the front and back pictures"),
}
ALWAYS = [
    ("DINOv3", "Meta", "DINOv3 License", "https://github.com/facebookresearch/dinov3",
     "read the picture for the 3D model"),
    ("BiRefNet", "ZhengPeng7", "MIT", "https://github.com/ZhengPeng7/BiRefNet", "removed the background"),
    ("ComfyUI", "Comfy Org", "GPL-3.0", "https://github.com/Comfy-Org/ComfyUI", "ran the AI models"),
    ("Image to Game Asset", "I23D_win", "GPL-3.0-or-later", "https://github.com/salpbes/I23D_win",
     "cleaned, coloured and exported the model"),
]


def export_glb(obj: bpy.types.Object, folder: str | Path, draco: bool = False) -> Path:
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{obj.name}.glb"

    view_layer = bpy.context.view_layer
    previous_selection = [o for o in view_layer.objects if o.select_get()]
    previous_active = view_layer.objects.active
    obj.hide_set(False)
    for other in previous_selection:
        other.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    try:
        bpy.ops.export_scene.gltf(
            filepath=str(path),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_materials="EXPORT",
            export_draco_mesh_compression_enable=draco,
        )
    finally:
        obj.select_set(False)
        for other in previous_selection:
            if other.name in view_layer.objects:
                other.select_set(True)
        view_layer.objects.active = previous_active
    return path


def write_licences(glb: Path, *, generator: str, seed=None, painted: bool = False) -> Path:
    """<name>.licences.json next to the .glb: which models made it and under which licences."""
    by, licence, url, role = MODELS.get(generator, MODELS["TRELLIS.2"])
    made_with = [{"name": generator, "by": by, "licence": licence, "url": url, "role": role}]
    made_with += [{"name": n, "by": b, "licence": l, "url": u, "role": r} for n, b, l, u, r in ALWAYS]
    doc = {
        "asset": glb.name,
        "made_on": datetime.date.today().isoformat(),
        "seed": seed,
        "pictures_painted_on": painted,
        "made_with": made_with,
        "note": "Each licence has its own terms; check them before you sell or publish this model. "
                "You are responsible for having the rights to the pictures you used. Not legal advice.",
    }
    path = glb.with_suffix(".licences.json")
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path
