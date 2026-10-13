"""Sidebar panel: 3D View > press N > Image→3D tab."""

import textwrap

import bpy

from . import installer, operators, preferences
from .pipeline import ORIGINALS
from .properties import budget_tris

CATEGORY = "Image→3D"


class _Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


def _draw_setup(layout, context):
    """Top of the panel: the one-time setup while ComfyUI or TRELLIS.2 is missing, the installer's
    progress while it runs, or what went wrong."""
    if preferences.draw_setup_status(layout):
        return
    if not preferences.setup_missing(preferences.get(context)):
        return
    box = layout.box()
    box.label(text="One-time setup", icon="IMPORT")
    col = box.column(align=True)
    col.label(text="TRELLIS.2, the AI that makes the")
    col.label(text="models, isn't installed yet.")
    col.label(text=f"About {installer.DOWNLOAD_GB} GB, no account needed.")
    big = box.row()
    big.scale_y = 1.5
    big.operator("i23d.install_comfy", icon="IMPORT")
    box.operator("i23d.check_setup", text="Already have it? Check Setup", icon="CHECKMARK")


def _wrapped(layout, text, icon, width=34):
    for i, line in enumerate(textwrap.wrap(text, width=width)):
        layout.label(text=line, icon=icon if i == 0 else "BLANK1")


def _draw_picture_check(layout, context):
    """Under the picture: its cut-out as TRELLIS.2 will see it, and what may go wrong."""
    s = context.scene.i23d
    if not s.image_path or s.is_running:
        return
    check = operators.picture_check_for(context)
    if check is None:
        layout.operator("i23d.check_picture", icon="VIEWZOOM")
        return
    if check.running:
        layout.label(text=f"Checking the picture: {check.job.label}", icon="TIME")
        return
    if check.error:
        col = layout.column(align=True)
        _wrapped(col, check.error, "ERROR")
        layout.operator("i23d.check_picture", text="Check Again", icon="FILE_REFRESH")
        return
    if check.icon_id:
        col = layout.column()
        col.template_icon(icon_value=check.icon_id, scale=9)
    col = layout.column(align=True)
    for note in check.notes:
        _wrapped(col, note.text, "CHECKMARK" if note.good else "ERROR")
    row = layout.row(align=True)
    row.operator("i23d.view_cutout", icon="ZOOM_IN")
    row.operator("i23d.check_picture", text="", icon="FILE_REFRESH")


class I23D_PT_main(_Base, bpy.types.Panel):
    bl_idname = "I23D_PT_main"
    bl_label = "Image to Game Asset"

    def draw(self, context):
        s = context.scene.i23d
        layout = self.layout
        _draw_setup(layout, context)

        # 1. Picture -> model
        box = layout.box()
        box.label(text="1. Picture → 3D model", icon="IMAGE_DATA")
        col = box.column(align=True)
        col.enabled = not s.is_running
        col.prop(s, "image_path", text="")
        col.prop(s, "asset_name")
        _draw_picture_check(box, context)
        row = box.row()
        row.enabled = not s.is_running
        row.prop(s, "auto_clean")
        if s.auto_clean:
            box.row().prop(s, "auto_export")

        if s.is_running:
            box.progress(factor=s.progress, type="BAR", text=s.status or "Working...")
            box.label(text=s.activity, icon="TIME")
            if s.looks_stuck:
                warn = box.column(align=True)
                warn.alert = True
                warn.label(text="No news from ComfyUI for a long time.", icon="ERROR")
                warn.label(text="It may be out of graphics memory (Task")
                warn.label(text="Manager > Performance > GPU). Cancel and")
                warn.label(text="try Standard detail.")
            box.operator("i23d.cancel", icon="CANCEL")
            box.label(text="Blender stays usable; keep the scene light.", icon="INFO")
        else:
            big = box.row()
            big.scale_y = 1.6
            big.operator("i23d.generate", icon="PLAY")
            if s.status:
                box.label(text=s.status, icon="CHECKMARK" if s.status.startswith("Done") else "INFO")
            if s.activity:
                box.label(text=s.activity, icon="TIME")
            if s.last_log:
                box.operator("i23d.open_log", icon="TEXT")
            if s.quality != "1024":
                box.label(text="Detail is High: needs more graphics memory", icon="ERROR")

        # 2. Clean
        box = layout.box()
        box.label(text="2. Clean for games", icon="MOD_REMESH")
        box.label(text="Triangle budget")
        box.row().prop(s, "budget", expand=True)
        if s.budget == "CUSTOM":
            box.prop(s, "custom_tris")
        row = box.row(align=True)
        row.prop(s, "material_preset", text="")
        if s.material_preset != "TRELLIS":
            row.prop(s, "color", text="")
        else:
            box.prop(s, "colour_match", slider=True)
            box.prop(s, "surface_maps")
        if s.material_preset == "CUSTOM":
            sub = box.row(align=True)
            sub.prop(s, "metallic", slider=True)
            sub.prop(s, "roughness", slider=True)
        big = box.row(align=True)
        big.scale_y = 1.3
        big.operator("i23d.clean", text=f"Clean Selected ({budget_tris(s):,} tris)", icon="BRUSH_DATA")
        big.operator("i23d.apply_material", text="", icon="MATERIAL")
        if bpy.data.collections.get(ORIGINALS):
            box.prop(s, "show_originals")
        if s.last_result:
            for chunk in s.last_result.split(" · "):
                box.label(text=chunk)

        # 3. Export
        box = layout.box()
        box.label(text="3. Export", icon="EXPORT")
        box.prop(s, "export_dir", text="")
        if not s.export_dir:
            box.label(text="Default: output folder / game-ready")
        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("i23d.export", icon="FILE_3D")
        row.operator("i23d.open_folder", text="", icon="FILE_FOLDER")

        if s.last_error:
            err = layout.box()
            err.alert = True
            err.label(text="Problem:", icon="ERROR")
            for line in textwrap.wrap(s.last_error, width=40)[:8]:
                err.label(text=line)
            row = err.row(align=True)
            row.operator("i23d.open_log", icon="TEXT")
            row.operator("i23d.dismiss_error", icon="X")


class I23D_PT_advanced(_Base, bpy.types.Panel):
    bl_idname = "I23D_PT_advanced"
    bl_label = "Advanced"
    bl_parent_id = "I23D_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        s = context.scene.i23d
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column(heading="Generate")
        col.enabled = not s.is_running
        col.prop(s, "quality")
        if s.quality != "1024":
            col.label(text="Not yet tested on 16 GB cards", icon="ERROR")
        col.prop(s, "check_picture")
        col.prop(s, "random_seed")
        sub = col.row()
        sub.enabled = not s.random_seed
        sub.prop(s, "seed")

        col = layout.column(heading="Clean")
        col.prop(s, "detail")
        col.prop(s, "thickness_factor")
        col.prop(s, "target_height")
        col.prop(s, "to_ground")

        col = layout.column(heading="Colours")
        col.prop(s, "texture_size")

        col = layout.column(heading="Export")
        col.prop(s, "draco")

        layout.separator()
        row = layout.row(align=True)
        row.operator("i23d.check_setup", icon="CHECKMARK")
        row.operator("i23d.stop_comfy", icon="X")
        layout.label(text="Paths: Edit > Preferences > Add-ons", icon="PREFERENCES")


CLASSES = (I23D_PT_main, I23D_PT_advanced)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
