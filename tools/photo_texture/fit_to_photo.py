"""Reshape a mesh's front outline to match a photo, and prepare the photo colours.

Input : mesh json {xyz, n, tris} (world coords, Z up, camera looks along +Y), photo path
Output: json {xz: new x,z per vertex, uv: photo uv per vertex, facing: 0..1 per vertex, iou: [...]}
        <name>_fill.jpg  (photo with background replaced by nearest object colour)
        <name>_side.jpg  (heavily blurred fill, used where the surface turns away from the camera)
"""
import json, sys
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage


def masks(photo_rgb, white=235, min_bg_blob=40):
    a = photo_rgb.astype(int)
    # background = bright and grey (white backdrop and its soft shadows); skin, cloth, metal are not
    bright, chroma = a.min(axis=2), a.max(axis=2) - a.min(axis=2)
    fg = ~((bright > 195) & (chroma < 22)) & ~(bright > white)
    fg = ndimage.binary_closing(fg, iterations=2)
    # outline: biggest object, holes filled (used to match the silhouette)
    lab, n = ndimage.label(fg)
    main = lab == (np.argmax(ndimage.sum(fg, lab, range(1, n + 1))) + 1)
    outline = ndimage.binary_fill_holes(main)
    # colour mask: big white gaps inside the outline (e.g. between chin strap and face) stay background,
    # and grey floor shadows count as background when they touch the backdrop
    shadow = (chroma < 18) & (bright > 120)
    seed = ~main
    lab_s, _ = ndimage.label(shadow | seed)
    touching = np.unique(lab_s[seed & (lab_s > 0)])
    main = main & ~(np.isin(lab_s, touching) & shadow)
    bg = ~main
    lab_bg, nb = ndimage.label(bg)
    sizes = ndimage.sum(bg, lab_bg, range(1, nb + 1))
    small = np.isin(lab_bg, np.nonzero(sizes < min_bg_blob)[0] + 1)
    colour = main | small
    return outline, colour


def fill_background(photo_rgb, colour_mask, erode=3):
    core = ndimage.binary_erosion(colour_mask, iterations=erode)
    _, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
    out = photo_rgb[iy, ix].copy()
    out[core] = photo_rgb[core]
    return out


def raster(P, tris, W, H):
    img = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(img)
    for t in tris:
        dr.polygon([tuple(P[i]) for i in t], fill=1)
    return np.asarray(img).astype(bool)


def fit(xyz, tris, outline, steps=(10, 7, 5, 4, 3)):
    H, W = outline.shape
    ys, xs = np.nonzero(outline)
    X0, X1, Y0, Y1 = xs.min(), xs.max(), ys.min(), ys.max()
    xmin, xmax = xyz[:, 0].min(), xyz[:, 0].max(); zmin, zmax = xyz[:, 2].min(), xyz[:, 2].max()
    to_px = lambda x, z: np.stack([X0 + (x - xmin) / (xmax - xmin) * (X1 - X0), Y0 + (zmax - z) / (zmax - zmin) * (Y1 - Y0)], 1)
    to_world = lambda P: (xmin + (P[:, 0] - X0) / (X1 - X0) * (xmax - xmin), zmax - (P[:, 1] - Y0) / (Y1 - Y0) * (zmax - zmin))
    sdf = lambda m: np.clip(ndimage.distance_transform_edt(m) - ndimage.distance_transform_edt(~m), -40, 40)
    to8 = lambda s: ((s + 40) / 80 * 255).astype(np.uint8)
    target = to8(sdf(outline))
    iou = lambda m: float((m & outline).sum() / (m | outline).sum())
    P = to_px(xyz[:, 0], xyz[:, 2]); history = [iou(raster(P, tris, W, H))]
    best_P, best = P, history[0]
    for sigma in steps:
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_ULTRAFAST)
        dis.setFinestScale(0); dis.setGradientDescentIterations(60); dis.setVariationalRefinementIterations(10)
        dis.setVariationalRefinementAlpha(15); dis.setPatchSize(12); dis.setPatchStride(3)
        flow = cv2.GaussianBlur(dis.calc(to8(sdf(raster(P, tris, W, H))), target, None), (0, 0), sigma)
        P = P + np.stack([ndimage.map_coordinates(flow[..., k], [P[:, 1], P[:, 0]], order=1, mode="nearest") for k in (0, 1)], 1)
        history.append(iou(raster(P, tris, W, H)))
        if history[-1] > best:
            best_P, best = P, history[-1]
    x, z = to_world(best_P)
    return best_P, np.stack([x, z], 1), history


if __name__ == "__main__":
    mesh_path, photo_path, out_prefix = sys.argv[1:4]
    m = json.load(open(mesh_path))
    xyz, nrm, tris = np.array(m["xyz"]), np.array(m["n"]), np.array(m["tris"])
    photo = np.asarray(Image.open(photo_path).convert("RGB"))
    H, W = photo.shape[:2]
    outline, colour = masks(photo)
    fill = fill_background(photo, colour)
    Image.fromarray(fill).save(out_prefix + "_fill.jpg", quality=93)
    Image.fromarray(fill).filter(ImageFilter.GaussianBlur(40)).save(out_prefix + "_side.jpg", quality=90)
    if "--colours-only" in sys.argv:
        print("colours updated"); sys.exit(0)
    P, xz, hist = fit(xyz, tris, outline)
    facing = np.clip(-nrm[:, 1], 0, 1)          # 1 = faces the camera, 0 = side/back (original, un-folded normals)
    uv = np.stack([P[:, 0] / W, 1 - P[:, 1] / H], 1)
    json.dump({"xz": np.round(xz, 5).tolist(), "uv": np.round(uv, 5).tolist(), "facing": np.round(facing, 3).tolist(), "iou": hist},
              open(out_prefix + "_fit.json", "w"))
    print("outline match per step:", [round(h, 3) for h in hist])
