"""Export objects as .glb files (one file per object) for three.js / game engines."""

from __future__ import annotations

from pathlib import Path

import bpy


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
