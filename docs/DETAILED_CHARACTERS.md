# Getting a better face and feet (manual "zoom-in" method)

This was worked out on a WW2 soldier photo. It is **manual for now** (done with Blender Python,
not yet a button in the add-on).

## Why faces and feet come out blurry
- **What happens:** TRELLIS.2 first decides the rough shape on a **64×64×64 grid** and squeezes the
  picture to a fixed size. A full-body person is ~1.8 m tall, so the face gets only a handful of
  grid cells and a few hundred pixels. Detail that isn't there can't be invented later.
- **Why "High" detail doesn't fix it on a Mac:** it costs far more memory and time (it stalled on
  24 GB) and the first, rough grid is still 64³.
- **Why photo projection didn't fix it:** projecting the photo onto the model doubled the face,
  smeared the rifle and left white edges. Bending the model to fit the photo distorted it.
  TRELLIS.2's own colours fit its own shape far better.

## The idea
Give TRELLIS.2 **close-up crops**, so the small part fills the whole picture and gets the full
grid. Then put the close-up parts onto the full-body model.

## Steps
1. **Crop** the photo (any image editor):
   - `name_head.png`: head and shoulders, a little margin around them.
   - `name_boots.png`: from mid-shin down, both feet.
   Keep the original photo too.
2. **Generate all three** with the add-on (full body, head, boots). Try 2–3 seeds each and keep
   the best. The close-ups usually look much better than the same parts in the full-body run.
3. **Line them up** in Blender (scale, move, rotate) so the head and boots sit on the body:
   - Use the crop boxes (pixel rectangles in the original photo) to work out scale and height.
     The ratio between the crop's height and the full outline's height gives the size.
   - **Head:** cut the body at the neck and replace everything above.
   - **Boots:** fit **each leg separately**. Measure the leg's centre in a thin band at the cut
     height (not the whole leg, where stray points throw the measurement off), move each boot under
     its own leg, and **don't scale** the boots. Taper the trouser bottom a little so it tucks into
     the boot.
4. **Join** the parts and run the add-on's **Clean Selected** (it rebuilds everything as one closed
   solid, so the seams disappear) with *TRELLIS colours*.
5. Optional: raise *Match photo colours* if the colours look washed out. Grey/neutral areas keep
   their tint, so metal parts don't turn blue or brown.

## Results on the soldier (M4, 24 GB, Fast/512)
- Exported `.glb`: 20k triangles, 2048 texture, ~5 MB, 1 m tall (scale ×1.8 in three.js for a real
  person).
- Face and boots clearly better than any single full-body run. A small head offset remained.

## Lessons
- Don't bend or stretch the AI geometry to match the photo. It flattens and distorts.
- Measure in a thin slice, not over a whole part; stray points ruin averages.
- Check sizes from the real vertex coordinates. `object.dimensions` can be stale right after edits.

## Possible future add-on feature
A "Detailed character" option: you mark head/feet boxes on the picture, the add-on makes the crops,
runs TRELLIS.2 three times, aligns the parts with the measured boxes and cleans the joined result.
