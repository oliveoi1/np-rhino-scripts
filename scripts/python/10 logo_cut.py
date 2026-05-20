"""
Logo cut: match Rhino ExtrudeCrv Straight - Distance 1/8, Both sides, Solid - then BooleanDifference hosts.

Uses planar curve plane normal. Open or closed planar curves use the same extrusion (like your manual flow).
Self-intersecting curves are extruded anyway (same as clicking Yes in Rhino).

Target must be a closed polysurface (optionally a grouped stack of closed solids).
"""

import rhinoscriptsyntax as rs
import Rhino
import os
import sys
try:
    import importlib
except ImportError:
    importlib = None

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu
try:
    if importlib and hasattr(importlib, "reload"):
        gcu = importlib.reload(gcu)
    else:
        builtin_reload = getattr(__builtins__, "reload", None)
        if not builtin_reload and isinstance(__builtins__, dict):
            builtin_reload = __builtins__.get("reload")
        if builtin_reload:
            gcu = builtin_reload(gcu)
except Exception:
    pass

# Same as Rhino ExtrudeCrv: Distance = 1/8, Both sides = Yes (half on each side of the curve plane).
EXTRUDE_DISTANCE = 1.0 / 8.0
HALF_EACH_SIDE = EXTRUDE_DISTANCE / 2.0


def planar_straight_extrude_solid_cutter(crv_id):
    """ExtrudeCurveStraight + CapPlanarHoles, same net as ExtrudeCrv 1/8 both sides."""
    if not rs.IsCurvePlanar(crv_id):
        return None
    plane = rs.CurvePlane(crv_id)
    if not plane:
        return None

    origin = plane.Origin
    z_axis = Rhino.Geometry.Vector3d(plane.ZAxis)
    if not z_axis.Unitize():
        return None

    start_pt = Rhino.Geometry.Point3d(origin) - z_axis * HALF_EACH_SIDE
    end_pt = Rhino.Geometry.Point3d(origin) + z_axis * HALF_EACH_SIDE

    try:
        solid = rs.ExtrudeCurveStraight(crv_id, start_pt, end_pt)
    except Exception:
        return None
    if not solid:
        return None
    try:
        rs.CapPlanarHoles(solid)
    except Exception:
        pass
    solid = gcu.replace_extrusion_with_brep_if_needed(solid)
    return solid


def curve_to_cutter(crv_id):
    if not rs.IsCurve(crv_id):
        return None
    return planar_straight_extrude_solid_cutter(crv_id)


def normalize_boolean_union_result(res):
    if res is None:
        return []
    if isinstance(res, list):
        return [x for x in res if x and rs.IsObject(x)]
    if rs.IsObject(res):
        return [res]
    return []


def main():
    rs.UnselectAllObjects()

    seed_host = rs.GetObject(
        "Select one closed solid from target stack/group (panel body)",
        rs.filter.polysurface,
        preselect=False,
    )
    if not seed_host:
        return

    host_ids = gcu.collect_group_closed_solids(seed_host)
    if not host_ids:
        rs.MessageBox(
            "Selected object/group does not contain closed solids.\n"
            "Use a closed polysurface (not an open surface only)."
        )
        return

    curves = rs.GetObjects(
        "Select planar logo curves (open or closed; self-intersecting ok)",
        rs.filter.curve,
        preselect=False,
    )
    if not curves:
        return

    cutter_ids = []
    skipped = 0
    for crv in curves:
        cid = curve_to_cutter(crv)
        if cid:
            cutter_ids.append(cid)
        else:
            skipped += 1

    if not cutter_ids:
        rs.MessageBox(
            "No valid cutters.\n"
            "Curves must be planar (Rhino-style straight extrude 1/8 both sides).\n"
            "Skipped: {}".format(skipped)
        )
        return

    rs.EnableRedraw(False)

    current_hosts = list(host_ids)
    cuts_done = 0
    host_touches = 0
    bool_failed = 0

    try:
        if len(cutter_ids) == 1:
            combined = cutter_ids[0]
            updated, touched, failed = gcu.boolean_difference_many(current_hosts, combined)
            current_hosts = updated
            host_touches += touched
            bool_failed += failed
            if touched > 0:
                cuts_done = 1
        else:
            union_res = rs.BooleanUnion(cutter_ids, delete_input=False)
            union_parts = normalize_boolean_union_result(union_res)

            if union_parts:
                for old_id in cutter_ids:
                    if rs.IsObject(old_id):
                        rs.DeleteObject(old_id)
                if len(union_parts) == 1:
                    updated, touched, failed = gcu.boolean_difference_many(
                        current_hosts, union_parts[0]
                    )
                    current_hosts = updated
                    host_touches += touched
                    bool_failed += failed
                    if touched > 0:
                        cuts_done = 1
                else:
                    for part_id in union_parts:
                        if not rs.IsObject(part_id):
                            continue
                        updated, touched, failed = gcu.boolean_difference_many(
                            current_hosts, part_id
                        )
                        current_hosts = updated
                        host_touches += touched
                        bool_failed += failed
                        if touched > 0:
                            cuts_done += 1
            else:
                for cid in cutter_ids:
                    if not rs.IsObject(cid):
                        continue
                    updated, touched, failed = gcu.boolean_difference_many(current_hosts, cid)
                    current_hosts = updated
                    host_touches += touched
                    bool_failed += failed
                    if touched > 0:
                        cuts_done += 1
    finally:
        rs.EnableRedraw(True)

    rs.MessageBox(
        "Logo cut pass(es): {}\nHosts touched (total): {}\n"
        "Curves skipped (non-planar or extrude failed): {}\n"
        "Boolean failures (pieces): {}\n\n"
        "Extrude distance (model units) = {} (BothSides: {} each side of curve plane). "
        "Edit EXTRUDE_DISTANCE at top of script to match your Rhino units.".format(
            cuts_done, host_touches, skipped, bool_failed, EXTRUDE_DISTANCE, HALF_EACH_SIDE
        )
    )


if __name__ == "__main__":
    main()
