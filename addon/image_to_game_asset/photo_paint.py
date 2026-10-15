"""Paint the pictures the AI saw back onto its model ("Pixel Match", front + back pictures).

Pixal3D builds the model from cameras it knows exactly (a fixed orbit: field of view, distance,
front and back 180 degrees apart), so every point of the model can be traced back to the pixel
of each picture that shows it. Where a picture sees a point clearly, the point takes the
picture's real colour; elsewhere it keeps the AI's paint, shifted towards the pictures' colours.
The idea comes from AssetFurnace's "Pixel Match" (github.com/Bingeljell/image-to-3dlab, Apache-2.0);
this is our own implementation.

No Blender code here: Blender bakes where each texel sits and which way it faces, this module
works out the new colours (numpy only).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FACING = (0.2, 0.5)  # a surface takes a picture's colour fully when it faces it more than this
EDGE_PX = 8          # fade over this many pixels inside the cut-out's outline
DEPTH_EPS = 0.01     # how far behind the nearest surface still counts as seen (model is ~1 unit)
BACKGROUND = 0.02    # the cut-outs have a black background: darker than this is not the object


@dataclass
class Camera:
    position: np.ndarray
    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray
    focal: float   # in picture widths


def orbit_camera(azimuth_deg: float, fov_deg: float, pad: float) -> Camera:
    """Pixal3D's multi-view rig in Blender's imported (Z-up) space: the object fills 1/pad of the
    frame, the camera looks at the middle, azimuth 0 = front (camera on -Y)."""
    a, fov = math.radians(azimuth_deg), math.radians(fov_deg)
    distance = pad * 0.5 / math.tan(fov / 2)
    position = np.array([math.sin(a), -math.cos(a), 0.0]) * distance
    return Camera(position=position, right=np.array([math.cos(a), math.sin(a), 0.0]),
                  up=np.array([0.0, 0.0, 1.0]), forward=-position / distance,
                  focal=0.5 / math.tan(fov / 2))


def project(points: np.ndarray, cam: Camera, size: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points (n x 3) -> picture column, row (pixels, from the top left) and depth."""
    v = points - cam.position
    depth = v @ cam.forward
    safe = np.where(depth > 1e-6, depth, 1e-6)
    col = (0.5 + cam.focal * (v @ cam.right) / safe) * size
    row = (0.5 - cam.focal * (v @ cam.up) / safe) * size
    return col, row, depth


def _shift(a: np.ndarray, dy: int, dx: int, fill) -> np.ndarray:
    out = np.full_like(a, fill)
    h, w = a.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = \
        a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def _inner(mask: np.ndarray, steps: int) -> np.ndarray:
    """0 outside the mask, rising to 1 at `steps` pixels inside its outline."""
    out = np.zeros(mask.shape, np.float32)
    m = mask.copy()
    for _ in range(steps):
        out += m
        m = m & _shift(m, 1, 0, False) & _shift(m, -1, 0, False) & _shift(m, 0, 1, False) & _shift(m, 0, -1, False)
    return out / steps


def view_weights(points: np.ndarray, normals: np.ndarray, cam: Camera, picture: np.ndarray,
                 mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """How much each point trusts this picture (0-1), and the picture's colour there."""
    size = picture.shape[0]
    col, row, depth = project(points, cam, size)
    to_cam = cam.position - points
    to_cam /= np.maximum(np.linalg.norm(to_cam, axis=1, keepdims=True), 1e-9)
    facing = np.clip(((normals * to_cam).sum(1) - FACING[0]) / (FACING[1] - FACING[0]), 0, 1)
    inside = (col >= 0) & (col < size) & (row >= 0) & (row < size) & (depth > 0)
    ic = np.clip(col.astype(np.int64), 0, size - 1)
    ir = np.clip(row.astype(np.int64), 0, size - 1)
    # Visibility: the nearest surface at each pixel, from the texels themselves (splatted as
    # points, then a 5 x 5 minimum fills the small gaps between them).
    nearest = np.full((size, size), np.inf, np.float32)
    seen = inside & (facing > 0)
    np.minimum.at(nearest, (ir[seen], ic[seen]), depth[seen].astype(np.float32))
    filled = nearest.copy()
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            filled = np.minimum(filled, _shift(nearest, dy, dx, np.inf))
    visible = depth <= filled[ir, ic] + DEPTH_EPS
    weight = facing * visible * inside * _inner(mask, EDGE_PX)[ir, ic]
    return weight.astype(np.float32), picture[ir, ic]


def paint(points: np.ndarray, normals: np.ndarray, colours: np.ndarray,
          views: list[tuple[Camera, np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """New colours for points (n x 3, in the cameras' space) with normals and current colours
    (0-1). views: (camera, picture rows x cols x 3 in 0-1, object mask). Returns the new colours,
    each point's trust in the pictures (0-1) and the colour shift given to the AI's paint."""
    normals = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    total = np.zeros(len(points), np.float32)
    mixed = np.zeros((len(points), 3), np.float32)
    for cam, picture, mask in views:
        w, c = view_weights(points, normals, cam, picture, mask)
        total += w
        mixed += w[:, None] * c
    photo = mixed / np.maximum(total, 1e-6)[:, None]
    trust = np.clip(total, 0, 1)
    sure = trust > 0.8
    shift = (photo[sure] - colours[sure]).mean(0) if sure.any() else np.zeros(3, np.float32)
    rest = np.clip(colours + shift, 0, 1)
    return trust[:, None] * photo + (1 - trust[:, None]) * rest, trust, shift


# ---------------------------------------------------------------- the views file
# Written by trellis_runner.TrellisJob next to the model: <name>_views.json + one cut-out per view.
def read_views(path: str | Path) -> list[tuple[Camera, Path]]:
    """The cameras in a views file and the cut-out each saw (next to the file)."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [(orbit_camera(v["azimuth"], doc["fov"], doc["pad"]), path.parent / v["picture"])
            for v in doc["views"]]


def object_mask(picture: np.ndarray) -> np.ndarray:
    """The cut-outs show the object on pure black."""
    return picture.max(axis=2) > BACKGROUND
