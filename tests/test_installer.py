"""Installer progress tests: how Blender reads install_progress.json (no Blender, no downloads).

    python tests/test_installer.py <work folder>
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "installer", HERE.parent / "addon" / "image_to_game_asset" / "installer.py")
inst = importlib.util.module_from_spec(spec)
sys.modules["installer"] = inst  # dataclasses look their module up there
spec.loader.exec_module(inst)

W = Path(sys.argv[1]) / "progress"
W.mkdir(parents=True, exist_ok=True)
pf = W / inst.PROGRESS_FILE
comfy, model = W / "ComfyUI.7z", W / "birefnet.safetensors.part"
GB = 1_000_000_000


def write(state, current, files, message="..."):
    pf.write_text(json.dumps({"state": state, "message": message, "current": current, "files": files}),
                  encoding="utf-8-sig")  # PowerShell 5.1 writes a byte-order mark
    return inst.read_progress(pf)


assert inst.read_progress(W / "missing.json") is None
pf.write_text("{half a fi", encoding="utf-8")
assert inst.read_progress(pf) is None, "a half-written file is skipped, not an error"

two = [{"name": "ComfyUI", "path": str(comfy), "size": 2 * GB},
       {"name": "birefnet.safetensors", "path": str(model), "size": 6 * GB}]
p = write("checking", -1, two, "Asking for the download sizes")
assert p.fraction == 0 and p.amount == "0.0 of 8.0 GB", p

comfy.write_bytes(b"x" * 1000)  # the archive has started to grow
p = write("downloading", 0, two)
assert 0 < p.fraction < 0.001 and p.done_bytes == 1000, p

p = write("unpacking", 0, two)  # the archive is unpacked (and then deleted): it counts as done
comfy.unlink()
assert p.fraction == 0.25 and p.amount == "2.0 of 8.0 GB", p
assert write("unpacking", 0, two).fraction == 0.25, "deleting the archive doesn't move the bar back"

model.write_bytes(b"x" * 3000)
p = write("downloading", 1, two, "Downloading birefnet.safetensors (2 of 2)")
assert p.done_bytes == 2 * GB + 3000 and p.message.endswith("(2 of 2)"), p

p = write("downloading", 0, two[1])  # a list of one, written by PowerShell as a single object
assert p.total_bytes == 6 * GB and p.done_bytes == 3000, p

p = write("done", 1, two, "Everything is installed")
assert p.fraction == 1 and p.state == "done", p
p = write("done", -1, [], "Everything is installed")  # nothing needed downloading
assert p.fraction == 1 and p.amount == "", p
p = write("checking", -1, [], "Checking this PC")
assert p.fraction is None, "no bar until something is downloaded"

# How a tracked install ended, once its window has closed.
inst._process = None
inst._progress_path = pf
write("downloading", 1, two)
end = inst.finish()
assert end.state == "stopped" and "carries on" in end.message and inst._progress_path is None, end
assert inst.finish() is None, "nothing tracked any more"
inst._progress_path = pf
write("failed", 1, two, "Download failed (curl code 56). Re-run to continue.")
assert inst.finish().message.startswith("Download failed")
inst._progress_path = W / "never_written.json"
assert inst.finish().state == "stopped", "closed before the script wrote anything"


class Window:  # stands in for the installer's PowerShell window: open until poll() says otherwise
    code = None
    def poll(self):
        return self.code


inst._process, inst._check_only = Window(), False
inst._progress_path = pf
write("downloading", 1, two)
assert inst.working() and inst.finish() is None, "still downloading"
write("done", 1, two, "Everything is installed")
assert not inst.working(), "Done: the open window only waits to be closed"
assert inst.finish().state == "done" and not inst.working() and inst.is_running()
inst._check_only = True
assert inst.working(), "a check of this PC counts as working while its window is open"
inst._process.code = 0
assert not inst.working() and not inst.is_running()
print("INSTALLER TESTS PASSED")
