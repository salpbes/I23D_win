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
