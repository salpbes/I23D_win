"""Build the TRELLIS.2 workflow that ships inside the add-on.

Takes ComfyUI's "3d_pixal3d_trellis2_image_to_model" template, converts it to the API format,
picks TRELLIS.2 at its Pixal3D/TRELLIS.2 switch, keeps only the nodes that feed the saved .glb,
and labels each step for the add-on's progress bar. Needs a running ComfyUI (for /object_info).

    python scripts/make_addon_workflow.py [template.json] [--server http://127.0.0.1:8188]

Without a template path, the template is downloaded from Comfy-Org/workflow_templates.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from comfy_workflow_to_api import convert, fetch_object_info

TEMPLATE_URL = ("https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/"
                "templates/3d_pixal3d_trellis2_image_to_model.json")
OUT = Path(__file__).resolve().parents[1] / "addon" / "image_to_game_asset" / "workflows" / \
    "trellis2_image_to_glb.json"
OUTPUT_NODE = "Save3DAdvanced"

# Loader input -> ComfyUI models subfolder (for the add-on's setup check and the installer).
MODEL_INPUTS = {
    ("UNETLoader", "unet_name"): "diffusion_models",
    ("VAELoader", "vae_name"): "vae",
    ("CLIPVisionLoader", "clip_name"): "clip_vision",
    ("LoadBackgroundRemovalModel", "bg_removal_name"): "background_removal",
}

# The add-on bakes only the base colour onto its own game mesh, so ComfyUI's ambient-occlusion
# and normal-map bakes (72 of 182 s on an RTX 5060 Ti) are left out. Both inputs are optional.
SKIP_INPUTS = {("ApplyTextureToMesh", "occlusion"), ("ApplyTextureToMesh", "normal_map")}

STEPS = {
    "load": "Loading the AI models",
    "background": "Removing the background",
    "picture": "Reading the picture",
    "structure": "Step 1 of 4: rough shape",
    "shape": "Step 2 of 4: detailed shape",
    "upsample": "Step 3 of 4: finer shape",
    "texture": "Step 4 of 4: surface colours",
    "decode": "Building the 3D mesh",
    "tidy": "Tidying the mesh",
    "bake": "Baking textures",
    "save": "Saving the model",
    "other": "Working",
}
# Seconds per node on an RTX 5060 Ti 16 GB, detail 1024, models already in memory
# (tests/calibrate_progress.py). Only the proportions matter; unlisted nodes count 1.
SECONDS = {"structure": 5, "shape": 4, "upsample": 15, "texture": 7,
           "UnwrapMesh": 27, "BakeTextureFromVoxel": 27, "RemeshMesh": 4, "DecimateMesh": 4,
           "MeshToFile3D": 4, "Save3DAdvanced": 2, "VaeDecodeShapeTrellis": 2,
           "VaeDecodeTextureTrellis": 2, "VaeDecodeStructureTrellis2": 2, "MeshSmoothNormals": 2}
BY_TYPE = {
    "UNETLoader": "load", "VAELoader": "load", "CLIPVisionLoader": "load",
    "LoadBackgroundRemovalModel": "load", "LoadImage": "load",
    "RemoveBackground": "background", "ImageCropToMask": "background",
    "Trellis2Conditioning": "picture", "Trellis2ShapeStage": "picture",
    "Trellis2TextureStage": "picture", "Trellis2UpsampleStage": "upsample",
    "VaeDecodeStructureTrellis2": "decode", "VaeDecodeShapeTrellis": "decode",
    "VaeDecodeTextureTrellis": "decode",
    "RemeshMesh": "tidy", "DecimateMesh": "tidy", "UnwrapMesh": "tidy", "MeshSmoothNormals": "tidy",
    "BakeTextureFromVoxel": "bake", "BakeNormalMapFromMesh": "bake",
    "BakeAmbientOcclusion": "bake", "ApplyTextureToMesh": "bake",
    "MeshToFile3D": "save", "Save3DAdvanced": "save",
}
# A KSampler's job is told by the node that uses its result.
KSAMPLER_BY_CONSUMER = {
    "VaeDecodeStructureTrellis2": "structure",
    "Trellis2UpsampleStage": "shape",
    "VaeDecodeShapeTrellis": "upsample",
    "VaeDecodeTextureTrellis": "texture",
}


def pick_trellis2(api: dict) -> dict:
    """Resolve every ComfySwitchNode to its TRELLIS.2 side, then drop what the .glb doesn't need."""
    trellis_flags = {nid for nid, n in api.items() if n["class_type"] == "PrimitiveBoolean"
                     and "trellis2" in n["_meta"]["title"].lower()}
    if not trellis_flags:
        raise ValueError("No 'Switch to Trellis2' boolean found in the template")
    choice = {}
    for nid, n in api.items():
        if n["class_type"] == "ComfySwitchNode":
            sw = n["inputs"]["switch"]
            on = sw[0] in trellis_flags if isinstance(sw, list) else bool(sw)
            choice[nid] = n["inputs"]["on_true" if on else "on_false"]
    for n in api.values():
        for key, value in n["inputs"].items():
            while isinstance(value, list) and value[0] in choice:
                value = choice[value[0]]
            n["inputs"][key] = value
        for kind, key in SKIP_INPUTS:
            if n["class_type"] == kind:
                n["inputs"].pop(key, None)
    outputs = [nid for nid, n in api.items() if n["class_type"] == OUTPUT_NODE]
    if len(outputs) != 1:
        raise ValueError(f"Expected one {OUTPUT_NODE}, found {len(outputs)}")
    keep, todo = set(), outputs[:]
    while todo:
        nid = todo.pop()
        if nid not in keep:
            keep.add(nid)
            todo += [v[0] for v in api[nid]["inputs"].values() if isinstance(v, list)]
    return {nid: n for nid, n in api.items() if nid in keep}


def label_steps(api: dict) -> None:
    consumers = {}
    for n in api.values():
        for value in n["inputs"].values():
            if isinstance(value, list):
                consumers.setdefault(value[0], []).append(n["class_type"])
    for nid, n in api.items():
        if n["class_type"] == "KSampler":
            step = next((KSAMPLER_BY_CONSUMER[c] for c in consumers.get(nid, [])
                         if c in KSAMPLER_BY_CONSUMER), "other")
        else:
            step = BY_TYPE.get(n["class_type"], "other")
        n["_meta"]["i23d_step"] = step
        n["_meta"]["i23d_label"] = STEPS[step]
        n["_meta"]["i23d_weight"] = SECONDS.get(step if n["class_type"] == "KSampler" else n["class_type"], 1)
    missing = {s for s in ("structure", "shape", "upsample", "texture")
               if not any(n["_meta"]["i23d_step"] == s for n in api.values())}
    if missing:
        raise ValueError(f"Could not find the KSampler for: {sorted(missing)}")


def required_models(api: dict, template: dict) -> list[dict]:
    """Model files the workflow loads, with the download links the template gives for them."""
    urls = {m["name"]: m["url"] for n in template["nodes"]
            for m in (n.get("properties", {}).get("models") or [])}
    models = []
    for n in api.values():
        for (kind, key), folder in MODEL_INPUTS.items():
            if n["class_type"] == kind and isinstance(n["inputs"].get(key), str):
                name = n["inputs"][key]
                if name not in urls:
                    raise ValueError(f"The template gives no download link for {name}")
                models.append({"folder": folder, "file": name, "url": urls[name]})
    return sorted(models, key=lambda m: (m["folder"], m["file"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template", nargs="?")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    args = ap.parse_args()
    if args.template:
        template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(TEMPLATE_URL, timeout=60) as r:
            template = json.load(r)
    info = fetch_object_info(args.server)
    api = pick_trellis2(convert(template, info))
    label_steps(api)
    with urllib.request.urlopen(f"{args.server}/system_stats", timeout=10) as r:
        version = json.load(r)["system"]["comfyui_version"]
    doc = {
        "about": "TRELLIS.2 image -> textured .glb, from ComfyUI's "
                 "3d_pixal3d_trellis2_image_to_model template. Made by scripts/make_addon_workflow.py.",
        "comfyui_version": version,
        "models": required_models(api, template),
        "prompt": api,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(api)} nodes, {len(doc['models'])} models -> {OUT}")
    for m in doc["models"]:
        print(f"  {m['folder']}/{m['file']}")


if __name__ == "__main__":
    main()
