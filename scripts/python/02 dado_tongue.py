import rhinoscriptsyntax as rs
import math
import os
import sys

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

def get_four_points():
    pts = []
    for i in range(4):
        pt = rs.GetPoint("Pick point {}".format(i + 1))
        if pt is None:
            return None
        pts.append(pt)
    return pts

def sort_points_around_center(pts):
    cx = sum(p.X for p in pts) / float(len(pts))
    cy = sum(p.Y for p in pts) / float(len(pts))

    def angle(p):
        return math.atan2(p.Y - cy, p.X - cx)

    return sorted(pts, key=angle)

def is_closed_solid(obj_id):
    return gcu.is_closed_solid(obj_id)

def get_target_solid():
    obj_id = rs.GetObject(
        "Select one solid from target stack/group",
        rs.filter.polysurface,
        preselect=True
    )
    if not obj_id:
        return None

    if not rs.IsPolysurface(obj_id):
        print("Selected object is not a polysurface.")
        return None

    if not is_closed_solid(obj_id):
        print("Selected object is not a closed solid.")
        return None

    return obj_id

def make_cutter(pts, global_top_z, raise_amt, cut_depth):
    pts = sort_points_around_center(pts)

    profile_z = global_top_z + raise_amt
    total_drop = raise_amt + cut_depth

    profile_pts = []
    for p in pts:
        profile_pts.append(rs.CreatePoint(p.X, p.Y, profile_z))

    poly_id = rs.AddPolyline(profile_pts + [profile_pts[0]])
    if not poly_id:
        print("Could not create polyline.")
        return None

    if not rs.IsCurveClosed(poly_id):
        rs.DeleteObject(poly_id)
        print("Polyline is not closed.")
        return None

    srf_ids = rs.AddPlanarSrf(poly_id)
    rs.DeleteObject(poly_id)

    if not srf_ids:
        print("Could not create planar surface.")
        return None

    srf_id = srf_ids[0]

    centroid = rs.SurfaceAreaCentroid(srf_id)
    if not centroid:
        rs.DeleteObject(srf_id)
        print("Could not get centroid.")
        return None

    c = centroid[0]
    path_id = rs.AddLine(
        (c.X, c.Y, profile_z),
        (c.X, c.Y, profile_z - total_drop)
    )

    if not path_id:
        rs.DeleteObject(srf_id)
        print("Could not create path.")
        return None

    cutter_id = rs.ExtrudeSurface(srf_id, path_id, True)

    rs.DeleteObject(path_id)
    rs.DeleteObject(srf_id)

    if not cutter_id:
        print("Could not create cutter.")
        return None

    return cutter_id

def main():
    raise_amt = 1.0 / 16.0
    cut_depth = 3.0 / 8.0

    seed_host = get_target_solid()
    if not seed_host:
        return

    host_ids = gcu.collect_group_closed_solids(seed_host)
    if not host_ids:
        print("Selected object/group does not contain closed solids.")
        return

    pts = get_four_points()
    if not pts:
        print("Command cancelled.")
        return

    global_top_z = gcu.compute_global_stack_top_z(host_ids)
    if global_top_z is None:
        print("Could not determine top of selected host stack.")
        return

    cutter_id = make_cutter(pts, global_top_z, raise_amt, cut_depth)
    if not cutter_id:
        return

    updated_hosts, touched, failed = gcu.boolean_difference_many(host_ids, cutter_id)
    if touched == 0:
        print("Boolean failed.")
        return

    print("Dado tongue cut successfully.")
    print("Cut depth below surface is exactly 3/8.")
    print("Hosts touched: {} | failed: {} | current host count: {}".format(touched, failed, len(updated_hosts)))

if __name__ == "__main__":
    main()