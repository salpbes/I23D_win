"""Start TRELLIS.2 as a background process and turn its output into progress.

No Blender code here, so it can be tested on its own.
"""

from __future__ import annotations

import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# (text that marks the stage, overall start, overall end, friendly label)
STAGES = (
    ("Loading pipeline", 0.00, 0.12, "Loading the AI model"),
    ("Sampling sparse structure", 0.12, 0.45, "Step 1 of 3: rough shape"),
    ("Sampling shape SLat", 0.45, 0.75, "Step 2 of 3: detailed shape"),
    ("Sampling texture SLat", 0.75, 0.92, "Step 3 of 3: surface"),
    ("Exporting", 0.92, 0.99, "Saving the model"),
)
_PERCENT = re.compile(r":\s*(\d{1,3})%")
_SAVED_GLB = re.compile(r"Saved:\s*(.+?\.glb)\s*$")
_MESH = re.compile(r"Mesh:\s*([\d,]+)\s+vertices,\s*([\d,]+)\s+triangles")
_DOWNLOAD = re.compile(r"downloading bytes|Downloading|\.safetensors", re.IGNORECASE)

EXIT_GPU_WATCHDOG = 2
QUIET_WARNING_SECONDS = {"512": 15 * 60, "1024": 30 * 60, "1024_cascade": 30 * 60}


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"  # generate.py uses this code when macOS stops the GPU work


def sanitize_name(text: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return name or "model"


def check_setup(trellis_dir: str | os.PathLike) -> list[str]:
    """Return a list of plain-English problems (empty list = all good)."""
    root = Path(trellis_dir).expanduser()
    problems = []
    if not root.is_dir():
        return [f"TRELLIS folder not found: {root}"]
    if not (root / "generate.py").is_file():
        problems.append("generate.py is missing - is this the trellis-mac folder?")
    if not (root / ".venv" / "bin" / "python").exists():
        problems.append("Python environment (.venv) is missing - run the install script first.")
    return problems


def check_image(image: str | os.PathLike) -> str | None:
    path = Path(image).expanduser()
    if not path.is_file():
        return f"Picture not found: {path}"
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return "Use a .png, .jpg or .webp picture."
    return None


def build_command(trellis_dir, image, out_base, seed=42, bake_textures=False, texture_size=1024,
                  pipeline_type="512"):
    python = Path(trellis_dir).expanduser() / ".venv" / "bin" / "python"
    cmd = [str(python), "-u", "generate.py", str(Path(image).expanduser()),
           "--output", str(out_base), "--seed", str(int(seed)),
           "--pipeline-type", str(pipeline_type)]
    if bake_textures:
        cmd += ["--texture-size", str(int(texture_size))]
    else:
        cmd.append("--no-texture")
    caffeinate = Path("/usr/bin/caffeinate")
    if sys.platform == "darwin" and caffeinate.exists():
        cmd = [str(caffeinate), "-i"] + cmd  # keep the Mac awake while it works
    return cmd


class ProgressParser:
    """Feed it output lines; read .fraction (0-1), .label, .glb_path, .mesh_info."""

    def __init__(self):
        self.fraction = 0.0
        self.label = "Starting..."
        self.glb_path: str | None = None
        self.mesh_info: tuple[int, int] | None = None

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        saved = _SAVED_GLB.search(line)
        if saved:
            self.glb_path = saved.group(1).strip()
            self.fraction, self.label = 1.0, "Model saved"
            return
        mesh = _MESH.search(line)
        if mesh:
            self.mesh_info = tuple(int(g.replace(",", "")) for g in mesh.groups())
            return
        for marker, start, end, label in STAGES:
            if marker in line:
                pct = _PERCENT.search(line)
                part = min(int(pct.group(1)), 100) / 100 if pct else 0.0
                self.fraction = max(self.fraction, start + (end - start) * part)
                self.label = f"{label} ({int(part * 100)}%)" if pct else label
                if marker == "Sampling texture SLat" and part >= 1.0:
                    self.label = "Building the 3D mesh (no progress bar here)"
                return
        if _DOWNLOAD.search(line) and self.fraction < STAGES[1][1]:
            self.label = "Downloading model files (first run only)"


class TrellisJob:
    """One TRELLIS.2 run. Output is read on a thread so Blender never freezes."""

    def __init__(self, cmd, cwd, log_path=None):
        self.cmd = list(cmd)
        self.cwd = str(Path(cwd).expanduser())
        self.log_path = Path(log_path) if log_path else None
        self.cancelled = False
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._reader: threading.Thread | None = None
        self.started_at: float | None = None
        self.last_output_at: float | None = None

    def start(self) -> None:
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        for key in ("PYTHONHOME", "PYTHONPATH"):  # don't leak Blender's Python settings
            env.pop(key, None)
        self._proc = subprocess.Popen(
            self.cmd, cwd=self.cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            bufsize=0, start_new_session=True,
        )
        self.started_at = self.last_output_at = time.monotonic()
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        log = open(self.log_path, "w", encoding="utf-8") if self.log_path else None
        buffer = ""
        try:
            while True:
                chunk = self._proc.stdout.read(4096)
                if not chunk:
                    break
                self.last_output_at = time.monotonic()
                text = chunk.decode("utf-8", errors="replace")
                if log:
                    log.write(text)
                    log.flush()
                buffer += text
                # progress bars rewrite the same line with \r, so split on both
                parts = re.split(r"[\r\n]", buffer)
                buffer = parts.pop()
                for part in parts:
                    if part.strip():
                        self._lines.put(part)
            if buffer.strip():
                self._lines.put(buffer)
        finally:
            if log:
                log.close()

    def elapsed(self) -> float:
        return 0.0 if self.started_at is None else time.monotonic() - self.started_at

    def quiet_for(self) -> float:
        """Seconds since TRELLIS.2 last printed anything."""
        return 0.0 if self.last_output_at is None else time.monotonic() - self.last_output_at

    def poll_lines(self) -> list[str]:
        lines = []
        while True:
            try:
                lines.append(self._lines.get_nowait())
            except queue.Empty:
                return lines

    def is_running(self) -> bool:
        if self._proc is None or self._proc.poll() is None:
            return self._proc is not None
        # process ended: wait for the reader to flush the last lines
        if self._reader and self._reader.is_alive():
            self._reader.join(timeout=2)
        return False

    @property
    def returncode(self):
        return None if self._proc is None else self._proc.poll()

    def cancel(self) -> None:
        self.cancelled = True
        if self._proc and self._proc.poll() is None:
            try:
                os.killpg(self._proc.pid, signal.SIGTERM)
                self._proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
                try:
                    os.killpg(self._proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
