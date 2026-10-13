"""Add-on preferences: where ComfyUI lives, how to reach it, where models are saved, and installing it."""

import textwrap
import time

import bpy
from bpy.props import BoolProperty, StringProperty

from . import installer, trellis_runner as tr
from .trellis_runner import DEFAULT_URL

ADDON_ID = __package__

_HOME = installer.HOME


def _comfy_dir_changed(self, context):
    installer.check_passed = False  # a new folder needs a new check


class I23D_Preferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    comfy_dir: StringProperty(
        name="ComfyUI folder",
        description="The ComfyUI_windows_portable folder made by Install ComfyUI + TRELLIS.2",
        subtype="DIR_PATH",
        default=str(_HOME / installer.COMFY_FOLDER),
        update=_comfy_dir_changed,
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
    show_result: BoolProperty(
        name="Show the new model in colour", default=True,
        description="After Generate, switch the 3D view from plain grey to Material Preview and "
                    "centre it on the new model (remembered for every file)")

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
        draw_setup_status(layout, width=110, install_button=False)


def _wrapped(layout, text, width, icon):
    for i, line in enumerate(textwrap.wrap(text, width=width)):
        layout.label(text=line, icon=icon if i == 0 else "BLANK1")


def draw_setup_status(layout, width=30, install_button=True) -> bool:
    """The installer's progress while it runs, or what is missing and the button that fixes it.
    Returns whether it drew anything."""
    if installer.working():
        box = layout.box()
        box.label(text="Installing ComfyUI + TRELLIS.2", icon="IMPORT")
        p = installer.progress()
        if p is None:  # a check of this PC: nothing to follow
            box.label(text="Checking this PC in its own window", icon="TIME")
            return True
        _wrapped(box, p.message, width, "TIME")
        if p.fraction is not None:
            box.progress(factor=p.fraction, type="BAR",
                         text=p.amount or f"{round(p.fraction * 100)}%")
        _wrapped(box, "Details are in the installer's window. Blender stays usable, and checks "
                      "the setup by itself at the end.", width, "INFO")
        return True
    if installer.note:  # how the install ended
        box = layout.box()
        col = box.column(align=True)
        col.alert = not installer.note_ok
        _wrapped(col, installer.note, width, "CHECKMARK" if installer.note_ok else "ERROR")
        if install_button and not installer.note_ok:
            box.operator("i23d.install_comfy", icon="IMPORT")
        return True
    if not installer.last_problems:
        return False
    box = layout.box()
    col = box.column(align=True)
    col.alert = True
    for i, problem in enumerate(installer.last_problems[:3]):
        for j, line in enumerate(textwrap.wrap(problem, width=width)):
            col.label(text=line, icon="ERROR" if i == j == 0 else "BLANK1")
    if len(installer.last_problems) > 3:
        col.label(text=f"...and {len(installer.last_problems) - 3} more", icon="BLANK1")
    _wrapped(box, f"Not set up yet? Install ComfyUI + TRELLIS.2 downloads it all (about "
                  f"{installer.DOWNLOAD_GB} GB).", width, "INFO")
    if install_button:
        box.operator("i23d.install_comfy", icon="IMPORT")
    return True


_folder_check = {"key": None, "time": 0.0, "missing": False}
_workflow = None


def setup_missing(prefs) -> bool:
    """Is ComfyUI or a TRELLIS.2 file missing from the ComfyUI folder? Looks at the folder only
    (no network) and at most every few seconds, so panels can ask while they draw."""
    global _workflow
    if installer.check_passed:  # e.g. someone running their own ComfyUI elsewhere
        return False
    key, now = bpy.path.abspath(prefs.comfy_dir), time.monotonic()
    if key != _folder_check["key"] or now - _folder_check["time"] > 3:
        _workflow = _workflow or tr.load_workflow()
        _folder_check.update(key=key, time=now, missing=bool(tr.check_folder(key, _workflow)))
    return _folder_check["missing"]


def get(context=None) -> I23D_Preferences:
    context = context or bpy.context
    return context.preferences.addons[ADDON_ID].preferences


def register():
    bpy.utils.register_class(I23D_Preferences)


def unregister():
    bpy.utils.unregister_class(I23D_Preferences)
