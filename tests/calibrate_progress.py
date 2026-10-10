"""Run one real TRELLIS.2 job through the add-on's runner and time each progress step.

    python tests/calibrate_progress.py <picture> <out folder> [detail] [--url http://127.0.0.1:8188]

Prints seconds per step; copy them into STEPS in scripts/make_addon_workflow.py.
Needs a running ComfyUI with the TRELLIS.2 models.
"""
import importlib.util
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "tr", HERE.parent / "addon" / "image_to_game_asset" / "trellis_runner.py")
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

args = [a for a in sys.argv[1:] if not a.startswith("--url")]
url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")), tr.DEFAULT_URL)
picture, out = Path(args[0]), Path(args[1])
detail = args[2] if len(args) > 2 else "1024"

peak = [0]
stop = threading.Event()


def watch_vram():
    while not stop.is_set():
        used = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip()
        if used.isdigit():
            peak[0] = max(peak[0], int(used))
        time.sleep(1)


threading.Thread(target=watch_vram, daemon=True).start()
job = tr.TrellisJob(url=url, image=picture, out_base=out / f"calibrate_{detail}", seed=42, detail=detail,
                    log_path=out / f"calibrate_{detail}_log.txt")
job.start()
starts, current, last_label = {}, None, None
while job.is_running():
    if job.label != last_label:
        print(f"{job.elapsed():6.1f}s {job.fraction:5.2f}  {job.label}", flush=True)
        last_label = job.label
    time.sleep(0.2)
stop.set()
print("error:", job.error, "| glb:", job.glb_path, f"| {job.elapsed():.0f} s | peak VRAM {peak[0]} MiB")

# per-node durations from the log's "executing" lines
steps = {nid: n["_meta"]["i23d_step"] for nid, n in tr.load_workflow()["prompt"].items()}
times, events = {}, []
for line in (out / f"calibrate_{detail}_log.txt").read_text().splitlines():
    m = re.match(r"\[(\d+):(\d+)(?::(\d+))?\] executing (.*)", line)
    if m:
        parts = [int(x) for x in m.groups()[:3] if x is not None]
        secs = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
        events.append((secs, json.loads(m.group(4)).get("node")))
for (t0, node), (t1, _) in zip(events, events[1:]):
    times[steps.get(node, "other")] = times.get(steps.get(node, "other"), 0) + (t1 - t0)
print("seconds per step:", json.dumps(times))
