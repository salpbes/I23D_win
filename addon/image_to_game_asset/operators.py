"""Buttons. Each operator is thin: it checks inputs, calls pipeline, reports."""

from __future__ import annotations

import atexit
import random
from dataclasses import dataclass, field
from pathlib import Path

import bpy
import bpy.utils.previews
import numpy as np
from bpy.props import BoolProperty

from . import installer, picture_check, pipeline, preferences, trellis_runner as tr

_job: tr.TrellisJob | None = None        # only one TRELLIS run at a time
_server: tr.ComfyServer | None = None    # the ComfyUI this add-on started (if any)


def _stop_server() -> None:
    global _server
    if _server is not None:
        _server.stop()
        _server = None


def _server_for(prefs, log_path) -> tr.ComfyServer | None:
    """The ComfyUI to start if none is running (None if the user doesn't want that)."""
    global _server
    if not prefs.start_comfy:
        return None
    comfy_dir = bpy.path.abspath(prefs.comfy_dir)
    if _server is None or not _server.is_alive() or str(_server.comfy_dir) != str(Path(comfy_dir).expanduser()):
        _server = tr.ComfyServer(comfy_dir, prefs.comfy_url, log_path=log_path)
    return _server


def _redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _show_result(context, obj):
    """Aim the 3D views at the new model and show its colours (otherwise a beginner sees a plain
    grey model, often off to the side)."""
    if context.window is None or not preferences.get(context).show_result:
        return
    for other in context.selected_objects:
        other.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    for area in context.window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        space = area.spaces.active
        if space.shading.type == "SOLID":  # leave wireframe and rendered views as the user set them
            space.shading.type = "MATERIAL"
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        with context.temp_override(window=context.window, area=area, region=region):
            bpy.ops.view3d.view_selected()


def _redraw_everywhere():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _watch_installer():
    """Timer while the installer window works: keeps its progress bar moving, then runs Check Setup."""
    _redraw_everywhere()
    result = installer.finish()
    if result is None:
        return 1.0 if installer.working() else None
    if result.state == "done":
        prefs = preferences.get(bpy.context)
        problems = tr.check_setup(bpy.path.abspath(prefs.comfy_dir), prefs.comfy_url)
        installer.last_problems, installer.check_passed = problems, not problems
        installer.note, installer.note_ok = ("", False) if problems else (
            "Setup finished: ComfyUI and TRELLIS.2 are ready. Pick a picture and press Generate.", True)
    else:
        installer.note, installer.note_ok = result.message, False
    _redraw_everywhere()
    return None


# ---------------------------------------------------------------- picture check
@dataclass
class PictureCheck:
    image: str                                  # the picture checked (absolute path)
    job: tr.CutoutJob | None = None
    notes: list = field(default_factory=list)   # picture_check.Note
    error: str = ""
    icon_id: int = 0                            # the cut-out, for template_icon

    @property
    def running(self) -> bool:
        return self.job is not None and self.job.is_running()

    @property
    def cutout(self) -> str | None:
        return self.job.cutout_path if self.job and not self.running and not self.error else None


_check: PictureCheck | None = None
_previews = None  # bpy.utils.previews collection holding the cut-out shown in the panel


def picture_check_for(context) -> PictureCheck | None:
    """The check of the picture now chosen in the panel (None if it hasn't been checked)."""
    s = context.scene.i23d
    if _check is None or not s.image_path or _check.image != bpy.path.abspath(s.image_path):
        return None
    return _check


def _image_pixels(path: str) -> np.ndarray:
    """A picture's pixels (rows x columns x channels, 0-1), read with Blender."""
    img = bpy.data.images.load(path, check_existing=False)
    try:
        w, h = img.size
        px = np.empty(w * h * img.channels, np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(h, w, img.channels)
    finally:
        bpy.data.images.remove(img)


def start_picture_check(context) -> str:
    """Check the panel's picture: its size now, its cut-out in the background. Returns a problem
    that stops the check from starting (empty when it started)."""
    global _check
    s, prefs = context.scene.i23d, preferences.get(context)
    image = bpy.path.abspath(s.image_path)
    problem = tr.check_image(image) if s.image_path else "Choose a picture first."
    if not problem and preferences.setup_missing(prefs) and not tr.server_up(prefs.comfy_url):
        problem = "The picture check needs ComfyUI + TRELLIS.2: install them first (see above)."
    if not problem and not prefs.start_comfy and not tr.server_up(prefs.comfy_url):
        problem = f"ComfyUI is not running at {prefs.comfy_url}."
    if problem:
        _check = PictureCheck(image=image, error=problem)
        return problem
    try:
        img = bpy.data.images.load(image, check_existing=False)
        notes = picture_check.picture_notes(*img.size)
        bpy.data.images.remove(img)
    except RuntimeError as exc:
        _check = PictureCheck(image=image, error=f"Blender can't read this picture ({exc}).")
        return _check.error
    out_dir = pipeline.output_dir(context) / "previews"
    name = tr.sanitize_name(Path(image).stem)
    job = tr.CutoutJob(url=prefs.comfy_url, image=image, out_base=out_dir / name,
                       log_path=out_dir / f"{name}_check_log.txt",
                       server=_server_for(prefs, pipeline.output_dir(context) / "comfyui_log.txt"))
    job.start()
    _check = PictureCheck(image=image, job=job, notes=notes)
    if not bpy.app.timers.is_registered(_watch_picture_check):
        bpy.app.timers.register(_watch_picture_check, first_interval=0.5)
    return ""


def finish_picture_check(check: PictureCheck) -> None:
    """The cut-out is back: read what its mask says and load it for the panel."""
    job = check.job
    if job.error or not job.cutout_path:
        check.error = job.error or "ComfyUI made no cut-out."
        return
    check.notes = check.notes + picture_check.mask_notes(_image_pixels(job.mask_path)[..., :3])
    if _previews is not None:
        _previews.clear()
        check.icon_id = _previews.load(job.cutout_path, job.cutout_path, "IMAGE").icon_id


def _watch_picture_check():
    _redraw_everywhere()
    check = _check
    if check is None or check.job is None:
        return None
    if check.running:
        return 0.5
    try:
        finish_picture_check(check)
    except Exception as exc:  # shown in the panel
        check.error = str(exc)
    if not preferences.get(bpy.context).keep_comfy and (_job is None or not _job.is_running()):
        _stop_server()
    _redraw_everywhere()
    return None


def _clean_and_maybe_export(op, context, obj):
    s = context.scene.i23d
    game, stats = pipeline.clean(context, obj)
    s.last_result = pipeline.describe(stats)
    if s.auto_export:
        path = pipeline.export(context, game)
        s.last_result += f" · saved {path.name}"
    return game


class I23D_OT_generate(bpy.types.Operator):
    bl_idname = "i23d.generate"
    bl_label = "Generate 3D Model"
    bl_description = ("Make a 3D model from the picture with TRELLIS.2 on this PC "
                      "(under 3 minutes). Blender stays usable")
    bl_options = {"REGISTER"}

    def execute(self, context):
        global _job
        s = context.scene.i23d
        prefs = preferences.get(context)
        if _job is not None and _job.is_running():
            self.report({"WARNING"}, "A model is already being generated.")
            return {"CANCELLED"}

        image = bpy.path.abspath(s.image_path)
        problems = [tr.check_image(image) if s.image_path else "Choose a picture first."]
        if not problems[0]:
            problems = tr.check_setup(bpy.path.abspath(prefs.comfy_dir), prefs.comfy_url)
            installer.last_problems, installer.check_passed = problems, not problems
            if not problems and not prefs.start_comfy and not tr.server_up(prefs.comfy_url):
                problems = [f"ComfyUI is not running at {prefs.comfy_url}. Start it, or turn on "
                            "'Start ComfyUI when needed' in the add-on preferences."]
        if problems and problems[0]:
            s.status, s.last_error = "Can't start", problems[0]
            self.report({"ERROR"}, problems[0])
            return {"CANCELLED"}

        installer.note = ""
        self._name = tr.sanitize_name(s.asset_name or Path(image).stem)
        s.asset_name = self._name
        out_dir = pipeline.output_dir(context)
        if s.random_seed:
            s.seed = random.randint(0, 2_147_483_647)
        s.last_log = str(out_dir / f"{self._name}_log.txt")
        _job = tr.TrellisJob(url=prefs.comfy_url, image=image, out_base=out_dir / self._name,
                             seed=s.seed, detail=s.quality, log_path=s.last_log,
                             server=_server_for(prefs, out_dir / "comfyui_log.txt"))
        _job.start()

        s.is_running, s.progress, s.status = True, 0.0, "Starting..."
        s.last_error = s.last_result = ""
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _read(self, context):
        s = context.scene.i23d
        s.progress, s.status = _job.fraction, _job.label
        quiet = _job.quiet_for()
        s.activity = (f"Running {tr.fmt_duration(_job.elapsed())} · "
                      f"last news {tr.fmt_duration(quiet)} ago")
        s.looks_stuck = quiet > tr.QUIET_WARNING_SECONDS.get(s.quality, 15 * 60)
        _redraw(context)

    def _finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        context.scene.i23d.is_running = False
        context.scene.i23d.looks_stuck = False
        context.scene.i23d.activity = f"Took {tr.fmt_duration(_job.elapsed())}"
        _redraw(context)

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        s = context.scene.i23d
        self._read(context)
        if _job.is_running():
            return {"PASS_THROUGH"}

        self._read(context)  # last news
        self._finish(context)
        if not preferences.get(context).keep_comfy:
            _stop_server()  # only stops a ComfyUI this add-on started
        if _job.cancelled:
            s.status = "Cancelled"
            return {"CANCELLED"}

        glb = Path(_job.glb_path) if _job.glb_path else None
        if _job.error or glb is None or not glb.is_file():
            s.last_error = _job.error or "ComfyUI finished without a model."
            if "out of memory" in s.last_error.lower():
                s.last_error += (" - Close other programs that use the graphics card, "
                                 "or choose Standard detail.")
            s.status = f"Failed - see {self._name}_log.txt"
            self.report({"ERROR"}, s.last_error[:300])
            return {"CANCELLED"}

        try:
            original = pipeline.import_original(context, glb, self._name, bpy.path.abspath(s.image_path))
            s.status = "Model imported"
            result = original
            if s.auto_clean:
                s.status = "Cleaning for games..."
                _redraw(context)
                result = _clean_and_maybe_export(self, context, original)
            s.status = f"Done (seed {s.seed})"
            _show_result(context, result)
        except Exception as exc:  # show any Blender-side problem in the panel
            s.status, s.last_error = "Failed after generating", str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{self._name}: done")
        return {"FINISHED"}


class I23D_OT_cancel(bpy.types.Operator):
    bl_idname = "i23d.cancel"
    bl_label = "Cancel"
    bl_description = "Stop making this model (ComfyUI keeps running for the next one)"

    def execute(self, context):
        if _job is not None:
            _job.cancel()
        context.scene.i23d.status = "Cancelling..."
        return {"FINISHED"}


class I23D_OT_stop_comfy(bpy.types.Operator):
    bl_idname = "i23d.stop_comfy"
    bl_label = "Stop ComfyUI"
    bl_description = "Stop the ComfyUI this add-on started and free its memory (the next model starts slower)"

    @classmethod
    def poll(cls, context):
        return _server is not None and _server.is_alive() and not context.scene.i23d.is_running

    def execute(self, context):
        _stop_server()
        self.report({"INFO"}, "ComfyUI stopped.")
        return {"FINISHED"}


class I23D_OT_clean(bpy.types.Operator):
    bl_idname = "i23d.clean"
    bl_label = "Clean for Game"
    bl_description = ("Make a light, watertight copy of the selected model. "
                      "The original is kept (hidden), so you can re-run with other settings")
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == "MESH" and not context.scene.i23d.is_running

    def execute(self, context):
        s = context.scene.i23d
        try:
            _clean_and_maybe_export(self, context, context.active_object)
        except Exception as exc:
            s.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        s.last_error = ""
        self.report({"INFO"}, s.last_result)
        return {"FINISHED"}


class I23D_OT_apply_material(bpy.types.Operator):
    bl_idname = "i23d.apply_material"
    bl_label = "Apply Colours"
    bl_description = "Re-apply the chosen colours (TRELLIS colours re-bake from the hidden original)"

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        notes = []
        for obj in [o for o in context.selected_objects if o.type == "MESH"]:
            try:
                notes.append(pipeline.apply_look(context, obj, pipeline.resolve_source(obj)))
            except Exception as exc:
                self.report({"ERROR"}, str(exc))
                return {"CANCELLED"}
        if notes:
            self.report({"INFO"}, notes[-1])
        return {"FINISHED"}


class I23D_OT_export(bpy.types.Operator):
    bl_idname = "i23d.export"
    bl_label = "Export .glb"
    bl_description = "Save each selected model as its own .glb file"

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects)

    def execute(self, context):
        objs = [o for o in context.selected_objects if o.type == "MESH"]
        try:
            paths = [pipeline.export(context, o) for o in objs]
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        context.scene.i23d.last_result = "Saved: " + ", ".join(p.name for p in paths)
        self.report({"INFO"}, f"Saved {len(paths)} file(s) to {paths[0].parent}")
        return {"FINISHED"}


class I23D_OT_open_folder(bpy.types.Operator):
    bl_idname = "i23d.open_folder"
    bl_label = "Open Folder"
    bl_description = "Show the export folder in File Explorer"

    def execute(self, context):
        folder = pipeline.export_dir(context)
        folder.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.path_open(filepath=str(folder))
        return {"FINISHED"}


class I23D_OT_open_log(bpy.types.Operator):
    bl_idname = "i23d.open_log"
    bl_label = "Open Log"
    bl_description = "Open the log of the last run (what ComfyUI reported, step by step)"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.i23d.last_log) and Path(context.scene.i23d.last_log).is_file()

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=context.scene.i23d.last_log)
        return {"FINISHED"}


class I23D_OT_dismiss_error(bpy.types.Operator):
    bl_idname = "i23d.dismiss_error"
    bl_label = "Dismiss"
    bl_description = "Hide this message"

    def execute(self, context):
        context.scene.i23d.last_error = ""
        return {"FINISHED"}


class I23D_OT_check_picture(bpy.types.Operator):
    bl_idname = "i23d.check_picture"
    bl_label = "Check Picture"
    bl_description = ("Remove the picture's background the way TRELLIS.2 will, show the result and "
                      "say if something may go wrong (seconds once ComfyUI is running)")

    @classmethod
    def poll(cls, context):
        return bool(context.scene.i23d.image_path) and not (_check and _check.running)

    def execute(self, context):
        problem = start_picture_check(context)
        if problem:
            self.report({"WARNING"}, problem)
            return {"CANCELLED"}
        return {"FINISHED"}


class I23D_OT_view_cutout(bpy.types.Operator):
    bl_idname = "i23d.view_cutout"
    bl_label = "View Larger"
    bl_description = "Open the cut-out in its own window, as TRELLIS.2 will see it (scroll to zoom)"

    @classmethod
    def poll(cls, context):
        check = picture_check_for(context)
        return check is not None and check.cutout is not None and Path(check.cutout).is_file()

    def execute(self, context):
        check = picture_check_for(context)
        img = bpy.data.images.load(check.cutout, check_existing=True)
        img.reload()
        before = {w.as_pointer() for w in context.window_manager.windows}
        bpy.ops.screen.userpref_show("INVOKE_DEFAULT")  # a small new window, turned into an image viewer
        new = [w for w in context.window_manager.windows if w.as_pointer() not in before]
        if not new:
            self.report({"ERROR"}, "Blender didn't open a new window.")
            return {"CANCELLED"}
        area = new[0].screen.areas[0]
        area.ui_type = "IMAGE_EDITOR"
        area.spaces.active.image = img
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        with context.temp_override(window=new[0], area=area, region=region):
            bpy.ops.image.view_all(fit_view=True)
        return {"FINISHED"}


class I23D_OT_check_setup(bpy.types.Operator):
    bl_idname = "i23d.check_setup"
    bl_label = "Check Setup"
    bl_description = "Check that ComfyUI and the TRELLIS.2 model files are where the add-on expects them"

    def execute(self, context):
        prefs = preferences.get(context)
        problems = tr.check_setup(bpy.path.abspath(prefs.comfy_dir), prefs.comfy_url)
        installer.last_problems, installer.check_passed = problems, not problems
        installer.note = ""
        if problems:
            for p in problems:
                self.report({"ERROR"}, p)
            return {"CANCELLED"}
        running = "running" if tr.server_up(prefs.comfy_url) else "installed (starts when needed)"
        self.report({"INFO"}, f"Ready: ComfyUI {running}, TRELLIS.2 models found.")
        return {"FINISHED"}


class I23D_OT_install_comfy(bpy.types.Operator):
    bl_idname = "i23d.install_comfy"
    bl_label = "Install ComfyUI + TRELLIS.2"
    bl_description = (f"Download and set up ComfyUI and the TRELLIS.2 model files (about "
                      f"{installer.DOWNLOAD_GB} GB) in a separate window. Blender stays usable. "
                      "Safe to run again: finished files are skipped")

    check_only: BoolProperty(name="Only check this PC", options={"SKIP_SAVE", "HIDDEN"},
                             description="Only check the graphics card, memory and disk; download nothing")

    @classmethod
    def poll(cls, context):
        if installer.working():
            cls.poll_message_set("The installer is already running in its own window")
            return False
        return True

    def _folder(self, context):
        return installer.install_dir_for(bpy.path.abspath(preferences.get(context).comfy_dir))

    def invoke(self, context, event):
        if self.check_only:
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(
            self, width=460, title="Install ComfyUI + TRELLIS.2", confirm_text="Download and Install")

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text=f"This downloads about {installer.DOWNLOAD_GB} GB (ComfyUI and the TRELLIS.2 "
                       "model files) into:", icon="IMPORT")
        col.label(text=f"    {self._folder(context)}")
        col.separator()
        col.label(text="It runs in its own window, where you can watch it.")
        col.label(text="It can take an hour on a slow connection. Blender stays usable.")
        col.label(text="Blender shows its progress and checks the setup when it is done.")

    def execute(self, context):
        folder = self._folder(context)
        try:
            installer.start(folder, check_only=self.check_only)
        except OSError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        if self.check_only:
            self.report({"INFO"}, "Checking this PC in a separate window.")
            return {"FINISHED"}
        # The add-on looks for ComfyUI where the installer puts it.
        preferences.get(context).comfy_dir = str(folder / installer.COMFY_FOLDER)
        installer.last_problems = []
        if not bpy.app.timers.is_registered(_watch_installer):
            bpy.app.timers.register(_watch_installer, first_interval=1.0)
        self.report({"INFO"}, "Installing in a separate window. Blender shows its progress and "
                              "checks the setup when it's done.")
        return {"FINISHED"}


CLASSES = (I23D_OT_generate, I23D_OT_cancel, I23D_OT_stop_comfy, I23D_OT_clean,
           I23D_OT_apply_material, I23D_OT_export, I23D_OT_open_folder, I23D_OT_open_log,
           I23D_OT_dismiss_error, I23D_OT_check_picture, I23D_OT_view_cutout, I23D_OT_check_setup,
           I23D_OT_install_comfy)


@bpy.app.handlers.persistent
def _reset_after_load(_dummy):
    """A file saved mid-run would otherwise reopen showing a stuck progress bar."""
    if _job is None or not _job.is_running():
        for scene in bpy.data.scenes:
            if scene.i23d.is_running:
                scene.i23d.is_running = False
                scene.i23d.status = ""


def register():
    global _previews
    _previews = bpy.utils.previews.new()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_reset_after_load)
    atexit.register(_stop_server)  # don't leave ComfyUI running after Blender quits


def unregister():
    global _previews, _check
    for timer in (_watch_installer, _watch_picture_check):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    if _check and _check.running:
        _check.job.cancel()
    _check = None
    if _previews is not None:
        bpy.utils.previews.remove(_previews)
        _previews = None
    if _reset_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_after_load)
    if _job is not None:
        _job.cancel()
        _job.wait(10)
    _stop_server()
    atexit.unregister(_stop_server)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
