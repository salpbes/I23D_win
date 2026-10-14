# The picture check: what the notes say about a cut-out, and how a finished check reaches the panel.
# Uses the cut-out and mask that test_runner.py fetched from the fake ComfyUI (a white square on black).
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.ps1
import bpy, addon_utils
import numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
from image_to_game_asset import operators as ops, picture_check as pc

# ---- what the notes say
def mask(*rects, size=(600, 800)):
    m = np.zeros(size)
    for y0, y1, x0, x1 in rects:
        m[y0:y1, x0:x1] = 1
    return m
def says(m):
    return " | ".join(n.text for n in pc.mask_notes(m))
assert pc.mask_notes(mask((100, 500, 200, 600)))[0].good, "one clear object"
assert "No object found" in says(mask()), says(mask())
assert "small in the picture" in says(mask((300, 320, 400, 420)))
assert "touches the edge" in says(mask((0, 400, 200, 600)))
assert "2 separate pieces" in says(mask((100, 500, 50, 300), (100, 500, 450, 750)))
assert pc.mask_notes(mask((100, 500, 200, 600), (550, 553, 10, 13)))[0].good, "a speck is not a piece"
ring = mask((100, 500, 200, 600)) - mask((150, 450, 250, 550))
assert pc.mask_notes(ring)[0].good, "a hole doesn't make two pieces"
assert pc.mask_notes(np.dstack([mask((100, 500, 200, 600)) * 255] * 3))[0].good, "RGB 0-255 masks work"
assert "small (300 x 400" in pc.picture_notes(300, 400)[0].text and pc.picture_notes(1024, 768) == []

# ---- front + back: where a side-by-side picture splits, and do the two views match
sheet = np.ones((100, 300, 3)); sheet[20:90, 30:110] = 0.2; sheet[20:90, 190:270] = 0.3
assert pc.find_split(sheet) == 150, pc.find_split(sheet)
assert pc.find_split(sheet * 255) == 150, "0-255 pictures work"
assert pc.find_split(np.ones((100, 300, 3))) is None, "nothing in the picture"
joined = sheet.copy(); joined[50:55, 100:200] = 0.2
assert pc.find_split(joined) is None, "no gap between front and back"
one = np.ones((100, 300, 3)); one[20:90, 100:200] = 0.2
assert pc.find_split(one) is None, "one object in the middle is not front + back"
rgba = np.zeros((100, 300, 4)); rgba[20:90, 30:110, 3] = 1; rgba[20:90, 190:270, 3] = 1
assert pc.find_split(rgba) == 150, "transparent background"
pair = pc.pair_notes(mask((100, 500, 200, 400)), mask((100, 500, 210, 410)))
assert len(pair) == 1 and pair[0].good and "front and back" in pair[0].text, pair
assert "different outlines" in " ".join(n.text for n in pc.pair_notes(mask((100, 500, 200, 400)),
                                                                        mask((100, 300, 200, 400))))
edge = pc.pair_notes(mask((100, 500, 200, 400)), mask((0, 500, 200, 400)))
assert any(n.text.startswith("Back: The object touches") for n in edge), edge

# ---- a finished check reaches the panel
ctx = bpy.context
prefs = ctx.preferences.addons["image_to_game_asset"].preferences
prefs.comfy_dir = T + "/ComfyUI_windows_portable"; prefs.output_dir = T + "/out_picture"
prefs.comfy_url = "http://127.0.0.1:9"; prefs.start_comfy = False   # nothing listens, nothing starts
s = ctx.scene.i23d
s.image_path = T + "/picture.png"   # the automatic check stays off in background mode
assert ops.picture_check_for(ctx) is None
assert bpy.ops.i23d.check_picture.poll()
try:
    bpy.ops.i23d.check_picture()
except RuntimeError as exc:   # reported as a warning: ComfyUI isn't running and may not be started
    assert "not running" in str(exc), exc
check = ops.picture_check_for(ctx)
assert check is not None and "not running" in check.error and not check.running

class Done:  # a finished CutoutJob, with the files test_runner.py downloaded
    error, label = None, "Cut-out ready"
    cutout_path = T + "/out/previews/picture_cutout.png"
    mask_path = T + "/out/previews/picture_mask.png"
    back_cutout_path = back_mask_path = None
    def is_running(self):
        return False
check = ops.PictureCheck(image=bpy.path.abspath(s.image_path), job=Done(),
                         notes=pc.picture_notes(300, 400), key=ops._check_key(ctx))
ops.finish_picture_check(check)
ops._check = check
print("notes:", [n.text for n in check.notes])
assert check.notes[0].text.startswith("The picture is small") and check.notes[-1].good, check.notes
# (Background Blender makes no preview icons, so check.icon_id stays 0 here.)
assert check.cutout == Done.cutout_path and not check.error
assert ops.picture_check_for(ctx) is check and bpy.ops.i23d.view_cutout.poll()
assert bpy.ops.i23d.generate.poll()

class Busy(Done):  # a check still removing the background: Generate waits for it
    def is_running(self):
        return True
ops._check = ops.PictureCheck(image=check.image, job=Busy())
assert not bpy.ops.i23d.generate.poll(), "Generate must wait for the picture check"
ops._check = check
s.views = "FRONT_BACK"
assert ops.picture_check_for(ctx) is None, "front + back needs its own check"
s.views = "ONE"
assert ops.picture_check_for(ctx) is check

# ---- front + back input: a side-by-side picture is split, a separate back is used as it is
img = bpy.data.images.new("sheet", 300, 100)
img.pixels.foreach_set(np.dstack([sheet, np.ones((100, 300))]).astype(np.float32).ravel())
img.filepath_raw, img.file_format = T + "/sheet.png", "PNG"
img.save()
bpy.data.images.remove(img)
s.image_path = T + "/sheet.png"
s.views = "FRONT_BACK"
assert ops.front_back_input(ctx, bpy.path.abspath(s.image_path)) == (None, (300, 100, 150), "")
s.back_path = T + "/picture.png"
back, split, problem = ops.front_back_input(ctx, bpy.path.abspath(s.image_path))
assert back == bpy.path.abspath(s.back_path) and split is None and not problem
s.back_path = ""
s.image_path = T + "/picture.png"
assert "no gap" in ops.front_back_input(ctx, bpy.path.abspath(s.image_path))[2]
s.views = "ONE"
assert ops.front_back_input(ctx, bpy.path.abspath(s.image_path)) == (None, None, "")
s.image_path = T + "/other.png"
assert ops.picture_check_for(ctx) is None, "a new picture needs a new check"
assert len(bpy.data.images) == 0, "reading the mask left an image behind"
print("PICTURE TESTS PASSED")
