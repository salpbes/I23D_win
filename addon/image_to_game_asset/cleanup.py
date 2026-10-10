"""Turn a messy AI mesh into a clean, light, watertight game mesh.

The recipe (found by testing on a TRELLIS.2 crown):
  1. Thicken  - AI meshes are paper-thin open shells; give them a tiny thickness.
  2. Rebuild  - voxel remesh into one clean, closed solid (fixes holes and tangles).
  3. Tidy     - delete tiny floating bits.
  4. Simplify - collapse down to the triangle budget.
  5. Finish   - smooth shading with crisp sharp edges, optional resize and ground.
Skipping step 1 makes thin parts fall apart; simplifying first gets stuck.
"""

from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

# Voxel size as a fraction of the model's largest dimension.
DETAIL_VOXEL = {"FINE": 0.0015, "NORMAL": 0.002, "COARSE": 0.003}


def triangle_count(mesh: bpy.types.Mesh) -> int:
    mesh.calc_loop_triangles()
    return len(mesh.loop_triangles)


def apply_modifiers(obj: bpy.types.Object) -> None:
    """Bake all modifiers into the mesh without needing UI context."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    new_mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))
    old_mesh = obj.data
    old_name = old_mesh.name
    obj.modifiers.clear()
    obj.data = new_mesh
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    new_mesh.name = old_name  # rename after removal so it doesn't get a .001 suffix


def remove_small_parts(mesh: bpy.types.Mesh, min_verts: int) -> int:
    """Delete connected pieces with fewer than min_verts vertices. Returns verts removed."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    seen = bytearray(len(bm.verts))
    doomed = []
    for start in bm.verts:
        if seen[start.index]:
            continue
        piece = [start]
        seen[start.index] = 1
        i = 0
        while i < len(piece):
            vert = piece[i]
            i += 1
            for edge in vert.link_edges:
                other = edge.other_vert(vert)
                if not seen[other.index]:
                    seen[other.index] = 1
                    piece.append(other)
        if len(piece) < min_verts:
            doomed.extend(piece)
    if doomed:
        bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return len(doomed)


def count_open_edges(mesh: bpy.types.Mesh) -> int:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bad = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return bad


def _bake_transform(obj: bpy.types.Object) -> None:
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)


def _bounds(mesh: bpy.types.Mesh):
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return Vector(co.min(axis=0).tolist()), Vector(co.max(axis=0).tolist())


def make_game_mesh(
    source: bpy.types.Object,
    *,
    name: str,
    collection: bpy.types.Collection,
    target_tris: int = 60000,
    detail: str = "NORMAL",
    thickness_factor: float = 2.0,
    min_part_verts: int = 100,
    target_height: float = 0.0,
    to_ground: bool = True,
    sharp_angle_deg: float = 40.0,
) -> tuple[bpy.types.Object, dict]:
    """Copy `source`, clean the copy, and return (new_object, stats). Source is untouched."""
    obj = source.copy()
    obj.data = source.data.copy()
    obj.name = name
    obj.data.name = name
    obj.modifiers.clear()
    collection.objects.link(obj)
    obj.hide_viewport = False
    obj.hide_render = False
    obj.hide_set(False)

    stats = {"tris_in": triangle_count(source.data)}
    _bake_transform(obj)

    to_final = Matrix.Identity(4)   # how the copy is moved/resized after it leaves the original's place
    low, high = _bounds(obj.data)
    if target_height > 0 and (high.z - low.z) > 0:
        scale = Matrix.Scale(target_height / (high.z - low.z), 4)
        obj.data.transform(scale)
        to_final = scale @ to_final
        low, high = _bounds(obj.data)
    size = max(high - low)

    # 1 + 2: thicken, then rebuild as one closed solid
    voxel = DETAIL_VOXEL.get(detail, DETAIL_VOXEL["NORMAL"]) * size
    solidify = obj.modifiers.new("I23D_Thicken", "SOLIDIFY")
    solidify.thickness = voxel * thickness_factor
    solidify.offset = 0.0
    remesh = obj.modifiers.new("I23D_Rebuild", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = voxel
    remesh.adaptivity = 0.0
    apply_modifiers(obj)

    # 3: tidy
    stats["verts_removed"] = remove_small_parts(obj.data, min_part_verts)

    # 4: simplify
    tris = triangle_count(obj.data)
    if 0 < target_tris < tris:
        decimate = obj.modifiers.new("I23D_Simplify", "DECIMATE")
        decimate.decimate_type = "COLLAPSE"
        decimate.ratio = target_tris / tris
        decimate.use_collapse_triangulate = True
        apply_modifiers(obj)

    # 5: finish
    mesh = obj.data
    mesh.shade_smooth()
    mesh.set_sharp_from_angle(angle=math.radians(sharp_angle_deg))
    if to_ground:
        low, high = _bounds(mesh)
        move = Matrix.Translation(-Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z)))
        mesh.transform(move)
        to_final = move @ to_final
    mesh.update()
    stats["to_final"] = to_final

    stats["tris"] = triangle_count(mesh)
    stats["open_edges"] = count_open_edges(mesh)
    low, high = _bounds(mesh)
    stats["size"] = tuple(round(v, 3) for v in (high - low))
    return obj, stats
