"""
Make a 2D drawing of the view stored in each chosen snapshot and export it.

Restores the snapshot, selects the visible model, and runs Make2D on
that view only. Tangent edges and scene silhouettes are included. Hidden
lines are not. The Make2D curves are removed from the model after export.
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
SILHOUETTE_NONE = getattr(Rhino.Geometry.SilhouetteType, "None")
SILHOUETTE_TANGENT = getattr(Rhino.Geometry.SilhouetteType, "Tangent", None)


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
    viewport = view.ActiveViewport
    try:
        if viewport.Size.Width < 2 or viewport.Size.Height < 2:
            return None
    except Exception:
        return None
    return viewport


def layer_is_visible(layer_index):
    try:
        layer = sc.doc.Layers[layer_index]
    except Exception:
        return True
    for _step in range(32):
        if layer is None or not layer.IsVisible:
            return False
        parent_id = layer.ParentLayerId
        if parent_id == System.Guid.Empty:
            return True
        parent = sc.doc.Layers.FindId(parent_id)
        if isinstance(parent, int):
            if parent < 0:
                return True
            layer = sc.doc.Layers[parent]
        else:
            layer = parent
    return True


def append_drawable(obj, extra_xform, bucket, depth):
    if obj is None or depth > 16 or obj.IsDeleted:
        return
    try:
        if obj.IsHidden:
            return
    except Exception:
        pass
    try:
        if not layer_is_visible(obj.Attributes.LayerIndex):
            return
    except Exception:
        pass
    geom = obj.Geometry
    if geom is None:
        return
    duplicate = geom.Duplicate()
    if duplicate is None:
        return
    geom = duplicate
    if isinstance(geom, Rhino.Geometry.InstanceReferenceGeometry):
        xform = geom.Xform
        if extra_xform is not None:
            xform = extra_xform * geom.Xform
        idef = sc.doc.InstanceDefinitions.FindId(geom.ParentIdefId)
        if idef is None:
            return
        try:
            members = idef.GetObjects()
        except Exception:
            members = None
        if not members:
            return
        for member in members:
            append_drawable(member, xform, bucket, depth + 1)
        return
    xform = extra_xform if extra_xform is not None else Rhino.Geometry.Transform.Identity
    bucket.append((geom, xform))


def add_drawable_geometry(parameters):
    bucket = []
    for obj in sc.doc.Objects:
        if obj is None or obj.IsDeleted:
            continue
        try:
            selectable = obj.IsSelectable(True, False, False, False)
        except Exception:
            selectable = False
        if not selectable:
            continue
        append_drawable(obj, None, bucket, 0)
    added = 0
    for geom, xform in bucket:
        try:
            ok = parameters.AddGeometry(geom, xform, "snapshot")
        except Exception:
            ok = False
        if ok:
            added += 1
    return added


def screen_transform(viewport):
    xform = viewport.GetTransform(
        Rhino.DocObjects.CoordinateSystem.World,
        Rhino.DocObjects.CoordinateSystem.Screen,
    )
    height = float(viewport.Size.Height)
    return xform, height


def sample_points(curve):
    try:
        ok, polyline = curve.TryGetPolyline()
    except Exception:
        ok, polyline = False, None
    if ok and polyline is not None and len(polyline) >= 2:
        return list(polyline)
    try:
        length = curve.GetLength()
    except Exception:
        length = 0.0
    count = 12
    if length > 0.0:
        count = int(length / max(sc.doc.ModelAbsoluteTolerance * 10.0, 0.05))
        count = max(8, min(count, 80))
    parameters = curve.DivideByCount(count, True)
    if not parameters:
        return [curve.PointAtStart, curve.PointAtEnd]
    return [curve.PointAt(parameter) for parameter in parameters]


def map_to_screen(point, xform):
    x_value = point.X
    y_value = point.Y
    z_value = point.Z
    screen_x = xform.M00 * x_value + xform.M01 * y_value + xform.M02 * z_value + xform.M03
    screen_y = xform.M10 * x_value + xform.M11 * y_value + xform.M12 * z_value + xform.M13
    weight = xform.M30 * x_value + xform.M31 * y_value + xform.M32 * z_value + xform.M33
    if weight < 1e-9:
        return None
    return screen_x / weight, screen_y / weight


def project_curve(curve, xform, height):
    projected = []
    for point in sample_points(curve):
        mapped = map_to_screen(point, xform)
        if mapped is None:
            continue
        screen_x, screen_y = mapped
        # Screen Y grows downward. PDF Y grows upward.
        y_value = height - screen_y
        if abs(screen_x) > 100000.0 or abs(y_value) > 100000.0:
            continue
        projected.append(Rhino.Geometry.Point3d(screen_x, y_value, 0.0))
    if len(projected) < 2:
        return None
    return Rhino.Geometry.PolylineCurve(projected)


def layer_for_segment(segment):
    if segment.IsSceneSilhouette:
        return LAYER_NAME + "::Visible::SceneSilhouetteCurves"
    parent = segment.ParentCurve
    if parent is not None and SILHOUETTE_TANGENT is not None:
        if parent.SilhouetteType == SILHOUETTE_TANGENT:
            return LAYER_NAME + "::Visible::Tangents"
    return LAYER_NAME + "::Visible::Curves"


def project_view(viewport):
    parameters = Rhino.Geometry.HiddenLineDrawingParameters()
    parameters.AbsoluteTolerance = sc.doc.ModelAbsoluteTolerance
    parameters.Flatten = False
    parameters.IncludeHiddenCurves = False
    parameters.IncludeTangentEdges = True
    parameters.SetViewport(viewport)
    if add_drawable_geometry(parameters) < 1:
        raise RuntimeError("no surfaces or meshes were visible")
    drawing = Rhino.Geometry.HiddenLineDrawing.Compute(parameters, True)
    if drawing is None:
        return []
    xform, height = screen_transform(viewport)
    if xform is None or not xform.IsValid or height < 2.0:
        raise RuntimeError("could not read the snapshot view")
    projected = []
    for segment in drawing.Segments:
        if not segment or not segment.ParentCurve or not segment.CurveGeometry:
            continue
        if not segment_is_drawn(segment):
            continue
        curve = project_curve(segment.CurveGeometry, xform, height)
        if curve is None:
            continue
        projected.append((curve, layer_for_segment(segment)))
    return projected


def segment_is_drawn(segment):
    try:
        name = str(segment.SegmentVisibility)
    except Exception:
        return True
    return ("Hidden" not in name) and ("Clipped" not in name)


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


def page_transform(box):
    """Scale screen-space curves onto the page without changing their proportions."""
    width = box.Max.X - box.Min.X
    height = box.Max.Y - box.Min.Y
    if width <= 1e-9 or height <= 1e-9:
        return None
    usable_w = PAGE_WIDTH_PT - (2.0 * PAGE_MARGIN_PT)
    usable_h = PAGE_HEIGHT_PT - (2.0 * PAGE_MARGIN_PT)
    scale = min(usable_w / width, usable_h / height)
    move = Rhino.Geometry.Transform.Translation(-box.Min.X, -box.Min.Y, -box.Min.Z)
    scale_xform = Rhino.Geometry.Transform.Scale(Rhino.Geometry.Point3d.Origin, scale)
    margin = Rhino.Geometry.Transform.Translation(PAGE_MARGIN_PT, PAGE_MARGIN_PT, 0.0)
    return margin * scale_xform * move


def add_curves(doc, items, xform):
    added = 0
    for curve, full_path in items:
        geom = curve.Duplicate()
        if geom is None:
            continue
        geom.Transform(xform)
        layer_index = ensure_layer_path(doc, full_path)
        attributes = doc.CreateDefaultAttributes()
        if layer_index >= 0:
            attributes.LayerIndex = layer_index
        if doc.Objects.Add(geom, attributes) != System.Guid.Empty:
            added += 1
    return added


def apply_ai_units(options):
    units = getattr(Rhino.FileIO.FileAiWriteOptions, "Units", None)
    inches = getattr(units, "Inches", None) if units is not None else None
    if inches is not None:
        options.AiUnits = inches


PATH_COMMANDS = set(["m", "l", "L", "c", "C", "v", "V", "y", "Y"])
PAGE_WIDTH_PT = 792.0
PAGE_HEIGHT_PT = 612.0
PAGE_MARGIN_PT = 36.0


def path_coordinates(line):
    parts = line.split()
    if len(parts) < 3 or parts[-1] not in PATH_COMMANDS:
        return None
    try:
        numbers = [float(part) for part in parts[:-1]]
    except ValueError:
        return None
    if len(numbers) < 2 or len(numbers) % 2 != 0:
        return None
    return numbers, parts[-1]


def fit_vector_file_to_page(path):
    """Rhino writes the curves in a tiny coordinate range. Scale them onto the page."""
    try:
        raw = open(path, "rb").read()
    except Exception:
        return False
    newline = "\r\n" if b"\r\n" in raw[:200] else "\n"
    text = raw.decode("latin1")
    lines = text.splitlines()
    parsed = [path_coordinates(line) for line in lines]
    xs = []
    ys = []
    for item in parsed:
        if not item:
            continue
        numbers, _cmd = item
        xs.extend(numbers[0::2])
        ys.extend(numbers[1::2])
    if not xs:
        return False
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if width < 1e-9 or height < 1e-9:
        return False
    usable_w = PAGE_WIDTH_PT - (2.0 * PAGE_MARGIN_PT)
    usable_h = PAGE_HEIGHT_PT - (2.0 * PAGE_MARGIN_PT)
    scale = min(usable_w / width, usable_h / height)

    def map_x(value):
        return PAGE_MARGIN_PT + (value - min_x) * scale

    def map_y(value):
        return PAGE_MARGIN_PT + (value - min_y) * scale

    output = []
    for line, item in zip(lines, parsed):
        if item:
            numbers, cmd = item
            mapped = []
            for index in range(0, len(numbers), 2):
                mapped.append("{:.4f}".format(map_x(numbers[index])))
                mapped.append("{:.4f}".format(map_y(numbers[index + 1])))
            mapped.append(cmd)
            output.append(" ".join(mapped))
            continue
        if line.startswith("%%BoundingBox:"):
            output.append("%%BoundingBox: 0 0 {:.0f} {:.0f}".format(PAGE_WIDTH_PT, PAGE_HEIGHT_PT))
        elif line.startswith("%AI3_TileBox:"):
            output.append("%AI3_TileBox: 0 0 {:.0f} {:.0f}".format(PAGE_WIDTH_PT, PAGE_HEIGHT_PT))
        elif line.startswith("%AI3_TemplateBox:"):
            output.append("%AI3_TemplateBox: 0 0 {:.0f} {:.0f}".format(PAGE_WIDTH_PT, PAGE_HEIGHT_PT))
        else:
            output.append(line)
    data = newline.join(output) + newline
    with open(path, "wb") as handle:
        handle.write(data.encode("latin1"))
    return True


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


def curve_points(curve):
    try:
        ok, polyline = curve.TryGetPolyline()
    except Exception:
        ok, polyline = False, None
    if ok and polyline is not None and len(polyline) >= 2:
        return [(point.X, point.Y) for point in polyline]
    return []


def build_vector_pdf(polylines, page_width, page_height, stroke_width):
    """Write a one-page PDF whose lines are vector paths, in points, origin bottom-left."""
    commands = []
    for polyline in polylines:
        if len(polyline) < 2:
            continue
        x0, y0 = polyline[0]
        commands.append("{:.3f} {:.3f} m".format(x0, y0))
        for x_value, y_value in polyline[1:]:
            commands.append("{:.3f} {:.3f} l".format(x_value, y_value))
        commands.append("S")
    if not commands:
        return None
    content = "{:.3f} w\n1 J\n1 j\n0 0 0 RG\n".format(stroke_width)
    content += "\n".join(commands) + "\n"
    stream = content.encode("ascii")
    header = b"%PDF-1.4\n"
    page = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.3f} {h:.3f}] /CropBox [0 0 {w:.3f} {h:.3f}] /Contents 4 0 R /Resources << >> >>".format(
        w=page_width, h=page_height
    )
    bodies = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        "3 0 obj\n{}\nendobj\n".format(page),
    ]
    stream_obj = ("4 0 obj\n<< /Length {} >>\nstream\n".format(len(stream))).encode("ascii")
    stream_obj += stream + b"endstream\nendobj\n"
    chunks = [header]
    offsets = [0]
    position = len(header)
    for body in bodies:
        offsets.append(position)
        piece = body.encode("ascii")
        chunks.append(piece)
        position += len(piece)
    offsets.append(position)
    chunks.append(stream_obj)
    position += len(stream_obj)
    xref_at = position
    xref_lines = ["xref", "0 5", "0000000000 65535 f "]
    for offset in offsets[1:]:
        xref_lines.append("{:010d} 00000 n ".format(offset))
    trailer = "\n".join(xref_lines)
    trailer += "\ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(xref_at)
    chunks.append(trailer.encode("ascii"))
    return b"".join(chunks)


def write_vector_pdf(curves, path):
    polylines = []
    for curve in curves:
        points = curve_points(curve)
        if len(points) >= 2:
            polylines.append(points)
    data = build_vector_pdf(polylines, PAGE_WIDTH_PT, PAGE_HEIGHT_PT, 0.5)
    if not data or (b" m\n" not in data):
        return False
    with open(path, "wb") as handle:
        handle.write(data)
    return True


def write_snapshot_file(items, path, extension):
    box = Rhino.Geometry.BoundingBox.Empty
    for curve, _full_path in items:
        box.Union(curve.GetBoundingBox(True))
    if not box.IsValid:
        return False
    xform = page_transform(box)
    if xform is None:
        return False
    fitted = []
    for curve, full_path in items:
        geom = curve.Duplicate()
        if geom is None:
            continue
        geom.Transform(xform)
        fitted.append((geom, full_path))
    if not fitted:
        return False
    if extension == ".pdf":
        return write_vector_pdf([curve for curve, _full_path in fitted], path)
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    if doc is None:
        raise RuntimeError("Could not create a drawing document")
    try:
        try:
            doc.ModelUnitSystem = Rhino.UnitSystem.Inches
        except Exception:
            pass
        if add_curves(doc, fitted, Rhino.Geometry.Transform.Identity) < 1:
            return False
        if not export_drawing(doc, path, extension):
            return False
        if extension in (".ai", ".eps"):
            fit_vector_file_to_page(path)
        return True
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


def is_output_layer(layer_index):
    try:
        layer = sc.doc.Layers[layer_index]
    except Exception:
        return False
    if layer is None:
        return False
    full = layer.FullPath or ""
    return full == LAYER_NAME or full.startswith(LAYER_NAME + "::")


def object_ids():
    found = []
    for obj in sc.doc.Objects:
        if obj is not None and not obj.IsDeleted:
            found.append(obj.Id)
    return found


def select_all_for_make2d():
    rs.UnselectAllObjects()
    count = 0
    for obj in sc.doc.Objects:
        if obj is None or obj.IsDeleted or is_output_layer(obj.Attributes.LayerIndex):
            continue
        try:
            selectable = obj.IsSelectable(True, False, False, False)
        except Exception:
            selectable = False
        if not selectable:
            continue
        obj.Select(True)
        count += 1
    return count


def run_make2d():
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


def curves_from_objects(obj_ids):
    items = []
    for obj_id in obj_ids:
        rhobj = sc.doc.Objects.FindId(obj_id)
        if rhobj is None or rhobj.Geometry is None:
            continue
        geom = rhobj.Geometry.Duplicate()
        if not isinstance(geom, Rhino.Geometry.Curve):
            continue
        try:
            full_path = sc.doc.Layers[rhobj.Attributes.LayerIndex].FullPath or LAYER_NAME
        except Exception:
            full_path = LAYER_NAME
        items.append((geom, full_path))
    return items


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
            sc.doc.Views.Redraw()
            Rhino.RhinoApp.Wait()
            if select_all_for_make2d() < 1:
                skipped.append("{} (nothing visible to draw)".format(name))
                continue
            before = set(object_ids())
            if not run_make2d():
                skipped.append("{} (Make2D did not finish)".format(name))
                continue
            new_ids = [obj_id for obj_id in object_ids() if obj_id not in before]
            items = curves_from_objects(new_ids)
            if not items:
                skipped.append("{} (no 2D curves)".format(name))
                continue

            filename = unique_filename(used_names, name, extension)
            path = os.path.join(folder, filename)
            ok = write_snapshot_file(items, path, extension)
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
        "Each file is the Make2D of the view stored in that snapshot.",
        "PDF lines are vectors, so they stay sharp in InDesign.",
        "The model is left on the last snapshot that was restored.",
    ]
    if skipped:
        lines.append("")
        lines.append("Skipped:")
        lines.extend(skipped)
    rs.MessageBox("\n".join(lines), 0, "Snapshot 2D Export")


main()
