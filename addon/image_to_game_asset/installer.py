"""Start the bundled ComfyUI + TRELLIS.2 installer (install/install_comfyui.ps1) in its own window.

The download is about 11 GB, so it runs in a visible PowerShell window where the user can watch
it, and Blender never waits for it. The script also writes install_progress.json into the install
folder; read_progress() turns that into a fraction for a progress bar in Blender. No Blender code
here.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

SCRIPT = Path(__file__).parent / "install" / "install_comfyui.ps1"
HOME = Path.home() / "I23D"            # the installer's default folder
COMFY_FOLDER = "ComfyUI_windows_portable"  # what the installer makes inside it
DOWNLOAD_GB = 11                       # ComfyUI about 2 GB + TRELLIS.2 model files about 9 GB
PROGRESS_FILE = "install_progress.json"

last_problems: list[str] = []          # what the last Check Setup found (empty = fine or not checked)
check_passed = False                   # the last Check Setup found everything
note = ""                              # how the last install ended (shown until the next action)
note_ok = False                        # ... and whether that was good news
_process: subprocess.Popen | None = None
_check_only = False                    # the open window is only checking this PC
_progress_path: Path | None = None     # set while a real install (not a check) is tracked


@dataclass
class Progress:
    state: str             # starting, checking, downloading, unpacking, done, failed or stopped
    message: str           # what the installer is doing, in plain words
    fraction: float | None  # 0..1 of all downloads (None: nothing to download or not known yet)
    done_bytes: int = 0
    total_bytes: int = 0

    @property
    def amount(self) -> str:
        """'3.1 of 9.0 GB' (empty when nothing is downloaded)."""
        if not self.total_bytes:
            return ""
        return f"{self.done_bytes / 1e9:.1f} of {self.total_bytes / 1e9:.1f} GB"


def install_dir_for(comfy_dir: str) -> Path:
    """The folder the installer fills: the one that holds (or will hold) ComfyUI_windows_portable."""
    path = Path(comfy_dir).expanduser() if comfy_dir else HOME / COMFY_FOLDER
    return path.parent if path.name.lower() == COMFY_FOLDER.lower() else HOME


def command(install_dir: Path, check_only: bool = False) -> list[str]:
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-InstallDir", str(install_dir), "-Pause"]
    return cmd + ["-Check"] if check_only else cmd


def is_running() -> bool:
    """The installer's window is open (it may only be waiting to be closed)."""
    return _process is not None and _process.poll() is None


def working() -> bool:
    """The installer is still at work: its window is open and it hasn't said Done or failed."""
    if not is_running():
        return False
    p = progress()
    if p is None:  # nothing tracked: a check, or an install that has already ended
        return _check_only
    return p.state not in ("done", "failed")


def start(install_dir: Path, check_only: bool = False) -> None:
    """Open a new PowerShell window running the installer; returns at once."""
    global _process, _progress_path, _check_only, note
    if not SCRIPT.is_file():
        raise FileNotFoundError(f"The installer is missing from the add-on: {SCRIPT}. Re-install the add-on zip.")
    _progress_path, _check_only = None, check_only
    if not check_only:  # a check writes no progress; an install starts from a clean slate
        _progress_path = Path(install_dir) / PROGRESS_FILE
        _progress_path.unlink(missing_ok=True)
        note = ""
    _process = subprocess.Popen(command(install_dir, check_only),
                                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def read_progress(path: Path) -> Progress | None:
    """Turn the installer's install_progress.json into a Progress (None if it can't be read yet)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    files = data.get("files") or []
    if isinstance(files, dict):  # PowerShell writes a list of one as a single object
        files = [files]
    sizes = [int(f.get("size") or 0) for f in files]
    state, current = data.get("state", ""), int(data.get("current", -1))
    if state == "done":
        done = sum(sizes)
    elif state == "downloading" and 0 <= current < len(files):
        try:
            grown = Path(files[current].get("path", "")).stat().st_size
        except OSError:
            grown = 0
        done = sum(sizes[:current]) + min(grown, sizes[current] or grown)
    else:  # checking, unpacking, failed: everything up to the current file is downloaded
        done = sum(sizes[:current + 1])
    total = sum(sizes)
    fraction = done / total if total else (1.0 if state == "done" else None)
    return Progress(state, data.get("message", ""), fraction, done, total)


def progress() -> Progress | None:
    """What the tracked install is doing now (None if no install is tracked)."""
    if _progress_path is None:
        return None
    return read_progress(_progress_path) or Progress("starting", "Starting the installer", None)


def finish() -> Progress | None:
    """How the tracked install ended, once it has (then it stops being tracked); None while it works.
    It has ended when it says Done or failed (its window waits to be closed), or when its window
    was closed."""
    global _progress_path
    if _progress_path is None:
        return None
    result = progress()
    if is_running() and result.state not in ("done", "failed"):
        return None
    _progress_path = None
    if result.state not in ("done", "failed"):
        result = Progress("stopped", "The installer window was closed before it finished. Press "
                          "Install again: it carries on where it stopped.", result.fraction,
                          result.done_bytes, result.total_bytes)
    return result
