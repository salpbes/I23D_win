import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.sh
import bpy, addon_utils
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
s=bpy.context.scene.i23d
print("defaults:", s.quality, s.random_seed, s.seed)
from image_to_game_asset import trellis_runner as tr
cmd=tr.build_command("/x","/y.png","/o/z",seed=s.seed,pipeline_type="1024_cascade"); print(cmd[-6:])
s.quality="1024_cascade"; print("V102 OK")
