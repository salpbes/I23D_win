"""Bake TRELLIS.2's own colours from the detailed original onto the light game mesh.

The detailed original keeps TRELLIS.2's colours either in its material's base colour texture
(ComfyUI on Windows) or on its points as a colour attribute (the Mac version).
Cleaning rebuilds the shape, which drops those colours, so we copy them across:
for every pixel of the game mesh's texture, Blender looks out from the game surface,
finds the detailed original, and takes its colour ("selected to active" bake).

A ComfyUI original also has metallic/roughness textures and far more surface detail than the
game mesh. With surface maps on, those are carried over too: a metallicRoughness texture (glTF's
channel order: green = roughness, blue = metallic) and a tangent-space normal map baked from the
detailed shape, so metal parts keep their shine and small bumps stay visible.

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


def _bsdf_socket(material, name: str):
    """The Principled BSDF's `name` input of `material` (e.g. "Base Color"), or None."""
    if material is None or material.node_tree is None:
        return None
    bsdf = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bsdf.inputs[name] if bsdf else None


def _base_colour_socket(material):
    return _bsdf_socket(material, "Base Color")


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


def _light_copy(material, suffix: str):
    """A temporary copy of `material` whose surface is an Emission node (for EMIT bakes).
    Returns (copy, its node tree, the emission node)."""
    mat = material.copy()
    mat.name = f"I23D_bake_{material.name}{suffix}"
    nt = mat.node_tree
    for node in [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"]:
        nt.nodes.remove(node)
    em = nt.nodes.new("ShaderNodeEmission")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat, nt, em


def _emission_copy(material) -> bpy.types.Material:
    """A temporary copy of `material` that shows its base colour as light (for the EMIT bake)."""
    mat, nt, em = _light_copy(material, "")
    socket = _base_colour_socket(mat)
    if socket is not None and socket.links:
        nt.links.new(socket.links[0].from_socket, em.inputs["Color"])
    elif socket is not None:
        em.inputs["Color"].default_value = socket.default_value
    else:
        em.inputs["Color"].default_value = (*material.diffuse_color[:3], 1.0)
    return mat


def _metal_rough_copy(material) -> bpy.types.Material:
    """A temporary copy of `material` that shows (1, roughness, metallic) as light: glTF's
    metallicRoughness channel order, so the baked image can be exported as it is."""
    mat, nt, em = _light_copy(material, "_mr")
    pack = nt.nodes.new("ShaderNodeCombineColor")
    pack.inputs["Red"].default_value = 1.0
    for name, channel, fallback in (("Roughness", "Green", material.roughness),
                                    ("Metallic", "Blue", material.metallic)):
        socket = _bsdf_socket(mat, name)
        if socket is not None and socket.links:
            nt.links.new(socket.links[0].from_socket, pack.inputs[channel])
        else:
            pack.inputs[channel].default_value = socket.default_value if socket is not None else fallback
    nt.links.new(pack.outputs["Color"], em.inputs["Color"])
    return mat


def has_texture_metal_rough(obj) -> bool:
    """True if a material of obj feeds Metallic or Roughness from other nodes (e.g. a texture)."""
    return any((sock := _bsdf_socket(m, name)) is not None and sock.links
               for m in obj.data.materials for name in ("Metallic", "Roughness"))


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
def _new_image(name: str, size: int, data: bool) -> bpy.types.Image:
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    image = bpy.data.images.new(name, size, size, alpha=not data)
    if data:   # numbers (roughness, normals), not colours: stored as they are
        image.colorspace_settings.name = "Non-Color"
    return image


def bake_colours(context, source, target, *, size=2048, match_stats=None, match_strength=0.0,
                 surface_maps=False, save_dir: str | Path | None = None) -> dict[str, bpy.types.Image]:
    """Bake source's colours (colour attribute or base colour texture) onto target's texture.

    With `surface_maps`, a textured original (ComfyUI) also gives a metallicRoughness texture
    (if its material feeds Metallic/Roughness from other nodes) and a tangent-space normal map.
    Returns the baked images by role: "base_color", plus "metallic_roughness" and "normal"
    when baked. All are packed."""
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
    surface_maps = surface_maps and layer is None    # the colour-layer (Mac) original has no maps
    metal_rough = surface_maps and has_texture_metal_rough(source)

    unwrap(context, target)

    # how far to look from the game surface to the original (the clean step thickened it slightly)
    lo, hi = cleanup._bounds(target.data)
    size_m = max(hi - lo)
    voxel = cleanup.DETAIL_VOXEL["NORMAL"] * size_m

    images = {"base_color": _new_image(f"{target.name}_basecolor", size, data=False)}
    if metal_rough:
        images["metallic_roughness"] = _new_image(f"{target.name}_metallicroughness", size, data=True)
    if surface_maps:
        images["normal"] = _new_image(f"{target.name}_normal", size, data=True)

    # target material: Principled with the (to be baked) textures; the image node being baked
    # into must be the active node
    mat = bpy.data.materials.get(f"{target.name}_mat") or bpy.data.materials.new(f"{target.name}_mat")
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = images["base_color"]
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    src_mats = list(source.data.materials)
    passes = [("EMIT", tex, bake_mats)]
    if metal_rough:
        # the layout Blender's glTF exporter writes as one metallicRoughness texture
        mr_tex = nt.nodes.new("ShaderNodeTexImage")
        mr_tex.image = images["metallic_roughness"]
        split = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(mr_tex.outputs["Color"], split.inputs["Color"])
        nt.links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
        passes.append(("EMIT", mr_tex, [_metal_rough_copy(m) for m in src_mats]))
    else:
        bsdf.inputs["Roughness"].default_value = 0.8
    if surface_maps:
        n_tex = nt.nodes.new("ShaderNodeTexImage")
        n_tex.image = images["normal"]
        n_map = nt.nodes.new("ShaderNodeNormalMap")
        n_map.space = "TANGENT"
        n_map.uv_map = "UVMap"
        nt.links.new(n_tex.outputs["Color"], n_map.inputs["Color"])
        nt.links.new(n_map.outputs["Normal"], bsdf.inputs["Normal"])
        passes.append(("NORMAL", n_tex, src_mats))   # the detailed shape with its own materials
    target.data.materials.clear()
    target.data.materials.append(mat)
    all_bake_mats = [m for _, _, mats in passes for m in mats if m not in src_mats]

    # source: temporarily make it visible and selectable; each pass gives it its own materials
    src_hidden, src_hide_render = source.hide_get(), source.hide_render
    source.hide_set(False)
    source.hide_render = False

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
        for bake_type, node, mats in passes:
            source.data.materials.clear()
            for m in mats:  # same slots, so each face keeps its own material
                source.data.materials.append(m)
            nt.nodes.active = node
            with context.temp_override(**_view3d_override(context), active_object=target, object=target,
                                       selected_objects=[source, target],
                                       selected_editable_objects=[source, target]):
                bpy.ops.object.bake(type=bake_type, use_selected_to_active=True,
                                    cage_extrusion=4 * voxel, max_ray_distance=10 * voxel,
                                    normal_space="TANGENT", margin=16, use_clear=True, uv_layer="UVMap")
    finally:
        nt.nodes.active = tex
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
        for m in all_bake_mats:
            if m.name.startswith("I23D_bake_") and m.name != "I23D_bake_source" and m.users == 0:
                bpy.data.materials.remove(m)

    if layer is None and match:
        _match_image(images["base_color"], match_stats, match_strength)

    for image in images.values():
        if save_dir:
            path = Path(save_dir).expanduser() / f"{image.name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            image.filepath_raw = str(path)
            image.file_format = "PNG"
            image.save()
        image.pack()   # stays inside the .blend and is embedded in .glb exports
    return images


# ---------------------------------------------------------------- front + back: paint the pictures on
def _base_colour_image_node(obj):
    """The image node that gives obj's (first textured) material its base colour."""
    for mat in obj.data.materials:
        socket = _base_colour_socket(mat)
        todo = [link.from_node for link in socket.links] if socket else []
        while todo:
            node = todo.pop()
            if node.type == "TEX_IMAGE" and node.image is not None:
                return node
            todo += [link.from_node for inp in node.inputs for link in inp.links]
    return None


def _read_picture(path) -> np.ndarray:
    """A picture's colours, rows from the top, 0-1 (as stored: sRGB)."""
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(h, w, 4)[::-1, :, :3].copy()
    finally:
        bpy.data.images.remove(img)


def _bake_geometry(context, obj, size: int) -> tuple[np.ndarray, np.ndarray]:
    """Where each texel of obj's texture sits on the model and which way it faces (world space,
    rows from the bottom as Blender stores them). Texels no face uses have a zero normal."""
    out = []
    mats = list(obj.data.materials)
    scene, view_layer = context.scene, context.view_layer
    prev_engine, prev_samples = scene.render.engine, scene.cycles.samples
    prev_active = view_layer.objects.active
    prev_sel = [o for o in view_layer.objects if o.select_get()]
    hidden, hide_render = obj.hide_get(), obj.hide_render
    try:
        obj.hide_set(False)
        obj.hide_render = False
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 1
        for o in prev_sel:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        for socket in ("Position", "Normal"):
            img = bpy.data.images.new(f"I23D_bake_{socket}", size, size, alpha=True, float_buffer=True)
            img.pixels.foreach_set(np.zeros(size * size * 4, np.float32))
            mat = bpy.data.materials.new(f"I23D_bake_{socket}")
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            em = nt.nodes.new("ShaderNodeEmission")
            outn = nt.nodes.new("ShaderNodeOutputMaterial")
            nt.links.new(geo.outputs[socket], em.inputs["Color"])
            nt.links.new(em.outputs["Emission"], outn.inputs["Surface"])
            node = nt.nodes.new("ShaderNodeTexImage")
            node.image = img
            nt.nodes.active = node
            obj.data.materials.clear()
            for _ in mats or [None]:
                obj.data.materials.append(mat)
            try:
                with context.temp_override(**_view3d_override(context), active_object=obj, object=obj,
                                           selected_objects=[obj], selected_editable_objects=[obj]):
                    bpy.ops.object.bake(type="EMIT", margin=0, use_clear=False)
                px = np.empty(size * size * 4, np.float32)
                img.pixels.foreach_get(px)
                out.append(px.reshape(size, size, 4)[..., :3])
            finally:
                bpy.data.images.remove(img)
                obj.data.materials.clear()
                for m in mats:
                    obj.data.materials.append(m)
                bpy.data.materials.remove(mat)
    finally:
        scene.render.engine, scene.cycles.samples = prev_engine, prev_samples
        obj.select_set(False)
        for o in prev_sel:
            if o.name in view_layer.objects:
                o.select_set(True)
        view_layer.objects.active = prev_active
        obj.hide_set(hidden)
        obj.hide_render = hide_render
    return out[0], out[1]


def paint_from_pictures(context, obj, views_path, max_size: int = 4096) -> str:
    """Front + back (Pixal3D): paint the cut-outs Pixal3D saw onto obj's colour texture, where
    they see it clearly ("Pixel Match"). obj is the original, as imported. Keeps the AI's texture
    too (use_painted_colours switches). Returns a short note."""
    from . import photo_paint

    node = _base_colour_image_node(obj)
    if node is None:
        return "no colour texture to paint"
    ai_image = bpy.data.images.get(obj.get("i23d_ai_colours", "")) or node.image  # never paint twice
    w, h = ai_image.size
    size = min(max(w, h), max_size)
    views = []
    for cam, picture_path in photo_paint.read_views(views_path):
        picture = _read_picture(picture_path)
        views.append((cam, picture, photo_paint.object_mask(picture)))

    positions, normals = _bake_geometry(context, obj, size)
    used = np.linalg.norm(normals, axis=2) > 0.5
    # the cameras live in the model's own space, as it was imported
    to_local = np.array(obj.matrix_world.inverted())
    points = positions[used] @ to_local[:3, :3].T + to_local[:3, 3]
    nrm = normals[used] @ np.array(obj.matrix_world)[:3, :3]   # inverse-transpose of to_local
    del positions, normals

    source = ai_image.copy()
    if (w, h) != (size, size):
        source.scale(size, size)
    px = np.empty(size * size * 4, np.float32)
    source.pixels.foreach_get(px)
    if source is not ai_image:
        bpy.data.images.remove(source)
    result = px.reshape(size, size, 4)
    result[..., 3] = 1.0
    new, trust, shift = photo_paint.paint(points, nrm, result[used][:, :3], views)
    rgb = result[..., :3]
    rgb[used] = new
    # carry the new colours a few texels past each texture island, so its edges don't show
    filled = used.copy()
    for _ in range(4):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            grow = photo_paint._shift(filled, dy, dx, False) & ~filled
            ys, xs = np.nonzero(grow)
            rgb[ys, xs] = rgb[ys - dy, xs - dx]
            filled |= grow

    name = f"{obj.name}_painted"
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    painted = bpy.data.images.new(name, size, size)
    painted.pixels.foreach_set(result.ravel())
    painted.pack()
    for image in (ai_image, painted):  # only one is in use at a time; keep both in the .blend
        image.use_fake_user = True
    obj["i23d_ai_colours"] = ai_image.name
    obj["i23d_painted_colours"] = painted.name
    obj["i23d_views"] = str(views_path)
    node.image = painted
    share = float((trust > 0.5).mean())
    return f"pictures painted on ({share:.0%} of the surface)"


def use_painted_colours(obj, on: bool) -> bool:
    """Switch a front + back original between the painted colours and the AI's own.
    False if it has no painted colours."""
    names = obj.get("i23d_ai_colours", ""), obj.get("i23d_painted_colours", "")
    if not all(names) or not all(n in bpy.data.images for n in names):
        return False
    node = _base_colour_image_node(obj)
    if node is None:
        return False
    node.image = bpy.data.images[names[1] if on else names[0]]
    return True
