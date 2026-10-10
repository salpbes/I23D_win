import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "addon"))  # so Blender can find the add-on
T = os.environ.get("I23D_TEST_WORK", os.path.join(HERE, "_work"))  # scratch folder made by run_tests.sh
import sys, time
import importlib.util
spec = importlib.util.spec_from_file_location("tr", os.path.join(HERE, "..", "addon", "image_to_game_asset", "trellis_runner.py"))
tr = importlib.util.module_from_spec(spec); spec.loader.exec_module(tr)
root = sys.argv[1]
assert tr.check_setup(root) == [], tr.check_setup(root)
assert tr.check_setup("/nope")[0].startswith("TRELLIS folder not found")
assert tr.check_image(root + "/../picture.png") is None
assert "png" in tr.check_image(root + "/generate.py")
assert tr.sanitize_name("my crown (v2).png") == "my_crown_v2_png"
cmd = tr.build_command(root, root+"/../picture.png", root+"/../out/test", seed=7)
assert "--no-texture" in cmd and "7" in cmd
import os; os.makedirs(root+"/../out", exist_ok=True)
job = tr.TrellisJob(cmd, root, log_path=root+"/../out/test_log.txt"); job.start()
p = tr.ProgressParser(); fracs=[]; labels=set()
while job.is_running():
    for l in job.poll_lines(): p.feed(l); fracs.append(p.fraction); labels.add(p.label)
    time.sleep(0.05)
for l in job.poll_lines(): p.feed(l); fracs.append(p.fraction)
print("rc", job.returncode, "glb", p.glb_path, "mesh", p.mesh_info)
print("labels", sorted(labels))
assert job.returncode == 0 and p.glb_path.endswith("test.glb") and os.path.isfile(p.glb_path)
assert fracs == sorted(fracs) and fracs[-1] == 1.0, fracs
assert p.mesh_info == (1308352, 2703762)
assert os.path.getsize(root+"/../out/test_log.txt") > 100
# failure path
os.environ["FAKE_FAIL"]="1"
job = tr.TrellisJob(cmd, root); job.start()
while job.is_running(): time.sleep(0.05)
lines = job.poll_lines(); print("fail rc", job.returncode, lines[-1])
assert job.returncode == 1 and "boom" in lines[-1]
# cancel path
del os.environ["FAKE_FAIL"]
job = tr.TrellisJob(["python3","-c","import time; time.sleep(30)"], root); job.start(); time.sleep(0.3)
t=time.time(); job.cancel(); 
while job.is_running(): time.sleep(0.05)
print("cancelled in", round(time.time()-t,2), "s, rc", job.returncode); assert job.cancelled
print("RUNNER TESTS PASSED")
# v1.0.3: activity tracking + mesh-building label
p = tr.ProgressParser(); p.feed("Sampling texture SLat: 100%|###| 12/12"); assert p.label.startswith("Building the 3D mesh"), p.label
job = tr.TrellisJob(["python3","-u","-c","import time; print('hi'); time.sleep(1.2); print('bye')"], root); job.start(); time.sleep(0.5)
q1 = job.quiet_for(); time.sleep(0.4); q2 = job.quiet_for(); assert q2 > q1 > 0.2, (q1, q2)
while job.is_running(): time.sleep(0.05)
assert job.quiet_for() < 0.5 and job.elapsed() >= 1.2
assert tr.fmt_duration(3725) == "1:02:05" and tr.fmt_duration(65) == "1:05"
print("ACTIVITY TESTS PASSED")
