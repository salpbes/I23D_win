"""A stand-in ComfyUI for the tests: same HTTP + WebSocket messages, no AI, no graphics card.

    python fake_comfyui.py <port> <model.glb>

Seed 666 makes the job fail at the first KSampler; seed 777 makes every step slow (for Cancel).
A prompt without a LoadImage picture is rejected like ComfyUI does (HTTP 400).
A prompt without Save3DAdvanced is the add-on's picture check: it answers with two PNG previews
(a white square on black, standing in for the cut-out and its mask).
"""

import base64
import hashlib
import json
import struct
import sys
import threading
import time
import uuid
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PORT, GLB = int(sys.argv[1]), sys.argv[2]
MODELS = {"diffusion_models": ["trellis_2_int8_convrot.safetensors"],
          "vae": ["trellis_2_shape_vae_bf16.safetensors", "trellis_2_texture_vae_bf16.safetensors"],
          "clip_vision": ["dino_v3_L_naf_fp32.safetensors"], "background_removal": ["birefnet.safetensors"]}
sockets, history, uploads, interrupted = {}, {}, set(), set()
lock = threading.Lock()


def ws_send(client, kind, data):
    sock = sockets.get(client)
    if sock is None:
        return
    payload = json.dumps({"type": kind, "data": data}).encode()
    head = bytes([0x81]) + (bytes([len(payload)]) if len(payload) < 126 else
                            bytes([126]) + struct.pack(">H", len(payload)) if len(payload) < 65536 else
                            bytes([127]) + struct.pack(">Q", len(payload)))
    try:
        with lock:
            sock.sendall(head + payload)
            sock.sendall(bytes([0x82, 4]) + b"\x00\x00\x00\x01")  # a binary "preview" to skip
    except OSError:
        sockets.pop(client, None)


def square_png(size=64, lo=16, hi=48):
    """A grey PNG: black with a white square, like a mask of one object."""
    rows = b"".join(b"\0" + bytes(255 if lo <= x < hi and lo <= y < hi else 0 for x in range(size))
                    for y in range(size))
    chunk = lambda kind, data: (struct.pack(">I", len(data)) + kind + data +
                                struct.pack(">I", zlib.crc32(kind + data)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def run_previews(prompt_id, prompt, client):
    ws_send(client, "execution_start", {"prompt_id": prompt_id})
    outputs = {}
    for nid, node in prompt.items():
        ws_send(client, "executing", {"node": nid, "prompt_id": prompt_id})
        if node["class_type"] in ("PreviewImage", "MaskPreview"):
            outputs[nid] = {"images": [{"filename": f"preview_{nid}.png", "subfolder": "", "type": "temp"}]}
            ws_send(client, "executed", {"node": nid, "prompt_id": prompt_id, "output": outputs[nid]})
    history[prompt_id] = {"status": {"status_str": "success", "completed": True, "messages": []},
                          "outputs": outputs}
    ws_send(client, "executing", {"node": None, "prompt_id": prompt_id})
    ws_send(client, "execution_success", {"prompt_id": prompt_id})


def run(prompt_id, prompt, client):
    if not any(n["class_type"] == "Save3DAdvanced" for n in prompt.values()):
        return run_previews(prompt_id, prompt, client)
    seed = next((n["inputs"]["seed"] for n in prompt.values() if n["class_type"] == "KSampler"), 0)
    delay = 0.4 if seed == 777 else 0.01
    ws_send(client, "execution_start", {"prompt_id": prompt_id})
    loaders = [k for k, n in prompt.items() if n["class_type"].endswith("Loader")]
    ws_send(client, "execution_cached", {"nodes": loaders, "prompt_id": prompt_id})
    save = next(k for k, n in prompt.items() if n["class_type"] == "Save3DAdvanced")
    for nid, node in prompt.items():
        if nid in loaders or nid == save:
            continue
        if prompt_id in interrupted:
            ws_send(client, "execution_interrupted", {"prompt_id": prompt_id, "node_id": nid})
            history[prompt_id] = {"status": {"status_str": "error", "completed": False, "messages": []},
                                  "outputs": {}}
            return
        ws_send(client, "executing", {"node": nid, "prompt_id": prompt_id})
        if node["class_type"] == "KSampler":
            if seed == 666:
                err = {"prompt_id": prompt_id, "node_id": nid, "node_type": "KSampler",
                       "exception_message": "CUDA out of memory. Tried to allocate 2.00 GiB\n"}
                ws_send(client, "execution_error", err)
                history[prompt_id] = {"status": {"status_str": "error", "completed": False,
                                                 "messages": [["execution_error", err]]}, "outputs": {}}
                return
            for i in range(1, 5):
                time.sleep(delay)
                ws_send(client, "progress", {"value": i, "max": 4, "node": nid, "prompt_id": prompt_id})
        time.sleep(delay)
    prefix = prompt[save]["inputs"]["filename_prefix"]
    folder, name = prefix.rsplit("/", 1)
    out = {"filename": f"{name}_00001_.glb", "subfolder": folder, "type": "output"}
    ws_send(client, "executing", {"node": save, "prompt_id": prompt_id})
    ws_send(client, "executed", {"node": save, "prompt_id": prompt_id, "output": {"3d": [out]}})
    outputs = {save: {"3d": [out], "result": [f"{prefix}.glb"]}}
    for nid, node in prompt.items():  # previews (e.g. the cut-outs a front + back run saw)
        if node["class_type"] == "PreviewImage":
            outputs[nid] = {"images": [{"filename": f"preview_{nid}.png", "subfolder": "", "type": "temp"}]}
    history[prompt_id] = {"status": {"status_str": "success", "completed": True, "messages": []},
                          "outputs": outputs}
    ws_send(client, "executing", {"node": None, "prompt_id": prompt_id})
    ws_send(client, "execution_success", {"prompt_id": prompt_id})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/system_stats":
            return self._json({"system": {"comfyui_version": "fake"}})
        if url.path.startswith("/models/"):
            return self._json(MODELS.get(url.path.split("/")[-1], []))
        if url.path.startswith("/history/"):
            pid = url.path.split("/")[-1]
            return self._json({pid: history[pid]} if pid in history else {})
        if url.path == "/queue":
            return self._json({"queue_running": [[0, pid] for pid in running], "queue_pending": []})
        if url.path == "/view":
            png = parse_qs(url.query).get("filename", [""])[0].endswith(".png")
            data = square_png() if png else open(GLB, "rb").read()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        if url.path == "/ws":
            client = parse_qs(url.query).get("clientId", [uuid.uuid4().hex])[0]
            accept = base64.b64encode(hashlib.sha1(
                (self.headers["Sec-WebSocket-Key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept.decode())
            self.end_headers()
            self.wfile.flush()
            sockets[client] = self.connection
            ws_send(client, "status", {"status": {}, "sid": client})
            try:
                while self.connection.recv(1024):
                    pass  # client frames (close/pong) are ignored
            except OSError:
                pass
            sockets.pop(client, None)
            self.close_connection = True
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        url = urlsplit(self.path)
        body = self._body()
        if url.path == "/upload/image":
            name = body.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
            uploads.add(name)
            return self._json({"name": name, "subfolder": "", "type": "input"})
        if url.path == "/prompt":
            data = json.loads(body)
            prompt = data["prompt"]
            load = next(k for k, n in prompt.items() if n["class_type"] == "LoadImage")
            if prompt[load]["inputs"].get("image") not in uploads:
                return self._json({"error": {"type": "prompt_outputs_failed_validation",
                                             "message": "Prompt outputs failed validation"},
                                   "node_errors": {load: {"class_type": "LoadImage", "errors": [
                                       {"message": "Invalid image file",
                                        "details": f"image - Invalid image file: {prompt[load]['inputs'].get('image')}"}]}}},
                                  400)
            pid = uuid.uuid4().hex
            running.add(pid)

            def go():
                try:
                    run(pid, prompt, data.get("client_id"))
                finally:
                    running.discard(pid)
            threading.Thread(target=go, daemon=True).start()
            return self._json({"prompt_id": pid, "number": 1, "node_errors": {}})
        if url.path == "/interrupt":
            interrupted.update(running)
            return self._json({})
        if url.path == "/queue":
            return self._json({})
        self._json({"error": "not found"}, 404)


running = set()
ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
