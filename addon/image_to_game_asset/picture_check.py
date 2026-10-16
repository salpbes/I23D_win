"""Look at a picture and its cut-out, and say in plain words what may go wrong with the model.

The cut-out comes from the workflow's own background removal (trellis_runner.CutoutJob), so it
is exactly what TRELLIS.2 will see. No Blender code here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SMALL_PICTURE = 512   # pixels on the short side; TRELLIS.2 looks at the object at 1024 x 1024


@dataclass
class Note:
    good: bool
    text: str


def picture_notes(width: int, height: int) -> list[Note]:
    """What can be said from the picture's size alone."""
    if min(width, height) < SMALL_PICTURE:
        return [Note(False, f"The picture is small ({width} x {height} pixels). 1024 pixels or more "
                            "gives sharper colours.")]
    return []


def count_pieces(obj: np.ndarray, size: int = 96, keep: float = 0.1) -> int:
    """How many separate pieces the cut-out has (ignoring specks under `keep` x the largest)."""
    step = max(1, -(-max(obj.shape) // size))
    h, w = -(-obj.shape[0] // step), -(-obj.shape[1] // step)
    padded = np.zeros((h * step, w * step), bool)
    padded[:obj.shape[0], :obj.shape[1]] = obj
    small = padded.reshape(h, step, w, step).mean(axis=(1, 3)) > 0.25
    labels = np.zeros(small.shape, int)
    sizes = []
    for y, x in zip(*np.nonzero(small)):
        if labels[y, x]:
            continue
        sizes.append(0)
        labels[y, x] = len(sizes)
        todo = [(y, x)]
        while todo:
            cy, cx = todo.pop()
            sizes[-1] += 1
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and small[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = len(sizes)
                    todo.append((ny, nx))
    return sum(s >= keep * max(sizes) for s in sizes) if sizes else 0


def mask_notes(mask: np.ndarray) -> list[Note]:
    """What the background removal's mask says (white = the object, over the whole picture)."""
    m = np.asarray(mask, dtype=float)
    if m.ndim == 3:
        m = m[..., :3].mean(axis=2)
    if m.max() > 1:
        m = m / 255
    obj = m > 0.5
    cover = obj.mean()
    if cover < 0.0003:
        return [Note(False, "No object found: the background removal kept almost nothing. Try a "
                            "picture where the object stands out from the background.")]
    notes = []
    if cover < 0.03:
        notes.append(Note(False, "The object is small in the picture. Crop closer to it for more "
                                 "detail."))
    border = np.concatenate([obj[0], obj[-1], obj[:, 0], obj[:, -1]])
    if border.mean() > 0.02:
        notes.append(Note(False, "The object touches the edge of the picture, so part of it may be "
                                 "cut off. Leave a little space around it."))
    pieces = count_pieces(obj)
    if pieces > 1:
        notes.append(Note(False, f"The cut-out has {pieces} separate pieces. TRELLIS.2 works best "
                                 "with one object: it makes one model of all of them."))
    return notes or [Note(True, "Looks good: one object, clearly cut out.")]


# ---------------------------------------------------------------- front + back pictures
def _object(pixels: np.ndarray) -> np.ndarray:
    """Which pixels belong to something (not the plain background), from transparency if the
    picture has it, else by how much they differ from the colour around the edges."""
    px = np.asarray(pixels, dtype=float)
    if px.max() > 1:
        px = px / 255
    if px.shape[2] == 4 and px[..., 3].min() < 0.99:
        return px[..., 3] > 0.5
    rgb = px[..., :3]
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    return np.abs(rgb - np.median(edge, axis=0)).max(axis=2) > 0.12


def find_views(pixels: np.ndarray, most: int = 3) -> list[tuple[int, int]]:
    """In a picture with several views side by side (front, back, maybe a side): each view's
    column range (x0, x1), split at the middle of the widest empty strips between them. One
    range when there is no gap; at most `most` ranges. Tiny specks don't count as views."""
    used = _object(pixels).mean(axis=0) > 0.002  # columns with some of the object in them
    width = len(used)
    cols = np.nonzero(used)[0]
    if not len(cols):
        return []
    gaps, start = [], None
    for x in range(cols[0], cols[-1] + 1):
        if not used[x]:
            start = x if start is None else start
        elif start is not None:
            if x - start >= max(4, width // 100):
                gaps.append((start, x))
            start = None
    weight = _object(pixels).sum(axis=0)
    gaps = sorted(gaps, key=lambda g: g[1] - g[0], reverse=True)
    while True:
        cuts = sorted((a + b) // 2 for a, b in gaps[:most - 1])
        edges = [0] + cuts + [width]
        mass = [weight[a:b].sum() for a, b in zip(edges, edges[1:])]
        if len(mass) == 1 or min(mass) >= 0.05 * max(mass):
            return list(zip(edges, edges[1:]))
        gaps.remove(next(g for g in gaps if (g[0] + g[1]) // 2 in cuts))  # a speck, not a view


def object_size(mask: np.ndarray) -> tuple[int, int] | None:
    """Width and height (pixels) of the object in a background-removal mask, counted the way
    ComfyUI's ImageCropToMask counts it (clearly inside the mask). None if there is none."""
    m = np.asarray(mask, dtype=float)
    if m.ndim == 3:
        m = m[..., :3].mean(axis=2)
    if m.max() > 1:
        m = m / 255
    obj = m > 0.8
    rows, cols = np.nonzero(obj.any(axis=1))[0], np.nonzero(obj.any(axis=0))[0]
    return None if not len(rows) else (int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def framing(sizes: dict[str, tuple[int, int]], length: float = 1.0, rig: float = 1.1,
            most: float = 4.0) -> tuple[dict[str, float], tuple[float, float]]:
    """How to frame each view for Pixal3D, so all of them share one scale.

    Pixal3D's rig expects the object's LONGEST side to span 1/rig of every view. From the front a
    tank shows only its width and height, so framing that tightly would squash its length into
    its width. sizes: each view's object size in its own picture (pixels), by view name ("front",
    "back", "left", "right"). The height is the common unit: width = front width / height;
    length (front to back) is measured from a side view, or else `length` x the width.
    Returns each view's framing (the object's outline spans 1/framing of the cut-out) and the
    object's (width, length) in heights."""
    fw, fh = sizes["front"]
    width = fw / fh
    if "back" in sizes:
        width = (width + sizes["back"][0] / sizes["back"][1]) / 2
    side = next((sizes[k] for k in ("left", "right") if k in sizes), None)
    depth = side[0] / side[1] if side else width * length
    longest = max(1.0, width, depth)
    pads = {name: min(most, rig * longest * h / max(w, h)) for name, (w, h) in sizes.items()}
    return pads, (width, depth)


def _shape(mask: np.ndarray) -> float:
    """Height / width of the object in a mask (0 if empty)."""
    size = object_size(mask)
    return 0.0 if size is None else size[1] / size[0]


VIEW_LABELS = {"front": "Front", "back": "Back", "left": "Side", "right": "Side"}


def views_notes(masks: dict[str, np.ndarray]) -> list[Note]:
    """Do the views show the same object the same way? Each mask on its own first."""
    notes = []
    for name, mask in masks.items():
        notes += [Note(n.good, f"{VIEW_LABELS[name]}: {n.text}") for n in mask_notes(mask) if not n.good]
    front, back = _shape(masks["front"]), _shape(masks.get("back", masks["front"]))
    if front and back and abs(front - back) / max(front, back) > 0.12:
        notes.append(Note(False, "The front and back have different outlines (one taller or wider than "
                                 "the other). Both should show the whole object, straight on, the same size."))
    if notes:
        return notes
    names = " and ".join(", ".join(VIEW_LABELS[n].lower() for n in masks).rsplit(", ", 1))
    return [Note(True, f"Looks good: {names} clearly cut out, and they match.")]
