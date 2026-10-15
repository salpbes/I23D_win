# Problems and fixes (Windows)

| Problem (what you see) | Why | Fix |
|---|---|---|
| **Check Setup:** "ComfyUI folder not found" or "Model file missing" | ComfyUI isn't installed where the add-on looks, or a download stopped | Press **Install ComfyUI + TRELLIS.2** in the panel's setup box or the add-on preferences (again: it continues where it stopped), or fix *ComfyUI folder* in the preferences |
| The panel says "The installer window was closed before it finished" | The installer's window was closed (or the PC restarted) mid-download | Press **Install ComfyUI + TRELLIS.2** again: finished files are skipped and the stopped download carries on |
| The panel shows "One-time setup" although you run your own ComfyUI | The add-on looks for ComfyUI in its own folder first | Start your ComfyUI at the *ComfyUI address*, then press **Already have it? Check Setup** |
| Stuck on "Starting ComfyUI" then "ComfyUI stopped while starting" | ComfyUI couldn't start (old NVIDIA driver, missing Visual C++ runtime, port in use) | Open `comfyui_log.txt` in the output folder. Update the NVIDIA driver; install https://aka.ms/vc14/vc_redist.x64.exe; or change *ComfyUI address* to another port |
| "ComfyUI is not running at …" | *Start ComfyUI when needed* is off | Turn it on, or start ComfyUI yourself |
| "KSampler: CUDA out of memory" | Not enough graphics memory | Close games, video tools and other ComfyUI windows; use **Standard** detail. Peak use is about 11.5 GB at Standard |
| "ComfyUI rejected the job - … Value not in list" | Your ComfyUI is missing a model file, or is a different version than the workflow was made for | **Check Setup**; use ComfyUI v0.39.0 from the installer, or rebuild the workflow (`scripts\make_addon_workflow.py`) |
| "No news from ComfyUI for a long time" | Out of graphics memory, or the PC went to sleep | Task Manager › Performance › GPU; Cancel and try again |
| "No textures" on the cleaned model | Viewport is in *Solid* mode | Switch to **Material Preview** |
| Cleaned model is plain Clay | The original has no colours, or a plain preset is chosen | Choose *TRELLIS colours*, then press the 🎨 button |
| A `.glb` saved with Blender's **File › Export › glTF** is 100+ MB (add-on 2.1.1 and older) | That export saves every object in the scene, and hidden ones too: each detailed original adds ~700k triangles and its 4096 textures | Update to 2.1.2: cleaned originals are kept in the .blend but out of the scene. Or use the add-on's **Export .glb** button, or tick *Limit to › Selected Objects* in File › Export |
| Every model lies on its back, front facing up (add-on 2.0.0–2.1.0) | Those versions turned every model 90° (the Mac version's *Stand upright*), but ComfyUI's `.glb` already stands upright | Update to 2.1.1. For models already in a scene: tick *Show detailed originals* (section 2), select the original, rotate it R X 90, press **Clean Selected** |
| A flat object (axe, sword, shield) comes out lying flat | TRELLIS.2 picks the pose in its first step; a flat thing seen from the front can also be read as lying down seen from above. Seed-dependent: the same axe picture came out upright with one seed and flat with another | Generate again (new seed), or rotate it (R X 90) and press **Clean Selected** |
| Washed-out colours | TRELLIS.2 colours can be pale | *Match photo colours* slider |
| Thin parts vanish after cleaning | Voxel rebuild too coarse | *Rebuild detail: Fine* or raise *Thicken* |
| Result differs between runs | Different **seed** (not a bug) | Random seed is on by default; run 2–3 times and keep the best |
| **Front + back:** "Front + back pictures need one more download" | Pixal3D's model (5.6 GB) isn't installed yet | Press **Download for Front + Back** in the panel (or run the installer with `-FrontBack`) |
| **Front + back:** "there is no gap between a front and a back in this picture" | The add-on splits a side-by-side picture at the empty strip between the two views. A title, label or shadow across the middle, or views that touch, leave no gap | Ask for "no other elements" and "side by side" in the prompt, or cut the picture in two and pick the back in the second box |
| **Front + back:** "The front and back have different outlines" | One view is taller, wider, turned or cut off, so the two don't line up in 3D | Use an exact front and back view, a level camera and the same size in both. You can still press Generate |
| **Front + back:** dark patches or shadows on the model (e.g. under the helmet) | *Paint the pictures onto the model* copies the picture's colours, including its light and shadow | Untick it (section 1) and press 🎨 next to **Clean Selected** for the AI's own colours, or use a picture with soft, even light |
| **Front + back:** painted colours slightly off a part's edge | The cleaned model is a little thicker than the AI's, and the picture and model never match to the pixel; the paint fades out near edges to hide this | Usually invisible in a game. Untick *Paint the pictures onto the model* and press 🎨 if it bothers you |
| **Front + back:** the model looks turned or squashed from the side | Pixal3D places the two pictures exactly 180° apart; a turned view (e.g. "15-degree rotation") ends up in the model, and the side is only guessed | Ask for "straight front view and exact back view, no rotation". The side depth is still a guess |

## Found while porting (for developers)
| Problem | Why | Fix |
|---|---|---|
| The official TRELLIS.2 install fails on RTX 50 cards | It pins PyTorch 2.6 + CUDA 12.4, which don't support Blackwell (`sm_120`) | Use ComfyUI's built-in TRELLIS.2: its portable build ships PyTorch 2.10 + CUDA 12.8 with `sm_120` |
| Front + back with plain TRELLIS.2 | ComfyUI's `Trellis2Conditioning` takes one picture; TRELLIS.2 has no multi-view mode | Pixal3D's multi-view model runs on the same stages: the add-on swaps the `UNETLoader` file and uses `Pixal3DMultiViewConditioning` (fov 20, views 180° apart), as ComfyUI's `3d_pixal3d_multi_views` template does |
| ComfyUI rejects the template workflow over a missing `pixal3d_int8_convrot` | The template switches between Pixal3D and TRELLIS.2, and ComfyUI checks both sides | `make_addon_workflow.py` resolves the switch to TRELLIS.2 and keeps only what the `.glb` needs |
| Template values land in the wrong inputs | Editor workflows store widget values as a list; "dynamic combo" inputs add extra values | `comfy_workflow_to_api.py` reads `/object_info` and expands dynamic combos as `name.option` |
| ComfyUI's ambient-occlusion and normal-map bakes take 72 of 182 s | The add-on bakes its own maps (colour, metal/roughness, normal) from the detailed original onto its light mesh | Left out of the add-on's workflow |
| Windows PowerShell 5.1 stops on Blender warnings | It turns a native program's stderr into errors | `run_tests.ps1` relaxes the error setting around Blender calls |

## Logs
Each run writes `<name>_log.txt` next to the model (every ComfyUI message, with times); the
panel's **Open Log** button opens it. When the add-on started ComfyUI, its own output is in
`comfyui_log.txt` in the same folder.
