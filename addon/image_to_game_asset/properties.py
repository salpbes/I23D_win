"""Settings shown in the panel (stored per scene as scene.i23d)."""

from pathlib import Path

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty, StringProperty)

from . import materials
from .trellis_runner import sanitize_name

BUDGETS = {"HERO": 60000, "STANDARD": 15000, "LIGHT": 5000}


def budget_tris(settings) -> int:
    return settings.custom_tris if settings.budget == "CUSTOM" else BUDGETS[settings.budget]


def _on_image_change(self, context):
    if self.image_path:
        self.asset_name = sanitize_name(Path(bpy.path.abspath(self.image_path)).stem)


def _on_preset_change(self, context):
    preset = materials.PRESETS.get(self.material_preset)
    if preset:
        _, color, metallic, roughness = preset
        self.color, self.metallic, self.roughness = color, metallic, roughness


class I23D_Settings(bpy.types.PropertyGroup):
    # 1. Picture
    image_path: StringProperty(
        name="Picture", subtype="FILE_PATH", update=_on_image_change,
        description="One object on a plain or transparent background (.png, .jpg, .webp)")
    asset_name: StringProperty(
        name="Name", description="Used for the object and file names (filled in from the picture)")
    auto_clean: BoolProperty(
        name="Clean automatically", default=True,
        description="Clean the model for games as soon as it is generated")
    auto_export: BoolProperty(
        name="Export .glb automatically", default=False,
        description="Save the cleaned model as .glb straight away")

    # 2. Clean
    budget: EnumProperty(
        name="Size",
        items=[("HERO", "60k", "Hero prop, close-ups: 60,000 triangles"),
               ("STANDARD", "15k", "Normal game object: 15,000 triangles"),
               ("LIGHT", "5k", "Background or mobile: 5,000 triangles"),
               ("CUSTOM", "Custom", "Choose your own triangle count")],
        default="STANDARD")
    custom_tris: IntProperty(name="Triangles", default=30000, min=500, max=2_000_000, step=1000)
    material_preset: EnumProperty(
        name="Material",
        items=[("TRELLIS", "TRELLIS colours", "Keep the colours TRELLIS.2 generated (baked into a texture)")]
              + [(k, v[0], "") for k, v in materials.PRESETS.items()] + [("CUSTOM", "Custom", "")],
        default="TRELLIS", update=_on_preset_change)
    colour_match: FloatProperty(
        name="Match photo colours", subtype="FACTOR", min=0.0, max=1.0, default=0.0,
        description="0 = pure TRELLIS.2 colours, 1 = brightness and tint fully matched to the picture")
    surface_maps: BoolProperty(
        name="Metal, roughness & bumps", default=True,
        description="With TRELLIS colours from ComfyUI: also bake the original's metal/roughness "
                    "texture and a normal map of its fine detail (adds a few seconds to Clean)")
    texture_size: EnumProperty(
        name="Texture size",
        items=[("1024", "1024", "Small file, mobile"), ("2048", "2048", "Good default"), ("4096", "4096", "Hero assets, big file")],
        default="2048")
    color: FloatVectorProperty(name="Colour", subtype="COLOR", size=3, min=0, max=1,
                               default=materials.PRESETS["CLAY"][1])
    metallic: FloatProperty(name="Metallic", min=0, max=1, default=0.0)
    roughness: FloatProperty(name="Roughness", min=0, max=1, default=0.9)

    # 3. Export
    export_dir: StringProperty(
        name="Folder", subtype="DIR_PATH",
        description="Where .glb files go (empty = 'game-ready' inside the output folder)")
    draco: BoolProperty(
        name="Compress (Draco)", default=False,
        description="Much smaller files; three.js then needs DRACOLoader")

    # Advanced
    quality: EnumProperty(
        name="Detail",
        items=[("1024", "Standard (1024)", "Under 3 minutes and about 11.5 GB of graphics memory on an RTX 5060 Ti 16 GB"),
               ("1536", "High (1536)", "Finer shape; slower and needs more graphics memory. Not yet tested on 16 GB")],
        default="1024")
    random_seed: BoolProperty(
        name="New seed each time", default=True,
        description="Like the Hugging Face page: every run gives a different take. The seed used is shown below")
    seed: IntProperty(name="Seed", default=42, min=0, max=2_147_483_647,
                      description="Same seed + same picture + same detail = same result")
    detail: EnumProperty(
        name="Rebuild detail",
        items=[("FINE", "Fine", "Keeps the thinnest details; slower"),
               ("NORMAL", "Normal", "Good balance (worked on the crown test)"),
               ("COARSE", "Coarse", "Faster; very thin parts may merge")],
        default="NORMAL")
    thickness_factor: FloatProperty(
        name="Thicken", default=2.0, min=1.0, max=6.0,
        description="How much to thicken paper-thin parts before rebuilding (x rebuild detail)")
    target_height: FloatProperty(
        name="Height (m)", default=0.0, min=0.0, unit="LENGTH",
        description="Resize so the model is this tall. 0 = keep size")
    to_ground: BoolProperty(
        name="Stand on ground", default=True,
        description="Centre the model and put its base at height 0")

    # Live status (not edited by the user)
    is_running: BoolProperty(default=False)
    progress: FloatProperty(default=0.0, min=0.0, max=1.0)
    status: StringProperty(default="")
    last_result: StringProperty(default="")
    last_error: StringProperty(default="")
    last_log: StringProperty(default="")
    activity: StringProperty(default="")
    looks_stuck: BoolProperty(default=False)


def register():
    bpy.utils.register_class(I23D_Settings)
    bpy.types.Scene.i23d = PointerProperty(type=I23D_Settings)


def unregister():
    del bpy.types.Scene.i23d
    bpy.utils.unregister_class(I23D_Settings)
