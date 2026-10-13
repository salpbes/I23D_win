# Getting started: from download to your first `.glb`

This guide takes you from nothing to a game-ready 3D model, one click at a time. You don't need to
know Blender or anything about AI 3D models. Red boxes in the pictures show what to click.

Plan for about 15 minutes of clicking, plus a one-time download of about 11 GB.

## Before you start

- **A Windows 10 or 11 PC with an NVIDIA graphics card that has 16 GB of graphics memory**
  (12 GB may work). To check: Task Manager › Performance › GPU › *Dedicated GPU memory*.
- **About 25 GB of free disk space.**
- **Blender 4.2 or newer**, free from [blender.org/download](https://www.blender.org/download/)
  (tested with 5.2).
- **Internet for the one-time download.** No account or sign-up needed. After that, everything
  runs offline on your own PC.
- **A picture of one object** (`.png`, `.jpg` or `.webp`): plain or see-through background, seen
  slightly from the side and from above.

## Part 1: Install (once)

### 1. Download the add-on

From the [latest release](https://github.com/salpbes/I23D_win/releases/latest), download
`image_to_game_asset-2.3.0.zip`. **Don't unzip it.** That one file is all you need.

### 2. Open "Install from Disk"

In Blender: **Edit › Preferences › Get Extensions**, then the small **⌄** menu at the top right ›
**Install from Disk…**. You can ignore the "Internet access" note: installing from disk works
offline.

![Get Extensions page with its menu open on Install from Disk](images/getting_started/01_install_from_disk_menu.png)

### 3. Pick the zip

Click the zip you downloaded, then **Install from Disk**. Leave *Enable on Install* ticked. Then
close the Preferences window.

![Blender's file picker with the add-on zip selected](images/getting_started/02_pick_the_zip.png)

### 4. Open the panel and press "Install ComfyUI + TRELLIS.2"

Move the mouse over the big 3D view and press **N**. A side panel opens on the right; click its
**Image→3D** tab. The first time, it starts with a **One-time setup** box. Press
**Install ComfyUI + TRELLIS.2**.

(The same button is also in **Edit › Preferences › Add-ons › Image to Game Asset**.)

![The Image→3D panel with its One-time setup box](images/getting_started/03_setup_box.png)

### 5. Say yes to the download

Blender asks first. It shows how much it downloads (about 11 GB) and where it goes
(`%USERPROFILE%\I23D`, a folder in your user folder). Press **Download and Install**.

![The confirm dialog: about 11 GB, the folder, Download and Install](images/getting_started/04_confirm_download.png)

### 6. Wait while it downloads

The panel shows a progress bar and how many GB are done. It downloads ComfyUI (about 2 GB), the
program that runs the AI, and then the TRELLIS.2 model files (about 9 GB), the AI itself.
Depending on your internet this takes from a few minutes to about an hour. Blender stays usable
meanwhile.

![The panel's progress bar while the AI model files download](images/getting_started/05_sidebar_progress.png)

A separate window opens too and does the actual work, with the details. Leave it open until
Blender says the setup is finished. If it gets closed early, just press Install again: finished
files are skipped and a stopped download carries on where it left off.

![The installer window after it finished, ending with Done](images/getting_started/06_installer_window.png)

### 7. Setup finished

When the download is done, Blender checks the setup by itself and says **Setup finished**. You
can close the installer window now. If something is missing, the panel says what, with the
Install button to fix it.

![The panel saying Setup finished: ComfyUI and TRELLIS.2 are ready](images/getting_started/07_setup_finished.png)

## Part 2: Your first model

### 8. Clear the starting scene

A new Blender scene starts with a grey cube in the middle, exactly where your model will appear.
Click the cube, press **X**, then **Delete**.

### 9. Pick a picture

In the **Image→3D** panel, click the folder icon next to the empty picture box and choose your
picture. The name fills itself in.

![The Image→3D tab with a picture chosen](images/getting_started/08_pick_a_picture.png)

### 10. Press "Generate 3D Model"

The bar shows each step as the AI works. On an RTX 5060 Ti 16 GB a model takes about 2 to 3
minutes. The very first time, the add-on also needs about 30 seconds to start ComfyUI in the
background. Blender stays usable meanwhile, and **Cancel** stops the run.

![The progress bar while the model is being made](images/getting_started/09_generating.png)

### 11. Look at your model

The model appears in colour, and the view turns to it by itself. It is already cleaned for
games: light (15,000 triangles), closed, standing on the ground, with its colours, metal and fine
bumps baked on. The panel lists what was done.

To turn the view, drag with the middle mouse button; scroll to zoom. The detailed original (about
700,000 triangles) is kept, hidden, in case you want to make another size later.

![The finished axe in colour, with the panel saying Done](images/getting_started/10_model_done.jpg)

### 12. Save it as a `.glb`

Press **Export .glb**. The panel says **Saved: *name*_15k.glb**. The folder button next to it
opens the folder where it went: `%USERPROFILE%\I23D\output\game-ready`.

That `.glb` file is your game-ready model. Godot, Unity, Unreal, three.js and Blender can all
open it.

Tip: tick **Export .glb automatically** (section 1 of the panel) and every new model is saved
by itself.

![Done, Saved: viking_wolf_rune_axe_15k.glb, and the Export .glb button](images/getting_started/11_exported.png)

## Next

- Smaller or bigger models, other colours, every setting: [WORKFLOW.md](WORKFLOW.md)
- Something went wrong: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Before you sell or publish what you make: read the [Disclaimer](../README.md#disclaimer)

<sub>Screenshots: Blender 5.2.2 on Windows 11 with an RTX 5060 Ti 16 GB. The picture is ComfyUI's
example axe.</sub>
