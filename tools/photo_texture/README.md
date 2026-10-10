# photo_texture (experimental, not used by the add-on)

Early experiments to put the **real photo** onto the model instead of TRELLIS.2's colours.

- `fit_to_photo.py`: finds the object in the photo (bright/grey backdrop and shadows removed),
  fills the background with nearby object colours, and fits the model's front outline to the photo
  outline with optical flow. Outputs `_fill.jpg`, `_side.jpg`, `_fit.json`.
  `--colours-only` gives just the colour statistics used by colour matching.
- `contact_sheet.py`: puts review renders side by side.

**Result:** projection doubled the face, smeared thin parts and bending the mesh to fit distorted it.
The add-on uses **TRELLIS colours + "Match photo colours"** instead, which looked better.
Kept here for reference.

Needs: `numpy opencv-python pillow scipy`.
