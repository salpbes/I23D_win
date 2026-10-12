# Installs the built add-on zip the way a user does (Install from Disk) and checks that it carries
# its own ComfyUI + TRELLIS.2 installer. run_tests.ps1 points BLENDER_USER_RESOURCES into tests\_work,
# so this never touches the real Blender settings. Usage: blender -b -P test_zip_bpy.py -- <zip>
import os, sys, importlib
from pathlib import Path
import bpy
ZIP = sys.argv[sys.argv.index("--") + 1]
assert "_work" in bpy.utils.resource_path("USER"), "refusing to install into the real Blender settings"
bpy.ops.wm.read_factory_settings(use_empty=True)
r = bpy.ops.extensions.package_install_files(filepath=ZIP, repo="user_default", enable_on_install=True)
assert r == {"FINISHED"}, r
addon = importlib.import_module("bl_ext.user_default.image_to_game_asset")
inst = importlib.import_module("bl_ext.user_default.image_to_game_asset.installer")
root = Path(addon.__file__).parent
print("installed at:", root)
assert inst.SCRIPT.is_file() and inst.SCRIPT.parent == root / "install", inst.SCRIPT
assert (root / "workflows" / "trellis2_image_to_glb.json").is_file()
assert hasattr(bpy.ops.i23d, "install_comfy") and bpy.ops.i23d.install_comfy.poll()

# Where the installer is sent, and how it is started (a visible window that waits at the end).
home = Path.home() / "I23D"
assert inst.install_dir_for(str(home / "ComfyUI_windows_portable")) == home
assert inst.install_dir_for("D:\\AI\\ComfyUI_windows_portable\\") == Path("D:\\AI")
assert inst.install_dir_for("D:\\somewhere\\else") == home  # not a folder the installer makes
assert inst.install_dir_for("") == home
cmd = inst.command(Path("D:\\AI"), check_only=True)
assert cmd[:4] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"], cmd
assert cmd[cmd.index("-File") + 1] == str(inst.SCRIPT) and cmd[cmd.index("-InstallDir") + 1] == "D:\\AI", cmd
assert "-Pause" in cmd and "-Check" in cmd and "-Check" not in inst.command(Path("D:\\AI"))

# Check Setup remembers what is missing, so the Install button can show next to it.
prefs = bpy.context.preferences.addons["bl_ext.user_default.image_to_game_asset"].preferences
assert Path(prefs.comfy_dir) == home / "ComfyUI_windows_portable", prefs.comfy_dir
prefs.comfy_dir = os.path.join(os.environ["I23D_TEST_WORK"], "no_comfy_here", "ComfyUI_windows_portable")
prefs.comfy_url = "http://127.0.0.1:9"  # nothing listens there: the folder check is used
try:  # in background mode the operator's error report arrives as an exception
    bpy.ops.i23d.check_setup()
    raise AssertionError("Check Setup passed without ComfyUI")
except RuntimeError as exc:
    assert "not found" in str(exc), exc
assert inst.last_problems and "not found" in inst.last_problems[0], inst.last_problems
print("ZIP TESTS PASSED")
