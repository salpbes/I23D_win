"""Add-on preferences: where ComfyUI lives, how to reach it, where models are saved, and installing it."""

import textwrap

import bpy
from bpy.props import BoolProperty, StringProperty

from . import installer
from .trellis_runner import DEFAULT_URL

ADDON_ID = __package__

_HOME = installer.HOME


class I23D_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    comfy_dir: StringProperty(
        name="ComfyUI folder",
        description="The ComfyUI_windows_portable folder made by Install ComfyUI + TRELLIS.2",
        subtype="DIR_PATH",
        default=str(_HOME / installer.COMFY_FOLDER),
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
        row = layout.row()
        row.operator("i23d.check_setup", icon="CHECKMARK")
        row.operator("i23d.install_comfy", icon="IMPORT")
        draw_setup_problems(layout, width=110, install_button=False)


def draw_setup_problems(layout, width=40, install_button=True):
    """What the last Check Setup found missing, and the button that fixes it."""
    if installer.is_running():
        layout.label(text="The installer is running in its own window. When it says Done, "
                          "press Check Setup.", icon="TIME")
        return
    if not installer.last_problems:
        return
    box = layout.box()
    col = box.column(align=True)
    col.alert = True
    for i, problem in enumerate(installer.last_problems[:3]):
        for j, line in enumerate(textwrap.wrap(problem, width=width)):
            col.label(text=line, icon="ERROR" if i == j == 0 else "BLANK1")
    if len(installer.last_problems) > 3:
        col.label(text=f"...and {len(installer.last_problems) - 3} more", icon="BLANK1")
    for i, line in enumerate(textwrap.wrap(f"Not set up yet? Install ComfyUI + TRELLIS.2 downloads "
                                           f"it all (about {installer.DOWNLOAD_GB} GB).", width=width)):
        box.label(text=line, icon="INFO" if i == 0 else "BLANK1")
    if install_button:
        box.operator("i23d.install_comfy", icon="IMPORT")


def get(context=None) -> I23D_Preferences:
    context = context or bpy.context
    return context.preferences.addons[ADDON_ID].preferences


def register():
    bpy.utils.register_class(I23D_Preferences)


def unregister():
    bpy.utils.unregister_class(I23D_Preferences)
