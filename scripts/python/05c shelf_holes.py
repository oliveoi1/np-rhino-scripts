import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc
import math
import os
import sys

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

HOLE_DIAMETER_IN = 0.2

REGULAR_DEPTH_IN = 0.5
FULL_DEPTH_IN = 0.75

CIRCLE_MIN_SIZE_IN = 0.15
CIRCLE_MAX_SIZE_IN = 0.3
ROUND_RATIO_TOL = 0.15
CIRCUMFERENCE_TOL = 0.15

SEARCH_DROP_IN = 0.02
INSIDE_TOL_IN = 0.01

def inches_to_doc_units(val_in):
    scale = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Inches, sc.doc.ModelUnitSystem)
    return val_in * scale

def choose_depth():
    result = rs.MessageBox(
        "Choose hole depth:\n\nYes = Regular (0.5\")\nNo = Full depth (0.75\")",
        4,
        "Hole Depth"
    )
    if result == 6:
        return REGULAR_DEPTH_IN
    elif result == 7:
        return FULL_DEPTH_IN
    return None

def bbox_info(obj_id):
    bb = rs.BoundingBox(obj_id)
    if not bb or len(bb) < 8:
        return None

    minx = min(p.X for p in bb)
    maxx = max(p.X for p in bb)
    miny = min(p.Y for p in bb)
    maxy = max(p.Y for p in bb)
    minz = min(p.Z for p in bb)
    maxz = max(p.Z for p in bb)

    return {
        "center": Rhino.Geometry.Point3d((minx + maxx) / 2.0, (miny + maxy) / 2.0, (minz + maxz) / 2.0),
        "width": maxx - minx,
        "height": maxy - miny
    }

def is_small_round_curve(obj_id, min_size, max_size):
    if not rs.IsCurve(obj_id):
        return False, None

    if not rs.IsCurveClosed(obj_id):
        return False, None

    info = bbox_info(obj_id)
    if not info:
        return False, None

    w = info["width"]
    h = info["height"]

    if w < min_size or h < min_size:
        return False, None

    if w > max_size or h > max_size:
        return False, None

    ratio = w / h if h != 0 else 9999
    if ratio < (1.0 - ROUND_RATIO_TOL) or ratio > (1.0 + ROUND_RATIO_TOL):
        return False, None

    avg_dia = (w + h) / 2.0
    expected = math.pi * avg_dia
    actual = rs.CurveLength(obj_id)

    if not actual or expected == 0:
        return False, None

    lr = actual / expected
    if lr < (1.0 - CIRCUMFERENCE_TOL) or lr > (1.0 + CIRCUMFERENCE_TOL):
        return False, None

    return True, info["center"]

def merge_host_updates(current_hosts, target_hosts, updated_hosts):
    target_set = set(target_hosts)
    kept = [obj_id for obj_id in current_hosts if obj_id not in target_set]
    kept.extend(updated_hosts)
    return kept

def main():
    depth_in = choose_depth()
    if depth_in is None:
        return

    hole_diameter = inches_to_doc_units(HOLE_DIAMETER_IN)
    hole_depth = inches_to_doc_units(depth_in)
    min_size = inches_to_doc_units(CIRCLE_MIN_SIZE_IN)
    max_size = inches_to_doc_units(CIRCLE_MAX_SIZE_IN)
    search_drop = inches_to_doc_units(SEARCH_DROP_IN)
    inside_tol = inches_to_doc_units(INSIDE_TOL_IN)

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select small circles to drill", rs.filter.curve, preselect=False)
    if not objs:
        return

    seed_host = rs.GetObject("Select one solid from target stack/group", rs.filter.polysurface, preselect=False)
    if not seed_host:
        return

    current_hosts = gcu.collect_group_closed_solids(seed_host)
    if not current_hosts:
        rs.MessageBox("Selected object/group does not contain closed solids.")
        return

    global_top_z = gcu.compute_global_stack_top_z(current_hosts)
    if global_top_z is None:
        rs.MessageBox("Could not determine global top of selected stack.")
        return

    cut_count = 0
    touched_hosts = 0
    missed = 0

    rs.EnableRedraw(False)

    for obj_id in objs:
        try:
            ok, center = is_small_round_curve(obj_id, min_size, max_size)
            if not ok or not center:
                missed += 1
                continue

            target_hosts = gcu.filter_hosts_under_point(current_hosts, center, search_drop, inside_tol)
            if not target_hosts:
                missed += 1
                continue

            cutter_id = gcu.make_global_depth_cylinder(center, hole_diameter, global_top_z, hole_depth)
            if not cutter_id:
                missed += 1
                continue

            updated_subset, touched, failed = gcu.boolean_difference_many(target_hosts, cutter_id)
            if touched == 0:
                missed += 1
                continue

            cut_count += 1
            touched_hosts += touched
            missed += failed
            current_hosts = merge_host_updates(current_hosts, target_hosts, updated_subset)

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    depth_label = "0.5" if abs(depth_in - 0.5) < 0.0001 else "0.75"
    rs.MessageBox(
        "Holes cut: {}\nHosts touched: {}\nMissed: {}\nDepth used: {}\"".format(
            cut_count, touched_hosts, missed, depth_label
        )
    )

main()