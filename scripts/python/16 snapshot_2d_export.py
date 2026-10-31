"""
Make a 2D drawing of the view stored in each chosen snapshot and export it.

Restores the snapshot, then either runs Make2D for a line drawing or
captures a high-resolution shaded view with flat color. Make2D includes
tangent edges and scene silhouettes, and those curves are removed after export.
"""

import os

import Rhino
import System
import System.Drawing
import System.Runtime.InteropServices
import rhinoscriptsyntax as rs
import scriptcontext as sc


FORMATS = [
    ("Adobe Illustrator (.ai)", ".ai", "lines"),
    ("EPS (.eps)", ".eps", "lines"),
    ("PDF (.pdf)", ".pdf", "lines"),
    ("Shaded view, high resolution (.png)", ".png", "shaded"),
    ("Cartoon (.png)", ".png", "cartoon"),
]

RENDER_LONG_EDGE = 4800
RENDER_DPI = 300.0
RENDER_SUPERSAMPLE = 2
COMIC_MODE_NAME = "NP Comic"
COMIC_EDGE_PIXELS = 6
COMIC_CAPTURE_SCALE = 2

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


def render_pixel_size(viewport):
    width = float(viewport.Size.Width)
    height = float(viewport.Size.Height)
    if width < 2.0 or height < 2.0:
        return RENDER_LONG_EDGE, int(RENDER_LONG_EDGE * 0.75)
    if width >= height:
        pixel_width = RENDER_LONG_EDGE
        pixel_height = max(1, int(round(RENDER_LONG_EDGE * height / width)))
    else:
        pixel_height = RENDER_LONG_EDGE
        pixel_width = max(1, int(round(RENDER_LONG_EDGE * width / height)))
    return pixel_width, pixel_height


def set_display_mode(view, mode_name):
    mode = Rhino.Display.DisplayModeDescription.FindByName(mode_name)
    if mode is None:
        return False
    view.ActiveViewport.DisplayMode = mode
    view.Redraw()
    Rhino.RhinoApp.Wait()
    return True


def capture_view_bitmap(view, pixel_width, pixel_height, passes):
    capture = Rhino.Display.ViewCapture()
    capture.Width = int(pixel_width)
    capture.Height = int(pixel_height)
    for prop, value in (
        ("ScaleScreenItems", False),
        ("DrawAxes", False),
        ("DrawGrid", False),
        ("DrawGridAxes", False),
        ("TransparentBackground", False),
        ("RealtimeRenderPasses", int(passes)),
    ):
        try:
            setattr(capture, prop, value)
        except Exception:
            pass
    view.Redraw()
    Rhino.RhinoApp.Wait()
    bitmap = None
    try:
        bitmap = capture.CaptureToBitmap(view)
    except Exception:
        try:
            bitmap = capture.CaptureToBitmap(view.ActiveViewport)
        except Exception:
            bitmap = None
    if passes or bitmap_has_content(bitmap):
        return bitmap
    if bitmap is not None:
        bitmap.Dispose()
    try:
        return view.CaptureToBitmap(System.Drawing.Size(int(pixel_width), int(pixel_height)))
    except Exception:
        return None


def downscale_bitmap(source, width, height):
    result = System.Drawing.Bitmap(int(width), int(height))
    result.SetResolution(RENDER_DPI, RENDER_DPI)
    graphics = System.Drawing.Graphics.FromImage(result)
    try:
        graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic
        graphics.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality
        graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.HighQuality
        graphics.DrawImage(source, 0, 0, int(width), int(height))
    finally:
        graphics.Dispose()
    return result


def display_enum(enum_name, member_name):
    enum_type = getattr(Rhino.Display.DisplayPipelineAttributes, enum_name, None)
    if enum_type is None:
        return None
    return getattr(enum_type, member_name, None)


def assign_display(attrs, prop, value):
    if value is None:
        return
    try:
        setattr(attrs, prop, value)
    except Exception:
        pass


def ensure_comic_mode():
    """Rendered panel color, with the same edge lines Rhino shows, drawn in black."""
    source = Rhino.Display.DisplayModeDescription.FindByName("Rendered")
    if source is None:
        return None
    mode = Rhino.Display.DisplayModeDescription.FindByName(COMIC_MODE_NAME)
    if mode is None:
        try:
            added = Rhino.Display.DisplayModeDescription.AddDisplayMode(COMIC_MODE_NAME)
        except Exception:
            added = None
        if added is not None and not isinstance(added, bool):
            mode = added
        else:
            mode = Rhino.Display.DisplayModeDescription.FindByName(COMIC_MODE_NAME)
    if mode is None:
        return source
    try:
        attrs = source.DisplayAttributes
        black = System.Drawing.Color.Black
        single = display_enum("SurfaceEdgeColorUse", "SingleColorForAll")
        naked_single = display_enum("SurfaceNakedEdgeColorUse", "SingleColorForAll")
        pixels = display_enum("SurfaceThicknessUse", "Pixels")
        naked_pixels = display_enum("SurfaceNakedEdgeThicknessUse", "Pixels")
        edge = int(COMIC_EDGE_PIXELS)
        for prop, value in (
            ("ShowSurfaceEdges", True),
            ("ShowSurfaceEdge", True),
            ("ShowSurfaceNakedEdge", True),
            ("ShowMeshEdges", True),
            ("ShowMeshNakedEdges", True),
            ("FlatShade", True),
            ("ShadingEnabled", True),
            ("SurfaceEdgeColor", black),
            ("SurfaceNakedEdgeColor", black),
            ("MeshEdgeColor", black),
            ("MeshNakedEdgeColor", black),
            ("SurfaceEdgeColorUsage", single),
            ("SurfaceNakedEdgeColorUsage", naked_single),
            ("SurfaceEdgeColorReduction", 0),
            ("SurfaceEdgeColorReductionPercent", 0),
            ("SurfaceEdgeThickness", edge),
            ("SurfaceNakedEdgeThickness", edge),
            ("MeshEdgeThickness", edge),
            ("MeshNakedEdgeThickness", edge),
        ):
            assign_display(attrs, prop, value)
        if pixels is not None:
            try:
                attrs.SetSurfaceEdgeThicknessUsage(pixels)
            except Exception:
                pass
        if naked_pixels is not None:
            try:
                attrs.SetSurfaceNakedEdgeThicknessUsage(naked_pixels)
            except Exception:
                pass
        mode.DisplayAttributes = attrs
    except Exception:
        return source
    return mode


def byte_at(raw, index):
    try:
        return int(raw[index]) & 255
    except Exception:
        return int(raw.GetValue(index)) & 255


def outline_mask(bitmap):
    """Black lines on a clear background, matched to the smooth edge in the capture."""
    width = bitmap.Width
    height = bitmap.Height
    detect_width = min(width, 2400)
    detect_height = max(1, int(round(height * float(detect_width) / float(width))))
    small = downscale_bitmap(bitmap, detect_width, detect_height)
    try:
        pixel_format = System.Drawing.Imaging.PixelFormat.Format32bppArgb
        rect = System.Drawing.Rectangle(0, 0, detect_width, detect_height)
        data = small.LockBits(rect, System.Drawing.Imaging.ImageLockMode.ReadOnly, pixel_format)
        try:
            stride = data.Stride
            count = abs(stride) * detect_height
            raw = System.Array.CreateInstance(System.Byte, count)
            System.Runtime.InteropServices.Marshal.Copy(data.Scan0, raw, 0, count)
        finally:
            small.UnlockBits(data)
        total = detect_width * detect_height
        lum = bytearray(total)
        stride_abs = abs(stride)
        for y_value in range(detect_height):
            source_y = y_value if stride >= 0 else (detect_height - 1 - y_value)
            row = source_y * stride_abs
            base = y_value * detect_width
            for x_value in range(detect_width):
                pixel = row + (x_value * 4)
                red = byte_at(raw, pixel + 2)
                green = byte_at(raw, pixel + 1)
                blue = byte_at(raw, pixel)
                lum[base + x_value] = (red * 3 + green * 6 + blue) // 10
        threshold = 28
        edge = bytearray(total)
        for y_value in range(1, detect_height - 1):
            row = y_value * detect_width
            for x_value in range(1, detect_width - 1):
                center = lum[row + x_value]
                contrast = max(
                    abs(center - lum[row + x_value + 1]),
                    abs(center - lum[row + detect_width + x_value]),
                    abs(center - lum[row + x_value - 1]),
                    abs(center - lum[row - detect_width + x_value]),
                )
                if contrast >= threshold:
                    edge[row + x_value] = 1
        keep = bytearray(total)
        for y_value in range(1, detect_height - 1):
            row = y_value * detect_width
            for x_value in range(1, detect_width - 1):
                if not edge[row + x_value]:
                    continue
                neighbors = (
                    edge[row - detect_width + x_value - 1]
                    + edge[row - detect_width + x_value]
                    + edge[row - detect_width + x_value + 1]
                    + edge[row + x_value - 1]
                    + edge[row + x_value]
                    + edge[row + x_value + 1]
                    + edge[row + detect_width + x_value - 1]
                    + edge[row + detect_width + x_value]
                    + edge[row + detect_width + x_value + 1]
                )
                if neighbors >= 3:
                    keep[row + x_value] = 1
        radius = 2
        horizontal = bytearray(total)
        for y_value in range(detect_height):
            row = y_value * detect_width
            count = 0
            for x_value in range(min(detect_width, radius + 1)):
                count += keep[row + x_value]
            for x_value in range(detect_width):
                if count:
                    horizontal[row + x_value] = 1
                remove_at = x_value - radius
                if remove_at >= 0:
                    count -= keep[row + remove_at]
                add_at = x_value + radius + 1
                if add_at < detect_width:
                    count += keep[row + add_at]
        inked = bytearray(total)
        for x_value in range(detect_width):
            count = 0
            for y_value in range(min(detect_height, radius + 1)):
                count += horizontal[(y_value * detect_width) + x_value]
            for y_value in range(detect_height):
                if count:
                    inked[(y_value * detect_width) + x_value] = 1
                remove_at = y_value - radius
                if remove_at >= 0:
                    count -= horizontal[(remove_at * detect_width) + x_value]
                add_at = y_value + radius + 1
                if add_at < detect_height:
                    count += horizontal[(add_at * detect_width) + x_value]
        mask = System.Drawing.Bitmap(detect_width, detect_height, pixel_format)
        mask_rect = System.Drawing.Rectangle(0, 0, detect_width, detect_height)
        mask_data = mask.LockBits(mask_rect, System.Drawing.Imaging.ImageLockMode.WriteOnly, pixel_format)
        try:
            mask_stride = mask_data.Stride
            mask_count = abs(mask_stride) * detect_height
            raw_mask = System.Array.CreateInstance(System.Byte, mask_count)
            for y_value in range(detect_height):
                if mask_stride >= 0:
                    row = y_value * mask_stride
                else:
                    row = (detect_height - 1 - y_value) * abs(mask_stride)
                base = y_value * detect_width
                for x_value in range(detect_width):
                    if not inked[base + x_value]:
                        continue
                    pixel = row + (x_value * 4)
                    raw_mask[pixel + 3] = 255
            System.Runtime.InteropServices.Marshal.Copy(raw_mask, 0, mask_data.Scan0, mask_count)
        finally:
            mask.UnlockBits(mask_data)
        sample = None
        for index in range(total):
            if inked[index]:
                sample = index
                break
        if sample is not None and mask.GetPixel(sample % detect_width, sample // detect_width).A < 200:
            graphics = System.Drawing.Graphics.FromImage(mask)
            graphics.Clear(System.Drawing.Color.FromArgb(0, 0, 0, 0))
            graphics.Dispose()
            black = System.Drawing.Color.FromArgb(255, 0, 0, 0)
            for y_value in range(detect_height):
                base = y_value * detect_width
                for x_value in range(detect_width):
                    if inked[base + x_value]:
                        mask.SetPixel(x_value, y_value, black)
        return mask
    finally:
        if small is not None and small is not bitmap:
            small.Dispose()


def ink_black_lines(bitmap):
    mask = outline_mask(bitmap)
    if mask is None:
        return bitmap
    graphics = System.Drawing.Graphics.FromImage(bitmap)
    try:
        graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic
        graphics.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality
        graphics.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceOver
        graphics.DrawImage(mask, 0, 0, bitmap.Width, bitmap.Height)
    finally:
        graphics.Dispose()
        mask.Dispose()
    return bitmap


def render_snapshot(path, style):
    view = sc.doc.Views.ActiveView
    if view is None:
        raise RuntimeError("no active view")
    rs.UnselectAllObjects()
    pixel_width, pixel_height = render_pixel_size(view.ActiveViewport)
    previous_mode = view.ActiveViewport.DisplayMode
    large = None
    bitmap = None
    try:
        if style == "cartoon":
            mode = ensure_comic_mode()
            if mode is not None:
                view.ActiveViewport.DisplayMode = mode
            scale = COMIC_CAPTURE_SCALE
        else:
            set_display_mode(view, "Shaded")
            scale = RENDER_SUPERSAMPLE
        view.Redraw()
        Rhino.RhinoApp.Wait()
        large = capture_view_bitmap(
            view,
            pixel_width * scale,
            pixel_height * scale,
            0,
        )
        if scale == 1 and bitmap_has_content(large):
            bitmap = large
            large = None
        elif bitmap_has_content(large):
            bitmap = downscale_bitmap(large, pixel_width, pixel_height)
        else:
            if large is not None:
                large.Dispose()
                large = None
            bitmap = capture_view_bitmap(view, pixel_width, pixel_height, 0)
        if not bitmap_has_content(bitmap):
            raise RuntimeError("view came out black")
        if style == "cartoon":
            ink_black_lines(bitmap)
        bitmap.SetResolution(RENDER_DPI, RENDER_DPI)
        bitmap.Save(path, System.Drawing.Imaging.ImageFormat.Png)
        return os.path.isfile(path) and os.path.getsize(path) > 1
    finally:
        if large is not None and large is not bitmap:
            large.Dispose()
        if bitmap is not None:
            bitmap.Dispose()
        try:
            view.ActiveViewport.DisplayMode = previous_mode
            view.Redraw()
        except Exception:
            pass


def bitmap_has_content(bitmap):
    if bitmap is None or bitmap.Width < 2 or bitmap.Height < 2:
        return False
    width = bitmap.Width
    height = bitmap.Height
    points = (
        (width // 2, height // 2),
        (width // 5, height // 5),
        (4 * width // 5, height // 2),
        (width // 2, 4 * height // 5),
        (width // 3, 2 * height // 3),
    )
    for x_value, y_value in points:
        color = bitmap.GetPixel(x_value, y_value)
        if color.R > 8 or color.G > 8 or color.B > 8:
            return True
    return False


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

    format_labels = [label for label, _ext, _style in FORMATS]
    format_choice = rs.ListBox(format_labels, "Choose the file type", "Snapshot 2D Export")
    if not format_choice:
        return
    extension = None
    style = "lines"
    for label, ext, item_style in FORMATS:
        if label == format_choice:
            extension = ext
            style = item_style
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
    if style == "cartoon":
        folder_prompt = "Folder for the cartoon views"
    elif style == "shaded":
        folder_prompt = "Folder for the shaded views"
    else:
        folder_prompt = "Folder for the 2D files"
    folder = rs.BrowseForFolder(start_folder, folder_prompt, "Snapshot 2D Export")
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
            filename = unique_filename(used_names, name, extension)
            path = os.path.join(folder, filename)
            if style in ("shaded", "cartoon"):
                ok = render_snapshot(path, style)
            else:
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
    ]
    if style == "cartoon":
        lines.append("Each file is a cartoon of that snapshot: flat color and a heavy black outline.")
        lines.append("The long edge is {} pixels at 300 dpi.".format(RENDER_LONG_EDGE))
    elif style == "shaded":
        lines.append("Each file is a high-resolution shaded view of that snapshot.")
        lines.append("Flat color, no wood grain, and no cast shadows.")
        lines.append("The long edge is {} pixels at 300 dpi.".format(RENDER_LONG_EDGE))
    else:
        lines.append("Each file is the Make2D of the view stored in that snapshot.")
        lines.append("PDF lines are vectors, so they stay sharp in InDesign.")
    lines.append("The model is left on the last snapshot that was restored.")
    if skipped:
        lines.append("")
        lines.append("Skipped:")
        lines.extend(skipped)
    rs.MessageBox("\n".join(lines), 0, "Snapshot 2D Export")


main()
