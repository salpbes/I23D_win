"""Image to Game Asset — picture -> TRELLIS.2 -> clean game mesh -> .glb.

Module map (each file has one job):
    trellis_runner.py  run TRELLIS.2 through a local ComfyUI, read its progress (no Blender code)
    workflows/         the TRELLIS.2 ComfyUI workflow (made by scripts/make_addon_workflow.py)
    cleanup.py         turn a messy AI mesh into a clean, light game mesh
    materials.py       simple material presets
    baking.py          bake TRELLIS.2's own colours onto the light game mesh
    exporter.py        .glb export
    pipeline.py        glue: import, organise, clean, export (used by operators)
    properties.py      the panel's settings
    preferences.py     where ComfyUI and the output folder live
    installer.py       start install/install_comfyui.ps1 (sets up ComfyUI + TRELLIS.2) in its own window
    operators.py       buttons
    ui.py              sidebar panel (3D View > N > Image→3D)
"""

bl_info = {  # used only when installed as a legacy add-on
    "name": "Image to Game Asset",
    "author": "Alper Baskan",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Image→3D",
    "description": "Turn a picture into a clean, game-ready 3D model with TRELLIS.2",
    "category": "3D View",
}

from . import preferences, properties, operators, ui

_MODULES = (preferences, properties, operators, ui)


def register():
    for module in _MODULES:
        module.register()


def unregister():
    for module in reversed(_MODULES):
        module.unregister()
