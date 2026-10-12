"""Buttons. Each operator is thin: it checks inputs, calls pipeline, reports."""

from __future__ import annotations

import atexit
import random
from pathlib import Path

import bpy
from bpy.props import BoolProperty

from . import installer, pipeline, preferences, trellis_runner as tr

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
            installer.last_problems = problems
            if not problems and not prefs.start_comfy and not tr.server_up(prefs.comfy_url):
                problems = [f"ComfyUI is not running at {prefs.comfy_url}. Start it, or turn on "
                            "'Start ComfyUI when needed' in the add-on preferences."]
        if problems and problems[0]:
            s.status, s.last_error = "Can't start", problems[0]
            self.report({"ERROR"}, problems[0])
            return {"CANCELLED"}

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
            if s.auto_clean:
                s.status = "Cleaning for games..."
                _redraw(context)
                _clean_and_maybe_export(self, context, original)
            s.status = f"Done (seed {s.seed})"
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


class I23D_OT_check_setup(bpy.types.Operator):
    bl_idname = "i23d.check_setup"
    bl_label = "Check Setup"
    bl_description = "Check that ComfyUI and the TRELLIS.2 model files are where the add-on expects them"

    def execute(self, context):
        prefs = preferences.get(context)
        problems = tr.check_setup(bpy.path.abspath(prefs.comfy_dir), prefs.comfy_url)
        installer.last_problems = problems
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
        if installer.is_running():
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
        col.label(text="When the window says Done, press Check Setup.")

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
        self.report({"INFO"}, "Installing in a separate window. When it says Done, press Check Setup.")
        return {"FINISHED"}


CLASSES = (I23D_OT_generate, I23D_OT_cancel, I23D_OT_stop_comfy, I23D_OT_clean,
           I23D_OT_apply_material, I23D_OT_export, I23D_OT_open_folder, I23D_OT_open_log,
           I23D_OT_dismiss_error, I23D_OT_check_setup, I23D_OT_install_comfy)


@bpy.app.handlers.persistent
def _reset_after_load(_dummy):
    """A file saved mid-run would otherwise reopen showing a stuck progress bar."""
    if _job is None or not _job.is_running():
        for scene in bpy.data.scenes:
            if scene.i23d.is_running:
                scene.i23d.is_running = False
                scene.i23d.status = ""


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_reset_after_load)
    atexit.register(_stop_server)  # don't leave ComfyUI running after Blender quits


def unregister():
    if _reset_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_reset_after_load)
    if _job is not None:
        _job.cancel()
        _job.wait(10)
    _stop_server()
    atexit.unregister(_stop_server)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
