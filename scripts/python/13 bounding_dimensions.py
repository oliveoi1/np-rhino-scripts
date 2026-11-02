import math

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


ALLOWED_LAYERS = [
    "NP-Extrusions",
    "Layer 1",
    "NP-CNC",
    "NP-Extrusions-RCMaple",
    "NP-Extrusions-SCMaple",
    "NP-Extrusions-SCHPL",
    "NP-Extrusions-Acrylic",
    "NP-Furniture",
    "NP-Fittings",
]

SAMPLE_COUNT = 200


def is_allowed_layer(layer_name):
    if not layer_name:
        return False
    for allowed in ALLOWED_LAYERS:
        if layer_name == allowed:
            return True
        if layer_name.startswith(allowed + "::"):
            return True
    return False


def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)
    return name


def ensure_dashed_linetype():
    for name in ["Hidden", "Dashed"]:
        if rs.IsLinetype(name):
            return name
    return None


def fmt_num(val):
    try:
        return "{:.3f}".format(float(val))
    except Exception:
        try:
            return "{:.3f}".format(float(val[0]))
        except Exception:
            return str(val)


def get_area_value(area_result):
    if area_result is None:
        return None
    try:
        if isinstance(area_result, (list, tuple)):
            return float(area_result[0])
        return float(area_result)
    except Exception:
        return None


def ensure_temp_dimstyle():
    current_style = rs.CurrentDimStyle()
    temp_style = "NP_TEMP_3DEC"
    if not rs.IsDimStyle(temp_style):
        rs.AddDimStyle(temp_style)
        rs.DimStyleLinearPrecision(temp_style, 3)
    return current_style, temp_style


def get_valid_object():
    while True:
        obj = rs.GetObject("Select object for bounding box and dimensions", preselect=True)
        if not obj:
            return None

        if rs.IsBlockInstance(obj):
            return obj

        layer = rs.ObjectLayer(obj)
        if not is_allowed_layer(layer):
            rs.MessageBox("Object must be on an allowed layer.")
            rs.UnselectAllObjects()
            continue

        return obj


def get_instance_def_objects(block_name):
    try:
        return rs.BlockObjects(block_name)
    except Exception:
        return None


def combine_xforms(a, b):
    xform = Rhino.Geometry.Transform(a)
    xform *= b
    return xform


def transform_point(pt, xform):
    point = Rhino.Geometry.Point3d(pt.X, pt.Y, pt.Z)
    point.Transform(xform)
    return point


def update_extents(ext, point):
    if ext["xmin"] is None or point.X < ext["xmin"]:
        ext["xmin"] = point.X
    if ext["xmax"] is None or point.X > ext["xmax"]:
        ext["xmax"] = point.X
    if ext["ymin"] is None or point.Y < ext["ymin"]:
        ext["ymin"] = point.Y
    if ext["ymax"] is None or point.Y > ext["ymax"]:
        ext["ymax"] = point.Y
    if ext["zmin"] is None or point.Z < ext["zmin"]:
        ext["zmin"] = point.Z
    if ext["zmax"] is None or point.Z > ext["zmax"]:
        ext["zmax"] = point.Z


def add_plan_pt(pts_out, point):
    pts_out.append(Rhino.Geometry.Point3d(point.X, point.Y, 0.0))


def sample_curve_points(curve, xform, pts_out, ext):
    try:
        length = curve.GetLength()
        if length is None or length <= 0:
            domain = curve.Domain
            for i in range(SAMPLE_COUNT + 1):
                t = domain.ParameterAt(float(i) / float(SAMPLE_COUNT))
                point = transform_point(curve.PointAt(t), xform)
                add_plan_pt(pts_out, point)
                update_extents(ext, point)
            return

        div_count = max(SAMPLE_COUNT, int(length / 0.25))
        params = curve.DivideByCount(div_count, True)

        if params:
            for t in params:
                point = transform_point(curve.PointAt(t), xform)
                add_plan_pt(pts_out, point)
                update_extents(ext, point)
        else:
            domain = curve.Domain
            for i in range(SAMPLE_COUNT + 1):
                t = domain.ParameterAt(float(i) / float(SAMPLE_COUNT))
                point = transform_point(curve.PointAt(t), xform)
                add_plan_pt(pts_out, point)
                update_extents(ext, point)
    except Exception:
        pass


def collect_geom_points(obj_id, parent_xform, pts_out, ext):
    if not rs.IsObject(obj_id):
        return

    if rs.IsBlockInstance(obj_id):
        block_name = rs.BlockInstanceName(obj_id)
        if not block_name:
            return

        inst_xform = rs.BlockInstanceXform(obj_id)
        if not inst_xform:
            return

        total_xform = combine_xforms(parent_xform, inst_xform)
        child_ids = get_instance_def_objects(block_name)
        if not child_ids:
            return

        for child_id in child_ids:
            collect_geom_points(child_id, total_xform, pts_out, ext)
        return

    layer = rs.ObjectLayer(obj_id)
    if not is_allowed_layer(layer):
        return

    rhobj = rs.coercerhinoobject(obj_id, True, True)
    if not rhobj:
        return

    geom = rhobj.Geometry
    if geom is None:
        return

    try:
        if isinstance(geom, Rhino.Geometry.Curve):
            sample_curve_points(geom, parent_xform, pts_out, ext)
            return
    except Exception:
        pass

    try:
        brep = Rhino.Geometry.Brep.TryConvertBrep(geom)
    except Exception:
        brep = None

    if brep:
        try:
            for edge in brep.Edges:
                sample_curve_points(edge, parent_xform, pts_out, ext)
            return
        except Exception:
            pass

    try:
        bbox = geom.GetBoundingBox(parent_xform)
        if bbox and bbox.IsValid:
            for corner in bbox.GetCorners():
                update_extents(ext, corner)
                add_plan_pt(pts_out, corner)
    except Exception:
        pass


def cross(o, a, b):
    return (a.X - o.X) * (b.Y - o.Y) - (a.Y - o.Y) * (b.X - o.X)


def convex_hull_2d(points):
    pts = []
    seen = set()
    for point in points:
        key = (round(point.X, 6), round(point.Y, 6))
        if key not in seen:
            seen.add(key)
            pts.append(Rhino.Geometry.Point3d(point.X, point.Y, 0.0))

    if len(pts) <= 1:
        return pts

    pts.sort(key=lambda p: (p.X, p.Y))

    lower = []
    for point in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper = []
    for point in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def dot2(a, b):
    return a.X * b.X + a.Y * b.Y


def unit2(vector):
    length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y)
    if length == 0:
        return None
    return Rhino.Geometry.Vector3d(vector.X / length, vector.Y / length, 0.0)


def minimum_area_rect_2d(points):
    hull = convex_hull_2d(points)
    if not hull:
        return None

    if len(hull) == 1:
        point = hull[0]
        return [point, point, point, point]

    best = None
    best_area = None

    point_count = len(hull)
    for i in range(point_count):
        p0 = hull[i]
        p1 = hull[(i + 1) % point_count]
        edge = Rhino.Geometry.Vector3d(p1.X - p0.X, p1.Y - p0.Y, 0.0)
        u = unit2(edge)
        if not u:
            continue
        v = Rhino.Geometry.Vector3d(-u.Y, u.X, 0.0)

        min_u = None
        max_u = None
        min_v = None
        max_v = None

        for point in hull:
            vec = Rhino.Geometry.Vector3d(point.X, point.Y, 0.0)
            du = dot2(vec, u)
            dv = dot2(vec, v)

            if min_u is None or du < min_u:
                min_u = du
            if max_u is None or du > max_u:
                max_u = du
            if min_v is None or dv < min_v:
                min_v = dv
            if max_v is None or dv > max_v:
                max_v = dv

        width = max_u - min_u
        height = max_v - min_v
        area = width * height

        if best_area is None or area < best_area:
            c0 = Rhino.Geometry.Point3d(
                u.X * min_u + v.X * min_v, u.Y * min_u + v.Y * min_v, 0.0
            )
            c1 = Rhino.Geometry.Point3d(
                u.X * max_u + v.X * min_v, u.Y * max_u + v.Y * min_v, 0.0
            )
            c2 = Rhino.Geometry.Point3d(
                u.X * max_u + v.X * max_v, u.Y * max_u + v.Y * max_v, 0.0
            )
            c3 = Rhino.Geometry.Point3d(
                u.X * min_u + v.X * max_v, u.Y * min_u + v.Y * max_v, 0.0
            )

            best_area = area
            best = [c0, c1, c2, c3]

    return best


def poly_signed_area(pts):
    area = 0.0
    point_count = len(pts)
    for i in range(point_count):
        p0 = pts[i]
        p1 = pts[(i + 1) % point_count]
        area += p0.X * p1.Y - p1.X * p0.Y
    return area * 0.5


def right_normal(vector):
    return Rhino.Geometry.Vector3d(vector.Y, -vector.X, 0.0)


def left_normal(vector):
    return Rhino.Geometry.Vector3d(-vector.Y, vector.X, 0.0)


def midpoint(a, b, z):
    return Rhino.Geometry.Point3d((a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0, z)


def reorder_corners_longest_first(corners):
    e0 = Rhino.Geometry.Vector3d(
        corners[1].X - corners[0].X, corners[1].Y - corners[0].Y, 0.0
    )
    e1 = Rhino.Geometry.Vector3d(
        corners[2].X - corners[1].X, corners[2].Y - corners[1].Y, 0.0
    )

    if e1.Length > e0.Length:
        return [corners[1], corners[2], corners[3], corners[0]]
    return corners


def choose_long_dim_side(corners, zmin, gap):
    p0 = Rhino.Geometry.Point3d(corners[0].X, corners[0].Y, zmin)
    p1 = Rhino.Geometry.Point3d(corners[1].X, corners[1].Y, zmin)
    p2 = Rhino.Geometry.Point3d(corners[2].X, corners[2].Y, zmin)
    p3 = Rhino.Geometry.Point3d(corners[3].X, corners[3].Y, zmin)

    signed = poly_signed_area(corners)

    e_bottom = Rhino.Geometry.Vector3d(p1.X - p0.X, p1.Y - p0.Y, 0.0)
    e_top = Rhino.Geometry.Vector3d(p2.X - p3.X, p2.Y - p3.Y, 0.0)

    u_bottom = unit2(e_bottom)
    u_top = unit2(e_top)

    if signed >= 0:
        n_bottom = right_normal(u_bottom)
        n_top = right_normal(u_top)
    else:
        n_bottom = left_normal(u_bottom)
        n_top = left_normal(u_top)

    mid_bottom = midpoint(p0, p1, zmin)
    mid_top = midpoint(p3, p2, zmin)

    off_bottom = Rhino.Geometry.Point3d(
        mid_bottom.X + n_bottom.X * gap, mid_bottom.Y + n_bottom.Y * gap, zmin
    )
    off_top = Rhino.Geometry.Point3d(
        mid_top.X + n_top.X * gap, mid_top.Y + n_top.Y * gap, zmin
    )

    if off_bottom.Y <= off_top.Y:
        return p0, p1, off_bottom
    return p3, p2, off_top


def choose_short_dim_side(corners, zmin, gap):
    p0 = Rhino.Geometry.Point3d(corners[0].X, corners[0].Y, zmin)
    p1 = Rhino.Geometry.Point3d(corners[1].X, corners[1].Y, zmin)
    p2 = Rhino.Geometry.Point3d(corners[2].X, corners[2].Y, zmin)
    p3 = Rhino.Geometry.Point3d(corners[3].X, corners[3].Y, zmin)

    signed = poly_signed_area(corners)

    e_right = Rhino.Geometry.Vector3d(p2.X - p1.X, p2.Y - p1.Y, 0.0)
    e_left = Rhino.Geometry.Vector3d(p3.X - p0.X, p3.Y - p0.Y, 0.0)

    u_right = unit2(e_right)
    u_left = unit2(e_left)

    if signed >= 0:
        n_right = right_normal(u_right)
        n_left = right_normal(u_left)
    else:
        n_right = left_normal(u_right)
        n_left = left_normal(u_left)

    mid_right = midpoint(p1, p2, zmin)
    mid_left = midpoint(p0, p3, zmin)

    off_right = Rhino.Geometry.Point3d(
        mid_right.X + n_right.X * gap, mid_right.Y + n_right.Y * gap, zmin
    )
    off_left = Rhino.Geometry.Point3d(
        mid_left.X + n_left.X * gap, mid_left.Y + n_left.Y * gap, zmin
    )

    if off_right.X >= off_left.X:
        return p1, p2, off_right
    return p0, p3, off_left


def main():
    obj = get_valid_object()
    if not obj:
        return

    layer_name = "NP-temporary"
    ensure_layer(layer_name)

    linetype_name = ensure_dashed_linetype()

    current_style, temp_style = ensure_temp_dimstyle()
    rs.CurrentDimStyle(temp_style)

    try:
        pts2d = []
        ext = {
            "xmin": None,
            "xmax": None,
            "ymin": None,
            "ymax": None,
            "zmin": None,
            "zmax": None,
        }

        collect_geom_points(obj, Rhino.Geometry.Transform.Identity, pts2d, ext)

        if not pts2d:
            raise Exception("Could not calculate filtered geometry")

        if ext["xmin"] is None:
            raise Exception("Could not calculate extents")

        zmin = ext["zmin"]
        zmax = ext["zmax"]
        zsize = zmax - zmin

        tol = sc.doc.ModelAbsoluteTolerance
        created = []

        corners = minimum_area_rect_2d(pts2d)
        if not corners:
            raise Exception("Could not calculate best fit rectangle")

        corners = reorder_corners_longest_first(corners)

        rect_pts = [
            Rhino.Geometry.Point3d(corners[0].X, corners[0].Y, zmin),
            Rhino.Geometry.Point3d(corners[1].X, corners[1].Y, zmin),
            Rhino.Geometry.Point3d(corners[2].X, corners[2].Y, zmin),
            Rhino.Geometry.Point3d(corners[3].X, corners[3].Y, zmin),
            Rhino.Geometry.Point3d(corners[0].X, corners[0].Y, zmin),
        ]

        rect_id = rs.AddPolyline(rect_pts)
        if rect_id:
            rs.ObjectLayer(rect_id, layer_name)
            rs.ObjectColor(rect_id, (150, 150, 150))
            if linetype_name:
                rs.ObjectLinetype(rect_id, linetype_name)
            created.append(rect_id)

        len0 = Rhino.Geometry.Vector3d(
            corners[1].X - corners[0].X, corners[1].Y - corners[0].Y, 0.0
        ).Length
        len1 = Rhino.Geometry.Vector3d(
            corners[2].X - corners[1].X, corners[2].Y - corners[1].Y, 0.0
        ).Length

        gap = max(len0, len1) * 0.08
        if gap <= tol:
            gap = 2.0

        a0, a1, off0 = choose_long_dim_side(corners, zmin, gap)
        b0, b1, off1 = choose_short_dim_side(corners, zmin, gap)

        dim0 = rs.AddAlignedDimension(a0, a1, off0)
        if dim0:
            rs.ObjectLayer(dim0, layer_name)
            created.append(dim0)

        dim1 = rs.AddAlignedDimension(b0, b1, off1)
        if dim1:
            rs.ObjectLayer(dim1, layer_name)
            created.append(dim1)

        area = None
        area_centroid = None

        if (
            (not rs.IsBlockInstance(obj))
            and rs.IsCurve(obj)
            and rs.IsCurveClosed(obj)
            and rs.IsCurvePlanar(obj)
        ):
            area_result = rs.CurveArea(obj)
            area = get_area_value(area_result)

            centroid_result = rs.CurveAreaCentroid(obj)
            if centroid_result and len(centroid_result) > 0:
                area_centroid = centroid_result[0]

        if area is not None and area_centroid is not None:
            maxx_rect = max(p.X for p in corners)
            maxy_rect = max(p.Y for p in corners)

            area_start = area_centroid
            area_knee = Rhino.Geometry.Point3d(
                maxx_rect + gap * 0.4, maxy_rect + gap * 0.2, area_centroid.Z
            )
            area_end = Rhino.Geometry.Point3d(
                maxx_rect + gap * 1.8, maxy_rect + gap * 0.2, area_centroid.Z
            )

            area_text = "Area = " + fmt_num(area)

            area_id = rs.AddLeader([area_start, area_knee, area_end], None, area_text)
            if area_id:
                rs.ObjectLayer(area_id, layer_name)
                created.append(area_id)

        if abs(zsize) > tol:
            maxx_rect = max(p.X for p in corners)
            maxy_rect = max(p.Y for p in corners)

            z_start = Rhino.Geometry.Point3d(maxx_rect, maxy_rect, zmax)
            z_knee = Rhino.Geometry.Point3d(
                maxx_rect + gap * 0.6, maxy_rect + gap * 0.9, zmax
            )
            z_end = Rhino.Geometry.Point3d(
                maxx_rect + gap * 1.8, maxy_rect + gap * 0.9, zmax
            )

            z_text = "Z = " + fmt_num(zsize)

            z_id = rs.AddLeader([z_start, z_knee, z_end], None, z_text)
            if z_id:
                rs.ObjectLayer(z_id, layer_name)
                created.append(z_id)

        if created:
            group_name = rs.AddGroup("NP_temporary_group")
            if group_name:
                rs.AddObjectsToGroup(created, group_name)

    finally:
        rs.CurrentDimStyle(current_style)
        sc.doc.Views.Redraw()


if __name__ == "__main__":
    main()
