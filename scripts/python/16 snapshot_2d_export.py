"""
Make a 2D drawing of the view stored in each chosen snapshot and export it.

Uses Make2D with Projection set to View, so only the snapshot's current
view is drawn. Properties come from the input objects, with tangent edges,
scene silhouettes, no hidden lines, grouped output, and layer name "2d".
The 2D curves are removed from the model after each file is written.
"""

import os

import Rhino
import System
import rhinoscriptsyntax as rs
import scriptcontext as sc


FORMATS = [
    ("Adobe Illustrator (.ai)", ".ai"),
    ("EPS (.eps)", ".eps"),
    ("PDF (.pdf)", ".pdf"),
]

LAYER_NAME = "2d"
PAGE_WIDTH_IN = 16.0
PAGE_HEIGHT_IN = 10.0
PAGE_MARGIN_IN = 0.5


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


def is_output_layer(layer_index):
    try:
        layer = sc.doc.Layers[layer_index]
    except Exception:
        return False
    if layer is None:
        return False
    full = layer.FullPath or ""
    return full == LAYER_NAME or full.startswith(LAYER_NAME + "::")


def select_source_objects():
    rs.UnselectAllObjects()
    count = 0
    for obj in sc.doc.Objects:
        if obj is None or obj.IsDeleted:
            continue
        try:
            selectable = obj.IsSelectable(True, False, False, False)
        except Exception:
            selectable = False
        if not selectable or is_output_layer(obj.Attributes.LayerIndex):
            continue
        obj.Select(True)
        count += 1
    return count


def object_ids():
    found = []
    for obj in sc.doc.Objects:
        if obj is not None and not obj.IsDeleted:
            found.append(obj.Id)
    return found


def run_make2d():
    # Projection=View draws only the active view. Restoring the snapshot
    # first makes that view the one on screen.
    script = " ".join([
        "_-Make2D",
        "_Layout=_View",
        "_Properties=_FromInputObjects",
        "_ShowTangents=_Yes",
        "_CreateHiddenLines=_No",
        "_CreateSceneSilhouette=_Yes",
        "_CreateClippingPlaneIntersections=_No",
        "_ShowViewRectangle=_No",
        "_GroupOutput=_Yes",
        '_LayerName "{}"'.format(LAYER_NAME),
        "_Enter",
    ])
    rs.Command(script, echo=False)
    Rhino.RhinoApp.Wait()
    try:
        return int(rs.LastCommandResult()) == 0
    except Exception:
        return bool(rs.LastCommandResult() == 0)


def drawing_bounds(object_ids_to_measure):
    box = Rhino.Geometry.BoundingBox.Empty
    for obj_id in object_ids_to_measure:
        rhobj = sc.doc.Objects.FindId(obj_id)
        if rhobj is None or rhobj.Geometry is None:
            continue
        box.Union(rhobj.Geometry.GetBoundingBox(True))
    return box


def fit_to_page(box):
    """Scale model-unit drawing geometry so the whole sheet fits a tabloid page."""
    width = box.Max.X - box.Min.X
    height = box.Max.Y - box.Min.Y
    if width <= 1e-9 or height <= 1e-9:
        return None
    to_inches = Rhino.RhinoMath.UnitScale(sc.doc.ModelUnitSystem, Rhino.UnitSystem.Inches)
    usable_w = PAGE_WIDTH_IN - (2.0 * PAGE_MARGIN_IN)
    usable_h = PAGE_HEIGHT_IN - (2.0 * PAGE_MARGIN_IN)
    scale = min(usable_w / (width * to_inches), usable_h / (height * to_inches))
    move = Rhino.Geometry.Transform.Translation(-box.Min.X, -box.Min.Y, -box.Min.Z)
    scale_xform = Rhino.Geometry.Transform.Scale(Rhino.Geometry.Point3d.Origin, scale * to_inches)
    margin = Rhino.Geometry.Transform.Translation(PAGE_MARGIN_IN, PAGE_MARGIN_IN, 0.0)
    return margin * scale_xform * move


def ensure_layer_path(doc, full_path):
    parent_index = -1
    built = []
    index = -1
    for part in (full_path or LAYER_NAME).split("::"):
        if not part:
            continue
        built.append(part)
        path = "::".join(built)
        index = doc.Layers.FindByFullPath(path, -1)
        if index >= 0:
            parent_index = index
            continue
        layer = Rhino.DocObjects.Layer()
        layer.Name = part
        layer.Color = System.Drawing.Color.Black
        if parent_index >= 0:
            layer.ParentLayerId = doc.Layers[parent_index].Id
        index = doc.Layers.Add(layer)
        parent_index = index
    return index


def copy_drawing(doc, object_ids_to_copy, xform):
    added = 0
    for obj_id in object_ids_to_copy:
        rhobj = sc.doc.Objects.FindId(obj_id)
        if rhobj is None or rhobj.Geometry is None:
            continue
        geom = rhobj.Geometry.Duplicate()
        if geom is None:
            continue
        geom.Transform(xform)
        try:
            source_layer = sc.doc.Layers[rhobj.Attributes.LayerIndex]
            full_path = source_layer.FullPath
        except Exception:
            full_path = LAYER_NAME
        layer_index = ensure_layer_path(doc, full_path)
        attributes = doc.CreateDefaultAttributes()
        if layer_index >= 0:
            attributes.LayerIndex = layer_index
        try:
            attributes.ColorSource = rhobj.Attributes.ColorSource
            attributes.ObjectColor = rhobj.Attributes.ObjectColor
            attributes.PlotWeightSource = rhobj.Attributes.PlotWeightSource
            attributes.PlotWeight = rhobj.Attributes.PlotWeight
        except Exception:
            pass
        if doc.Objects.Add(geom, attributes) != System.Guid.Empty:
            added += 1
    return added


def apply_ai_units(options):
    units = getattr(Rhino.FileIO.FileAiWriteOptions, "Units", None)
    inches = getattr(units, "Inches", None) if units is not None else None
    if inches is not None:
        options.AiUnits = inches


def export_drawing(doc, path, extension):
    try:
        doc.AdjustModelUnitSystem(Rhino.UnitSystem.Inches, False)
    except Exception:
        pass
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


def write_snapshot_file(object_ids_to_copy, path, extension):
    box = drawing_bounds(object_ids_to_copy)
    if not box.IsValid:
        return False
    xform = fit_to_page(box)
    if xform is None:
        return False
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    if doc is None:
        raise RuntimeError("Could not create a drawing document")
    try:
        if copy_drawing(doc, object_ids_to_copy, xform) < 1:
            return False
        return export_drawing(doc, path, extension)
    finally:
        doc.Dispose()


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


def delete_objects(obj_ids):
    if not obj_ids:
        return
    try:
        rs.DeleteObjects(obj_ids)
    except Exception:
        for obj_id in obj_ids:
            try:
                sc.doc.Objects.Delete(obj_id, True)
            except Exception:
                pass


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
        new_ids = []
        try:
            if not restore_snapshot(name):
                skipped.append("{} (could not restore)".format(name))
                continue
            if select_source_objects() < 1:
                skipped.append("{} (nothing visible to draw)".format(name))
                continue

            before = set(object_ids())
            if not run_make2d():
                skipped.append("{} (Make2D did not finish)".format(name))
                continue
            new_ids = [obj_id for obj_id in object_ids() if obj_id not in before]
            if not new_ids:
                skipped.append("{} (no 2D curves)".format(name))
                continue

            filename = unique_filename(used_names, name, extension)
            path = os.path.join(folder, filename)
            ok = write_snapshot_file(new_ids, path, extension)
            if not ok or not os.path.isfile(path) or os.path.getsize(path) < 1:
                skipped.append("{} (export failed)".format(name))
                continue
            exported.append(filename)
        except Exception as exc:
            skipped.append("{} ({})".format(name, exc))
        finally:
            delete_objects(new_ids)
            rs.UnselectAllObjects()

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
        "Each file is only the view stored in that snapshot.",
        "The drawing is fitted onto the page.",
        "The model is left on the last snapshot that was restored.",
    ]
    if skipped:
        lines.append("")
        lines.append("Skipped:")
        lines.extend(skipped)
    rs.MessageBox("\n".join(lines), 0, "Snapshot 2D Export")


main()
