"""Add-on preferences: where TRELLIS.2 lives and where models are saved."""

from pathlib import Path

import bpy
from bpy.props import StringProperty

ADDON_ID = __package__

_SOURCES = Path.home() / "Documents" / "sources"


class I23D_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    trellis_dir: StringProperty(
        name="TRELLIS.2 folder",
        description="The trellis-mac folder made by the install script",
        subtype="DIR_PATH",
        default=str(_SOURCES / "trellis-mac"),
    )
    output_dir: StringProperty(
        name="Output folder",
        description="Where generated models and logs are saved",
        subtype="DIR_PATH",
        default=str(_SOURCES / "trellis-output"),
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "trellis_dir")
        layout.prop(self, "output_dir")
        layout.operator("i23d.check_setup", icon="CHECKMARK")


def get(context=None) -> I23D_Preferences:
    context = context or bpy.context
    return context.preferences.addons[ADDON_ID].preferences


def register():
    bpy.utils.register_class(I23D_Preferences)


def unregister():
    bpy.utils.unregister_class(I23D_Preferences)
