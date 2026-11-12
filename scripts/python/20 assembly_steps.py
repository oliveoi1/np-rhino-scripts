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
import math
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
SYMBOL_LAYER_PREFIX = "NP-Assembly - "       # every layer of 21's symbols (Arrows, Glue, Icons, Blanket)
CAPTURE_FOLDER = "Assembly Steps"

SOURCE_KEY = "np_assembly_source"            # user string: id of the hidden original
ANCHOR_KEY = "np_assembly_anchor"            # user string: copy centre at highlight time
FRAME_KEY = "np_assembly_frame"              # user string: three vertex indices + positions at highlight time
ROLE_KEY = "np_assembly_role"                # user string: "highlight" or "fitting"
ROLE_HIGHLIGHT = "highlight"
ROLE_FITTING = "fitting"

STEP_SNAPSHOT = "Assembly step {:02d}"       # snapshot saved per captured step
STEP_PATTERN = re.compile(r"^Assembly step (\d+)$", re.IGNORECASE)
DOC_SECTION = "NP-Assembly"                  # document user text: step -> highlighted ids
SYMBOLS_SUFFIX = " symbols"                  # "<step name> symbols" -> ids of the symbols visible at capture
CPLANE_KEY = "cplane"                        # the construction plane every step shares: origin;x axis;y axis

HIGHLIGHT_LABEL = "Highlight selected piece"
CLEAR_LABEL = "Clear highlight"
CAPTURE_LABEL = "Capture step"
RESTORE_LABEL = "Restore step..."
RECAPTURE_LABEL = "Re-capture all steps"
COPY_STAGE_LABEL = "Copy stage sideways"
SHOW_SYMBOLS_LABEL = "Show all symbols"
SET_CPLANE_LABEL = "Use current CPlane for all steps"

DEFAULTS_FILENAME = "assembly_steps_defaults.json"
FALLBACK = {"scale": 3, "stage_distance": 0.0, "stage_direction": "Right", "stage_symbols": "Leave"}

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
    return [HIGHLIGHT_LABEL, CLEAR_LABEL, CAPTURE_LABEL, RESTORE_LABEL, RECAPTURE_LABEL,
            COPY_STAGE_LABEL, SHOW_SYMBOLS_LABEL, SET_CPLANE_LABEL]


# --- defaults -----------------------------------------------------------------

def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    data = dict(FALLBACK)
    try:
        with open(defaults_path(), "r") as handle:
            saved = json.load(handle)
        for key in FALLBACK:
            if key in saved:
                data[key] = saved[key]
        data["scale"] = int(data["scale"])
        data["stage_distance"] = float(data["stage_distance"])
    except Exception:
        pass
    return data


def save_defaults(data):
    """Merges `data` into the remembered defaults."""
    merged = load_defaults()
    merged.update(data)
    folder = os.path.dirname(defaults_path())
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump(merged, handle)
    except Exception:
        pass


# --- display modes ------------------------------------------------------------

# --- display mode files ---------------------------------------------------------
#
# Team display modes travel as .ini files, and importing them has two known traps:
#
# * Encoding. Rhino for Mac exports UTF-8 with a byte order mark and reads anything.
#   A reader that takes the mark for text no longer recognises the first line, the
#   [DisplayMode\<id>] header. Team files are kept as plain text without the mark.
# * Script engine. In Rhino 8 for Windows before 8.13, ImportFromFile did nothing
#   when called from the Python 3 engine (McNeel RH-83960: the engine's open undo
#   record got in the way); from IronPython it worked.
#
# import_mode_file therefore tries the file as saved, re-saved in other encodings,
# through a tiny IronPython script, and with the script's undo record closed, in
# that order, and says which one worked.

def read_mode_file(path):
    """Text of a display mode .ini, whichever encoding it was saved in."""
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def mode_file_bytes(text, encoding):
    if encoding == "UTF-16":
        return b"\xff\xfe" + text.encode("utf-16-le")
    if encoding == "UTF-8 with a byte order mark":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    return text.encode("utf-8")          # "plain text": no byte order mark


def portable_mode_bytes(text):
    """Bytes for a team file: plain text when it is all ASCII (every Rhino reads
    that), UTF-16 when a name has other characters."""
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return mode_file_bytes(text, "UTF-16")
    return mode_file_bytes(text, "plain text")


def mode_file_id(path):
    """The id in the header line of a display mode file, or None."""
    import re as _re
    try:
        match = _re.search(r"\[DisplayMode\\([0-9a-fA-F-]{36})\]", read_mode_file(path))
        return System.Guid(match.group(1)) if match else None
    except Exception:
        return None


def imported_mode(path, returned_id=None):
    """The display mode this Rhino has for the file `path`: looked up by the id
    the import returned, else by the id in the file. None when it is not there."""
    for mode_id in (returned_id, mode_file_id(path)):
        if mode_id is None or mode_id == System.Guid.Empty:
            continue
        mode = Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)
        if mode is not None:
            return mode
    return None


def import_direct(path):
    try:
        mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    except Exception:
        mode_id = None
    return imported_mode(path, mode_id)


def import_reencoded(path):
    import shutil
    import tempfile
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        text = read_mode_file(path)
    except Exception:
        return None
    folder = tempfile.mkdtemp(prefix="np-mode-")
    try:
        for encoding in ("plain text", "UTF-16", "UTF-8 with a byte order mark"):
            data = mode_file_bytes(text, encoding)
            if data == raw:
                continue
            temp_path = os.path.join(folder, os.path.basename(path))
            with open(temp_path, "wb") as handle:
                handle.write(data)
            mode = import_direct(temp_path)
            if mode is not None:
                return mode
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return None


def import_with_ironpython(path):
    """Runs the import in the IronPython engine, where it also works in the Rhino 8
    builds whose Python 3 engine cannot do it."""
    import shutil
    import tempfile
    folder = tempfile.mkdtemp(prefix="np-mode-")
    try:
        script = os.path.join(folder, "np_import_mode.py")
        literal = path.replace("\\", "\\\\").replace('"', '\\"')
        with open(script, "wb") as handle:
            handle.write(('# -*- coding: utf-8 -*-\nimport Rhino\n'
                          'Rhino.Display.DisplayModeDescription.ImportFromFile(u"{}")\n'
                          .format(literal)).encode("utf-8"))
        Rhino.RhinoApp.RunScript('_-RunPythonScript "{}"'.format(script), False)
        Rhino.RhinoApp.Wait()
    except Exception:
        pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return imported_mode(path)


def import_outside_undo(path):
    """Closes the undo record the script engine opened, then imports."""
    try:
        serial = sc.doc.CurrentUndoRecordSerialNumber
        if serial:
            sc.doc.EndUndoRecord(serial)
    except Exception:
        pass
    return import_direct(path)


IMPORT_ROUTES = [
    ("as saved", import_direct),
    ("re-saved in another encoding", import_reencoded),
    ("through IronPython", import_with_ironpython),
    ("with the script's undo record closed", import_outside_undo),
]


def import_mode_file(path):
    """Imports a display mode .ini; returns the DisplayModeDescription or None."""
    for index, (label, route) in enumerate(IMPORT_ROUTES):
        mode = route(path)
        if mode is not None:
            if index:
                print("Display mode file '{}' was imported {}.".format(os.path.basename(path), label))
            return mode
    return None


def mode_import_report(path):
    """Details for the message when a display mode file will not import."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        start = " ".join("{:02x}".format(b) for b in raw[:4])
        detail = "{} bytes, starts with {}".format(len(raw), start)
    except Exception as ex:
        detail = "could not be read: {}".format(ex)
    system = "Windows" if Rhino.Runtime.HostUtils.RunningOnWindows else "Mac"
    return ("File: {}\n({})\nRhino {} on {}.\n\n"
            "Tried it as saved, in other encodings, through IronPython and outside the undo record.\n"
            "Rhino 8 for Windows older than 8.13 has a bug here, so update Rhino first.\n"
            "Then run Display Modes > Check display mode import and send the report.").format(
                path, detail, Rhino.RhinoApp.Version, system)


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
        rs.MessageBox("Could not import display mode '{}'.\n\n{}".format(name, mode_import_report(path)), 0, TITLE)
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


def frame_candidates(geometry):
    """Points that move rigidly with `geometry`, in an order that survives transforms."""
    if isinstance(geometry, Rhino.Geometry.Brep):
        return [v.Location for v in geometry.Vertices]
    if isinstance(geometry, Rhino.Geometry.Extrusion):
        brep = geometry.ToBrep(False)
        return [v.Location for v in brep.Vertices] if brep is not None else []
    if isinstance(geometry, Rhino.Geometry.Mesh):
        return [Rhino.Geometry.Point3d(v) for v in geometry.Vertices]
    return []


def pick_frame(points):
    """Indices of three well-spread, non-collinear points, or None."""
    if len(points) < 3:
        return None
    tol = max(sc.doc.ModelAbsoluteTolerance, 1e-6)
    first = 0
    second = max(range(len(points)), key=lambda k: points[k].DistanceTo(points[first]))
    if points[second].DistanceTo(points[first]) < tol:
        return None
    line = Rhino.Geometry.Line(points[first], points[second])
    third = max(range(len(points)), key=lambda k: line.DistanceTo(points[k], True))
    if line.DistanceTo(points[third], True) < tol:
        return None
    return first, second, third


def frame_text(geometry):
    """Encodes three reference points of `geometry` so the move + rotation the
    copy gets later can be rebuilt: "i,j,k;x,y,z;x,y,z;x,y,z"."""
    points = frame_candidates(geometry)
    picked = pick_frame(points)
    if picked is None:
        return None
    parts = [",".join(str(i) for i in picked)]
    for i in picked:
        parts.append("{!r},{!r},{!r}".format(points[i].X, points[i].Y, points[i].Z))
    return ";".join(parts)


def copy_transform(copy):
    """The rigid transform `copy` has had since it was highlighted, or None."""
    text = copy.Attributes.GetUserString(FRAME_KEY)
    if not text:
        return None
    try:
        parts = text.split(";")
        picked = [int(v) for v in parts[0].split(",")]
        then = [Rhino.Geometry.Point3d(*[float(v) for v in part.split(",")]) for part in parts[1:4]]
    except Exception:
        return None
    points = frame_candidates(copy.Geometry)
    if len(picked) != 3 or len(then) != 3 or any(i >= len(points) for i in picked):
        return None
    now = [points[i] for i in picked]
    before = Rhino.Geometry.Plane(then[0], then[1], then[2])
    after = Rhino.Geometry.Plane(now[0], now[1], now[2])
    if not before.IsValid or not after.IsValid:
        return None
    return Rhino.Geometry.Transform.PlaneToPlane(before, after)


def nearly_identity(xform):
    tol = sc.doc.ModelAbsoluteTolerance
    for row in range(3):
        for col in range(4):
            expected = 1.0 if row == col else 0.0
            limit = tol if col == 3 else 1e-9
            if abs(xform[row, col] - expected) > limit:
                return False
    return True


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
        frame = frame_text(geometry)
        if frame:
            attrs.SetUserString(FRAME_KEY, frame)
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


def copies_transform(copies):
    """The move + rotation the copies of one original have had: rebuilt from the
    vertex frame of the first copy that has one, else from the centre shift
    (older highlights), else None."""
    for copy in copies:
        xform = copy_transform(copy)
        if xform is not None:
            return xform
    anchor_text = copies[0].Attributes.GetUserString(ANCHOR_KEY)
    now = centre_of(copies)
    if anchor_text and now is not None:
        try:
            x, y, z = [float(v) for v in anchor_text.split(",")]
            return Rhino.Geometry.Transform.Translation(now - Rhino.Geometry.Point3d(x, y, z))
        except Exception:
            return None
    return None


def restore_highlight(source_id_text, copies):
    """Deletes the copies of one original and shows it again, moved and rotated
    the way the copies were."""
    try:
        source_id = System.Guid(source_id_text)
    except Exception:
        source_id = System.Guid.Empty
    xform = copies_transform(copies)
    for copy in copies:
        sc.doc.Objects.Delete(copy.Id, True)
    original = sc.doc.Objects.FindId(source_id) if source_id != System.Guid.Empty else None
    if original is None:
        return False
    sc.doc.Objects.Show(source_id, True)
    if xform is not None and not nearly_identity(xform):
        sc.doc.Objects.Transform(source_id, xform, True)
    return True


def current_sources():
    """Ids (as text) of the pieces that are highlighted right now."""
    return sorted(highlight_copies().keys())


def drop_stale_copies(sources):
    """Deletes the orange copies of the pieces in `sources` (id texts) whose
    original is showing again. Rhino's own Snapshots panel and the Show command
    bring a hidden original back without knowing about its copies, which leaves
    both in the same place and the piece looking plain; the copies are then out
    of date, so the piece is highlighted afresh. Returns how many pieces."""
    dropped = 0
    for source, copies in highlight_copies().items():
        if source not in sources:
            continue
        try:
            original = sc.doc.Objects.FindId(System.Guid(source))
        except Exception:
            original = None
        if original is None or original.IsHidden:
            continue
        for copy in copies:
            sc.doc.Objects.Delete(copy.Id, True)
        dropped += 1
    return dropped


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
    drop_stale_copies(wanted)
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


# --- symbols (the objects 21 - Assembly Symbols makes) --------------------------

def is_symbol_layer(layer_index):
    layer = sc.doc.Layers.FindIndex(layer_index)
    if layer is None:
        return False
    return layer.Name.startswith(SYMBOL_LAYER_PREFIX) and layer.Name != HIGHLIGHT_LAYER


def symbol_objects():
    """Every object on a symbol layer, hidden ones included."""
    settings = Rhino.DocObjects.ObjectEnumeratorSettings()
    settings.HiddenObjects = True
    settings.IncludeLights = False
    settings.IncludeGrips = False
    return [obj for obj in sc.doc.Objects.GetObjectList(settings)
            if is_symbol_layer(obj.Attributes.LayerIndex)]


def visible_symbol_ids():
    return [obj.Id for obj in symbol_objects() if obj.Visible]


def set_symbol_visibility(visible_ids):
    """Shows the symbol objects in `visible_ids` and hides every other symbol
    object, so a step shows only its own arrows, glue and icons. Returns (shown, hidden)."""
    wanted = set(str(i) for i in visible_ids)
    shown = hidden = 0
    for obj in symbol_objects():
        if str(obj.Id) in wanted:
            if obj.IsHidden:
                sc.doc.Objects.Show(obj.Id, True)
                shown += 1
        elif not obj.IsHidden:
            sc.doc.Objects.Hide(obj.Id, True)
            hidden += 1
    return shown, hidden


def show_symbols():
    count = 0
    for obj in symbol_objects():
        if obj.IsHidden:
            sc.doc.Objects.Show(obj.Id, True)
            count += 1
    sc.doc.Views.Redraw()
    print("Showed {} hidden symbol object(s) on the NP-Assembly layers.".format(count))


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


def record_step(name, source_ids, symbol_ids=None):
    sc.doc.Strings.SetString(DOC_SECTION, name, ",".join(str(i) for i in source_ids))
    if symbol_ids is not None:
        sc.doc.Strings.SetString(DOC_SECTION, name + SYMBOLS_SUFFIX, ",".join(str(i) for i in symbol_ids))


def parse_ids(text):
    ids = []
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(System.Guid(part))
        except Exception:
            pass
    return ids


def recorded_sources(name):
    return parse_ids(sc.doc.Strings.GetValue(DOC_SECTION, name))


def recorded_symbols(name):
    """Ids of the symbols visible when the step was captured, or None for a step
    captured before symbols were tracked."""
    text = sc.doc.Strings.GetValue(DOC_SECTION, name + SYMBOLS_SUFFIX)
    if text is None:
        return None
    return parse_ids(text)


# --- shared construction plane ---------------------------------------------------
#
# A step snapshot keeps the viewport's construction plane with its view. A CPlane
# changed for one job (flipping a part, say) would otherwise stay in that step and
# every later one, so the view orbits differently from step to step. The file
# therefore remembers one plane; Capture step and Copy stage sideways put it back.

def stored_cplane():
    text = sc.doc.Strings.GetValue(DOC_SECTION, CPLANE_KEY)
    if not text:
        return None
    try:
        origin, x_axis, y_axis = [[float(v) for v in part.split(",")] for part in text.split(";")]
        plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(*origin),
                                     Rhino.Geometry.Vector3d(*x_axis), Rhino.Geometry.Vector3d(*y_axis))
    except Exception:
        return None
    return plane if plane.IsValid else None


def store_cplane(plane):
    parts = []
    for item in (plane.Origin, plane.XAxis, plane.YAxis):
        parts.append("{!r},{!r},{!r}".format(item.X, item.Y, item.Z))
    sc.doc.Strings.SetString(DOC_SECTION, CPLANE_KEY, ";".join(parts))


def same_orientation(a, b):
    return a.XAxis.IsParallelTo(b.XAxis, 1e-6) == 1 and a.YAxis.IsParallelTo(b.YAxis, 1e-6) == 1


def shared_cplane(vp, shift=None):
    """Puts the file's shared construction plane on the viewport `vp` and returns
    (plane, note). The first call in a file records the viewport's current plane.
    Only the orientation is enforced: a plane that already has it keeps its
    origin. `shift` moves the plane with a copied stage."""
    current = vp.ConstructionPlane()
    stored = stored_cplane()
    note = ""
    if stored is None:
        plane = current
        note = "This viewport's CPlane is now the one every step uses."
    elif same_orientation(current, stored):
        plane = current
    else:
        plane = stored
        note = "CPlane put back to the one the steps share."
    if shift is not None:
        plane = Rhino.Geometry.Plane(plane.Origin + shift, plane.XAxis, plane.YAxis)
    vp.SetConstructionPlane(plane)
    store_cplane(plane)
    return plane, note


def set_shared_cplane():
    vp = sc.doc.Views.ActiveView.ActiveViewport
    store_cplane(vp.ConstructionPlane())
    count = len(step_snapshots())
    note = ""
    if count:
        note = (" The {} step(s) already captured keep the plane they were saved with; "
                "Re-capture all steps updates them.".format(count))
    print("The CPlane of viewport '{}' is now the one every assembly step uses.{}".format(vp.Name, note))


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
THICKNESS_PROPERTIES = ("SurfaceEdgeThickness", "SurfaceNakedEdgeThickness", "MeshEdgeThickness")


def assembly_modes():
    """The NP Assembly display modes this Rhino has (base look and its colours)."""
    return [mode for mode in Rhino.Display.DisplayModeDescription.GetDisplayModes()
            if mode.EnglishName.startswith(BASE_MODE)]


def with_scaled_line_weights(scale, action):
    """Runs action() while the assembly modes carry edge weights multiplied by `scale`.

    ViewCapture keeps edges at their pixel thickness whatever the capture size
    (ScaleScreenItems does not touch surface edges), so a 3x capture would get
    hairlines. The thickness is changed on the modes themselves for the capture
    and put back afterwards; no mode file is imported while a mode is in use.
    """
    changed = []
    try:
        if scale != 1:
            for mode in assembly_modes():
                attrs = mode.DisplayAttributes
                before = {}
                for name in THICKNESS_PROPERTIES:
                    try:
                        value = getattr(attrs, name)
                        setattr(attrs, name, int(round(value * scale)))
                        before[name] = value
                    except Exception:
                        pass
                if before:
                    changed.append((mode, before))
                    Rhino.Display.DisplayModeDescription.UpdateDisplayMode(mode)
        return action()
    finally:
        for mode, before in changed:
            attrs = mode.DisplayAttributes
            for name, value in before.items():
                try:
                    setattr(attrs, name, value)
                except Exception:
                    pass
            Rhino.Display.DisplayModeDescription.UpdateDisplayMode(mode)
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
    symbols = visible_symbol_ids()
    name = step_name(step)
    clear_all()
    saved = save_snapshot(name)
    record_step(name, sources, symbols)
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
    _, cplane_note = shared_cplane(view.ActiveViewport)
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
    if cplane_note:
        print(cplane_note)


def resave_step_snapshot(name, active):
    """Saves the step's snapshot again from the current state (for a changed
    CPlane) without touching what the step records: highlight off, save, highlight on."""
    sources = [System.Guid(s) for s in current_sources()]
    clear_all()
    saved = save_snapshot(name)
    if sources:
        apply_highlight(sources, active)
    return saved


def bring_back_step(name, base, active):
    """Restores one step snapshot and its highlight. Returns (ok, missing ids)."""
    clear_all()
    if not restore_snapshot(name):
        return False, []
    symbols = recorded_symbols(name)
    if symbols is not None:
        set_symbol_visibility(symbols)
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
    print("Restored '{}' with its highlight and its symbols (other steps' symbols are hidden; "
          "Show all symbols brings them back).{} Capture step with the same number updates its image.".format(choice, note))


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
    symbols_before = visible_symbol_ids()
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
            shared = stored_cplane()
            if shared is not None and not same_orientation(view.ActiveViewport.ConstructionPlane(), shared):
                # origin stays with the step's own stage; only the orientation is shared
                here = view.ActiveViewport.ConstructionPlane().Origin
                view.ActiveViewport.SetConstructionPlane(Rhino.Geometry.Plane(here, shared.XAxis, shared.YAxis))
                if resave_step_snapshot(name, active):
                    print("{}: CPlane set to the shared one, snapshot updated.".format(name))
                else:
                    problems.append("{}: snapshot could not be saved with the shared CPlane".format(name))
            bitmap, width, height = with_grey_fittings(lambda: capture_view(view, int(scale)))
            if bitmap is None:
                problems.append("{}: capture failed".format(name))
                continue
            path = save_image(bitmap, folder, stem, step)
            done += 1
            print("Re-captured step {}: {}".format(step, path))
        clear_all()
        set_symbol_visibility(symbols_before)
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    summary = "Re-captured {} of {} step(s) into {}".format(done, len(steps), folder)
    if problems:
        summary += "\n\n" + "\n".join(problems)
    print(summary)
    rs.MessageBox(summary, 0, TITLE)


# --- copy stage sideways (side-by-side steps) ----------------------------------

def nice_number(value):
    """Rounds up to a tidy figure: 1234 -> 1500, 87 -> 90."""
    if value <= 0:
        return 0.0
    magnitude = 10 ** math.floor(math.log10(value))
    return math.ceil(value / magnitude * 2) / 2.0 * magnitude


def extent_along(objs, axis):
    """Width of the objects' bounding boxes measured along the unit vector `axis`."""
    low = high = None
    for obj in objs:
        box = obj.Geometry.GetBoundingBox(True)
        if not box.IsValid:
            continue
        for corner in box.GetCorners():
            d = Rhino.Geometry.Vector3d(corner.X, corner.Y, corner.Z) * axis
            low = d if low is None or d < low else low
            high = d if high is None or d > high else high
    return (high - low) if low is not None else 0.0


def ask_stage_distance(suggested, direction, symbols):
    """Distance prompt with Direction and Symbols options. Returns (distance, direction, symbols) or None."""
    directions = ["Right", "Left"]
    symbol_choices = ["Leave", "Copy"]
    while True:
        getter = Rhino.Input.Custom.GetNumber()
        getter.SetCommandPrompt("Distance to copy the stage sideways (the camera moves with it)")
        getter.SetDefaultNumber(suggested)
        getter.SetLowerLimit(0.0, True)
        dir_option = getter.AddOptionList("Direction", directions, directions.index(direction))
        sym_option = getter.AddOptionList("Symbols", symbol_choices, symbol_choices.index(symbols))
        result = getter.Get()
        if result == Rhino.Input.GetResult.Option:
            option = getter.Option()
            if option.Index == dir_option:
                direction = directions[option.CurrentListOptionIndex]
            elif option.Index == sym_option:
                symbols = symbol_choices[option.CurrentListOptionIndex]
            continue
        if result == Rhino.Input.GetResult.Number:
            return getter.Number(), direction, symbols
        return None


def copy_object(obj, xform):
    """Adds a transformed copy of `obj` (shown even if `obj` is hidden). Returns its id."""
    new_id = sc.doc.Objects.Transform(obj, xform, False)
    if new_id != System.Guid.Empty and obj.IsHidden:
        sc.doc.Objects.Show(new_id, True)
    return new_id


def regroup(new_ids):
    """Gives the copies fresh groups mirroring the originals' groups."""
    mapping = {}
    for new_id in new_ids:
        obj = sc.doc.Objects.FindId(new_id)
        if obj is None:
            continue
        groups = list(obj.Attributes.GetGroupList() or [])
        if not groups:
            continue
        attrs = obj.Attributes.Duplicate()
        attrs.RemoveFromAllGroups()
        for group in groups:
            if group not in mapping:
                mapping[group] = sc.doc.Groups.Add()
            attrs.AddToGroup(mapping[group])
        sc.doc.Objects.ModifyAttributes(obj, attrs, True)


def freeze_highlight(source, copies):
    """Bakes one highlight of the stage left behind: its orange copies become plain
    orange objects (no longer tracked) and the hidden original is removed, since
    the new stage got a clean copy of it."""
    for copy in copies:
        attrs = copy.Attributes.Duplicate()
        for key in (SOURCE_KEY, ANCHOR_KEY, FRAME_KEY, ROLE_KEY):
            attrs.DeleteUserString(key)
        sc.doc.Objects.ModifyAttributes(copy, attrs, True)
    try:
        source_id = System.Guid(source)
    except Exception:
        return
    if sc.doc.Objects.FindId(source_id) is not None:
        sc.doc.Objects.Show(source_id, True)   # Rhino will not delete a hidden object
        sc.doc.Objects.Delete(source_id, True)


def visible_object_ids():
    return [obj.Id for obj in sc.doc.Objects if obj.Visible]


def copy_stage_objects(objs, vector, symbols="Leave"):
    """Copies `objs` by `vector`. Highlighted pieces come across as their real
    parts in the pose their orange copies have, and are frozen where they were.
    Symbols are left behind unless `symbols` is "Copy". Returns
    (new ids, frozen highlight count, symbols left behind)."""
    translation = Rhino.Geometry.Transform.Translation(vector)
    all_copies = highlight_copies()
    new_ids = []
    frozen = []
    handled = set()
    left_symbols = 0
    for obj in objs:
        if is_symbol_layer(obj.Attributes.LayerIndex) and symbols == "Leave":
            left_symbols += 1
            continue
        source = obj.Attributes.GetUserString(SOURCE_KEY)
        if source and obj.Attributes.GetUserString(ROLE_KEY) == ROLE_HIGHLIGHT:
            if source in handled:
                continue
            handled.add(source)
            group = all_copies.get(source, [obj])
            xform = copies_transform(group) or Rhino.Geometry.Transform.Identity
            try:
                original = sc.doc.Objects.FindId(System.Guid(source))
            except Exception:
                original = None
            if original is not None:
                new_id = copy_object(original, translation * xform)
            else:
                new_id = copy_object(obj, translation)
            if new_id != System.Guid.Empty:
                new_ids.append(new_id)
            frozen.append((source, group))
            continue
        new_id = copy_object(obj, translation)
        if new_id != System.Guid.Empty:
            new_ids.append(new_id)
    regroup(new_ids)
    for source, group in frozen:
        freeze_highlight(source, group)
    return new_ids, len(frozen), left_symbols


def copy_stage():
    """Copies the selected stage sideways (along the view's horizontal) and moves the
    camera the same way, so the picture looks the same but shows the copy. The copy
    is clean: highlighted pieces come across as their real, un-highlighted parts
    in the pose the orange copies had. The stage left behind is frozen as a picture."""
    ids = rs.GetObjects("Select the stage to copy (Enter = everything visible)", preselect=True)
    if ids is None:
        ids = visible_object_ids()
    if not ids:
        print("Nothing to copy.")
        return
    objs = [sc.doc.Objects.FindId(i) for i in ids]
    objs = [o for o in objs if o is not None]
    view = sc.doc.Views.ActiveView
    vp = view.ActiveViewport
    axis = Rhino.Geometry.Vector3d(vp.CameraX)
    axis.Unitize()
    defaults = load_defaults()
    suggested = defaults["stage_distance"] or nice_number(extent_along(objs, axis) * 1.25)
    answer = ask_stage_distance(suggested, defaults["stage_direction"], defaults["stage_symbols"])
    if answer is None:
        return
    distance, direction, symbols = answer
    save_defaults({"stage_distance": float(distance), "stage_direction": direction, "stage_symbols": symbols})
    vector = axis * distance
    if direction == "Left":
        vector.Reverse()

    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Copy assembly stage sideways")
    try:
        new_ids, frozen, left_symbols = copy_stage_objects(objs, vector, symbols)
        vp.SetCameraLocations(vp.CameraTarget + vector, vp.CameraLocation + vector)
        shared_cplane(vp, vector)   # the plane travels with the stage, same orientation
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)
    rs.UnselectAllObjects()
    for new_id in new_ids:
        sc.doc.Objects.Select(new_id, True)
    view.Redraw()
    sc.doc.Views.Redraw()
    note = ""
    if frozen:
        note += " {} highlighted piece(s) came across as clean parts; the stage left behind keeps them orange as plain objects.".format(frozen)
    if left_symbols:
        note += " {} symbol(s) stayed with the old stage.".format(left_symbols)
    print("Copied {} object(s) {:g} {} and moved the camera with them; the copy is selected.{} "
          "Highlight the next piece and Capture step as usual.".format(len(new_ids), distance, direction.lower(), note))


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
    elif choice == COPY_STAGE_LABEL:
        copy_stage()
    elif choice == SHOW_SYMBOLS_LABEL:
        show_symbols()
    elif choice == SET_CPLANE_LABEL:
        set_shared_cplane()


if __name__ == "__main__":
    main()
