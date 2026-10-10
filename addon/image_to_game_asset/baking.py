"""Bake TRELLIS.2's own colours from the detailed original onto the light game mesh.

The detailed original keeps TRELLIS.2's colours either in its material's base colour texture
(ComfyUI on Windows) or on its points as a colour attribute (the Mac version).
Cleaning rebuilds the shape, which drops those colours, so we copy them across:
for every pixel of the game mesh's texture, Blender looks out from the game surface,
finds the detailed original, and takes its colour ("selected to active" bake).

Optional colour matching shifts the overall brightness and tint toward the photo
(0 = pure TRELLIS.2 colours, 1 = fully matched).
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
import numpy as np

from . import cleanup

_TMP_ATTR = "I23D_bake_colour"


# ---------------------------------------------------------------- colour maths
_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
_MI = np.linalg.inv(_M)
_WP = np.array([0.95047, 1.0, 1.08883])


def _to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = c @ _M.T / _WP
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def _from_lab(lab):
    fy = (lab[:, 0] + 16) / 116
    f = np.stack([fy + lab[:, 1] / 500, fy, fy - lab[:, 2] / 200], 1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _WP
    c = np.clip(xyz @ _MI.T, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def photo_colour_stats(image_path: str):
    """Brightness/tint statistics of the object in the photo (backdrop ignored). None if unreadable."""
    try:
        img = bpy.data.images.load(image_path, check_existing=True)
    except RuntimeError:
        return None
    w, h = img.size
    if not w or not h:
        return None
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)[::3]                       # every 3rd pixel is plenty
    rgb, alpha = px[:, :3], px[:, 3]
    bright, chroma = rgb.min(1), rgb.max(1) - rgb.min(1)
    keep = (alpha > 0.5) & ~((bright > 195 / 255) & (chroma < 22 / 255)) & ~(bright > 235 / 255)
    if keep.sum() < 500:
        return None
    lab = _to_lab(rgb[keep])
    return lab.mean(0), lab.std(0) + 1e-6


def colour_layer(obj) -> str | None:
    attrs = obj.data.color_attributes
    names = [a.name for a in attrs if a.name != _TMP_ATTR]
    return names[0] if names else None


def _base_colour_socket(material):
    """The Principled BSDF's Base Color input of `material`, or None."""
    if material is None or material.node_tree is None:
        return None
    bsdf = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bsdf.inputs["Base Color"] if bsdf else None


def has_texture_colours(obj) -> bool:
    """True if a material of obj gets its base colour from an image (e.g. a ComfyUI .glb)."""
    for mat in obj.data.materials:
        socket = _base_colour_socket(mat)
        todo = [link.from_node for link in socket.links] if socket else []
        while todo:
            node = todo.pop()
            if node.type == "TEX_IMAGE" and node.image is not None:
                return True
            todo += [link.from_node for inp in node.inputs for link in inp.links]
    return False


def _shift_colours(rgb, stats, strength: float, ref_mask=None):
    """Move sRGB colours' brightness and tint toward the photo's. Returns new sRGB colours."""
    lab = _to_lab(rgb)
    ref = lab[ref_mask] if ref_mask is not None and ref_mask.sum() > 100 else lab
    mu_m, sd_m = ref.mean(0), ref.std(0) + 1e-6
    mu_p, sd_p = stats
    mu_t = mu_m + strength * (mu_p - mu_m)
    sd_t = sd_m + strength * (sd_p - sd_m)
    new = (lab - mu_m) / sd_m * sd_t + mu_t
    # grey parts (metal, stone) keep their own tint, so they don't turn blue or green
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    keep_tint = 1 - np.clip(chroma / 12.0, 0, 1)
    new[:, 1:] = new[:, 1:] * (1 - keep_tint[:, None]) + lab[:, 1:] * keep_tint[:, None]
    return _from_lab(new)


def _matched_layer(source, layer: str, stats, strength: float) -> str:
    """Write an adjusted copy of the colours into a temporary layer; return its name."""
    me = source.data
    ca = me.color_attributes[layer]
    col = np.empty(len(ca.data) * 4, np.float32)
    ca.data.foreach_get("color_srgb", col)
    col = col.reshape(-1, 4)
    nrm = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    if ca.domain == "CORNER":
        lv = np.empty(len(me.loops), np.int32)
        me.loops.foreach_get("vertex_index", lv)
        facing = -nrm[lv, 1]
    else:
        facing = -nrm[:, 1]
    front = facing > 0.35                              # what the photo's camera saw
    col[:, :3] = _shift_colours(col[:, :3], stats, strength, front)
    if _TMP_ATTR in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[_TMP_ATTR])
    tmp = me.color_attributes.new(_TMP_ATTR, ca.data_type, ca.domain)
    tmp.data.foreach_set("color_srgb", col.ravel())
    return _TMP_ATTR


# ---------------------------------------------------------------- context helpers
def _view3d_override(context):
    win = context.window or (context.window_manager.windows[0] if context.window_manager.windows else None)
    if win is None:
        return {}
    for area in win.screen.areas:
        if area.type == "VIEW_3D":
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            return {"window": win, "area": area, "region": region}
    return {"window": win}


def unwrap(context, obj, margin=0.003):
    """Give obj a fresh UV layout (Smart UV Project)."""
    me = obj.data
    for uv in list(me.uv_layers):
        me.uv_layers.remove(uv)
    me.uv_layers.new(name="UVMap")
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_sel = [o for o in view_layer.objects if o.select_get()]
    for o in prev_sel:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    with context.temp_override(**_view3d_override(context), active_object=obj, object=obj,
                               selected_objects=[obj], selected_editable_objects=[obj]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin)
        bpy.ops.object.mode_set(mode="OBJECT")
    obj.select_set(False)
    for o in prev_sel:
        if o.name in view_layer.objects:
            o.select_set(True)
    view_layer.objects.active = prev_active


def _emit_material(layer: str) -> bpy.types.Material:
    mat = bpy.data.materials.get("I23D_bake_source") or bpy.data.materials.new("I23D_bake_source")
    nt = mat.node_tree
    nt.nodes.clear()
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = layer
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vc.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def _emission_copy(material) -> bpy.types.Material:
    """A temporary copy of `material` that shows its base colour as light (for the EMIT bake)."""
    mat = material.copy()
    mat.name = f"I23D_bake_{material.name}"
    nt = mat.node_tree
    socket = _base_colour_socket(mat)
    for node in [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]:
        nt.nodes.remove(node)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    if socket is not None and socket.links:
        nt.links.new(socket.links[0].from_socket, em.inputs["Color"])
    elif socket is not None:
        em.inputs["Color"].default_value = socket.default_value
    else:
        em.inputs["Color"].default_value = (*material.diffuse_color[:3], 1.0)
    return mat


def _match_image(image, stats, strength: float) -> None:
    """Colour-match a baked texture in place (empty, never-baked pixels are left alone)."""
    w, h = image.size
    px = np.empty(w * h * 4, np.float32)
    image.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    used = px[:, :3].sum(1) > 0.002
    if used.sum() < 100:
        return
    px[used, :3] = _shift_colours(px[used, :3], stats, strength)
    image.pixels.foreach_set(px.ravel())
    image.update()


# ---------------------------------------------------------------- main entry
def bake_colours(context, source, target, *, size=2048, match_stats=None, match_strength=0.0,
                 save_dir: str | Path | None = None) -> bpy.types.Image:
    """Bake source's colours (colour attribute or base colour texture) onto target's texture.
    Returns the image (packed)."""
    match = match_stats is not None and match_strength > 0
    layer = colour_layer(source)
    if layer is not None:
        if match:
            layer = _matched_layer(source, layer, match_stats, match_strength)
        bake_mats = [_emit_material(layer)]
    elif has_texture_colours(source):
        bake_mats = [_emission_copy(m) for m in source.data.materials]
    else:
        raise RuntimeError("The original has no TRELLIS colours.")

    unwrap(context, target)

    # how far to look from the game surface to the original (the clean step thickened it slightly)
    lo, hi = cleanup._bounds(target.data)
    size_m = max(hi - lo)
    voxel = cleanup.DETAIL_VOXEL["NORMAL"] * size_m

    name = f"{target.name}_basecolor"
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    image = bpy.data.images.new(name, size, size)

    # target material: Principled with the (to be baked) texture; the image node must be active
    mat = bpy.data.materials.get(f"{target.name}_mat") or bpy.data.materials.new(f"{target.name}_mat")
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = 0.8
    nt.nodes.active = tex
    target.data.materials.clear()
    target.data.materials.append(mat)

    # source: temporarily show its colours as light, make it visible and selectable
    src_mats = list(source.data.materials)
    src_hidden, src_hide_render = source.hide_get(), source.hide_render
    source.hide_set(False)
    source.hide_render = False
    source.data.materials.clear()
    for m in bake_mats:  # same slots, so each face keeps its own material
        source.data.materials.append(m)

    scene = context.scene
    prev_engine = scene.render.engine
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_sel = [o for o in view_layer.objects if o.select_get()]
    try:
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        try:
            prefs = context.preferences.addons["cycles"].preferences
            scene.cycles.device = "GPU" if prefs.compute_device_type not in ("", "NONE") else "CPU"
        except (KeyError, AttributeError):
            scene.cycles.device = "CPU"
        for o in prev_sel:
            o.select_set(False)
        source.select_set(True)
        target.select_set(True)
        view_layer.objects.active = target
        with context.temp_override(**_view3d_override(context), active_object=target, object=target,
                                   selected_objects=[source, target], selected_editable_objects=[source, target]):
            bpy.ops.object.bake(type="EMIT", use_selected_to_active=True,
                                cage_extrusion=4 * voxel, max_ray_distance=10 * voxel,
                                margin=16, use_clear=True, uv_layer="UVMap")
    finally:
        scene.render.engine = prev_engine
        source.select_set(False)
        target.select_set(False)
        for o in prev_sel:
            if o.name in view_layer.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active
        source.data.materials.clear()
        for m in src_mats:
            source.data.materials.append(m)
        source.hide_set(src_hidden)
        source.hide_render = src_hide_render
        if _TMP_ATTR in source.data.color_attributes:
            source.data.color_attributes.remove(source.data.color_attributes[_TMP_ATTR])
        for m in bake_mats:
            if m.name.startswith("I23D_bake_") and m.name != "I23D_bake_source" and m.users == 0:
                bpy.data.materials.remove(m)

    if layer is None and match:
        _match_image(image, match_stats, match_strength)

    if save_dir:
        path = Path(save_dir).expanduser() / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
    image.pack()   # stays inside the .blend and is embedded in .glb exports
    return image
