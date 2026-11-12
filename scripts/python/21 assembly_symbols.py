#! python 3
# -*- coding: utf-8 -*-
"""
21 - Assembly Symbols

Arrows and glue beads for the assembly instruction pictures made with
20 - Assembly Steps. Every symbol is a small solid, so it shades and outlines
like the parts, and carries its own display mode so it keeps its colour in
the NP Assembly look (which paints everything else off-white):

  Push / move arrow     a flat block arrow from a tail point to a tip point,
                        facing the camera. Layer NP-Assembly - Arrows,
                        mode NP Assembly - Arrows (green).
  Rotate arrow (screw)  one or two curved arrows around a screw's axis (pick
                        the screw block, or pick an axis), tighten or loosen.
                        Same layer and mode.
  Glue bead             a round-ended bead along picked or drawn curves.
                        Layer NP-Assembly - Glue, mode NP Assembly - Glue.
  Moving blanket        a dark blue quilted slab under the parts: two corners,
                        or Enter to fit it under everything in view.
                        Layer NP-Assembly - Blanket, mode NP Assembly - Blanket.
  Tool call-out         a flat icon facing the camera, placed at a picked
                        point: glue bottle, screwdriver bit, rubber mallet,
                        hammer, green tick or red cross. Grey parts use
                        NP Assembly - Fittings, the bottle NP Assembly - Glue,
                        the tick NP Assembly - Arrows, the cross
                        NP Assembly - Cross, white parts the base look.
                        Layer NP-Assembly - Icons; each icon is one group.

Sizes are in model units, remembered between runs. Hide or delete the symbols
of one step before capturing the next; the step snapshot keeps visibility.
"""

import json
import math
import os

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
MODES_FOLDER = os.path.join(_INSTALL_ROOT, "templates", "display_modes")

TITLE = "NP Assembly Symbols"
ARROW_MODE = "NP Assembly - Arrows"
GLUE_MODE = "NP Assembly - Glue"
FITTINGS_MODE = "NP Assembly - Fittings"
CROSS_MODE = "NP Assembly - Cross"
BLANKET_MODE = "NP Assembly - Blanket"
ARROW_LAYER = "NP-Assembly - Arrows"
GLUE_LAYER = "NP-Assembly - Glue"
ICON_LAYER = "NP-Assembly - Icons"
BLANKET_LAYER = "NP-Assembly - Blanket"
BLANKET_COLOR = (150, 165, 200)   # quilt lines and the slab's outline
EDGE_GREY = (40, 40, 40)        # arrow layer colour = outline colour of the arrows
GLUE_COLOR = (245, 225, 130)

PUSH_LABEL = "Push / move arrow"
ROTATE_LABEL = "Rotate arrow (screw)"
GLUE_LABEL = "Glue bead"
TOOL_LABEL = "Tool call-out"
BLANKET_LABEL = "Moving blanket"
ICONS = ["GlueBottle", "Bit", "Mallet", "Hammer", "Tick", "Cross"]

DEFAULTS_FILENAME = "assembly_symbols_defaults.json"
FALLBACK = {
    "arrow_width": 1.0,      # across the head
    "thickness": 0.1,        # slab thickness of arrows
    "rotate_radius": 0.6,    # centreline radius of the curved arrows
    "rotate_width": 0.2,     # band width of the curved arrows
    "rotate_sweep": 150.0,   # degrees per curved arrow
    "rotate_offset": 0.75,   # distance above the screw's insertion point
    "double": True,          # two curved arrows (the "turn" symbol)
    "glue_diameter": 0.1875,
    "icon_size": 2.0,        # overall height of a tool call-out icon
    "icon": "Bit",
    "blanket_margin": 6.0,   # blanket overhang around the parts when auto-fitted
    "blanket_thickness": 0.25,
    "quilt_spacing": 4.0,    # diamond quilt lines; 0 for a plain blanket
}


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
    return [PUSH_LABEL, ROTATE_LABEL, GLUE_LABEL, TOOL_LABEL, BLANKET_LABEL]


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
                data[key] = type(FALLBACK[key])(saved[key])
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


# --- display modes and layers -------------------------------------------------

# --- display mode files ---------------------------------------------------------
#
# Rhino for Mac writes display mode .ini files as UTF-8 with a byte order mark and
# reads any encoding. Rhino for Windows can trip over that mark: the first line,
# the [DisplayMode\<id>] header, is then not recognised and the import returns
# nothing. Team files are therefore kept as plain text without the mark, and a
# failed import is tried again in the other encodings Rhino has used.

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


def import_mode_id(path):
    try:
        mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    except Exception:
        return None
    if mode_id is None or mode_id == System.Guid.Empty:
        return None
    return mode_id


def import_mode_file(path):
    """Imports a display mode .ini; returns the DisplayModeDescription or None.
    When Rhino refuses the file as it is, the same content is tried in the other
    encodings."""
    mode_id = import_mode_id(path)
    if mode_id is None:
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
                mode_id = import_mode_id(temp_path)
                if mode_id is not None:
                    print("Display mode file '{}' was read after re-saving it as {}.".format(
                        os.path.basename(path), encoding))
                    break
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    if mode_id is None:
        return None
    return Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)


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
    return "File: {}\n({})\nRhino {} on {}. Tried as saved, as plain text and as UTF-16.".format(
        path, detail, Rhino.RhinoApp.Version, system)


def find_mode(name):
    for mode in Rhino.Display.DisplayModeDescription.GetDisplayModes():
        if mode.EnglishName == name:
            return mode
    return None


def ensure_mode(name):
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


def ensure_layer(name, color):
    if not rs.IsLayer(name):
        rs.AddLayer(name, color)
    return sc.doc.Layers.FindByFullPath(name, -1)


def add_symbol(brep, layer_index, mode, name):
    """Adds `brep` on the layer with the per-object display mode (None keeps
    the viewport's mode). Returns its id."""
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = name
    new_id = sc.doc.Objects.Add(brep, attrs)
    if new_id == System.Guid.Empty:
        return None
    if mode is None:
        return new_id
    obj = sc.doc.Objects.FindId(new_id)
    changed = obj.Attributes.Duplicate()
    # the return value of SetDisplayModeOverride is unreliable; the stored state counts
    changed.SetDisplayModeOverride(mode)
    if changed.HasDisplayModeOverride(System.Guid.Empty):
        sc.doc.Objects.ModifyAttributes(obj, changed, True)
    return new_id


# --- geometry -----------------------------------------------------------------

def camera_direction():
    view = sc.doc.Views.ActiveView
    direction = Rhino.Geometry.Vector3d(view.ActiveViewport.CameraDirection)
    direction.Unitize()
    return direction


def facing_plane(origin, direction):
    """Plane with X along `direction` whose flat face looks at the camera."""
    x_axis = Rhino.Geometry.Vector3d(direction)
    x_axis.Unitize()
    y_axis = Rhino.Geometry.Vector3d.CrossProduct(x_axis, camera_direction())
    if not y_axis.Unitize() or y_axis.IsTiny():
        y_axis = Rhino.Geometry.Vector3d.CrossProduct(x_axis, Rhino.Geometry.Vector3d.ZAxis)
        if not y_axis.Unitize():
            y_axis = Rhino.Geometry.Vector3d.CrossProduct(x_axis, Rhino.Geometry.Vector3d.YAxis)
            y_axis.Unitize()
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def slab(outline, plane, thickness):
    """Closed planar `outline` (in world space, lying on `plane`) as a solid slab
    of `thickness`, centred on the plane."""
    curve = outline.DuplicateCurve()
    curve.Translate(plane.Normal * (-thickness / 2.0))
    extrusion = Rhino.Geometry.Extrusion.Create(curve, thickness, True)
    if extrusion is None:
        return None
    brep = extrusion.ToBrep(True)
    if brep is not None and brep.SolidOrientation == Rhino.Geometry.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def push_arrow_brep(start, end, width, thickness):
    direction = end - start
    length = direction.Length
    if length <= sc.doc.ModelAbsoluteTolerance:
        return None
    plane = facing_plane(start, direction)
    head_length = min(width * 0.9, length * 0.45)
    shaft = width * 0.25
    head = width * 0.5
    local = [(0, -shaft), (length - head_length, -shaft), (length - head_length, -head),
             (length, 0), (length - head_length, head), (length - head_length, shaft),
             (0, shaft), (0, -shaft)]
    points = [plane.PointAt(x, y) for x, y in local]
    outline = Rhino.Geometry.PolylineCurve(points)
    return slab(outline, plane, thickness)


def rotate_arrow_brep(plane, radius, band, sweep_degrees, start_degrees, thickness):
    """One curved arrow in `plane` around its origin. Positive sweep turns
    anticlockwise seen from the plane normal, negative turns clockwise."""
    def polar(angle_degrees, r):
        angle = math.radians(angle_degrees)
        return plane.PointAt(r * math.cos(angle), r * math.sin(angle))

    a0 = start_degrees
    a1 = start_degrees + sweep_degrees
    mid = (a0 + a1) / 2.0
    inner = radius - band / 2.0
    outer = radius + band / 2.0
    head_length = band * 1.8
    head_angle = math.degrees(head_length / radius) * (1 if sweep_degrees >= 0 else -1)
    pieces = [
        Rhino.Geometry.ArcCurve(Rhino.Geometry.Arc(polar(a0, inner), polar(mid, inner), polar(a1, inner))),
        Rhino.Geometry.PolylineCurve([polar(a1, inner), polar(a1, radius - band), polar(a1 + head_angle, radius),
                                      polar(a1, radius + band), polar(a1, outer)]),
        Rhino.Geometry.ArcCurve(Rhino.Geometry.Arc(polar(a1, outer), polar(mid, outer), polar(a0, outer))),
        Rhino.Geometry.LineCurve(polar(a0, outer), polar(a0, inner)),
    ]
    joined = Rhino.Geometry.Curve.JoinCurves(pieces, sc.doc.ModelAbsoluteTolerance)
    if not joined or not joined[0].IsClosed:
        return None
    return slab(joined[0], plane, thickness)


def glue_breps(curve, diameter):
    tolerance = sc.doc.ModelAbsoluteTolerance
    angle = sc.doc.ModelAngleToleranceRadians
    breps = Rhino.Geometry.Brep.CreatePipe(curve, diameter / 2.0, False,
                                           Rhino.Geometry.PipeCapMode.Round, True, tolerance, angle)
    return list(breps or [])


def instance_axis(obj):
    """Insertion point and unit local +Z of a block instance (fittings: out of the face)."""
    xform = obj.InstanceXform
    origin = Rhino.Geometry.Point3d(xform.M03, xform.M13, xform.M23)
    axis = Rhino.Geometry.Vector3d(xform.M02, xform.M12, xform.M22)
    if not axis.Unitize():
        return None, None
    return origin, axis


# --- tools ----------------------------------------------------------------------

def push_arrow():
    mode = ensure_mode(ARROW_MODE)
    if mode is None:
        return
    defaults = load_defaults()
    start = rs.GetPoint("Arrow tail (where the part comes from)")
    if start is None:
        return
    end = rs.GetPoint("Arrow tip (where it goes)", start)
    if end is None:
        return
    width = rs.GetReal("Arrow width across the head", defaults["arrow_width"], 0.01)
    if width is None:
        return
    defaults["arrow_width"] = float(width)
    save_defaults(defaults)
    brep = push_arrow_brep(start, end, float(width), defaults["thickness"])
    if brep is None:
        rs.MessageBox("Could not build the arrow (tail and tip are too close).", 0, TITLE)
        return
    layer_index = ensure_layer(ARROW_LAYER, EDGE_GREY)
    undo = sc.doc.BeginUndoRecord("Assembly push arrow")
    new_id = add_symbol(brep, layer_index, mode, "assembly arrow")
    if undo:
        sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    if new_id:
        rs.UnselectAllObjects()
        rs.SelectObject(new_id)
        print("Push arrow added on '{}' (width {}).".format(ARROW_LAYER, width))


def rotate_arrow():
    mode = ensure_mode(ARROW_MODE)
    if mode is None:
        return
    defaults = load_defaults()
    picked = rs.GetObject("Pick the screw or fitting block to turn (Enter to pick an axis instead)",
                          rs.filter.instance, preselect=True)
    if picked:
        obj = sc.doc.Objects.FindId(picked)
        origin, axis = instance_axis(obj)
        if origin is None:
            rs.MessageBox("That block has no usable axis.", 0, TITLE)
            return
        offset = rs.GetReal("Distance above the fitting's insertion point", defaults["rotate_offset"], 0.0)
        if offset is None:
            return
        defaults["rotate_offset"] = float(offset)
        centre = origin + axis * float(offset)
    else:
        centre = rs.GetPoint("Centre of rotation")
        if centre is None:
            return
        toward = rs.GetPoint("Point along the axis, on the side the arrows are seen from", centre)
        if toward is None:
            return
        axis = toward - centre
        if not axis.Unitize():
            return
    radius = rs.GetReal("Radius of the curved arrows", defaults["rotate_radius"], 0.01)
    if radius is None:
        return
    turn = rs.GetString("Turn direction (seen from the arrows' side)", "Tighten", ["Tighten", "Loosen"])
    if not turn:
        return
    double = rs.GetString("Two arrows", "Yes" if defaults["double"] else "No", ["Yes", "No"])
    if not double:
        return
    defaults["rotate_radius"] = float(radius)
    defaults["double"] = double.lower().startswith("y")
    save_defaults(defaults)

    plane = Rhino.Geometry.Plane(centre, axis)
    band = max(defaults["rotate_width"], float(radius) * 0.3)
    sweep = defaults["rotate_sweep"]
    clockwise = turn.lower().startswith("t")       # right-hand thread tightens clockwise
    if clockwise:
        sweep = -sweep
    starts = [0.0, 180.0] if defaults["double"] else [0.0]
    layer_index = ensure_layer(ARROW_LAYER, EDGE_GREY)
    undo = sc.doc.BeginUndoRecord("Assembly rotate arrow")
    made = []
    for start in starts:
        brep = rotate_arrow_brep(plane, float(radius), band, sweep, start + 15.0, defaults["thickness"])
        if brep is not None:
            new_id = add_symbol(brep, layer_index, mode, "assembly rotate arrow")
            if new_id:
                made.append(new_id)
    if undo:
        sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    if made:
        rs.UnselectAllObjects()
        rs.SelectObjects(made)
        print("{} rotate arrow(s) added on '{}' ({}, radius {}).".format(len(made), ARROW_LAYER, turn.lower(), radius))
    else:
        rs.MessageBox("Could not build the rotate arrows.", 0, TITLE)


def glue_bead():
    mode = ensure_mode(GLUE_MODE)
    if mode is None:
        return
    defaults = load_defaults()
    curve_ids = rs.GetObjects("Select curves for the glue bead (Enter to draw one)", rs.filter.curve, preselect=True)
    curves = []
    drawn = None
    if curve_ids:
        curves = [rs.coercecurve(i, -1, True) for i in curve_ids]
    else:
        points = rs.GetPoints(True, False, "First point of the glue bead", "Next point (Enter to finish)")
        if not points or len(points) < 2:
            return
        drawn = Rhino.Geometry.PolylineCurve(points)
        curves = [drawn]
    diameter = rs.GetReal("Bead diameter", defaults["glue_diameter"], 0.001)
    if diameter is None:
        return
    defaults["glue_diameter"] = float(diameter)
    save_defaults(defaults)
    layer_index = ensure_layer(GLUE_LAYER, GLUE_COLOR)
    undo = sc.doc.BeginUndoRecord("Assembly glue bead")
    made = []
    for curve in curves:
        for brep in glue_breps(curve, float(diameter)):
            new_id = add_symbol(brep, layer_index, mode, "glue bead")
            if new_id:
                made.append(new_id)
    if undo:
        sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    if made:
        rs.UnselectAllObjects()
        rs.SelectObjects(made)
        print("{} glue bead(s) added on '{}' (diameter {}).".format(len(made), GLUE_LAYER, diameter))
    else:
        rs.MessageBox("Could not build the glue bead along those curves.", 0, TITLE)


# --- tool call-out icons --------------------------------------------------------
# Each icon is a list of pieces: (list of closed outline curves in local x,y with
# the overall height 1, style, lift). Style "grey" = Fittings mode, "glue" = Glue
# mode, "white" = the base look with its outline. Lift stacks a piece above
# another, in slab thicknesses. Local y points up on screen.

def screen_plane(origin):
    vp = sc.doc.Views.ActiveView.ActiveViewport
    return Rhino.Geometry.Plane(origin, vp.CameraX, vp.CameraY)


def local_curve(plane, size, points, fillet=0.0, rotate=0.0):
    """Closed polyline from local unit coordinates, scaled, optionally rotated
    (degrees, anticlockwise) and corner-filleted, mapped onto `plane`."""
    angle = math.radians(rotate)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    world = []
    for x, y in points:
        rx, ry = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        world.append(plane.PointAt(rx * size, ry * size))
    if world[0].DistanceTo(world[-1]) > 1e-9:
        world.append(world[0])
    curve = Rhino.Geometry.PolylineCurve(world)
    if fillet > 0:
        rounded = Rhino.Geometry.Curve.CreateFilletCornersCurve(
            curve, fillet * size, sc.doc.ModelAbsoluteTolerance, sc.doc.ModelAngleToleranceRadians)
        if rounded is not None:
            curve = rounded
    return curve


def local_circle(plane, size, centre, radius, rotate=0.0):
    angle = math.radians(rotate)
    cx, cy = centre
    rx, ry = cx * math.cos(angle) - cy * math.sin(angle), cx * math.sin(angle) + cy * math.cos(angle)
    middle = Rhino.Geometry.Plane(plane.PointAt(rx * size, ry * size), plane.XAxis, plane.YAxis)
    return Rhino.Geometry.Circle(middle, radius * size).ToNurbsCurve()


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def drop(cx, cy, r):
    """Teardrop pointing up (the drop hangs from its apex)."""
    points = [(cx, cy + r * 2.2)]
    for step in range(13):
        angle = math.radians(150 + step * 20)
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return points


def stroke(points, half_width):
    """Outline polygon of a thick open polyline with mitred joins."""
    def unit(ax, ay):
        length = math.hypot(ax, ay) or 1.0
        return ax / length, ay / length
    normals = []
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        dx, dy = unit(x1 - x0, y1 - y0)
        normals.append((-dy, dx))
    def side(sign):
        out = []
        for index, (x, y) in enumerate(points):
            if index == 0:
                nx, ny = normals[0]
            elif index == len(points) - 1:
                nx, ny = normals[-1]
            else:
                ax, ay = normals[index - 1]
                bx, by = normals[index]
                mx, my = unit(ax + bx, ay + by)
                scale = 1.0 / max(mx * ax + my * ay, 0.2)
                nx, ny = mx * scale, my * scale
            out.append((x + sign * half_width * nx, y + sign * half_width * ny))
        return out
    return side(1) + list(reversed(side(-1)))


def flat_piece(plane, curves, thickness, lift=0):
    """Solid slab of `thickness` from closed planar `curves` (first is the outer
    boundary, the rest are holes), lifted `lift` slabs toward the viewer."""
    breps = Rhino.Geometry.Brep.CreatePlanarBreps(curves, sc.doc.ModelAbsoluteTolerance)
    if not breps:
        return None
    face = breps[0].Faces[0]
    solid = Rhino.Geometry.Brep.CreateFromOffsetFace(face, thickness, sc.doc.ModelAbsoluteTolerance, False, True)
    if solid is None:
        return None
    if lift:
        solid.Translate(plane.Normal * (thickness * lift))
    if solid.SolidOrientation == Rhino.Geometry.BrepSolidOrientation.Inward:
        solid.Flip()
    return solid


# Tools that can be aimed: local point of the working end (lands on the first
# click), local point the second click pulls toward (the body or handle end), and
# the prompts for the two clicks. Tick and Cross are simply centred.
ICON_AIM = {
    "GlueBottle": ((0.0, 0.5), (0.0, -0.5), "Tip of the glue nozzle", "Click where the bottle body goes"),
    "Bit": ((0.0, -0.5), (0.0, 0.5), "Tip of the screwdriver bit", "Click where the shank goes"),
    "Mallet": ((-0.42, 0.325), (0.0, -0.5), "Point the mallet strikes", "Click where the handle end goes"),
    "Hammer": ((0.35, 0.35), (0.12, -0.5), "Point the hammer strikes", "Click where the handle end goes"),
}


def aimed_plane(plane, size, name, toward):
    """`plane` (origin = first click, facing the camera) turned and shifted so the
    icon's working end sits on the first click and its body lies toward the point
    `toward`. Returns None when `toward` gives no direction."""
    anchor, back = ICON_AIM[name][0], ICON_AIM[name][1]
    ok, u, v = plane.ClosestParameter(toward)
    if not ok or math.hypot(u, v) < 1e-9:
        return None
    angle = math.atan2(v, u) - math.atan2(back[1] - anchor[1], back[0] - anchor[0])
    # built from scratch: Plane is a struct, so changing a copy in place is unreliable from Python
    x_axis = plane.XAxis * math.cos(angle) + plane.YAxis * math.sin(angle)
    y_axis = plane.YAxis * math.cos(angle) - plane.XAxis * math.sin(angle)
    origin = plane.Origin - x_axis * (anchor[0] * size) - y_axis * (anchor[1] * size)
    return Rhino.Geometry.Plane(origin, x_axis, y_axis)


def anchored_plane(plane, size, name):
    """`plane` shifted so the working end of the icon, in its standard
    orientation, sits on the plane origin."""
    anchor = ICON_AIM[name][0]
    if name == "GlueBottle":
        angle = math.radians(-35.0)          # the standard tilt of the bottle
        anchor = (anchor[0] * math.cos(angle) - anchor[1] * math.sin(angle),
                  anchor[0] * math.sin(angle) + anchor[1] * math.cos(angle))
    origin = plane.Origin - plane.XAxis * (anchor[0] * size) - plane.YAxis * (anchor[1] * size)
    return Rhino.Geometry.Plane(origin, plane.XAxis, plane.YAxis)


def icon_pieces(name, plane, size, aimed=False):
    """(curves, style, lift) pieces of the named icon, world space, height `size`.
    `aimed` = the plane is already turned to the wanted direction (aimed_plane)."""
    pieces = []
    if name == "GlueBottle" and aimed:
        pieces.append(([local_curve(plane, size, rect(-0.22, -0.5, 0.22, 0.05), 0.05)], "glue", 0))
        pieces.append(([local_curve(plane, size, [(-0.22, 0.05), (0.22, 0.05), (0.09, 0.22), (-0.09, 0.22)])], "glue", 0))
        pieces.append(([local_curve(plane, size, rect(-0.1, 0.22, 0.1, 0.32))], "grey", 0))
        pieces.append(([local_curve(plane, size, [(-0.06, 0.32), (0.06, 0.32), (0.0, 0.5)])], "grey", 0))
        # the drop leaves the nozzle along its axis, pointed end toward the tip
        centre_y = 0.72
        pieces.append(([local_curve(plane, size, [(x, 2 * centre_y - y) for x, y in drop(0.0, centre_y, 0.06)])], "glue", 0))
    elif name == "GlueBottle":
        tilt = -35.0   # nozzle leaning right, drop falling out of it
        pieces.append(([local_curve(plane, size, rect(-0.22, -0.5, 0.22, 0.05), 0.05, tilt)], "glue", 0))
        pieces.append(([local_curve(plane, size, [(-0.22, 0.05), (0.22, 0.05), (0.09, 0.22), (-0.09, 0.22)], 0, tilt)], "glue", 0))
        pieces.append(([local_curve(plane, size, rect(-0.1, 0.22, 0.1, 0.32), 0, tilt)], "grey", 0))
        pieces.append(([local_curve(plane, size, [(-0.06, 0.32), (0.06, 0.32), (0.0, 0.5)], 0, tilt)], "grey", 0))
        # the drop falls straight down from the nozzle tip, so it is not tilted
        angle = math.radians(tilt)
        tip_x, tip_y = -0.5 * math.sin(angle), 0.5 * math.cos(angle)
        pieces.append(([local_curve(plane, size, drop(tip_x + 0.1, tip_y - 0.05, 0.06))], "glue", 0))
    elif name == "Bit":
        pieces.append(([local_curve(plane, size, rect(-0.11, -0.05, 0.11, 0.5))], "grey", 0))
        pieces.append(([local_curve(plane, size, [(-0.11, -0.05), (0.11, -0.05), (0.03, -0.5), (-0.03, -0.5)])], "grey", 0))
        pieces.append(([local_circle(plane, size, (0.45, 0.28), 0.19)], "white", 0))
        pieces.append(([local_curve(plane, size, rect(0.45 - 0.14, 0.28 - 0.025, 0.45 + 0.14, 0.28 + 0.025))], "grey", 1))
        pieces.append(([local_curve(plane, size, rect(0.45 - 0.025, 0.28 - 0.14, 0.45 + 0.025, 0.28 + 0.14))], "grey", 1))
    elif name == "Mallet":
        pieces.append(([local_curve(plane, size, rect(-0.3, 0.15, 0.3, 0.5), 0.04)], "grey", 0))
        pieces.append(([local_curve(plane, size, rect(-0.42, 0.15, -0.3, 0.5), 0.04)], "white", 0))
        pieces.append(([local_curve(plane, size, rect(0.3, 0.15, 0.42, 0.5), 0.04)], "white", 0))
        pieces.append(([local_curve(plane, size, rect(-0.06, -0.5, 0.06, 0.15), 0.02)], "white", 0))
    elif name == "Hammer":
        head = [(0.35, 0.22), (0.35, 0.48), (-0.05, 0.48), (-0.42, 0.40), (-0.3, 0.33), (-0.42, 0.14), (-0.05, 0.22)]
        pieces.append(([local_curve(plane, size, head)], "grey", 0))
        pieces.append(([local_curve(plane, size, rect(0.06, -0.5, 0.18, 0.22), 0.02)], "white", 0))
    elif name == "Tick":
        pieces.append(([local_curve(plane, size, stroke([(-0.45, 0.02), (-0.14, -0.42), (0.48, 0.46)], 0.1), 0.03)], "green", 0))
    elif name == "Cross":
        arm, half = 0.46, 0.1
        plus = [(-half, -arm), (half, -arm), (half, -half), (arm, -half), (arm, half), (half, half),
                (half, arm), (-half, arm), (-half, half), (-arm, half), (-arm, -half), (-half, -half)]
        pieces.append(([local_curve(plane, size, plus, 0.02, 45.0)], "red", 0))
    return pieces


def tool_callout():
    grey = ensure_mode(FITTINGS_MODE)
    glue = ensure_mode(GLUE_MODE)
    green = ensure_mode(ARROW_MODE)
    red = ensure_mode(CROSS_MODE)
    if None in (grey, glue, green, red):
        return
    defaults = load_defaults()
    default_icon = defaults["icon"] if defaults["icon"] in ICONS else ICONS[0]
    icon = rs.GetString("Tool call-out", default_icon, ICONS)
    if not icon:
        return
    icon = [name for name in ICONS if name.lower() == icon.strip().lower()]
    if not icon:
        return
    icon = icon[0]
    aim = ICON_AIM.get(icon)
    centre = rs.GetPoint(aim[2] if aim else "Centre of the {} icon".format(icon))
    if centre is None:
        return
    toward = None
    if aim:
        toward = rs.GetPoint(aim[3] + " (Enter for the standard orientation)", centre)
    size = rs.GetReal("Icon height", defaults["icon_size"], 0.01)
    if size is None:
        return
    defaults["icon"] = icon
    defaults["icon_size"] = float(size)
    save_defaults(defaults)

    plane = screen_plane(centre)
    aimed = False
    if aim:
        turned = aimed_plane(plane, float(size), icon, toward) if toward is not None else None
        if turned is not None:
            plane, aimed = turned, True
        else:
            plane = anchored_plane(plane, float(size), icon)
    layer_index = ensure_layer(ICON_LAYER, EDGE_GREY)
    modes = {"grey": grey, "glue": glue, "green": green, "red": red, "white": None}
    thickness = defaults["thickness"]
    undo = sc.doc.BeginUndoRecord("Assembly tool call-out")
    made = []
    for curves, style, lift in icon_pieces(icon, plane, float(size), aimed):
        brep = flat_piece(plane, curves, thickness, lift)
        if brep is None:
            continue
        new_id = add_symbol(brep, layer_index, modes[style], "tool icon " + icon)
        if new_id:
            made.append(new_id)
    if made:
        group = sc.doc.Groups.Add()
        sc.doc.Groups.AddToGroup(group, made)
    if undo:
        sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    if made:
        rs.UnselectAllObjects()
        rs.SelectObjects(made)
        print("{} icon added on '{}' ({} pieces, height {}), grouped.".format(icon, ICON_LAYER, len(made), size))
    else:
        rs.MessageBox("Could not build the {} icon.".format(icon), 0, TITLE)


# --- moving blanket --------------------------------------------------------------

def visible_extent():
    """Bounding box of what is in the active view, ignoring earlier blankets."""
    vp = sc.doc.Views.ActiveView.ActiveViewport
    box = Rhino.Geometry.BoundingBox.Empty
    for obj in sc.doc.Objects:
        if obj.IsHidden or not obj.Visible:
            continue
        if sc.doc.Layers[obj.Attributes.LayerIndex].Name == BLANKET_LAYER:
            continue
        part = obj.Geometry.GetBoundingBox(True)
        if part.IsValid and vp.IsVisible(part.Center):
            box.Union(part)
    return box


def quilt_lines(x0, y0, x1, y1, z, spacing):
    """Diamond quilt: two families of 45-degree lines clipped to the rectangle."""
    lines = []
    if spacing <= 0:
        return lines
    step = spacing * math.sqrt(2.0)
    c = (x0 - y1) + step
    while c < x1 - y0:                     # family x - y = c
        lo, hi = max(x0, y0 + c), min(x1, y1 + c)
        if hi - lo > spacing * 0.2:
            lines.append(Rhino.Geometry.LineCurve(Rhino.Geometry.Point3d(lo, lo - c, z), Rhino.Geometry.Point3d(hi, hi - c, z)))
        c += step
    c = (x0 + y0) + step
    while c < x1 + y1:                     # family x + y = c
        lo, hi = max(x0, c - y1), min(x1, c - y0)
        if hi - lo > spacing * 0.2:
            lines.append(Rhino.Geometry.LineCurve(Rhino.Geometry.Point3d(lo, c - lo, z), Rhino.Geometry.Point3d(hi, c - hi, z)))
        c += step
    return lines


def blanket_objects(x0, y0, x1, y1, top_z, thickness, spacing, mode, layer_index):
    """Adds the slab and quilt lines; returns the new ids."""
    plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(0, 0, top_z - thickness), Rhino.Geometry.Vector3d.ZAxis)
    corners = [plane.PointAt(x0, y0), plane.PointAt(x1, y0), plane.PointAt(x1, y1), plane.PointAt(x0, y1), plane.PointAt(x0, y0)]
    outline = Rhino.Geometry.PolylineCurve(corners)
    radius = min(1.0, (x1 - x0) * 0.1, (y1 - y0) * 0.1)
    rounded = Rhino.Geometry.Curve.CreateFilletCornersCurve(outline, radius, sc.doc.ModelAbsoluteTolerance, sc.doc.ModelAngleToleranceRadians)
    slab = flat_piece(plane, [rounded or outline], thickness)
    made = []
    if slab is not None:
        new_id = add_symbol(slab, layer_index, mode, "moving blanket")
        if new_id:
            made.append(new_id)
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer_index
    attrs.Name = "moving blanket quilt"
    inset = min(radius, thickness)
    for line in quilt_lines(x0 + inset, y0 + inset, x1 - inset, y1 - inset, top_z + 0.01, spacing):
        new_id = sc.doc.Objects.AddCurve(line, attrs)
        if new_id != System.Guid.Empty:
            made.append(new_id)
    return made


def moving_blanket():
    mode = ensure_mode(BLANKET_MODE)
    if mode is None:
        return
    defaults = load_defaults()
    corner = rs.GetPoint("First corner of the blanket (Enter to fit it under everything in view)")
    if corner is None:
        box = visible_extent()
        if not box.IsValid:
            rs.MessageBox("Nothing in view to put a blanket under.", 0, TITLE)
            return
        margin = rs.GetReal("Blanket overhang around the parts", defaults["blanket_margin"], 0.0)
        if margin is None:
            return
        defaults["blanket_margin"] = float(margin)
        x0, y0 = box.Min.X - margin, box.Min.Y - margin
        x1, y1 = box.Max.X + margin, box.Max.Y + margin
        top_z = box.Min.Z
    else:
        other = rs.GetPoint("Opposite corner", corner)
        if other is None:
            return
        x0, x1 = sorted((corner.X, other.X))
        y0, y1 = sorted((corner.Y, other.Y))
        top_z = min(corner.Z, other.Z)
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        rs.MessageBox("The blanket needs two different corners.", 0, TITLE)
        return
    spacing = rs.GetReal("Quilt line spacing (0 for a plain blanket)", defaults["quilt_spacing"], 0.0)
    if spacing is None:
        return
    defaults["quilt_spacing"] = float(spacing)
    save_defaults(defaults)
    layer_index = ensure_layer(BLANKET_LAYER, BLANKET_COLOR)
    undo = sc.doc.BeginUndoRecord("Assembly moving blanket")
    made = blanket_objects(x0, y0, x1, y1, top_z, defaults["blanket_thickness"], float(spacing), mode, layer_index)
    if made:
        group = sc.doc.Groups.Add()
        sc.doc.Groups.AddToGroup(group, made)
    if undo:
        sc.doc.EndUndoRecord(undo)
    sc.doc.Views.Redraw()
    if made:
        rs.UnselectAllObjects()
        rs.SelectObjects(made)
        print("Moving blanket {:.1f} x {:.1f} added on '{}', top at Z {:.3f}, grouped.".format(x1 - x0, y1 - y0, BLANKET_LAYER, top_z))
    else:
        rs.MessageBox("Could not build the blanket.", 0, TITLE)


def main():
    items = menu_items()
    choice = take_menu_choice(items)
    if not choice:
        choice = rs.ListBox(items, "Assembly symbols", TITLE, items[0])
    if not choice:
        return
    if choice == PUSH_LABEL:
        push_arrow()
    elif choice == ROTATE_LABEL:
        rotate_arrow()
    elif choice == GLUE_LABEL:
        glue_bead()
    elif choice == TOOL_LABEL:
        tool_callout()
    elif choice == BLANKET_LABEL:
        moving_blanket()


if __name__ == "__main__":
    main()
