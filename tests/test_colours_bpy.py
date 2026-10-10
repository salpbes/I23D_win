import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.sh
import sys, os
import bpy, addon_utils, bmesh
import numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
ctx = bpy.context; s = ctx.scene.i23d
prefs = ctx.preferences.addons["image_to_game_asset"].preferences; prefs.output_dir = T + "/out_v11"
# stand-in TRELLIS original: a sphere whose colour = its position (so we can check the bake lands right)
me = bpy.data.meshes.new("toy_original"); bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=0.5); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("toy_original", me); ctx.scene.collection.objects.link(ob)
ca = me.color_attributes.new("Color", "BYTE_COLOR", "CORNER")
lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", lv)
co = np.empty(len(me.vertices)*3); me.vertices.foreach_get("co", co); co = co.reshape(-1,3)
rgb = np.clip(co + 0.5, 0, 1)
col = np.concatenate([rgb[lv], np.ones((len(lv),1))], 1).astype(np.float32)
ca.data.foreach_set("color_srgb", col.ravel())
ob["i23d_role"] = "original"; ob["i23d_base"] = "toy"; ob["i23d_image"] = T + "/picture.png"
ctx.view_layer.objects.active = ob; ob.select_set(True)
assert s.material_preset == "TRELLIS", s.material_preset
s.budget = "LIGHT"
r = bpy.ops.i23d.clean(); assert r == {"FINISHED"}, r
print("clean:", s.last_result)
g = bpy.data.objects["toy_5k"]
img = g.data.materials[0].node_tree.nodes.active.image
W = img.size[0]; px = np.empty(W*W*4, np.float32); img.pixels.foreach_get(px); px = px.reshape(W, W, 4)
# compare texture colour at each vertex's UV with the expected colour (position-based) in the ORIGINAL's frame
gme = g.data; uv = np.empty(len(gme.loops)*2); gme.uv_layers["UVMap"].data.foreach_get("uv", uv); uv = uv.reshape(-1,2)
glv = np.empty(len(gme.loops), np.int32); gme.loops.foreach_get("vertex_index", glv)
gco = np.empty(len(gme.vertices)*3); gme.vertices.foreach_get("co", gco); gco = gco.reshape(-1,3)
to_final = np.array(g["i23d_to_final"]); inv = np.linalg.inv(to_final)
world_on_orig = gco @ inv[:3,:3].T + inv[:3,3]
expected = np.clip(world_on_orig[glv] + 0.5, 0, 1)
xy = np.clip((uv * (W - 1)).round().astype(int), 0, W - 1)
got = px[xy[:,1], xy[:,0], :3]
# texture pixels are stored as (sRGB-encoded) values in the image buffer
err = np.abs(got - expected).mean()
print("mean colour error per channel (0-1):", round(float(err), 3))
assert err < 0.06, err
# photo matching: 100% should pull the overall colour toward the brown photo
s.colour_match = 1.0
g.select_set(True); ctx.view_layer.objects.active = g
r = bpy.ops.i23d.apply_material(); assert r == {"FINISHED"}, r
img2 = g.data.materials[0].node_tree.nodes.active.image
px2 = np.empty(W*W*4, np.float32); img2.pixels.foreach_get(px2); px2 = px2.reshape(W, W, 4)
got2 = px2[xy[:,1], xy[:,0], :3]
print("mean colour before match:", got.mean(0).round(3), "after:", got2.mean(0).round(3), "(photo object = 0.35 0.24 0.16)")
assert got2.mean(0)[0] < got.mean(0)[0] and got2.mean(0)[2] < got.mean(0)[2]
assert "temp layer gone", "I23D_bake_colour" not in me.color_attributes
assert not ob.data.materials or ob.data.materials[0] is None or "I23D" not in ob.data.materials[0].name
# export and re-read
s.export_dir = T + "/out_v11/exp"
r = bpy.ops.i23d.export(); assert r == {"FINISHED"}
path = T + "/out_v11/exp/toy_5k.glb"; print("glb bytes:", os.path.getsize(path))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=path)
o = [o for o in bpy.data.objects if o.type == "MESH"][0]
tex = [n for n in o.data.materials[0].node_tree.nodes if n.type == "TEX_IMAGE"]
print("re-imported: texture", tex[0].image.size[:] if tex else None)
assert tex and tex[0].image.size[0] == 2048
print("V11 TESTS PASSED")
