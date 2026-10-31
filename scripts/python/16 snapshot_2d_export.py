"""
Make a 2D drawing of each chosen snapshot and export it.

Restores the snapshot, draws the visible outlines from that view, and writes
one file per snapshot. The 2D curves are not added to the model.
"""

import os

import Rhino
import System
import rhinoscriptsyntax as rs
import scriptcontext as sc


SILHOUETTE_NONE = getattr(Rhino.Geometry.SilhouetteType, "None")

FORMATS = [
    ("Adobe Illustrator (.ai)", ".ai"),
    ("EPS (.eps)", ".eps"),
    ("PDF (.pdf)", ".pdf"),
]


def snapshot_names():
    try:
        names = sc.doc.Snapshots.Names
    except Exception:
        return []
    if not names:
        return []
    found = []
    for name in names:
        if name:
            found.append(name)
    return found


def restore_snapshot(name):
    quoted = name.replace('"', '""')
    script = '_-Snapshots _Restore "{}" _Enter _Enter'.format(quoted)
    ok = Rhino.RhinoApp.RunScript(script, False)
    Rhino.RhinoApp.Wait()
    return bool(ok)


def active_viewport():
    view = sc.doc.Views.ActiveView
    if view is None:
        return None
    return view.ActiveViewport


def collect_visible_curves(viewport):
    parameters = Rhino.Geometry.HiddenLineDrawingParameters()
    parameters.AbsoluteTolerance = sc.doc.ModelAbsoluteTolerance
    parameters.Flatten = True
    parameters.IncludeHiddenCurves = False
    parameters.IncludeTangentEdges = False
    parameters.SetViewport(viewport)

    identity = Rhino.Geometry.Transform.Identity
    for obj in sc.doc.Objects:
        if obj is None or obj.IsDeleted:
            continue
        try:
            selectable = obj.IsSelectable(True, False, False, False)
        except Exception:
            selectable = False
        if not selectable or obj.Geometry is None:
            continue
        parameters.AddGeometry(obj.Geometry, identity)

    drawing = Rhino.Geometry.HiddenLineDrawing.Compute(parameters, True)
    if drawing is None:
        return [], []

    silhouettes = []
    curves = []
    for segment in drawing.Segments:
        if not segment or not segment.ParentCurve or not segment.CurveGeometry:
            continue
        if segment.ParentCurve.SilhouetteType == SILHOUETTE_NONE:
            continue
        if segment.SegmentVisibility != Rhino.Geometry.HiddenLineDrawingSegment.Visibility.Visible:
            continue
        curve = segment.CurveGeometry.DuplicateCurve()
        if curve is None:
            continue
        if segment.IsSceneSilhouette:
            silhouettes.append(curve)
        else:
            curves.append(curve)
    return silhouettes, curves


def move_to_origin(curves):
    box = Rhino.Geometry.BoundingBox.Empty
    for curve in curves:
        box.Union(curve.GetBoundingBox(True))
    if not box.IsValid:
        return
    move = Rhino.Geometry.Transform.Translation(
        -box.Min.X,
        -box.Min.Y,
        -box.Min.Z,
    )
    for curve in curves:
        curve.Transform(move)


def safe_filename(name):
    cleaned = (name or "").strip()
    for ch in ['\\', '/', ':', ';', '*', '?', '"', '<', '>', '|']:
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.strip().rstrip(". ")
    return cleaned or "snapshot"


def unique_filename(used, name, extension):
    base = safe_filename(name)
    candidate = base
    number = 2
    while candidate.lower() in used:
        candidate = "{} {}".format(base, number)
        number += 1
    used.add(candidate.lower())
    return candidate + extension


def add_layer(doc, name, parent_index):
    layer = Rhino.DocObjects.Layer()
    layer.Name = safe_filename(name)[:200]
    layer.Color = System.Drawing.Color.Black
    if parent_index is not None and parent_index >= 0:
        layer.ParentLayerId = doc.Layers[parent_index].Id
    return doc.Layers.Add(layer)


def add_curves(doc, curves, layer_index):
    attributes = doc.CreateDefaultAttributes()
    if layer_index is not None and layer_index >= 0:
        attributes.LayerIndex = layer_index
    for curve in curves:
        doc.Objects.AddCurve(curve, attributes)


def apply_source_units(doc):
    try:
        doc.AdjustModelUnitSystem(sc.doc.ModelUnitSystem, False)
    except Exception:
        try:
            doc.ModelUnitSystem = sc.doc.ModelUnitSystem
        except Exception:
            pass
    try:
        doc.ModelAbsoluteTolerance = sc.doc.ModelAbsoluteTolerance
    except Exception:
        pass


def apply_ai_units(options):
    names = {
        Rhino.UnitSystem.Inches: "Inches",
        Rhino.UnitSystem.Feet: "Feet",
        Rhino.UnitSystem.Millimeters: "Millimeters",
        Rhino.UnitSystem.Centimeters: "Centimeters",
        Rhino.UnitSystem.Meters: "Meters",
    }
    unit_name = names.get(sc.doc.ModelUnitSystem)
    if not unit_name:
        return
    units = getattr(Rhino.FileIO.FileAiWriteOptions, "Units", None)
    value = getattr(units, unit_name, None) if units is not None else None
    if value is not None:
        options.AiUnits = value


def export_drawing(doc, path, extension):
    if extension == ".ai":
        options = Rhino.FileIO.FileAiWriteOptions()
        options.PreserveModelScale = True
        options.RhinoScale = 1.0
        options.AIScale = 1.0
        options.ExportViewBoundary = False
        options.UseCMYK = False
        try:
            options.ExportHatchesAsSolidFills = True
            options.OrderLayers = True
        except Exception:
            pass
        apply_ai_units(options)
        return bool(Rhino.FileIO.FileAi.Write(path, doc, options))
    return bool(doc.Export(path))


def write_snapshot_file(silhouettes, curves, path, extension):
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    if doc is None:
        raise RuntimeError("Could not create a drawing document")
    try:
        apply_source_units(doc)
        parent_index = add_layer(doc, "Snapshot 2D", None)
        silhouette_index = add_layer(doc, "Silhouettes", parent_index)
        curve_index = add_layer(doc, "Curves", parent_index)
        add_curves(doc, silhouettes, silhouette_index)
        add_curves(doc, curves, curve_index)
        if doc.Objects.Count < 1:
            return False
        return export_drawing(doc, path, extension)
    finally:
        doc.Dispose()


def main():
    names = snapshot_names()
    if not names:
        rs.MessageBox("This file has no snapshots.", 0, "Snapshot 2D Export")
        return

    format_labels = [label for label, _ext in FORMATS]
    format_choice = rs.ListBox(format_labels, "Choose the file type", "Snapshot 2D Export")
    if not format_choice:
        return
    extension = None
    for label, ext in FORMATS:
        if label == format_choice:
            extension = ext
            break
    if not extension:
        return

    selected = rs.MultiListBox(
        names,
        "Select the snapshots to export",
        "Snapshot 2D Export",
    )
    if not selected:
        return

    start_folder = rs.DocumentPath() or os.path.expanduser("~")
    folder = rs.BrowseForFolder(start_folder, "Folder for the 2D files", "Snapshot 2D Export")
    if not folder:
        return
    if not os.path.isdir(folder):
        rs.MessageBox("That folder is not available.", 0, "Snapshot 2D Export")
        return

    exported = []
    skipped = []
    used_names = set()

    for index, name in enumerate(selected):
        Rhino.RhinoApp.Wait()
        if sc.escape_test(False):
            skipped.append("{} (cancelled)".format(name))
            break

        print("Snapshot 2D {}/{}: {}".format(index + 1, len(selected), name))
        if not restore_snapshot(name):
            skipped.append("{} (could not restore)".format(name))
            continue

        viewport = active_viewport()
        if viewport is None:
            skipped.append("{} (no active view)".format(name))
            continue

        try:
            silhouettes, curves = collect_visible_curves(viewport)
        except Exception as exc:
            skipped.append("{} ({})".format(name, exc))
            continue

        drawing = silhouettes + curves
        if not drawing:
            skipped.append("{} (no visible curves)".format(name))
            continue

        move_to_origin(drawing)
        filename = unique_filename(used_names, name, extension)
        path = os.path.join(folder, filename)
        try:
            ok = write_snapshot_file(silhouettes, curves, path, extension)
        except Exception as exc:
            skipped.append("{} ({})".format(name, exc))
            continue
        if not ok or not os.path.isfile(path) or os.path.getsize(path) < 1:
            skipped.append("{} (export failed)".format(name))
            continue
        exported.append(filename)

    sc.doc.Views.Redraw()

    lines = [
        "Exported {} of {} snapshots as {}.".format(
            len(exported),
            len(selected),
            extension,
        ),
        "Folder:",
        folder,
        "",
        "The model is left on the last snapshot that was restored.",
    ]
    if skipped:
        lines.append("")
        lines.append("Skipped:")
        lines.extend(skipped)
    rs.MessageBox("\n".join(lines), 0, "Snapshot 2D Export")


main()
