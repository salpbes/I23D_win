"""Glue between Blender scenes and the modules: import, organise, clean, export.

Operators call these functions; nothing here touches the UI.
"""

from __future__ import annotations

from pathlib import Path

import bpy
from mathutils import Matrix

from . import baking, cleanup, exporter, materials, preferences
from .properties import budget_tris

ORIGINALS = "Image→3D Originals"
GAME_READY = "Image→3D Game Ready"

ROLE = "i23d_role"      # "original" or "game"
BASE = "i23d_base"      # asset name shared by original + game versions
SOURCE = "i23d_source"  # on a game object: name of its original


def get_collection(context, name: str) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in context.scene.collection.children:
        context.scene.collection.children.link(coll)
    return coll


def _move_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def output_dir(context) -> Path:
    path = Path(bpy.path.abspath(preferences.get(context).output_dir)).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_dir(context) -> Path:
    custom = context.scene.i23d.export_dir
    return Path(bpy.path.abspath(custom)).expanduser() if custom else output_dir(context) / "game-ready"


def import_original(context, glb_path: str | Path, name: str, image_path: str = "") -> bpy.types.Object:
    """Import a TRELLIS .glb, merge it into one mesh, and file it under Originals."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("The model file contained no mesh.")
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = world
    for obj in new:
        if obj.type != "MESH":
            bpy.data.objects.remove(obj)
    if len(meshes) > 1:
        with context.temp_override(active_object=meshes[0], object=meshes[0],
                                   selected_objects=meshes, selected_editable_objects=meshes):
            bpy.ops.object.join()
    # ComfyUI writes standard Y-up glTF, which Blender's import already stands upright (Z-up).
    # (The Mac version's TRELLIS.2 files were Z-up and needed a turn; these must not get one.)
    obj = meshes[0]
    obj.name = f"{name}_original"
    obj.data.name = obj.name
    obj[ROLE] = "original"
    obj[BASE] = name
    if image_path:
        obj["i23d_image"] = image_path      # the picture it came from (used for colour matching)
    _move_to(obj, get_collection(context, ORIGINALS))
    return obj


def resolve_source(obj: bpy.types.Object) -> bpy.types.Object:
    """A game object points back to its original; anything else is its own source."""
    source_name = obj.get(SOURCE)
    if source_name and source_name in bpy.data.objects:
        return bpy.data.objects[source_name]
    return obj


def _short(tris: int) -> str:
    return f"{tris // 1000}k" if tris >= 1000 else str(tris)


def clean(context, obj: bpy.types.Object) -> tuple[bpy.types.Object, dict]:
    """Make a game-ready copy of obj's original. Re-running with the same size replaces it."""
    s = context.scene.i23d
    source = resolve_source(obj)
    base = source.get(BASE) or source.name.removesuffix("_original")
    source[ROLE] = "original"
    source[BASE] = base
    target = budget_tris(s)
    name = f"{base}_{_short(target)}"

    old = bpy.data.objects.get(name)
    if old is not None and old is not source:
        old_mesh = old.data
        bpy.data.objects.remove(old)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    game, stats = cleanup.make_game_mesh(
        source, name=name, collection=get_collection(context, GAME_READY),
        target_tris=target, detail=s.detail, thickness_factor=s.thickness_factor,
        target_height=s.target_height, to_ground=s.to_ground)
    game[ROLE] = "game"
    game[BASE] = base
    game[SOURCE] = source.name
    game["i23d_to_final"] = [list(r) for r in stats.pop("to_final")]
    stats["colours"] = apply_look(context, game, source)

    source.hide_set(True)
    for other in context.view_layer.objects:
        other.select_set(False)
    game.select_set(True)
    context.view_layer.objects.active = game
    return game, stats


def apply_look(context, game, source) -> str:
    """Give `game` its colours: TRELLIS.2's own (baked) or a plain preset. Returns a short note."""
    s = context.scene.i23d
    if s.material_preset != "TRELLIS":
        materials.apply(game, s.color, s.metallic, s.roughness)
        return "plain material"
    if baking.colour_layer(source) is None and not baking.has_texture_colours(source):
        clay = materials.PRESETS["CLAY"]
        materials.apply(game, clay[1], clay[2], clay[3])
        return "no TRELLIS colours found on the original - used Clay"
    stats = None
    if s.colour_match > 0:
        picture = source.get("i23d_image") or bpy.path.abspath(s.image_path)
        stats = baking.photo_colour_stats(picture) if picture else None
    to_final = Matrix([list(r) for r in game["i23d_to_final"]]) if "i23d_to_final" in game else Matrix.Identity(4)
    keep = game.matrix_world.copy()
    game.matrix_world = to_final.inverted()          # sit exactly on the original while baking
    try:
        images = baking.bake_colours(context, source, game, size=int(s.texture_size),
                                     match_stats=stats, match_strength=s.colour_match if stats else 0.0,
                                     surface_maps=s.surface_maps, save_dir=output_dir(context) / "textures")
    finally:
        game.matrix_world = keep
    if s.colour_match > 0 and stats is None:
        note = "TRELLIS colours (photo not readable - no matching)"
    else:
        note = f"TRELLIS colours, {int(round(s.colour_match * 100))}% matched to photo" if stats else "TRELLIS colours"
    maps = [label for key, label in (("metallic_roughness", "metal/roughness"), ("normal", "normal map"))
            if key in images]
    return note + (" + " + " + ".join(maps) if maps else "")


def describe(stats: dict) -> str:
    tidy = "watertight" if stats["open_edges"] == 0 else f"{stats['open_edges']:,} open edges"
    text = (f"{stats['tris_in']:,} → {stats['tris']:,} triangles · {tidy} · "
            f"{stats['size'][0]} × {stats['size'][1]} × {stats['size'][2]} m")
    return text + (f" · {stats['colours']}" if stats.get("colours") else "")


def export(context, obj: bpy.types.Object) -> Path:
    return exporter.export_glb(obj, export_dir(context), draco=context.scene.i23d.draco)
