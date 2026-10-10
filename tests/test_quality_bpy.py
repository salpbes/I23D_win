import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests
import bpy, addon_utils
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
s = bpy.context.scene.i23d
prefs = bpy.context.preferences.addons["image_to_game_asset"].preferences
print("defaults:", s.quality, s.random_seed, s.seed, prefs.comfy_url, prefs.start_comfy, prefs.keep_comfy)
assert s.quality == "1024" and prefs.comfy_url == "http://127.0.0.1:8188"
assert prefs.comfy_dir.endswith("ComfyUI_windows_portable")
from image_to_game_asset import trellis_runner as tr
items = [i.identifier for i in s.bl_rna.properties["quality"].enum_items]
assert tuple(items) == tr.DETAILS, items
for detail in items:
    p = tr.build_prompt(tr.load_workflow(), "x.png", seed=s.seed, detail=detail, prefix="i23d/x")
    assert any(n["inputs"].get("target_resolution") == int(detail) for n in p.values())
    assert detail in tr.QUIET_WARNING_SECONDS
print("QUALITY TESTS PASSED")
