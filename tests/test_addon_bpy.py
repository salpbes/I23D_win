import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.sh
import sys, os, math
import bpy, addon_utils
bpy.ops.wm.read_factory_settings(use_empty=True)
mod = addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
assert mod is not None, "enable failed"
ctx = bpy.context
prefs = ctx.preferences.addons["image_to_game_asset"].preferences
prefs.trellis_dir = T + "/fake_trellis"; prefs.output_dir = T + "/out_bpy"
s = ctx.scene.i23d
# properties behaviour
s.image_path = T + "/picture.png"; assert s.asset_name == "picture", s.asset_name
s.material_preset = "GOLD"; assert abs(s.metallic-1)<1e-6 and abs(s.color[0]-0.83)<1e-3
assert bpy.ops.i23d.check_setup() == {"FINISHED"}
from image_to_game_asset import pipeline
orig = pipeline.import_original(ctx, T + "/out/test.glb", "crown")
print("imported:", orig.name, len(orig.data.polygons), [c.name for c in orig.users_collection])
ctx.view_layer.objects.active = orig; orig.select_set(True)
for budget in ("STANDARD", "LIGHT"):
    s.budget = budget
    s.budget = budget
    r = bpy.ops.i23d.clean(); assert r == {"FINISHED"}, r
    print(budget, "->", s.last_result)
g = bpy.data.objects["crown_5k"]
print("objects:", sorted(o.name for o in bpy.data.objects))
print("game props:", dict(g.items()), "mat:", g.data.materials[0].name, "hidden orig:", orig.hide_get())
# re-run same budget replaces, from the game object as active
ctx.view_layer.objects.active = g
assert bpy.ops.i23d.clean() == {"FINISHED"}
assert sorted(o.name for o in bpy.data.objects) == ["crown_15k","crown_5k","crown_original"], sorted(o.name for o in bpy.data.objects)
# min z == 0 (stand on ground)
import numpy as np; g = bpy.data.objects["crown_5k"]
co=np.empty(len(g.data.vertices)*3); g.data.vertices.foreach_get("co",co); co=co.reshape(-1,3)
print("min z", co[:,2].min().round(5), "center xy", ((co[:,0].min()+co[:,0].max())/2).round(4))
# target height
s.target_height = 2.0; s.budget="CUSTOM"; s.custom_tris=3000
assert bpy.ops.i23d.clean() == {"FINISHED"}; print("height test:", s.last_result)
# export
g = bpy.data.objects["crown_5k"]; [o.select_set(False) for o in ctx.view_layer.objects]; g.select_set(True); ctx.view_layer.objects.active = g
assert bpy.ops.i23d.export() == {"FINISHED"}, "export"
out = T + "/out_bpy/game-ready/crown_5k.glb"; assert os.path.isfile(out); print("exported", os.path.getsize(out), "bytes")
s.draco = True; s.export_dir = T + "/draco"
assert bpy.ops.i23d.export() == {"FINISHED"}; print("draco", os.path.getsize(T+"/draco/crown_5k.glb"), "bytes")
# reimport exported file to verify material & tri count
before=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=out)
new=[o for o in bpy.data.objects if o not in before][0]; new.data.calc_loop_triangles()
print("reimported tris", len(new.data.loop_triangles), "mat", new.data.materials[0].name)
addon_utils.disable("image_to_game_asset")
print("BPY TESTS PASSED")
