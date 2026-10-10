"""Image to Game Asset — picture -> TRELLIS.2 -> clean game mesh -> .glb.

Module map (each file has one job):
    trellis_runner.py  start/stop TRELLIS.2 and read its progress (no Blender code)
    cleanup.py         turn a messy AI mesh into a clean, light game mesh
    materials.py       simple material presets
    baking.py          bake TRELLIS.2's own colours onto the light game mesh
    exporter.py        .glb export
    pipeline.py        glue: import, organise, clean, export (used by operators)
    properties.py      the panel's settings
    preferences.py     where TRELLIS.2 and the output folder live
    operators.py       buttons
    ui.py              sidebar panel (3D View > N > Image→3D)
"""

bl_info = {  # used only when installed as a legacy add-on
    "name": "Image to Game Asset",
    "author": "Alper Baskan",
    "version": (1, 1, 0),
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
