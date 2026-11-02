"""
Engrave: select centreline curve(s), enter width and depth, then pick a host
solid. Cuts a centred trench (width x depth) from the stack top, like a dado.
Entered width/depth are remembered as the next-run defaults.
"""

import json
import os
import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

STICKY_WIDTH = "np_engrave_width"
STICKY_DEPTH = "np_engrave_depth"
FALLBACK_WIDTH = 0.375
FALLBACK_DEPTH = 0.375
RAISE_AMT = 1.0 / 16.0
DEFAULTS_FILENAME = "engrave_defaults.json"
MIN_SIZE = 0.001


def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    width = sc.sticky.get(STICKY_WIDTH, None)
    depth = sc.sticky.get(STICKY_DEPTH, None)
    if width is not None and depth is not None:
        try:
            return float(width), float(depth)
        except Exception:
            pass

    path = defaults_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as handle:
                data = json.load(handle)
            return float(data.get("width", FALLBACK_WIDTH)), float(
                data.get("depth", FALLBACK_DEPTH)
            )
        except Exception:
            pass

    return FALLBACK_WIDTH, FALLBACK_DEPTH


def save_defaults(width, depth):
    sc.sticky[STICKY_WIDTH] = width
    sc.sticky[STICKY_DEPTH] = depth

    folder = os.path.join(_INSTALL_ROOT, "_user_data")
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump({"width": float(width), "depth": float(depth)}, handle)
    except Exception:
        pass


def prompt_size(message, default_value):
    value = rs.GetReal(message, default_value, MIN_SIZE)
    if value is None:
        return None
    return float(value)


def model_tol():
    try:
        if sc.doc and sc.doc.ModelAbsoluteTolerance > 0:
            return sc.doc.ModelAbsoluteTolerance
    except Exception:
        pass
    return 0.01


def delete_ids(ids):
    for obj_id in ids:
        if obj_id and rs.IsObject(obj_id):
            rs.DeleteObject(obj_id)


def unitize(vec):
    length = rs.VectorLength(vec)
    if not length:
        return None
    return rs.VectorScale(vec, 1.0 / length)


def is_straight_open_curve(curve_id):
    if rs.IsCurveClosed(curve_id):
        return False
    start = rs.CurveStartPoint(curve_id)
    end = rs.CurveEndPoint(curve_id)
    if not start or not end:
        return False
    chord = rs.Distance(start, end)
    length = rs.CurveLength(curve_id)
    if not chord or not length:
        return False
    return abs(length - chord) <= max(model_tol(), 1e-6)


def as_curve_list(result):
    if result is None:
        return None
    try:
        curves = list(result)
    except TypeError:
        curves = [result]
    return [crv for crv in curves if crv]


def join_offset_result(curves, tol):
    curves = as_curve_list(curves)
    if not curves:
        return None
    if len(curves) == 1:
        return curves[0]
    joined = Rhino.Geometry.Curve.JoinCurves(curves, tol)
    if joined:
        return joined[0]
    return None


def close_open_offsets(left, right, tol):
    a = left.DuplicateCurve()
    b = right.DuplicateCurve()
    a0 = a.PointAtStart
    a1 = a.PointAtEnd
    b0 = b.PointAtStart
    b1 = b.PointAtEnd

    if a0.DistanceTo(b0) <= a0.DistanceTo(b1):
        b.Reverse()
        b0 = b.PointAtStart
        b1 = b.PointAtEnd

    cap1 = Rhino.Geometry.LineCurve(a1, b0)
    cap2 = Rhino.Geometry.LineCurve(b1, a0)
    joined = Rhino.Geometry.Curve.JoinCurves([a, cap1, b, cap2], tol)
    if not joined:
        return None

    profile = joined[0]
    if not profile.IsClosed:
        try:
            profile.MakeClosed(tol)
        except Exception:
            pass
    if not profile.IsClosed:
        return None
    return profile


def build_trench_profiles(curve_id, width, profile_z):
    crv = rs.coercecurve(curve_id)
    if crv is None:
        return None, "Could not read curve."

    plane = Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(0.0, 0.0, profile_z),
        Rhino.Geometry.Vector3d.ZAxis,
    )
    projected = Rhino.Geometry.Curve.ProjectToPlane(crv, plane)
    if projected is None:
        return None, "Could not flatten curve to World XY."

    tol = model_tol()
    half = width / 2.0
    ok, crv_plane = projected.TryGetPlane(tol)
    if not ok:
        crv_plane = plane

    left = projected.Offset(
        crv_plane, half, tol, Rhino.Geometry.CurveOffsetCornerStyle.Sharp
    )
    right = projected.Offset(
        crv_plane, -half, tol, Rhino.Geometry.CurveOffsetCornerStyle.Sharp
    )
    if not left or not right:
        return None, "Could not offset curve by half width."

    left_crv = join_offset_result(left, tol)
    right_crv = join_offset_result(right, tol)
    if not left_crv or not right_crv:
        return None, "Could not join offset curves."

    if projected.IsClosed:
        return (left_crv, right_crv), None

    profile = close_open_offsets(left_crv, right_crv, tol)
    if not profile:
        return None, "Could not close trench profile."
    return (profile,), None


def extrude_planar_srf_down(srf_id, profile_z, total_drop):
    centroid = rs.SurfaceAreaCentroid(srf_id)
    if not centroid:
        return None
    c = centroid[0]
    path_id = rs.AddLine(
        (c.X, c.Y, profile_z),
        (c.X, c.Y, profile_z - total_drop),
    )
    if not path_id:
        return None

    cutter_id = rs.ExtrudeSurface(srf_id, path_id, True)
    rs.DeleteObject(path_id)
    if cutter_id:
        cutter_id = gcu.replace_extrusion_with_brep_if_needed(cutter_id)
    return cutter_id


def make_box_cutter(curve_id, width, depth, global_top_z, raise_amt):
    start = rs.CurveStartPoint(curve_id)
    end = rs.CurveEndPoint(curve_id)
    if not start or not end:
        return None

    axis = rs.VectorCreate(end, start)
    axis_u = unitize(axis)
    if not axis_u:
        return None

    perp = unitize((-axis_u[1], axis_u[0], 0.0))
    if not perp:
        return None

    offset = rs.VectorScale(perp, width / 2.0)
    p1 = rs.PointAdd(start, offset)
    p2 = rs.PointAdd(end, offset)
    p3 = rs.PointSubtract(end, offset)
    p4 = rs.PointSubtract(start, offset)

    top_z = global_top_z + raise_amt
    bottom_z = global_top_z - depth

    corners = [
        (p1[0], p1[1], top_z),
        (p2[0], p2[1], top_z),
        (p3[0], p3[1], top_z),
        (p4[0], p4[1], top_z),
        (p1[0], p1[1], bottom_z),
        (p2[0], p2[1], bottom_z),
        (p3[0], p3[1], bottom_z),
        (p4[0], p4[1], bottom_z),
    ]
    return rs.AddBox(corners)


def make_offset_cutter(curve_id, width, depth, global_top_z, raise_amt):
    profile_z = global_top_z + raise_amt
    total_drop = raise_amt + depth

    profiles, error = build_trench_profiles(curve_id, width, profile_z)
    if not profiles:
        return None, error

    curve_ids = []
    srf_ids = []
    try:
        for geo in profiles:
            nid = sc.doc.Objects.AddCurve(geo)
            if nid:
                curve_ids.append(nid)
        if not curve_ids:
            return None, "Could not add trench profile."

        srf_ids = rs.AddPlanarSrf(curve_ids) or []
        if not srf_ids:
            return None, "Could not create trench surface."

        cutters = []
        for srf_id in srf_ids:
            cutter_id = extrude_planar_srf_down(srf_id, profile_z, total_drop)
            if cutter_id:
                cutters.append(cutter_id)

        if not cutters:
            return None, "Could not extrude trench cutter."
        if len(cutters) == 1:
            return cutters[0], None

        unioned = rs.BooleanUnion(cutters, delete_input=True)
        if not unioned:
            delete_ids(cutters)
            return None, "Could not join trench cutter pieces."
        if isinstance(unioned, list):
            keeper = unioned[0]
            delete_ids(unioned[1:])
            return keeper, None
        return unioned, None
    finally:
        delete_ids(curve_ids)
        delete_ids(srf_ids)


def make_cutter(curve_id, width, depth, global_top_z, raise_amt):
    if not rs.IsCurve(curve_id):
        return None, "Selected object is not a curve."
    if rs.IsCurveClosed(curve_id):
        if not rs.IsCurvePlanar(curve_id):
            return None, "Closed centreline must be planar."
        return make_offset_cutter(curve_id, width, depth, global_top_z, raise_amt)

    if is_straight_open_curve(curve_id):
        cutter_id = make_box_cutter(curve_id, width, depth, global_top_z, raise_amt)
        if cutter_id:
            return cutter_id, None

    if not rs.IsCurvePlanar(curve_id):
        return None, "Centreline must be planar."
    return make_offset_cutter(curve_id, width, depth, global_top_z, raise_amt)


def get_target_solid():
    obj_id = rs.GetObject(
        "Select one solid from target stack/group",
        rs.filter.polysurface,
        preselect=True,
    )
    if not obj_id:
        return None

    if not rs.IsPolysurface(obj_id):
        print("Selected object is not a polysurface.")
        return None

    if not gcu.is_closed_solid(obj_id):
        print("Selected object is not a closed solid.")
        return None

    return obj_id


def main():
    curve_ids = rs.GetObjects(
        "Select centreline curve(s) to engrave",
        rs.filter.curve,
        preselect=True,
    )
    if not curve_ids:
        return

    rs.UnselectAllObjects()

    default_width, default_depth = load_defaults()
    width = prompt_size("Engrave width", default_width)
    if width is None:
        return
    depth = prompt_size("Engrave depth", default_depth)
    if depth is None:
        return

    save_defaults(width, depth)

    seed_host = get_target_solid()
    if not seed_host:
        return

    host_ids = gcu.collect_group_closed_solids(seed_host)
    if not host_ids:
        print("Selected object/group does not contain closed solids.")
        return

    global_top_z = gcu.compute_global_stack_top_z(host_ids)
    if global_top_z is None:
        print("Could not determine top of selected host stack.")
        return

    rs.EnableRedraw(False)
    current_hosts = list(host_ids)
    cuts = 0
    skipped = 0
    host_touches = 0
    boolean_failures = 0
    first_error = None

    try:
        for curve_id in curve_ids:
            cutter_id, error = make_cutter(
                curve_id, width, depth, global_top_z, RAISE_AMT
            )
            if not cutter_id:
                skipped += 1
                if error and not first_error:
                    first_error = error
                continue

            current_hosts, touched, failed = gcu.boolean_difference_many(
                current_hosts, cutter_id
            )
            boolean_failures += failed
            if touched > 0:
                cuts += 1
                host_touches += touched
            else:
                skipped += 1
                if not first_error:
                    first_error = "Boolean failed."
    finally:
        rs.EnableRedraw(True)

    if cuts == 0:
        rs.MessageBox(
            "Engrave failed.\nNo host solids were changed.\n"
            "Curves skipped: {}\n{}".format(skipped, first_error or "")
        )
        return

    print("Engrave cut successfully.")
    print("Width: {} | Depth below surface: {}".format(width, depth))
    print(
        "Curves cut: {} | skipped: {} | hosts touched: {} | boolean failures: {}".format(
            cuts, skipped, host_touches, boolean_failures
        )
    )


if __name__ == "__main__":
    main()
