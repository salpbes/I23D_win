import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.sh
import bpy, addon_utils
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
assert all(hasattr(bpy.ops.i23d, n) for n in ("open_log","dismiss_error","generate","clean","export","stop_comfy","cancel","check_setup","install_comfy","check_picture","view_cutout")), "missing operators"
s=bpy.context.scene.i23d; s.last_error="RuntimeError: Input type (MPSFloatType) and weight type (MPSHalfType) should be the same"
assert bpy.ops.i23d.dismiss_error()=={"FINISHED"} and s.last_error==""
from image_to_game_asset.ui import _path_lines
p = r"C:\Users\someone_with_a_long_name\I23D\output\game-ready"
lines = _path_lines(p)
print("export folder lines:", lines)
assert "".join(lines) == p and all(len(l) <= 33 for l in lines) and len(lines) > 1, lines
assert _path_lines(r"D:\models") == [r"D:\models"]
print("UI TESTS PASSED")
