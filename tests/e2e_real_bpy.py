"""End to end with the real ComfyUI + TRELLIS.2 (needs the graphics card, ~3-4 minutes).

    blender -b --factory-startup -P tests/e2e_real_bpy.py -- <picture> <out folder> [ComfyUI folder]

Uses the add-on's own code: starts ComfyUI if it isn't running (offline, this PC only), makes the
model, imports it, cleans it to 15k triangles with TRELLIS colours (+ metal/roughness and normal
maps), exports a .glb and renders both. Also times the colour bake with and without the extra maps.
"""
import os, sys, time, json, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))
import bpy, addon_utils
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
picture, out = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
assert addon_utils.enable("image_to_game_asset", default_set=True, handle_error=None)
from image_to_game_asset import operators, pipeline, preferences, trellis_runner as tr
ctx = bpy.context
s, prefs = ctx.scene.i23d, preferences.get(ctx)
if len(args) > 2:
    prefs.comfy_dir = args[2]
prefs.output_dir = out
s.image_path = picture
assert not tr.check_setup(prefs.comfy_dir, prefs.comfy_url), tr.check_setup(prefs.comfy_dir, prefs.comfy_url)
was_running = tr.server_up(prefs.comfy_url)
print("ComfyUI already running:", was_running)

name = tr.sanitize_name(s.asset_name)
out_dir = pipeline.output_dir(ctx)
job = tr.TrellisJob(url=prefs.comfy_url, image=picture, out_base=out_dir / name, seed=s.seed,
                    detail=s.quality, log_path=out_dir / f"{name}_log.txt",
                    server=operators._server_for(prefs, out_dir / "comfyui_log.txt"))
job.start()
last = None
while job.is_running():
    if job.label != last:
        print(f"{job.elapsed():6.0f}s {job.fraction:4.0%}  {job.label}", flush=True)
        last = job.label
    time.sleep(0.5)
print(f"done in {tr.fmt_duration(job.elapsed())}: error={job.error} glb={job.glb_path}")
assert job.error is None and job.glb_path, job.error
if not was_running:
    assert operators._server is not None and operators._server.is_alive(), "add-on should have started ComfyUI"
    assert "--offline" in operators._server.command()

original = pipeline.import_original(ctx, job.glb_path, name, picture)
ctx.view_layer.objects.active = original
original.select_set(True)
s.budget, s.material_preset = "STANDARD", "TRELLIS"
t = time.time()
game, stats = pipeline.clean(ctx, original)
print(f"clean ({time.time() - t:.0f} s):", pipeline.describe(stats))
assert "TRELLIS colours + metal/roughness + normal map" in stats["colours"], stats["colours"]

# what the extra maps cost: re-bake the colours without them, then with them again
for maps in (False, True):
    s.surface_maps = maps
    t = time.time()
    pipeline.apply_look(ctx, game, original)
    print(f"colour bake {'with' if maps else 'without'} metal/roughness + normal maps: {time.time() - t:.1f} s")
path = pipeline.export(ctx, game)
print("exported", path, f"{path.stat().st_size / 1e6:.1f} MB")
data = path.read_bytes()
gl = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
m = gl["materials"][0]
print("glb material:", sorted(m), sorted(m["pbrMetallicRoughness"]),
      [(i.get("name"), i.get("mimeType")) for i in gl["images"]])
assert "metallicRoughnessTexture" in m["pbrMetallicRoughness"] and "normalTexture" in m


def render(obj, file, lit=False):
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o is not obj
    lo = Vector(map(min, *[obj.matrix_world @ Vector(c) for c in obj.bound_box]))
    hi = Vector(map(max, *[obj.matrix_world @ Vector(c) for c in obj.bound_box]))
    centre, size = (lo + hi) / 2, max(hi - lo)
    cam = bpy.data.objects.get("Cam") or bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    if cam.name not in ctx.scene.collection.objects:
        ctx.scene.collection.objects.link(cam)
    cam.location = centre + Vector((size * 1.2, -size * 1.6, size * 0.6))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    ctx.scene.camera = cam
    if lit:   # real materials: shows the metal, roughness and normal maps
        ctx.scene.render.engine = "BLENDER_EEVEE"
        world = ctx.scene.world or bpy.data.worlds.new("World")
        ctx.scene.world = world
        world.color = (0.35, 0.37, 0.4)
        sun = bpy.data.objects.get("Sun") or bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
        if sun.name not in ctx.scene.collection.objects:
            ctx.scene.collection.objects.link(sun)
        sun.data.energy = 4
        sun.rotation_euler = (0.9, 0.2, 0.6)
    else:
        ctx.scene.render.engine = "BLENDER_WORKBENCH"
        ctx.scene.display.shading.light = "FLAT"
        ctx.scene.display.shading.color_type = "TEXTURE"
    ctx.scene.render.resolution_x = ctx.scene.render.resolution_y = 640
    ctx.scene.render.filepath = os.path.join(out, file)
    bpy.ops.render.render(write_still=True)


s.show_originals = True
original.hide_set(False)
render(original, "e2e_original.png")
render(game, "e2e_game_15k.png")
render(original, "e2e_original_lit.png", lit=True)
render(game, "e2e_game_15k_lit.png", lit=True)
s.surface_maps = False
pipeline.apply_look(ctx, game, original)
render(game, "e2e_game_15k_lit_no_maps.png", lit=True)
operators._stop_server()
print("E2E PASSED")
