"""Run TRELLIS.2 through a local ComfyUI and turn its messages into progress.

ComfyUI runs on this PC only (127.0.0.1, started with --offline). The add-on starts it when it
isn't running, uploads the picture, sends the TRELLIS.2 workflow from workflows/, follows its
progress over a WebSocket and downloads the finished .glb.

No Blender code here, so it can be tested on its own.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
WORKFLOW = Path(__file__).with_name("workflows") / "trellis2_image_to_glb.json"
DEFAULT_URL = "http://127.0.0.1:8188"
DETAILS = ("1024", "1536")
QUIET_WARNING_SECONDS = {"1024": 10 * 60, "1536": 20 * 60}
SERVER_START_TIMEOUT = 240  # first start unpacks caches; later starts take ~20 s


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def sanitize_name(text: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return name or "model"


def check_image(image: str | os.PathLike) -> str | None:
    path = Path(image).expanduser()
    if not path.is_file():
        return f"Picture not found: {path}"
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return "Use a .png, .jpg or .webp picture."
    return None


def load_workflow(path: str | os.PathLike = WORKFLOW) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the ComfyUI folder
def comfy_python(comfy_dir: str | os.PathLike) -> Path:
    """The portable build's own Python (python_embeded is ComfyUI's spelling)."""
    return Path(comfy_dir).expanduser() / "python_embeded" / "python.exe"


def comfy_main(comfy_dir: str | os.PathLike) -> Path:
    return Path(comfy_dir).expanduser() / "ComfyUI" / "main.py"


def check_setup(comfy_dir: str | os.PathLike, url: str = DEFAULT_URL,
                workflow: dict | None = None) -> list[str]:
    """Return a list of plain-English problems (empty list = all good)."""
    workflow = workflow or load_workflow()
    if server_up(url):
        missing = [m for m in workflow["models"]
                   if m["file"] not in _get_json(url, f"/models/{m['folder']}", default=[])]
        return [f"ComfyUI is missing the model file {m['folder']}/{m['file']}" for m in missing]
    root = Path(comfy_dir).expanduser()
    if not root.is_dir():
        return [f"ComfyUI folder not found: {root}"]
    problems = []
    if not comfy_python(root).is_file() or not comfy_main(root).is_file():
        problems.append("This is not a ComfyUI portable folder (python_embeded or ComfyUI\\main.py "
                        "missing) - run the install script first.")
    models = root / "ComfyUI" / "models"
    for m in workflow["models"]:
        if not (models / m["folder"] / m["file"]).is_file():
            problems.append(f"Model file missing: ComfyUI\\models\\{m['folder']}\\{m['file']}")
    return problems


# ---------------------------------------------------------------- HTTP helpers
def _split_url(url: str) -> tuple[str, int]:
    parts = urllib.parse.urlsplit(url)
    return parts.hostname or "127.0.0.1", parts.port or 80


def _get_json(url: str, path: str, timeout: float = 10, default=None):
    try:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return json.load(r)
    except (OSError, ValueError):
        if default is not None:
            return default
        raise


def _post_json(url: str, path: str, data: dict, timeout: float = 30):
    req = urllib.request.Request(url + path, data=json.dumps(data).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}


def server_up(url: str = DEFAULT_URL, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(url + "/system_stats", timeout=timeout) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def upload_image(url: str, image: str | os.PathLike) -> str:
    """Copy the picture into ComfyUI's input folder; returns the name ComfyUI gave it."""
    path = Path(image).expanduser()
    boundary = uuid.uuid4().hex
    name = f"i23d_{sanitize_name(path.stem)}{path.suffix.lower()}"
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    tail = (f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
            f"\r\n--{boundary}--\r\n").encode()
    req = urllib.request.Request(url + "/upload/image", data=head + path.read_bytes() + tail,
                                 method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        info = json.load(r)
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def build_prompt(workflow: dict, image_name: str, *, seed: int, detail: str, prefix: str) -> dict:
    """The workflow with this run's picture, seed, detail and output name filled in."""
    if detail not in DETAILS:
        raise ValueError(f"Detail must be one of {DETAILS}")
    prompt = copy.deepcopy(workflow["prompt"])
    for node in prompt.values():
        kind, inputs = node["class_type"], node["inputs"]
        if kind == "LoadImage":
            inputs["image"] = image_name
        elif kind == "KSampler":
            inputs["seed"] = int(seed)
        elif kind == "Trellis2UpsampleStage":
            inputs["target_resolution"] = int(detail)
        elif kind == "Save3DAdvanced":
            inputs["filename_prefix"] = prefix
    return prompt


def describe_prompt_error(err: dict) -> str:
    """Turn ComfyUI's 'prompt rejected' answer into one readable line."""
    for node_id, info in (err.get("node_errors") or {}).items():
        for e in info.get("errors", []):
            return f"{info.get('class_type', 'node ' + node_id)}: {e.get('details') or e.get('message')}"
    e = err.get("error") or {}
    return e.get("details") or e.get("message") or "ComfyUI rejected the workflow."


# ---------------------------------------------------------------- starting ComfyUI
class ComfyServer:
    """A ComfyUI that the add-on started itself (and so may stop)."""

    def __init__(self, comfy_dir: str | os.PathLike, url: str = DEFAULT_URL, log_path=None):
        self.comfy_dir = Path(comfy_dir).expanduser()
        self.url = url
        self.log_path = Path(log_path) if log_path else None
        self._proc: subprocess.Popen | None = None
        self._log = None

    def command(self) -> list[str]:
        host, port = _split_url(self.url)
        return [str(comfy_python(self.comfy_dir)), "-s", str(comfy_main(self.comfy_dir)),
                "--windows-standalone-build", "--disable-auto-launch", "--offline",
                "--listen", host, "--port", str(port)]

    def start(self) -> None:
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        for key in ("PYTHONHOME", "PYTHONPATH"):  # don't leak Blender's Python settings
            env.pop(key, None)
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "ab")
        self._proc = subprocess.Popen(
            self.command(), cwd=str(self.comfy_dir), env=env, stdin=subprocess.DEVNULL,
            stdout=self._log or subprocess.DEVNULL, stderr=subprocess.STDOUT, creationflags=flags)

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def returncode(self):
        return None if self._proc is None else self._proc.poll()

    def stop(self) -> None:
        if self.is_alive():
            if sys.platform == "win32":  # /T also ends the processes ComfyUI started
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self._proc.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._log:
            self._log.close()
            self._log = None


# ---------------------------------------------------------------- a small WebSocket reader
class WebSocket:
    """Just enough of RFC 6455 to read ComfyUI's progress messages (no extra packages)."""

    def __init__(self, url: str, path: str, timeout: float = 10):
        host, port = _split_url(url)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("ComfyUI closed the progress connection")
            head += chunk
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(f"ComfyUI refused the progress connection: {status.decode(errors='replace')}")
        self._buf = head.split(b"\r\n\r\n", 1)[1]

    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("ComfyUI closed the progress connection")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def _send(self, opcode: int, payload: bytes = b"") -> None:
        mask = os.urandom(4)  # client frames must be masked
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)]) + mask + masked)

    def recv(self, timeout: float) -> str | None:
        """Next text message, or None if nothing arrived in time. Binary frames are skipped."""
        self.sock.settimeout(timeout)
        try:
            while True:
                if not self._buf:
                    self._buf = self.sock.recv(65536)
                    if not self._buf:
                        raise ConnectionError("ComfyUI closed the progress connection")
                self.sock.settimeout(30)  # a frame has started: read all of it
                b0, b1 = self._read(2)
                opcode, length = b0 & 0x0F, b1 & 0x7F
                if length == 126:
                    length = struct.unpack(">H", self._read(2))[0]
                elif length == 127:
                    length = struct.unpack(">Q", self._read(8))[0]
                mask = self._read(4) if b1 & 0x80 else None
                payload = self._read(length)
                if mask:
                    payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
                if opcode == 0x1:
                    return payload.decode("utf-8", errors="replace")
                if opcode == 0x8:
                    raise ConnectionError("ComfyUI closed the progress connection")
                if opcode == 0x9:
                    self._send(0xA, payload[:125])
                # 0x2 (preview images) and 0xA (pong) are ignored
        except socket.timeout:
            return None

    def close(self) -> None:
        try:
            self._send(0x8)
        except OSError:
            pass
        self.sock.close()


# ---------------------------------------------------------------- progress
class ProgressTracker:
    """Turn ComfyUI's per-node messages into one 0-1 fraction and a friendly label."""

    def __init__(self, prompt: dict):
        self.weights = {nid: float(n["_meta"].get("i23d_weight", 1)) for nid, n in prompt.items()}
        self.labels = {nid: n["_meta"].get("i23d_label", "Working") for nid, n in prompt.items()}
        self.total = sum(self.weights.values()) or 1.0
        self.done: set[str] = set()
        self.current: str | None = None
        self.partial = 0.0
        self.fraction = 0.0
        self.label = "Waiting for ComfyUI..."

    def _update(self, pct: float | None = None) -> None:
        done = sum(self.weights.get(n, 0) for n in self.done)
        now = self.weights.get(self.current, 0) * self.partial if self.current else 0
        self.fraction = max(self.fraction, min(0.99, (done + now) / self.total))
        if self.current:
            label = self.labels.get(self.current, "Working")
            self.label = f"{label} ({int(pct * 100)}%)" if pct is not None else label

    def feed(self, kind: str, data: dict) -> None:
        if kind == "execution_start":
            self.label = "Starting..."
        elif kind == "execution_cached":
            self.done.update(data.get("nodes") or [])
            self._update()
        elif kind == "executing":
            if self.current:
                self.done.add(self.current)
            self.current, self.partial = data.get("node"), 0.0
            self._update()
        elif kind == "progress" and data.get("node") == self.current and data.get("max"):
            self.partial = min(1.0, data["value"] / data["max"])
            self._update(self.partial)
        elif kind == "executed" and data.get("node"):
            self.done.add(data["node"])
            self._update()
        elif kind == "execution_success":
            self.fraction, self.label = 1.0, "Model saved"


# ---------------------------------------------------------------- one run
class TrellisJob:
    """One TRELLIS.2 run. Everything happens on a thread so Blender never freezes.

    Read .fraction, .label, .glb_path, .error and .cancelled; is_running() tells when it ends.
    """

    def __init__(self, *, url: str, image, out_base, seed: int = 42, detail: str = "1024",
                 log_path=None, server: ComfyServer | None = None, workflow: dict | None = None):
        self.url = url.rstrip("/")
        self.image = Path(image).expanduser()
        self.out_base = Path(out_base)
        self.seed, self.detail = int(seed), str(detail)
        self.log_path = Path(log_path) if log_path else None
        self.server = server  # started first when ComfyUI isn't running
        self.workflow = workflow or load_workflow()
        self.fraction, self.label = 0.0, "Starting..."
        self.glb_path: str | None = None
        self.error: str | None = None
        self.cancelled = False
        self.prompt_id: str | None = None
        self.started_at: float | None = None
        self.last_output_at: float | None = None
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._log = None

    # -- public
    def start(self) -> None:
        self.started_at = self.last_output_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def elapsed(self) -> float:
        return 0.0 if self.started_at is None else time.monotonic() - self.started_at

    def quiet_for(self) -> float:
        """Seconds since ComfyUI last reported anything."""
        return 0.0 if self.last_output_at is None else time.monotonic() - self.last_output_at

    def cancel(self) -> None:
        self.cancelled = True
        self._cancel.set()

    # -- the thread
    def _say(self, text: str) -> None:
        if self._log:
            self._log.write(f"[{fmt_duration(self.elapsed())}] {text}\n")
            self._log.flush()

    def _run(self) -> None:
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log = open(self.log_path, "w", encoding="utf-8")
        ws = None
        try:
            self._ensure_server()
            if self._cancel.is_set():
                return
            client_id = uuid.uuid4().hex
            ws = WebSocket(self.url, f"/ws?clientId={client_id}")  # before queueing: miss nothing
            self.label = "Sending the picture to ComfyUI"
            image_name = upload_image(self.url, self.image)
            prompt = build_prompt(self.workflow, image_name, seed=self.seed, detail=self.detail,
                                  prefix=f"i23d/{self.out_base.name}")
            self._say(f"picture {self.image} -> {image_name}, seed {self.seed}, detail {self.detail}")
            self.prompt_id = self._queue(prompt, client_id)
            self._follow(ws, ProgressTracker(prompt))
        except Exception as exc:  # shown in the panel
            if not self.cancelled:
                self.error = str(exc) or exc.__class__.__name__
                self._say(f"ERROR {self.error}")
        finally:
            if ws:
                ws.close()
            if self._log:
                self._log.close()
                self._log = None

    def _ensure_server(self) -> None:
        if server_up(self.url):
            return
        if self.server is None:
            raise RuntimeError(f"ComfyUI is not running at {self.url}.")
        self.label = "Starting ComfyUI (first start can take a minute)"
        self._say("starting ComfyUI: " + " ".join(self.server.command()))
        if not self.server.is_alive():
            self.server.start()
        deadline = time.monotonic() + SERVER_START_TIMEOUT
        while not server_up(self.url):
            if self._cancel.is_set():
                return
            if not self.server.is_alive():
                raise RuntimeError(f"ComfyUI stopped while starting (code {self.server.returncode}). "
                                   "See comfyui_log.txt in the output folder.")
            if time.monotonic() > deadline:
                raise RuntimeError("ComfyUI did not start in time. See comfyui_log.txt.")
            time.sleep(1)
        self.last_output_at = time.monotonic()
        self._say("ComfyUI is up")

    def _queue(self, prompt: dict, client_id: str) -> str:
        try:
            answer = _post_json(self.url, "/prompt", {"prompt": prompt, "client_id": client_id})
        except urllib.error.HTTPError as exc:
            try:
                detail = describe_prompt_error(json.loads(exc.read()))
            except ValueError:
                detail = f"HTTP {exc.code}"
            raise RuntimeError(f"ComfyUI rejected the job - {detail}") from None
        self._say(f"queued {answer['prompt_id']}")
        return answer["prompt_id"]

    def _follow(self, ws: WebSocket, tracker: ProgressTracker) -> None:
        last_history_check = time.monotonic()
        while True:
            if self._cancel.is_set():
                self._stop_remote()
                return
            text = ws.recv(timeout=1.0)
            if text is None:
                # Belt and braces: if a message was missed, the history still knows.
                if time.monotonic() - last_history_check > 15:
                    last_history_check = time.monotonic()
                    if self._finished_from_history():
                        return
                continue
            msg = json.loads(text)
            kind, data = msg.get("type"), msg.get("data") or {}
            if data.get("prompt_id") not in (None, self.prompt_id):
                continue
            if kind in ("progress_state", "status", "feature_flags"):
                continue
            self.last_output_at = time.monotonic()
            if kind != "progress":
                self._say(f"{kind} {json.dumps(data)[:300]}")
            if kind == "execution_error":
                self.error = (f"{data.get('node_type', 'ComfyUI')}: "
                              f"{(data.get('exception_message') or '').strip() or 'failed'}")
                return
            if kind == "execution_interrupted":
                self.error = self.error or "ComfyUI stopped the job."
                return
            tracker.feed(kind, data)
            self.fraction, self.label = tracker.fraction, tracker.label
            if kind == "execution_success":
                self._download()
                return

    def _finished_from_history(self) -> bool:
        history = _get_json(self.url, f"/history/{self.prompt_id}", default={})
        entry = history.get(self.prompt_id)
        if not entry or not entry.get("status", {}).get("completed") and \
                entry.get("status", {}).get("status_str") != "error":
            return False
        if entry["status"].get("status_str") == "error":
            msgs = [m[1] for m in entry["status"].get("messages", []) if m[0] == "execution_error"]
            self.error = msgs[0].get("exception_message", "ComfyUI failed") if msgs else "ComfyUI failed"
            return True
        self._download(entry)
        return True

    def _download(self, entry: dict | None = None) -> None:
        self.label = "Copying the model"
        if entry is None:
            entry = _get_json(self.url, f"/history/{self.prompt_id}", timeout=30)[self.prompt_id]
        files = [f for out in entry.get("outputs", {}).values() for f in out.get("3d", [])]
        if not files:
            raise RuntimeError("ComfyUI finished but saved no 3D file.")
        f = files[0]
        query = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                                        "type": f.get("type", "output")})
        target = self.out_base.with_suffix(".glb")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        with urllib.request.urlopen(f"{self.url}/view?{query}", timeout=120) as r, open(tmp, "wb") as out:
            while chunk := r.read(1 << 20):
                out.write(chunk)
        tmp.replace(target)
        self.glb_path = str(target)
        self.fraction, self.label = 1.0, "Model saved"
        self._say(f"saved {target} ({target.stat().st_size / 1e6:.1f} MB)")

    def _stop_remote(self) -> None:
        """Cancel: stop our job in ComfyUI (if it's running) and drop it from the queue."""
        self._say("cancelling")
        try:
            queue = _get_json(self.url, "/queue", default={})
            running = [item[1] for item in queue.get("queue_running", [])]
            if self.prompt_id in running:
                _post_json(self.url, "/interrupt", {"prompt_id": self.prompt_id})
            _post_json(self.url, "/queue", {"delete": [self.prompt_id]})
        except OSError as exc:
            self._say(f"cancel: {exc}")
