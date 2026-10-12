"""Start the bundled ComfyUI + TRELLIS.2 installer (install/install_comfyui.ps1) in its own window.

The download is about 11 GB, so it runs in a visible PowerShell window where the user can watch
it, and Blender never waits for it. No Blender code here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent / "install" / "install_comfyui.ps1"
HOME = Path.home() / "I23D"            # the installer's default folder
COMFY_FOLDER = "ComfyUI_windows_portable"  # what the installer makes inside it
DOWNLOAD_GB = 11                       # ComfyUI about 2 GB + TRELLIS.2 model files about 9 GB

last_problems: list[str] = []          # what the last Check Setup found (empty = fine or not checked)
_process: subprocess.Popen | None = None


def install_dir_for(comfy_dir: str) -> Path:
    """The folder the installer fills: the one that holds (or will hold) ComfyUI_windows_portable."""
    path = Path(comfy_dir).expanduser() if comfy_dir else HOME / COMFY_FOLDER
    return path.parent if path.name.lower() == COMFY_FOLDER.lower() else HOME


def command(install_dir: Path, check_only: bool = False) -> list[str]:
    cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-InstallDir", str(install_dir), "-Pause"]
    return cmd + ["-Check"] if check_only else cmd


def is_running() -> bool:
    return _process is not None and _process.poll() is None


def start(install_dir: Path, check_only: bool = False) -> None:
    """Open a new PowerShell window running the installer; returns at once."""
    global _process
    if not SCRIPT.is_file():
        raise FileNotFoundError(f"The installer is missing from the add-on: {SCRIPT}. Re-install the add-on zip.")
    _process = subprocess.Popen(command(install_dir, check_only),
                                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
