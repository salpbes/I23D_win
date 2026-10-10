import os, sys, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests
import bpy, addon_utils, bmesh
import numpy as np
from mathutils.kdtree import KDTree
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
ctx = bpy.context; s = ctx.scene.i23d
prefs = ctx.preferences.addons["image_to_game_asset"].preferences; prefs.output_dir = T + "/out_maps"
s.export_dir = T + "/out_maps/game-ready"

# stand-in ComfyUI original, wired like Blender's glTF import of a TRELLIS.2 .glb:
# base colour image -> Base Color; one Non-Color image -> Separate Color (G = roughness, B = metallic).
# A sphere with fine ridges (too fine for the light game mesh, so only the normal map can keep them),
# metallic = 1 on the top half (v > 0.5), roughness = 0.2 + 0.6 u.
me = bpy.data.meshes.new("orb_original"); bm = bmesh.new(); bm.loops.layers.uv.new("UVMap")
K, A = 64, 0.01          # ridges around the middle: count and height (x radius)
bmesh.ops.create_uvsphere(bm, u_segments=1024, v_segments=128, radius=0.5, calc_uvs=True)
for v in bm.verts:
    v.co *= 1 + A * np.sin(K * np.arctan2(v.co.y, v.co.x))
bm.to_mesh(me); bm.free()
me.shade_smooth()
ob = bpy.data.objects.new("orb_original", me); ctx.scene.collection.objects.link(ob)
N = 512
yy, xx = np.mgrid[0:N, 0:N] / (N - 1)


def image(name, rgb, non_color):
    img = bpy.data.images.new(name, N, N)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(np.concatenate([rgb, np.ones_like(xx)[..., None]], -1).astype(np.float32).ravel())
    return img


col_img = image("orb_basecolor", np.stack([xx, yy, np.full_like(xx, 0.5)], -1), False)
mr_img = image("orb_mr", np.stack([np.ones_like(xx), 0.2 + 0.6 * xx, (yy > 0.5).astype(float)], -1), True)
mat = bpy.data.materials.new("orb_material"); mat.use_nodes = True
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = col_img
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
mr = nt.nodes.new("ShaderNodeTexImage"); mr.image = mr_img
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(mr.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
me.materials.append(mat)
from image_to_game_asset import baking, pipeline
assert baking.has_texture_colours(ob) and baking.has_texture_metal_rough(ob)
ob["i23d_role"] = "original"; ob["i23d_base"] = "orb"; ob["i23d_image"] = T + "/picture.png"

ctx.view_layer.objects.active = ob; ob.select_set(True)
assert s.surface_maps, "surface maps should be on by default"
s.budget = "LIGHT"; s.texture_size = "1024"
assert bpy.ops.i23d.clean() == {"FINISHED"}
print("clean:", s.last_result)
assert "TRELLIS colours + metal/roughness + normal map" in s.last_result, s.last_result
g = bpy.data.objects["orb_5k"]
gmat = g.data.materials[0]; gnt = gmat.node_tree
assert gnt.nodes.active.image.name == "orb_5k_basecolor"   # base colour stays the active node
gbsdf = next(n for n in gnt.nodes if n.type == "BSDF_PRINCIPLED")
split = gbsdf.inputs["Metallic"].links[0].from_node
assert split.type == "SEPARATE_COLOR" and gbsdf.inputs["Metallic"].links[0].from_socket.name == "Blue"
assert gbsdf.inputs["Roughness"].links[0].from_node == split
assert gbsdf.inputs["Roughness"].links[0].from_socket.name == "Green"
mr_out = split.inputs["Color"].links[0].from_node.image
nmap = gbsdf.inputs["Normal"].links[0].from_node
assert nmap.type == "NORMAL_MAP" and nmap.space == "TANGENT"
n_out = nmap.inputs["Color"].links[0].from_node.image
assert mr_out.colorspace_settings.name == n_out.colorspace_settings.name == "Non-Color"
assert mr_out.packed_file and n_out.packed_file
# no temporary bake materials are left behind, the original keeps its own material
assert [m.name for m in me.materials] == ["orb_material"]
assert not [m.name for m in bpy.data.materials if m.name.startswith("I23D_bake_orb")]


def pixels(img):
    w = img.size[0]; px = np.empty(w * w * 4, np.float32); img.pixels.foreach_get(px)
    return px.reshape(w, w, 4)


# ---- 1. metallic/roughness land where the original has them
gme = g.data
guv = np.empty(len(gme.loops) * 2); gme.uv_layers["UVMap"].data.foreach_get("uv", guv); guv = guv.reshape(-1, 2)
glv = np.empty(len(gme.loops), np.int32); gme.loops.foreach_get("vertex_index", glv)
gco = np.empty(len(gme.vertices) * 3); gme.vertices.foreach_get("co", gco); gco = gco.reshape(-1, 3)
inv = np.linalg.inv(np.array(g["i23d_to_final"]))
on_orig = gco @ inv[:3, :3].T + inv[:3, 3]
ouv = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get("uv", ouv); ouv = ouv.reshape(-1, 2)
olv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", olv)
vert_uv = np.zeros((len(me.vertices), 2)); vert_spread = np.zeros(len(me.vertices))   # one point can have several UVs
order = np.argsort(olv, kind="stable")
starts = np.searchsorted(olv[order], np.arange(len(me.vertices)))
for vi in range(len(me.vertices)):
    uvs = ouv[order[starts[vi]:(starts[vi + 1] if vi + 1 < len(me.vertices) else len(order))]]
    vert_uv[vi] = uvs[0]; vert_spread[vi] = np.ptp(uvs, 0).max()
kd = KDTree(len(me.vertices))
for v in me.vertices:
    kd.insert(v.co, v.index)
kd.balance()
nearest = np.array([kd.find(p)[1] for p in on_orig])

MR = pixels(mr_out); W = MR.shape[0]
xy = np.clip((guv * (W - 1)).round().astype(int), 0, W - 1)
got = MR[xy[:, 1], xy[:, 0]]
u, v = vert_uv[nearest[glv]].T
ok = (vert_spread[nearest[glv]] < 0.01) & (u > 0.05) & (u < 0.95) & (np.abs(v - 0.5) > 0.06) & (v > 0.08) & (v < 0.92)
rough_err = np.abs(got[ok, 1] - (0.2 + 0.6 * u[ok])).mean()
metal_err = np.abs(got[ok, 2] - (v[ok] > 0.5)).mean()
print(f"metallic error {metal_err:.3f}, roughness error {rough_err:.3f} over {ok.sum()} points")
assert ok.sum() > 1000 and metal_err < 0.05 and rough_err < 0.04, (metal_err, rough_err)

# ---- 2. the normal map turns the light mesh's normals into the detailed original's
# (checked at triangle centres: pixels at a game point sit on a UV island's edge)
gme.calc_tangents(uvmap="UVMap")
loop_vec = lambda attr: np.array([getattr(l, attr) for l in gme.loops])
tan, nrm = loop_vec("tangent"), loop_vec("normal")
bit = loop_vec("bitangent_sign")[:, None] * np.cross(nrm, tan)
gme.calc_loop_triangles()
tri = np.empty(len(gme.loop_triangles) * 3, np.int32); gme.loop_triangles.foreach_get("loops", tri); tri = tri.reshape(-1, 3)
c_tan, c_bit, c_nrm = tan[tri].mean(1), bit[tri].mean(1), nrm[tri].mean(1)
cxy = np.clip((guv[tri].mean(1) * (W - 1)).round().astype(int), 0, W - 1)
ts = pixels(n_out)[cxy[:, 1], cxy[:, 0], :3] * 2 - 1
unit = lambda x: x / np.linalg.norm(x, axis=1, keepdims=True)
mapped = unit(ts[:, :1] * c_tan + ts[:, 1:2] * c_bit + ts[:, 2:3] * c_nrm)
# the ridged sphere's exact normal: grad(|p| - R(1 + A sin(K phi))), at each centre's direction
p = on_orig[glv][tri].mean(1)
around = np.stack([-p[:, 1], p[:, 0], np.zeros(len(p))], 1) / (p[:, 0] ** 2 + p[:, 1] ** 2)[:, None]
want = unit(unit(p) - 0.5 * A * K * np.cos(K * np.arctan2(p[:, 1], p[:, 0]))[:, None] * around)
ang = lambda a, b: np.degrees(np.arccos(np.clip((a * b).sum(1), -1, 1)))
mid = np.abs(unit(p)[:, 2]) < 0.3           # the ridges bunch up towards the poles
before, after = ang(unit(c_nrm), want)[mid].mean(), ang(mapped, want)[mid].mean()
tilt = np.corrcoef((want * unit(around)).sum(1)[mid], (mapped * unit(around)).sum(1)[mid])[0, 1]
print(f"normal error vs the detailed original: {before:.1f} deg without the map, {after:.1f} deg with it; "
      f"ridge tilt correlation {tilt:.3f}")
assert after < 4 and after < 0.5 * before and tilt > 0.95, (before, after, tilt)

# ---- 3. the exported .glb carries both maps
path = pipeline.export(ctx, g)


def glb_json(p):
    data = open(p, "rb").read()
    length = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + length])


gl = glb_json(path)
pbr = gl["materials"][0]["pbrMetallicRoughness"]
print("exported", path.name, "material:", sorted(gl["materials"][0]), "pbr:", sorted(pbr))
assert "baseColorTexture" in pbr and "metallicRoughnessTexture" in pbr and "normalTexture" in gl["materials"][0]
assert len({pbr["baseColorTexture"]["index"], pbr["metallicRoughnessTexture"]["index"],
            gl["materials"][0]["normalTexture"]["index"]}) == 3
assert len(gl["images"]) == 3
for f in ("orb_5k_basecolor", "orb_5k_metallicroughness", "orb_5k_normal"):
    assert os.path.exists(f"{T}/out_maps/textures/{f}.png"), f

# ---- 4. switched off: plain base colour material, as before
s.surface_maps = False
g.select_set(True); ctx.view_layer.objects.active = g
assert bpy.ops.i23d.apply_material() == {"FINISHED"}
gnt = g.data.materials[0].node_tree
gbsdf = next(n for n in gnt.nodes if n.type == "BSDF_PRINCIPLED")
assert not gbsdf.inputs["Normal"].links and not gbsdf.inputs["Metallic"].links
assert abs(gbsdf.inputs["Roughness"].default_value - 0.8) < 1e-6
gl = glb_json(pipeline.export(ctx, g))
assert "normalTexture" not in gl["materials"][0] and "metallicRoughnessTexture" not in gl["materials"][0]["pbrMetallicRoughness"]
print("SURFACE MAP TESTS PASSED")
