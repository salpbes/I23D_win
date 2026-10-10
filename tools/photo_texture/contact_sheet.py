"""Contact sheet: photo crop + model views, one row per (region, version)."""
import sys
from PIL import Image, ImageDraw
def build(photo_path, views_dir, versions, out, S=260):
    photo = Image.open(photo_path).convert("RGB")
    regions = [("face", (590, 20, 930, 380), ["front", "left34", "right34", "side", "below"]),
               ("feet", (560, 1480, 1090, 1860), ["front", "left34", "right34", "side", "above"])]
    def tile(img, label):
        img = img.convert("RGB"); img.thumbnail((S, S)); t = Image.new("RGB", (S, S + 22), (30, 30, 30))
        t.paste(img, ((S - img.width) // 2, 22)); ImageDraw.Draw(t).text((5, 5), label, fill=(255, 255, 255)); return t
    rows = []
    for reg, crop, names in regions:
        for prefix, label in versions:
            tiles = [tile(photo.crop(crop), f"PHOTO {reg}")] + [tile(Image.open(f"{views_dir}{prefix}{reg}_{n}.png"), f"{label} {reg}: {n}") for n in names]
            row = Image.new("RGB", (len(tiles) * (S + 4), S + 22), (30, 30, 30))
            for i, t in enumerate(tiles): row.paste(t, (i * (S + 4), 0))
            rows.append(row)
    sheet = Image.new("RGB", (rows[0].width, len(rows) * (S + 28)), (30, 30, 30))
    for i, r in enumerate(rows): sheet.paste(r, (0, i * (S + 28)))
    sheet.save(out); return sheet.size
if __name__ == "__main__":
    print(build(sys.argv[1], sys.argv[2], [("", "v5"), ("v6_", "v6")], sys.argv[3]))
