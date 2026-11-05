#! python 3
# -*- coding: utf-8 -*-
"""
20 - Assembly Steps

Cartoon-style assembly instruction images, straight from the viewport.

The look lives in two team display modes (templates/display_modes):
  NP Assembly             off-white parts, dark outlines, white background
  NP Assembly - Active    the same look in orange, for the piece being placed
  NP Assembly - Fittings  flat dark grey, no edges, for screws and hardware

Highlight  shows the selected pieces in orange and puts the viewport in
           NP Assembly. Rhino ignores per-object display modes on block
           instances, so the tool adds a plain copy of each piece's solids on
           the layer "NP-Assembly - Highlight", gives that copy the orange
           mode, and hides the original. Nothing in the blocks or on the
           production layers changes. Any piece highlighted before is
           restored first.
Clear      deletes the orange copies and shows the originals again. If a copy
           was moved while it was orange, the original is moved to match.
Capture    saves the viewport in NP Assembly at 2-3x scale as a PNG in an
           "Assembly Steps" folder next to the model, numbered per step. For
           the picture, visible fittings (block instances on the fittings
           layers) are swapped for grey copies the same way, then put back. It
           also saves a Rhino Snapshot "Assembly step NN" (positions, visibility,
           view) and records which pieces were orange, so the step can be
           brought back and captured again.
Restore    brings a step back: restores its snapshot and its highlight.
Re-capture replays every step snapshot into fresh PNGs, for when the
           assembly changes.

Both modes are imported from the team folder the first time they are needed.
"""

import json
import os
import re

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
MODES_FOLDER = os.path.join(_INSTALL_ROOT, "templates", "display_modes")

TITLE = "NP Assembly Steps"
BASE_MODE = "NP Assembly"
ACTIVE_MODE = "NP Assembly - Active"
FITTINGS_MODE = "NP Assembly - Fittings"
FITTING_LAYERS = ("NP-Fittings", "08_fittings")   # instances here turn grey in captures
ORANGE = (232, 128, 58)                      # same orange as the Active mode
EDGE_GREY = (40, 40, 40)                     # edge colour of both modes
HIGHLIGHT_LAYER = "NP-Assembly - Highlight"  # the orange copies; grey so their edges match
ARROW_LAYER = "NP-Assembly - Arrows"         # symbols from 21 - Assembly Symbols; grey = outline colour
CAPTURE_FOLDER = "Assembly Steps"

SOURCE_KEY = "np_assembly_source"            # user string: id of the hidden original
ANCHOR_KEY = "np_assembly_anchor"            # user string: copy centre at highlight time
ROLE_KEY = "np_assembly_role"                # user string: "highlight" or "fitting"
ROLE_HIGHLIGHT = "highlight"
ROLE_FITTING = "fitting"

STEP_SNAPSHOT = "Assembly step {:02d}"       # snapshot saved per captured step
STEP_PATTERN = re.compile(r"^Assembly step (\d+)$", re.IGNORECASE)
DOC_SECTION = "NP-Assembly"                  # document user text: step -> highlighted ids

HIGHLIGHT_LABEL = "Highlight selected piece"
CLEAR_LABEL = "Clear highlight"
CAPTURE_LABEL = "Capture step"
RESTORE_LABEL = "Restore step..."
RECAPTURE_LABEL = "Re-capture all steps"

DEFAULTS_FILENAME = "assembly_steps_defaults.json"
FALLBACK = {"scale": 3}

SKIP_TYPES = (Rhino.DocObjects.ObjectType.Curve, Rhino.DocObjects.ObjectType.Point,
              Rhino.DocObjects.ObjectType.PointSet, Rhino.DocObjects.ObjectType.Annotation,
              Rhino.DocObjects.ObjectType.TextDot, Rhino.DocObjects.ObjectType.Light)


# --- choice handed over by the NP Menu window --------------------------------

def take_menu_choice(valid_choices):
    import time
    path = os.path.join(_INSTALL_ROOT, "_user_data", "np_menu_choice.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except Exception:
        data = None
    try:
        os.remove(path)
    except Exception:
        pass
    if not isinstance(data, dict):
        return None
    if data.get("script") != os.path.basename(__file__):
        return None
    if time.time() - float(data.get("time", 0)) > 120:
        return None
    choice = data.get("choice")
    return choice if choice in valid_choices else None


def menu_items():
    """Choices offered by the list dialog and by the NP Menu drawer."""
    return [HIGHLIGHT_LABEL, CLEAR_LABEL, CAPTURE_LABEL, RESTORE_LABEL, RECAPTURE_LABEL]


# --- defaults -----------------------------------------------------------------

def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    data = dict(FALLBACK)
    try:
        with open(defaults_path(), "r") as handle:
            saved = json.load(handle)
        data["scale"] = int(saved.get("scale", data["scale"]))
    except Exception:
        pass
    return data


def save_defaults(data):
    folder = os.path.dirname(defaults_path())
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump(data, handle)
    except Exception:
        pass


# --- display modes ------------------------------------------------------------

def find_mode(name):
    for mode in Rhino.Display.DisplayModeDescription.GetDisplayModes():
        if mode.EnglishName == name:
            return mode
    return None


def ensure_mode(name):
    """The display mode called `name`, importing it from the team folder if missing."""
    mode = find_mode(name)
    if mode is not None:
        return mode
    path = os.path.join(MODES_FOLDER, name + ".ini")
    if not os.path.isfile(path):
        rs.MessageBox("Display mode '{}' is not installed and {} is missing.\n\n"
                      "Run Force Update, or import it with 19 - Display Modes."
                      .format(name, path), 0, TITLE)
        return None
    mode = import_mode_file(path)
    if mode is None:
        rs.MessageBox("Could not import display mode '{}'.".format(name), 0, TITLE)
        return None
    print("Imported display mode '{}'.".format(name))
    return mode


def viewport_to_base_mode(base):
    view = sc.doc.Views.ActiveView
    if view is None or base is None:
        return
    if view.ActiveViewport.DisplayMode.Id != base.Id:
        view.ActiveViewport.DisplayMode = base
        view.Redraw()


def ensure_layer(name, color):
    if not rs.IsLayer(name):
        rs.AddLayer(name, color)
    return sc.doc.Layers.FindByFullPath(name, -1)


# --- highlight copies ---------------------------------------------------------

def highlight_copies(role=ROLE_HIGHLIGHT):
    """The styled copies in the document, grouped by the id of their original.
    `role` picks the orange highlights (default), the grey fittings, or None for all."""
    groups = {}
    for obj in sc.doc.Objects:
        source = obj.Attributes.GetUserString(SOURCE_KEY)
        if not source:
            continue
        if role is not None and (obj.Attributes.GetUserString(ROLE_KEY) or ROLE_HIGHLIGHT) != role:
            continue
        groups.setdefault(source, []).append(obj)
    return groups


def source_pieces(obj):
    """(geometry, attributes) pairs for the solids that make up `obj`, in world space."""
    if isinstance(obj, Rhino.DocObjects.InstanceObject):
        pieces, attrs, xforms = obj.Explode(True)
        result = []
        for piece, piece_attrs, xform in zip(pieces, attrs, xforms):
            if piece.ObjectType in SKIP_TYPES:
                continue
            geometry = piece.Geometry.Duplicate()
            geometry.Transform(xform)
            result.append(geometry)
        return result
    if obj.ObjectType in SKIP_TYPES:
        return []
    return [obj.Geometry.Duplicate()]


def set_override(obj_id, mode):
    obj = sc.doc.Objects.FindId(obj_id)
    if obj is None:
        return False
    attrs = obj.Attributes.Duplicate()
    # SetDisplayModeOverride often returns False although the override is stored
    # (Rhino 8 Mac), so the stored state is what counts, not the return value.
    attrs.SetDisplayModeOverride(mode)
    if not attrs.HasDisplayModeOverride(System.Guid.Empty):
        return False
    return sc.doc.Objects.ModifyAttributes(obj, attrs, True)


def centre_of(objs):
    box = Rhino.Geometry.BoundingBox.Empty
    for obj in objs:
        box.Union(obj.Geometry.GetBoundingBox(True))
    return box.Center if box.IsValid else None


def add_highlight(obj, active, layer_index, role=ROLE_HIGHLIGHT):
    """Adds copies of `obj`'s solids in the display mode `active` and hides `obj`.
    Returns the copy count."""
    geometries = source_pieces(obj)
    if not geometries:
        return 0
    added = []
    for geometry in geometries:
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = layer_index
        attrs.SetUserString(SOURCE_KEY, str(obj.Id))
        attrs.SetUserString(ROLE_KEY, role)
        new_id = sc.doc.Objects.Add(geometry, attrs)
        if new_id != System.Guid.Empty:
            added.append(new_id)
    anchor = centre_of([sc.doc.Objects.FindId(i) for i in added])
    for new_id in added:
        set_override(new_id, active)
        if anchor is not None:
            copy = sc.doc.Objects.FindId(new_id)
            copy_attrs = copy.Attributes.Duplicate()
            copy_attrs.SetUserString(ANCHOR_KEY, "{},{},{}".format(anchor.X, anchor.Y, anchor.Z))
            sc.doc.Objects.ModifyAttributes(copy, copy_attrs, True)
    sc.doc.Objects.Hide(obj.Id, True)
    return len(added)


def restore_highlight(source_id_text, copies):
    """Deletes the copies of one original and shows it again, moved if the copies were."""
    try:
        source_id = System.Guid(source_id_text)
    except Exception:
        source_id = System.Guid.Empty
    delta = None
    anchor_text = copies[0].Attributes.GetUserString(ANCHOR_KEY)
    now = centre_of(copies)
    if anchor_text and now is not None:
        try:
            x, y, z = [float(v) for v in anchor_text.split(",")]
            delta = now - Rhino.Geometry.Point3d(x, y, z)
        except Exception:
            delta = None
    for copy in copies:
        sc.doc.Objects.Delete(copy.Id, True)
    original = sc.doc.Objects.FindId(source_id) if source_id != System.Guid.Empty else None
    if original is None:
        return False
    sc.doc.Objects.Show(source_id, True)
    if delta is not None and delta.Length > sc.doc.ModelAbsoluteTolerance:
        sc.doc.Objects.Transform(source_id, Rhino.Geometry.Transform.Translation(delta), True)
    return True


def current_sources():
    """Ids (as text) of the pieces that are highlighted right now."""
    return sorted(highlight_copies().keys())


def apply_highlight(source_ids, active, keep=()):
    """Highlights `source_ids` (Guids), restoring any other highlight first.
    Returns (highlighted, restored, missing)."""
    wanted = set(str(i) for i in source_ids)
    keep = set(keep) | wanted
    restored = 0
    for source, copies in highlight_copies().items():
        if source not in keep:
            restore_highlight(source, copies)
            restored += 1
    layer_index = ensure_layer(HIGHLIGHT_LAYER, EDGE_GREY)
    ensure_layer(ARROW_LAYER, EDGE_GREY)
    already = set(highlight_copies().keys())
    done = 0
    missing = []
    for source_id in source_ids:
        if str(source_id) in already:
            continue
        obj = sc.doc.Objects.FindId(source_id)
        if obj is None:
            missing.append(str(source_id))
        elif add_highlight(obj, active, layer_index):
            done += 1
    return done, restored, missing


def clear_all(role=None):
    """Restores every styled piece (of one role, or all); returns how many."""
    groups = highlight_copies(role)
    for source, copies in groups.items():
        restore_highlight(source, copies)
    return len(groups)


# --- fittings -----------------------------------------------------------------

def fitting_instances():
    """Visible block instances on the fittings layers that are not styled copies."""
    found = []
    for obj in sc.doc.Objects:
        if not isinstance(obj, Rhino.DocObjects.InstanceObject) or obj.IsHidden:
            continue
        if obj.Attributes.GetUserString(SOURCE_KEY):
            continue
        layer = sc.doc.Layers[obj.Attributes.LayerIndex]
        if layer.Name in FITTING_LAYERS:
            found.append(obj)
    return found


def with_grey_fittings(action):
    """Runs action() while the visible fittings are grey copies (mode NP Assembly -
    Fittings) and their originals hidden; always puts the originals back.
    Without the fittings mode, action() simply runs."""
    mode = find_mode(FITTINGS_MODE)
    if mode is None:
        path = os.path.join(MODES_FOLDER, FITTINGS_MODE + ".ini")
        mode = import_mode_file(path) if os.path.isfile(path) else None
    if mode is None:
        return action()
    layer_index = ensure_layer(HIGHLIGHT_LAYER, EDGE_GREY)
    rs.EnableRedraw(False)
    try:
        for obj in fitting_instances():
            add_highlight(obj, mode, layer_index, ROLE_FITTING)
    finally:
        rs.EnableRedraw(True)
    try:
        return action()
    finally:
        rs.EnableRedraw(False)
        try:
            clear_all(ROLE_FITTING)
        finally:
            rs.EnableRedraw(True)


# --- step snapshots -----------------------------------------------------------

def snapshot_names():
    try:
        return [n for n in sc.doc.Snapshots.Names if n]
    except Exception:
        return []


def run_snapshot_command(action, name):
    quoted = name.replace('"', '""')
    ok = Rhino.RhinoApp.RunScript('_-Snapshots _{} "{}" _Enter _Enter'.format(action, quoted), False)
    Rhino.RhinoApp.Wait()
    return bool(ok)


def save_snapshot(name):
    if name in snapshot_names():
        run_snapshot_command("Delete", name)
    run_snapshot_command("Save", name)
    return name in snapshot_names()


def restore_snapshot(name):
    if name not in snapshot_names():
        return False
    return run_snapshot_command("Restore", name)


def step_name(step):
    return STEP_SNAPSHOT.format(step)


def step_snapshots():
    """[(step number, snapshot name)] for the step snapshots in this file, in order."""
    found = []
    for name in snapshot_names():
        match = STEP_PATTERN.match(name)
        if match:
            found.append((int(match.group(1)), name))
    found.sort()
    return found


def record_step(name, source_ids):
    sc.doc.Strings.SetString(DOC_SECTION, name, ",".join(str(i) for i in source_ids))


def recorded_sources(name):
    text = sc.doc.Strings.GetValue(DOC_SECTION, name) or ""
    ids = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(System.Guid(part))
        except Exception:
            pass
    return ids


def highlight():
    base = ensure_mode(BASE_MODE)
    active = ensure_mode(ACTIVE_MODE)
    if base is None or active is None:
        return
    ids = rs.GetObjects("Select the piece(s) to highlight", preselect=True)
    if not ids:
        return
    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Highlight assembly piece")
    try:
        # pieces that are already orange stay; everything else is restored first
        keep = set()
        sources = []
        for obj_id in ids:
            obj = sc.doc.Objects.FindId(obj_id)
            source = obj.Attributes.GetUserString(SOURCE_KEY) if obj else None
            if source:
                keep.add(source)
            elif obj is not None:
                sources.append(obj_id)
        done, cleared, _ = apply_highlight(sources, active, keep)
        viewport_to_base_mode(base)
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)
    rs.UnselectAllObjects()
    sc.doc.Views.Redraw()
    print("Highlighted {} piece(s) in orange; {} earlier highlight(s) restored. "
          "Add arrows and glue with 21 - Assembly Symbols. Clear highlight puts the originals back.".format(
              done, cleared))


def clear():
    if not highlight_copies():
        print("Nothing is highlighted.")
        return
    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Clear assembly highlight")
    try:
        count = clear_all()
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)
    sc.doc.Views.Redraw()
    print("Cleared {} highlight(s); the original pieces are shown again.".format(count))


# --- capture ------------------------------------------------------------------

def capture_folder():
    path = sc.doc.Path
    if path:
        return os.path.join(os.path.dirname(path), CAPTURE_FOLDER)
    folder = rs.BrowseForFolder(message="The model is not saved yet. Folder for the step images")
    return folder or None


def doc_stem():
    path = sc.doc.Path
    if not path:
        return "Assembly"
    return os.path.splitext(os.path.basename(path))[0]


def next_step_number(folder, stem):
    pattern = re.compile(r"^" + re.escape(stem) + r" step (\d+)\.png$", re.IGNORECASE)
    highest = 0
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            match = pattern.match(name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


# surface and mesh edges keep their pixel width in a scaled capture; curves do scale
THICKNESS_KEYS = ("EdgeThickness", "NakedEdgeThickness", "MeshEdgeThickness")


def import_mode_file(path):
    mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    if mode_id is None or mode_id == System.Guid.Empty:
        return None
    return Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)


def scaled_mode_text(path, scale):
    """The .ini text with every line thickness multiplied by `scale`."""
    with open(path, "r", encoding="utf-8-sig") as handle:
        lines = handle.read().splitlines()
    out = []
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key in THICKNESS_KEYS:
            try:
                line = "{}={}".format(key, int(round(float(value) * scale)))
            except ValueError:
                pass
        out.append(line)
    return "\r\n".join(out) + "\r\n"


def with_scaled_line_weights(scale, action):
    """Runs action() while both modes carry line weights multiplied by `scale`.

    ViewCapture keeps edges at their pixel thickness whatever the capture size
    (ScaleScreenItems does not touch surface edges), so a 3x capture would get
    hairlines. The modes are re-imported with scaled thicknesses (same ids, so
    they update in place) and restored from the team files afterwards.
    """
    files = sorted(os.path.join(MODES_FOLDER, f) for f in os.listdir(MODES_FOLDER)
                   if f.startswith(BASE_MODE) and f.lower().endswith(".ini")) if os.path.isdir(MODES_FOLDER) else []
    if scale == 1 or not files:
        return action()
    temp_folder = os.path.join(_INSTALL_ROOT, "_temp")
    if not os.path.isdir(temp_folder):
        os.makedirs(temp_folder)
    try:
        for path in files:
            temp_path = os.path.join(temp_folder, os.path.basename(path))
            with open(temp_path, "w", encoding="utf-8-sig", newline="") as handle:
                handle.write(scaled_mode_text(path, scale))
            import_mode_file(temp_path)
        return action()
    finally:
        for path in files:
            import_mode_file(path)
        sc.doc.Views.Redraw()


def capture_view(view, scale):
    """Captures `view` at `scale` times its pixel size; returns (bitmap, width, height)."""
    size = view.ActiveViewport.Size
    vc = Rhino.Display.ViewCapture()
    vc.Width = size.Width * scale
    vc.Height = size.Height * scale
    vc.ScaleScreenItems = True
    vc.DrawAxes = False
    vc.DrawGrid = False
    vc.DrawGridAxes = False
    vc.TransparentBackground = False

    def grab():
        sc.doc.Views.Redraw()
        Rhino.RhinoApp.Wait()
        # the first captures after a display mode change can show the old state
        for _ in range(2):
            warm_up = vc.CaptureToBitmap(view)
            if warm_up is not None:
                warm_up.Dispose()
            Rhino.RhinoApp.Wait()
        return vc.CaptureToBitmap(view)

    return with_scaled_line_weights(scale, grab), vc.Width, vc.Height


def save_image(bitmap, folder, stem, step):
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, "{} step {:02d}.png".format(stem, step))
    bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png)
    return path


def snapshot_step(step, active):
    """Saves the step snapshot in the clean state (no orange copies, originals
    where the copies are) and records the highlighted pieces, then puts the
    highlight back. Returns the source ids."""
    sources = [System.Guid(s) for s in current_sources()]
    name = step_name(step)
    clear_all()
    saved = save_snapshot(name)
    record_step(name, sources)
    if sources:
        apply_highlight(sources, active)
    return sources, saved


def capture():
    base = ensure_mode(BASE_MODE)
    active = ensure_mode(ACTIVE_MODE)
    if base is None or active is None:
        return
    folder = capture_folder()
    if not folder:
        return
    stem = doc_stem()
    defaults = load_defaults()
    step = rs.GetInteger("Step number", next_step_number(folder, stem), 1)
    if step is None:
        return
    scale = rs.GetInteger("Capture scale (times the viewport size)", defaults["scale"], 1, 6)
    if scale is None:
        return
    save_defaults({"scale": int(scale)})

    view = sc.doc.Views.ActiveView
    viewport_to_base_mode(base)
    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Capture assembly step")
    try:
        sources, saved = snapshot_step(step, active)
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)
    bitmap, width, height = with_grey_fittings(lambda: capture_view(view, int(scale)))
    if bitmap is None:
        rs.MessageBox("The viewport capture failed.", 0, TITLE)
        return
    path = save_image(bitmap, folder, stem, step)
    print("Saved step {} ({}x{} px): {}".format(step, width, height, path))
    print("Snapshot '{}' {} with {} highlighted piece(s); Restore step brings it back, "
          "Re-capture all steps redoes every image.".format(
              step_name(step), "saved" if saved else "NOT saved", len(sources)))


def bring_back_step(name, base, active):
    """Restores one step snapshot and its highlight. Returns (ok, missing ids)."""
    clear_all()
    if not restore_snapshot(name):
        return False, []
    sources = recorded_sources(name)
    missing = []
    if sources:
        _, _, missing = apply_highlight(sources, active)
    viewport_to_base_mode(base)
    return True, missing


def restore_step():
    base = ensure_mode(BASE_MODE)
    active = ensure_mode(ACTIVE_MODE)
    if base is None or active is None:
        return
    steps = step_snapshots()
    if not steps:
        rs.MessageBox("This file has no step snapshots yet. Capture step saves one per step.", 0, TITLE)
        return
    names = [name for _, name in steps]
    choice = rs.ListBox(names, "Step to bring back", TITLE, names[-1])
    if not choice:
        return
    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Restore assembly step")
    try:
        ok, missing = bring_back_step(choice, base, active)
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)
    sc.doc.Views.Redraw()
    if not ok:
        rs.MessageBox("Could not restore snapshot '{}'.".format(choice), 0, TITLE)
        return
    note = " {} highlighted piece(s) no longer exist.".format(len(missing)) if missing else ""
    print("Restored '{}' with its highlight.{} Capture step with the same number updates its image.".format(choice, note))


def recapture_all():
    base = ensure_mode(BASE_MODE)
    active = ensure_mode(ACTIVE_MODE)
    if base is None or active is None:
        return
    steps = step_snapshots()
    if not steps:
        rs.MessageBox("This file has no step snapshots yet. Capture step saves one per step.", 0, TITLE)
        return
    folder = capture_folder()
    if not folder:
        return
    stem = doc_stem()
    defaults = load_defaults()
    scale = rs.GetInteger("Capture scale (times the viewport size)", defaults["scale"], 1, 6)
    if scale is None:
        return
    save_defaults({"scale": int(scale)})
    view = sc.doc.Views.ActiveView
    done = 0
    problems = []
    undo = sc.doc.BeginUndoRecord("Re-capture assembly steps")
    try:
        for step, name in steps:
            ok, missing = bring_back_step(name, base, active)
            if not ok:
                problems.append("{}: snapshot could not be restored".format(name))
                continue
            if missing:
                problems.append("{}: {} highlighted piece(s) no longer exist".format(name, len(missing)))
            bitmap, width, height = with_grey_fittings(lambda: capture_view(view, int(scale)))
            if bitmap is None:
                problems.append("{}: capture failed".format(name))
                continue
            path = save_image(bitmap, folder, stem, step)
            done += 1
            print("Re-captured step {}: {}".format(step, path))
        clear_all()
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    summary = "Re-captured {} of {} step(s) into {}".format(done, len(steps), folder)
    if problems:
        summary += "\n\n" + "\n".join(problems)
    print(summary)
    rs.MessageBox(summary, 0, TITLE)


def main():
    items = menu_items()
    choice = take_menu_choice(items)
    if not choice:
        choice = rs.ListBox(items, "Assembly instruction steps", TITLE, items[0])
    if not choice:
        return
    if choice == HIGHLIGHT_LABEL:
        highlight()
    elif choice == CLEAR_LABEL:
        clear()
    elif choice == CAPTURE_LABEL:
        capture()
    elif choice == RESTORE_LABEL:
        restore_step()
    elif choice == RECAPTURE_LABEL:
        recapture_all()


if __name__ == "__main__":
    main()
