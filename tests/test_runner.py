"""Runner tests against a fake ComfyUI (no Blender, no graphics card).

    python tests/test_runner.py <work folder with picture.png and messy.glb>
"""
import importlib.util
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "tr", HERE.parent / "addon" / "image_to_game_asset" / "trellis_runner.py")
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

W = Path(sys.argv[1])
picture, glb = W / "picture.png", W / "messy.glb"
out = W / "out"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_fake(port):
    proc = subprocess.Popen([sys.executable, str(HERE / "fixtures" / "fake_comfyui.py"), str(port), str(glb)])
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if tr.server_up(url):
            return proc, url
        time.sleep(0.1)
    raise SystemExit("fake ComfyUI did not start")


def run(url, seed=42, detail="1024", name="test", cancel_after=None):
    job = tr.TrellisJob(url=url, image=picture, out_base=out / name, seed=seed, detail=detail,
                        log_path=out / f"{name}_log.txt")
    job.start()
    fracs, labels = [], []
    t0 = time.time()
    while job.is_running():
        fracs.append(job.fraction)
        labels.append(job.label)
        if cancel_after and time.time() - t0 > cancel_after and not job.cancelled:
            job.cancel()
        time.sleep(0.01)
        assert time.time() - t0 < 60, "job did not finish"
    return job, fracs, labels


# ---- plain helpers
assert tr.check_image(picture) is None
assert "png" in tr.check_image(glb)
assert tr.sanitize_name("my axe (v2).png") == "my_axe_v2_png"
assert tr.fmt_duration(3725) == "1:02:05" and tr.fmt_duration(65) == "1:05"
wf = tr.load_workflow()


# ---- front + back prompts (Pixal3D multi-view on the same stages)
def links_ok(prompt):
    for node in prompt.values():
        for v in node["inputs"].values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in prompt, f"{node['class_type']} points at missing node {v[0]}"


def kinds(prompt):
    return [n["class_type"] for n in prompt.values()]


one = tr.build_prompt(wf, "f.png", seed=1, detail="1024", prefix="p")
assert "Trellis2Conditioning" in kinds(one) and "Pixal3DMultiViewConditioning" not in kinds(one)
sheet = tr.build_prompt(wf, "sheet.png", seed=1, detail="1024", prefix="p",
                        views=[{"name": "front", "box": (0, 0, 120, 100)}, {"name": "back", "box": (120, 0, 80, 100)}])
links_ok(sheet)
assert "Trellis2Conditioning" not in kinds(sheet) and kinds(sheet).count("RemoveBackground") == 2
assert kinds(sheet).count("ImageCropToMask") == 2 and kinds(sheet).count("LoadImage") == 1
assert next(n for n in sheet.values() if n["class_type"] == "UNETLoader")["inputs"]["unet_name"] == \
    wf["front_back"]["unet"] == "pixal3d_multiview_int8_convrot.safetensors"
cond = next(n for n in sheet.values() if n["class_type"] == "Pixal3DMultiViewConditioning")["inputs"]
assert set(cond) == {"clip_vision_model", "fov", "front", "back"} and cond["fov"] == 20
crops = {k: n["inputs"] for k, n in sheet.items() if n["class_type"] == "ImageCrop"}
assert sorted((c["x"], c["width"], c["height"]) for c in crops.values()) == [(0, 120, 100), (120, 80, 100)]
load = next(k for k, n in sheet.items() if n["class_type"] == "LoadImage")
assert {k for k, n in sheet.items() if [load, 0] in n["inputs"].values()} == set(crops), \
    "front and back steps start from their own half"
two = tr.build_prompt(wf, "f.png", seed=1, detail="1024", prefix="p",
                      views=[{"name": "front"}, {"name": "back", "image": "b.png"}])
links_ok(two)
assert sorted(n["inputs"]["image"] for n in two.values() if n["class_type"] == "LoadImage") == ["b.png", "f.png"]
assert "ImageCrop" not in kinds(two)
cut, nodes = tr.build_cutout_prompt(wf, "f.png", views=[{"name": "front"}, {"name": "back", "image": "b.png"}])
links_ok(cut)
assert [n for n, _, _ in nodes] == ["front", "back"] and kinds(cut).count("MaskPreview") == 2
assert "UNETLoader" not in kinds(cut)
# a side view and framing: a long object is framed loosely so its length fits Pixal3D's box;
# past ImageCropToMask's limit (2.0) the cut-out is set smaller on a black canvas
three = tr.build_prompt(wf, "f.png", seed=1, detail="1024", prefix="p", views=[
    {"name": "front", "pad": 2.5}, {"name": "back", "image": "b.png", "pad": 1.6},
    {"name": "left", "image": "s.png", "pad": 1.1}])
links_ok(three)
cond = next(n for n in three.values() if n["class_type"] == "Pixal3DMultiViewConditioning")["inputs"]
assert set(cond) == {"clip_vision_model", "fov", "front", "back", "left"}
frames = sorted((n["inputs"]["pad_factor"], n["inputs"]["width"]) for n in three.values()
                if n["class_type"] == "ImageCropToMask")
assert frames == [(1.1, 1024), (1.6, 1024), (2.0, 816)], frames
paste = next(k for k, n in three.items() if n["class_type"] == "ImageCompositeMasked")
assert three[paste]["inputs"]["x"] == three[paste]["inputs"]["y"] == (1024 - 816) // 2
assert cond["front"] == [paste, 0] or three[cond["front"][0]]["inputs"]["images"] == [paste, 0], \
    "Pixal3D gets the front on its canvas"
views_shown = {n["_meta"]["i23d_view"] for n in three.values() if n["_meta"].get("i23d_view")}
assert views_shown == {"front", "back", "left"}

# the extra model file is only asked for with front + back
fake_comfy = W / "fb_folder"
for rel in ["python_embeded/python.exe", "ComfyUI/main.py"] + \
        [f"ComfyUI/models/{m['folder']}/{m['file']}" for m in wf["models"]]:
    (fake_comfy / rel).parent.mkdir(parents=True, exist_ok=True)
    (fake_comfy / rel).touch()
assert tr.check_folder(fake_comfy, wf) == []
assert any("pixal3d_multiview" in p for p in tr.check_folder(fake_comfy, wf, front_back=True))
print("front + back prompts OK")
assert {m["folder"] for m in wf["models"]} == {"diffusion_models", "vae", "clip_vision", "background_removal"}
p = tr.build_prompt(wf, "pic.png", seed=7, detail="1536", prefix="i23d/axe")
kinds = {n["class_type"]: n["inputs"] for n in p.values()}
assert kinds["LoadImage"]["image"] == "pic.png" and kinds["Trellis2UpsampleStage"]["target_resolution"] == 1536
assert all(n["inputs"]["seed"] == 7 for n in p.values() if n["class_type"] == "KSampler")
assert kinds["Save3DAdvanced"]["filename_prefix"] == "i23d/axe"
assert wf["prompt"] != p, "build_prompt must not change the shipped workflow"
try:
    tr.build_prompt(wf, "x", seed=1, detail="512", prefix="x")
    raise AssertionError("512 should be refused")
except ValueError:
    pass
print("helpers OK")

# ---- setup check on a folder (ComfyUI not running at this address)
dead = f"http://127.0.0.1:{free_port()}"
assert not tr.server_up(dead)
assert tr.check_setup(W / "nope", dead)[0].startswith("ComfyUI folder not found")
fake_dir = W / "ComfyUI_windows_portable"
(fake_dir / "python_embeded").mkdir(parents=True, exist_ok=True)
(fake_dir / "python_embeded" / "python.exe").write_bytes(b"")
(fake_dir / "ComfyUI").mkdir(exist_ok=True)
(fake_dir / "ComfyUI" / "main.py").write_text("")
problems = tr.check_setup(fake_dir, dead)
assert len(problems) == 5 and all("Model file missing" in x for x in problems), problems
for m in wf["models"]:
    f = fake_dir / "ComfyUI" / "models" / m["folder"] / m["file"]
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"")
assert tr.check_setup(fake_dir, dead) == []
print("setup check OK")

proc, url = start_fake(free_port())
try:
    assert tr.check_setup(W / "nope", url) == [], "a running ComfyUI with the models is enough"

    # ---- a normal run
    job, fracs, labels = run(url)
    print("labels:", sorted(set(labels)))
    assert job.error is None, job.error
    assert job.glb_path and Path(job.glb_path).read_bytes() == glb.read_bytes()
    assert job.glb_path.endswith("test.glb")
    assert fracs == sorted(fracs), "progress went backwards"
    assert job.fraction == 1.0 and job.label == "Model saved"
    assert any("Step 1 of 4" in l and "%" in l for l in labels), labels
    assert any(l.startswith("Step 4 of 4") for l in labels)
    log = (out / "test_log.txt").read_text()
    assert "queued" in log and "saved" in log
    assert job.views_path is None, "one picture: no views to paint"
    print("normal run OK")

    # ---- the graphics card fails
    job, _, _ = run(url, seed=666, name="fail")
    print("error:", job.error)
    assert job.glb_path is None and job.error.startswith("KSampler: CUDA out of memory")

    # ---- ComfyUI rejects the job (picture not uploaded)
    orig_upload = tr.upload_image
    tr.upload_image = lambda url, image: "never_uploaded.png"
    try:
        job, _, _ = run(url, name="rejected")
    finally:
        tr.upload_image = orig_upload
    print("rejected:", job.error)
    assert "rejected" in job.error and "Invalid image file" in job.error

    # ---- cancel
    t = time.time()
    job, _, _ = run(url, seed=777, name="cancel", cancel_after=1.0)
    print(f"cancelled after {time.time() - t:.1f} s")
    assert job.cancelled and job.error is None and job.glb_path is None
    assert time.time() - t < 6
    assert "cancelling" in (out / "cancel_log.txt").read_text()

    # ---- picture check: only background removal + crop, and their two previews come back
    cut_prompt, cut_nodes = tr.build_cutout_prompt(tr.load_workflow(), "x.png")
    assert [n for n, _, _ in cut_nodes] == ["front"]
    assert {n["class_type"] for n in cut_prompt.values()} == {
        "LoadImage", "LoadBackgroundRemovalModel", "RemoveBackground", "MaskPreview", "ImageCropToMask",
        "PreviewImage"}, "the check must not run any TRELLIS.2 step"
    job = tr.CutoutJob(url=url, image=picture, out_base=out / "previews" / "picture",
                       log_path=out / "previews" / "check_log.txt")
    job.start()
    job.wait(20)
    assert not job.is_running() and job.error is None, job.error
    assert job.cutout_path.endswith("picture_cutout.png") and job.mask_path.endswith("picture_mask.png")
    assert Path(job.cutout_path).read_bytes()[:4] == b"\x89PNG" and Path(job.mask_path).is_file()
    assert job.fraction == 1.0 and job.label == "Cut-out ready"
    assert list(job.view_files) == ["front"]
    print("picture check OK")

    # ---- front + back pictures: views side by side in one picture, or pictures of their own
    job = tr.CutoutJob(url=url, image=picture, out_base=out / "previews" / "pair", views=[
        {"name": "front", "file": None, "box": (0, 0, 30, 64)}, {"name": "back", "file": None, "box": (30, 0, 34, 64)}])
    job.start()
    job.wait(20)
    assert job.error is None, job.error
    assert job.view_files["back"][0].endswith("pair_back_cutout.png") and Path(job.view_files["back"][1]).is_file()
    assert job.view_files["front"] == (job.cutout_path, job.mask_path)
    job = tr.TrellisJob(url=url, image=picture, out_base=out / "front_back", log_path=out / "front_back_log.txt",
                        views=[{"name": "front", "file": None, "pad": 2.4},
                               {"name": "back", "file": picture, "pad": 2.4},
                               {"name": "right", "file": picture, "pad": 1.1}])
    job.start()
    job.wait(60)
    assert job.error is None and Path(job.glb_path).is_file(), job.error
    log = (out / "front_back_log.txt").read_text()
    assert "back view" in log and "framing 2.40" in log, log
    # the cut-outs Pixal3D saw and its cameras are kept, for painting the pictures on
    import json
    views = json.loads(Path(job.views_path).read_text())
    assert views["fov"] == 20 and views["pad"] == 1.1, views
    assert sorted((v["name"], v["azimuth"]) for v in views["views"]) == \
        [("back", 180.0), ("front", 0.0), ("right", 270.0)], views
    assert all((out / v["picture"]).read_bytes()[:4] == b"\x89PNG" for v in views["views"])
    print("front + back jobs OK")

    # ---- quiet timer
    job = tr.TrellisJob(url=url, image=picture, out_base=out / "q")
    assert job.quiet_for() == 0 and job.elapsed() == 0
finally:
    proc.kill()

# ---- ComfyUI not running and not allowed to start it
job, _, _ = run(dead, name="dead")
assert "not running" in job.error, job.error

# ---- ComfyUI not running: the job starts it (here: the fake, via a stand-in "portable" folder)
port = free_port()
starter = W / "starter"
(starter / "python_embeded").mkdir(parents=True, exist_ok=True)
(starter / "ComfyUI").mkdir(exist_ok=True)
server = tr.ComfyServer(starter, f"http://127.0.0.1:{port}", log_path=out / "comfyui_log.txt")
server.command = lambda: [sys.executable, str(HERE / "fixtures" / "fake_comfyui.py"), str(port), str(glb)]
cmd = tr.ComfyServer(starter, f"http://127.0.0.1:{port}").command()
assert "--offline" in cmd and "--listen" in cmd and cmd[cmd.index("--listen") + 1] == "127.0.0.1"
job = tr.TrellisJob(url=f"http://127.0.0.1:{port}", image=picture, out_base=out / "started",
                    server=server)
job.start()
job.wait(60)
try:
    assert job.error is None and Path(job.glb_path).is_file(), job.error
    assert server.is_alive()
finally:
    server.stop()
assert not server.is_alive()
print("start/stop ComfyUI OK")
print("RUNNER TESTS PASSED")
