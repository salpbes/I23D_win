import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests
import bpy, addon_utils, bmesh
import numpy as np
from mathutils.kdtree import KDTree
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
ctx = bpy.context; s = ctx.scene.i23d
prefs = ctx.preferences.addons["image_to_game_asset"].preferences; prefs.output_dir = T + "/out_tex"

# stand-in ComfyUI original: a sphere whose colours live in a texture, colour = (u, v, 0.5)
me = bpy.data.meshes.new("orb_original"); bm = bmesh.new(); bm.loops.layers.uv.new("UVMap")
bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=0.5, calc_uvs=True)
bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("orb_original", me); ctx.scene.collection.objects.link(ob)
N = 512
tex_img = bpy.data.images.new("orb_basecolor", N, N)
yy, xx = np.mgrid[0:N, 0:N] / (N - 1)
tex_img.pixels.foreach_set(np.stack([xx, yy, np.full_like(xx, 0.5), np.ones_like(xx)], -1)
                           .astype(np.float32).ravel())
mat = bpy.data.materials.new("orb_material"); mat.use_nodes = True
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = tex_img
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.append(mat)
assert not me.color_attributes
from image_to_game_asset import baking
assert baking.has_texture_colours(ob) and baking.colour_layer(ob) is None
ob["i23d_role"] = "original"; ob["i23d_base"] = "orb"; ob["i23d_image"] = T + "/picture.png"

ctx.view_layer.objects.active = ob; ob.select_set(True)
s.budget = "LIGHT"
assert bpy.ops.i23d.clean() == {"FINISHED"}
print("clean:", s.last_result)
assert "TRELLIS colours" in s.last_result, s.last_result
g = bpy.data.objects["orb_5k"]
img = g.data.materials[0].node_tree.nodes.active.image
W = img.size[0]; px = np.empty(W * W * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(W, W, 4)

# expected colour at each game vertex = texture colour at the nearest original vertex's UV
ouv = np.empty(len(me.loops) * 2); me.uv_layers[0].data.foreach_get("uv", ouv); ouv = ouv.reshape(-1, 2)
olv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", olv)
vert_uvs = {}
for li, vi in enumerate(olv):
    vert_uvs.setdefault(vi, []).append(ouv[li])
kd = KDTree(len(me.vertices))
for v in me.vertices:
    kd.insert(v.co, v.index)
kd.balance()
gme = g.data
guv = np.empty(len(gme.loops) * 2); gme.uv_layers["UVMap"].data.foreach_get("uv", guv); guv = guv.reshape(-1, 2)
glv = np.empty(len(gme.loops), np.int32); gme.loops.foreach_get("vertex_index", glv)
gco = np.empty(len(gme.vertices) * 3); gme.vertices.foreach_get("co", gco); gco = gco.reshape(-1, 3)
inv = np.linalg.inv(np.array(g["i23d_to_final"]))
on_orig = gco @ inv[:3, :3].T + inv[:3, 3]
errs = []
for li, vi in enumerate(glv):
    _, oi, _ = kd.find(on_orig[vi])
    uvs = np.array(vert_uvs[oi])
    if np.ptp(uvs, 0).max() > 0.01 or not (0.05 < uvs[0, 0] < 0.95 and 0.08 < uvs[0, 1] < 0.92):
        continue  # seam and poles: one point has several UVs
    expected = np.array([uvs[0, 0], uvs[0, 1], 0.5])
    x, y = np.clip((guv[li] * (W - 1)).round().astype(int), 0, W - 1)
    errs.append(np.abs(px[y, x, :3] - expected).mean())
err = float(np.mean(errs))
print(f"mean colour error per channel (0-1): {err:.3f} over {len(errs)} points")
assert len(errs) > 1000 and err < 0.06, err

# the original keeps its own material; no temporary bake materials are left behind
assert [m.name for m in me.materials] == ["orb_material"], [m.name for m in me.materials]
assert not [m.name for m in bpy.data.materials if m.name.startswith("I23D_bake_orb")]

# photo matching on a texture original pulls colours toward the brown photo
before = px[..., :3][px[..., :3].sum(-1) > 0.002].mean(0)
s.colour_match = 1.0
g.select_set(True); ctx.view_layer.objects.active = g
assert bpy.ops.i23d.apply_material() == {"FINISHED"}
img2 = g.data.materials[0].node_tree.nodes.active.image
px2 = np.empty(W * W * 4, np.float32); img2.pixels.foreach_get(px2); px2 = px2.reshape(W, W, 4)
after = px2[..., :3][px2[..., :3].sum(-1) > 0.002].mean(0)
print("mean colour before match:", before.round(3), "after:", after.round(3), "(photo object = 0.35 0.24 0.16)")
assert after[2] < before[2] and abs(after[0] - 0.35) < abs(before[0] - 0.35)
print("TEXTURE COLOUR TESTS PASSED")
