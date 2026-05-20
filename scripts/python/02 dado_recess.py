import rhinoscriptsyntax as rs
import os
import sys

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

WIDTH = 0.375
DEPTH = 0.375
TOP_PROUD = 0.01

def unitize(vec):
    length = rs.VectorLength(vec)
    if not length or length == 0:
        return None
    return rs.VectorScale(vec, 1.0 / length)


def add_cutter_box_from_line(start, end, width, depth, global_top_z, top_proud):
    axis = rs.VectorCreate(end, start)
    axis_u = unitize(axis)
    if not axis_u:
        return None

    perp = (-axis_u[1], axis_u[0], 0.0)
    perp_u = unitize(perp)
    if not perp_u:
        return None

    half_w = width / 2.0
    offset = rs.VectorScale(perp_u, half_w)

    p1 = rs.PointAdd(start, offset)
    p2 = rs.PointAdd(end, offset)
    p3 = rs.PointSubtract(end, offset)
    p4 = rs.PointSubtract(start, offset)

    top_z = global_top_z + top_proud
    bottom_z = top_z - depth

    p1u = (p1[0], p1[1], top_z)
    p2u = (p2[0], p2[1], top_z)
    p3u = (p3[0], p3[1], top_z)
    p4u = (p4[0], p4[1], top_z)

    p1d = (p1[0], p1[1], bottom_z)
    p2d = (p2[0], p2[1], bottom_z)
    p3d = (p3[0], p3[1], bottom_z)
    p4d = (p4[0], p4[1], bottom_z)

    corners = [p1u, p2u, p3u, p4u, p1d, p2d, p3d, p4d]
    return rs.AddBox(corners)

def main():
    rs.UnselectAllObjects()

    seed_host = rs.GetObject("Select one solid from target stack/group", rs.filter.polysurface, preselect=False)
    if not seed_host:
        return

    host_ids = gcu.collect_group_closed_solids(seed_host)
    if not host_ids:
        rs.MessageBox("Selected object/group does not contain closed solids.")
        return

    global_top_z = gcu.compute_global_stack_top_z(host_ids)
    if global_top_z is None:
        rs.MessageBox("Could not determine global top of selected stack.")
        return

    curves = rs.GetObjects("Select center lines to cut recesses", rs.filter.curve, preselect=False)
    if not curves:
        return

    cuts = 0
    missed = 0
    host_touches = 0

    rs.EnableRedraw(False)
    current_hosts = host_ids

    for obj in curves:
        if not rs.IsCurve(obj):
            missed += 1
            continue

        start = rs.CurveStartPoint(obj)
        end = rs.CurveEndPoint(obj)
        if not start or not end:
            missed += 1
            continue

        if rs.Distance(start, end) == 0:
            missed += 1
            continue

        cutter_id = add_cutter_box_from_line(start, end, WIDTH, DEPTH, global_top_z, TOP_PROUD)
        if not cutter_id:
            missed += 1
            continue

        current_hosts, touched, failed = gcu.boolean_difference_many(current_hosts, cutter_id)
        if touched > 0:
            cuts += 1
            host_touches += touched
            missed += failed
        else:
            missed += 1

    rs.EnableRedraw(True)
    rs.MessageBox(
        "{} recess cut(s) completed\nHosts touched: {}\n{} missed".format(
            cuts, host_touches, missed
        )
    )

main()