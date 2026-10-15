# Painting the front + back pictures onto a Pixal3D model ("Pixel Match"), and the licence record.
# A cube stands in for the model: a red front picture and a blue back picture must land on the
# front and back faces only, hidden and sideways surfaces keep their own paint.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.ps1
import bpy, addon_utils
import numpy as np
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
from image_to_game_asset import baking, exporter, photo_paint as pp

W = Path(T) / "paint"
W.mkdir(parents=True, exist_ok=True)

# ---- the cameras: Pixal3D's orbit rig in Blender's space (front camera on -Y, Z up)
front, back = pp.orbit_camera(0, 20, 1.1), pp.orbit_camera(180, 20, 1.1)
assert np.allclose(front.position, [0, -3.1194, 0], atol=1e-3) and np.allclose(back.position, [0, 3.1194, 0], atol=1e-3)
col, row, depth = pp.project(np.array([[0, 0, 0], [0.1, 0, 0.1]]), front, 1024)
assert np.allclose([col[0], row[0]], 512) and col[1] > 512 and row[1] < 512, (col, row)
assert pp.project(np.array([[0.1, 0, 0]]), back, 1024)[0][0] < 512, "seen from behind, +X is on the left"
# the object fills 1/pad of the frame: the edge of the unit cube at the middle lands there
assert abs(pp.project(np.array([[0.5, 0, 0]]), front, 1024)[0][0] - (512 + 512 / 1.1)) < 1

# ---- the maths: a plane facing the front camera, and a hidden plane right behind it
# (points about a pixel apart, as dense as the texels of a real texture)
g = np.stack(np.meshgrid(np.linspace(-0.3, 0.3, 300), np.linspace(-0.3, 0.3, 300)), -1).reshape(-1, 2)
seen = np.column_stack([g[:, 0], np.full(len(g), -0.2), g[:, 1]])
hidden = seen + [0, 0.2, 0]
points = np.vstack([seen, hidden])
normals = np.tile([0.0, -1.0, 0.0], (len(points), 1))
grey = np.full((len(points), 3), 0.5)
red = np.zeros((1024, 1024, 3), np.float32); red[100:924, 100:924] = (0.8, 0.1, 0.1)
new, trust, shift = pp.paint(points, normals, grey, [(front, red, pp.object_mask(red))])
assert trust[:len(seen)].min() > 0.99 and np.allclose(new[:len(seen)], (0.8, 0.1, 0.1), atol=1e-4), "seen: picture colour"
assert trust[len(seen):].max() == 0, "hidden behind the first plane: no picture colour"
assert np.allclose(shift, (0.3, -0.4, -0.4), atol=1e-3) and np.allclose(new[len(seen):], (0.8, 0.1, 0.1), atol=1e-3)
sideways = pp.paint(seen, np.tile([1.0, 0, 0], (len(seen), 1)), grey[:len(seen)], [(front, red, pp.object_mask(red))])[1]
assert sideways.max() == 0, "a surface turned away from the camera keeps its own paint"
print("photo_paint maths OK")

# ---- in Blender: a textured cube, painted from a red front and a blue back picture
def save_png(rgb, path):
    img = bpy.data.images.new(path.stem, rgb.shape[1], rgb.shape[0])
    img.pixels.foreach_set(np.dstack([rgb, np.ones(rgb.shape[:2])])[::-1].astype(np.float32).ravel())
    img.filepath_raw, img.file_format = str(path), "PNG"
    img.save()
    bpy.data.images.remove(img)

blue = np.zeros((1024, 1024, 3), np.float32); blue[100:924, 100:924] = (0.1, 0.1, 0.8)
save_png(red, W / "cube_front_view.png")
save_png(blue, W / "cube_back_view.png")
(W / "cube_views.json").write_text(json.dumps({"fov": 20.0, "pad": 1.1, "views": [
    {"name": "front", "azimuth": 0.0, "picture": "cube_front_view.png"},
    {"name": "back", "azimuth": 180.0, "picture": "cube_back_view.png"}]}))

bpy.ops.mesh.primitive_cube_add(size=0.6)
cube = bpy.context.active_object
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.uv.smart_project(island_margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")
tex = bpy.data.images.new("cube_ai_colours", 256, 256)
tex.pixels.foreach_set(np.full(256 * 256 * 4, 0.5, np.float32))
mat = bpy.data.materials.new("cube"); mat.use_nodes = True
node = mat.node_tree.nodes.new("ShaderNodeTexImage"); node.image = tex
bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
cube.data.materials.append(mat)

note = baking.paint_from_pictures(bpy.context, cube, W / "cube_views.json")
print(note)
assert "pictures painted on" in note
painted = node.image
assert painted.name == cube["i23d_painted_colours"] and cube["i23d_ai_colours"] == "cube_ai_colours"
assert painted.packed_file is not None and tex.use_fake_user and painted.use_fake_user
px = np.empty(256 * 256 * 4, np.float32); painted.pixels.foreach_get(px); px = px.reshape(-1, 4)[:, :3]
is_red = (px[:, 0] > 0.6) & (px[:, 1] < 0.3)
is_blue = (px[:, 2] > 0.6) & (px[:, 0] < 0.3)
print(f"red {is_red.mean():.1%}, blue {is_blue.mean():.1%} of the texture")
assert 0.05 < is_red.mean() < 0.2 and 0.05 < is_blue.mean() < 0.2, "front and back faces painted"
assert abs(is_red.mean() - is_blue.mean()) < 0.03
assert not (is_red | is_blue).all(), "the sides keep their own (shifted) paint"

# painting again starts from the AI's colours, not from the painted ones
again = baking.paint_from_pictures(bpy.context, cube, W / "cube_views.json")
assert node.image.name == cube["i23d_painted_colours"] and "cube_ai_colours" in bpy.data.images
# the switch between painted and AI colours
assert baking.use_painted_colours(cube, False) and node.image.name == "cube_ai_colours"
assert baking.use_painted_colours(cube, True) and node.image.name == cube["i23d_painted_colours"]
bpy.ops.mesh.primitive_plane_add()
assert not baking.use_painted_colours(bpy.context.active_object, True), "nothing painted: no switch"

# ---- the licence record next to an exported .glb
glb = W / "cube_15k.glb"
glb.write_bytes(b"glTF")
doc = json.loads(exporter.write_licences(glb, generator="Pixal3D", seed=7, painted=True).read_text())
names = [m["name"] for m in doc["made_with"]]
assert doc["asset"] == "cube_15k.glb" and doc["seed"] == 7 and doc["pictures_painted_on"] is True
assert names[0] == "Pixal3D" and {"DINOv3", "BiRefNet", "ComfyUI", "Image to Game Asset"} <= set(names), names
doc = json.loads(exporter.write_licences(glb, generator="TRELLIS.2").read_text())
assert doc["made_with"][0]["name"] == "TRELLIS.2" and doc["made_with"][0]["licence"] == "MIT"
print("PAINT TESTS PASSED")
