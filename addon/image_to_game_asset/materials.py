"""Simple material presets that export cleanly to glTF / three.js."""

from __future__ import annotations

import bpy

# name: (label, base colour, metallic, roughness)
PRESETS = {
    "GOLD": ("Gold", (0.83, 0.62, 0.25), 1.0, 0.30),
    "SILVER": ("Silver", (0.91, 0.91, 0.92), 1.0, 0.25),
    "BRONZE": ("Bronze", (0.55, 0.35, 0.18), 1.0, 0.40),
    "STONE": ("Stone", (0.50, 0.50, 0.48), 0.0, 0.85),
    "WOOD": ("Wood", (0.45, 0.28, 0.15), 0.0, 0.60),
    "CLAY": ("Clay", (0.80, 0.78, 0.75), 0.0, 0.90),
    "PLASTIC": ("Plastic", (0.20, 0.35, 0.80), 0.0, 0.35),
}


def _principled(material: bpy.types.Material):
    if not material.use_nodes:  # always on in newer Blender; harmless otherwise
        material.use_nodes = True
    tree = material.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = next((n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None) \
            or tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return bsdf


def apply(obj: bpy.types.Object, color, metallic: float, roughness: float) -> bpy.types.Material:
    """Give `obj` its own material (named after it) with these settings."""
    name = f"{obj.name}_mat"
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    bsdf = _principled(material)
    rgba = (*color[:3], 1.0)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    material.diffuse_color = rgba  # colour in Solid view too
    material.metallic = metallic
    material.roughness = roughness
    obj.data.materials.clear()
    obj.data.materials.append(material)
    return material
