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


def find_split(pixels: np.ndarray) -> int | None:
    """In a picture with the front and the back side by side: the column where the back starts
    (the middle of the widest empty strip near the centre). None if there is no such strip."""
    used = _object(pixels).mean(axis=0) > 0.002  # columns with some of the object in them
    width = len(used)
    lo, hi = width // 4, width * 3 // 4
    best_gap, split, start = 0, None, None
    for x in range(lo, hi + 1):
        if x < hi and not used[x]:
            start = x if start is None else start
        elif start is not None:
            if x - start > best_gap:
                best_gap, split = x - start, (start + x) // 2
            start = None
    if split is None or best_gap < max(4, width // 100) or not used[:split].any() or not used[split:].any():
        return None
    return split


def _shape(mask: np.ndarray) -> float:
    """Height / width of the object in a mask (0 if empty)."""
    m = np.asarray(mask, dtype=float)
    if m.ndim == 3:
        m = m[..., :3].mean(axis=2)
    obj = m > (127 if m.max() > 1 else 0.5)
    rows, cols = np.nonzero(obj.any(axis=1))[0], np.nonzero(obj.any(axis=0))[0]
    return 0.0 if not len(rows) else (rows[-1] - rows[0] + 1) / (cols[-1] - cols[0] + 1)


def pair_notes(front_mask: np.ndarray, back_mask: np.ndarray) -> list[Note]:
    """Do the front and back show the same object the same way? Each mask on its own first."""
    notes = []
    for side, mask in (("Front", front_mask), ("Back", back_mask)):
        notes += [Note(n.good, f"{side}: {n.text}") for n in mask_notes(mask) if not n.good]
    front, back = _shape(front_mask), _shape(back_mask)
    if front and back and abs(front - back) / max(front, back) > 0.12:
        notes.append(Note(False, "The front and back have different outlines (one taller or wider than "
                                 "the other). Both should show the whole object, straight on, the same size."))
    return notes or [Note(True, "Looks good: front and back clearly cut out, and they match.")]
