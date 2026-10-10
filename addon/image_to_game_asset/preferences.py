"""Add-on preferences: where ComfyUI lives, how to reach it, and where models are saved."""

from pathlib import Path

import bpy
from bpy.props import BoolProperty, StringProperty

from .trellis_runner import DEFAULT_URL

ADDON_ID = __package__

_HOME = Path.home() / "I23D"


class I23D_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    comfy_dir: StringProperty(
        name="ComfyUI folder",
        description="The ComfyUI_windows_portable folder made by the install script",
        subtype="DIR_PATH",
        default=str(_HOME / "ComfyUI_windows_portable"),
    )
    comfy_url: StringProperty(
        name="ComfyUI address",
        description="Where ComfyUI listens. Keep it on this PC (127.0.0.1) so nothing leaves it",
        default=DEFAULT_URL,
    )
    start_comfy: BoolProperty(
        name="Start ComfyUI when needed", default=True,
        description="If ComfyUI isn't running, start it in the background (offline, this PC only)")
    keep_comfy: BoolProperty(
        name="Keep ComfyUI running between models", default=True,
        description="The next model starts faster, but ComfyUI keeps using memory until you "
                    "press Stop ComfyUI or quit Blender")
    output_dir: StringProperty(
        name="Output folder",
        description="Where generated models and logs are saved",
        subtype="DIR_PATH",
        default=str(_HOME / "output"),
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "comfy_dir")
        layout.prop(self, "comfy_url")
        row = layout.row()
        row.prop(self, "start_comfy")
        row.prop(self, "keep_comfy")
        layout.prop(self, "output_dir")
        layout.operator("i23d.check_setup", icon="CHECKMARK")


def get(context=None) -> I23D_Preferences:
    context = context or bpy.context
    return context.preferences.addons[ADDON_ID].preferences


def register():
    bpy.utils.register_class(I23D_Preferences)


def unregister():
    bpy.utils.unregister_class(I23D_Preferences)
