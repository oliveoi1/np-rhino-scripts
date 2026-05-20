"""
Surface recess: select a closed solid, then one or more closed planar curves.

The curve is copied up 1/32" and extruded downward 1/16", so the cutter spans
1/32" above and 1/32" below the selected curve before BooleanDifference.
"""

import os
import sys

import rhinoscriptsyntax as rs

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
        gcu = reload(gcu)
except Exception:
    pass

RECESS_DEPTH = 1.0 / 32.0
SAFETY_RAISE = 1.0 / 32.0


def make_surface_recess_cutter(curve_id):
    if not rs.IsCurve(curve_id):
        return None, "Selected object is not a curve."
    if not rs.IsCurveClosed(curve_id):
        return None, "Curve must be closed."
    if not rs.IsCurvePlanar(curve_id):
        return None, "Curve must be planar."

    raised_curve = rs.CopyObject(curve_id, (0.0, 0.0, SAFETY_RAISE))
    if not raised_curve:
        return None, "Could not copy curve upward."

    cutter_id = None
    try:
        cutter_id = rs.ExtrudeCurveStraight(
            raised_curve,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, -(SAFETY_RAISE + RECESS_DEPTH)),
        )
        if cutter_id:
            rs.CapPlanarHoles(cutter_id)
            cutter_id = gcu.replace_extrusion_with_brep_if_needed(cutter_id)
    finally:
        if rs.IsObject(raised_curve):
            rs.DeleteObject(raised_curve)

    if not cutter_id:
        return None, "Could not create capped extrusion cutter."

    return cutter_id, None


def main():
    rs.UnselectAllObjects()

    seed_host = rs.GetObject(
        "Select closed solid to subtract from",
        rs.filter.polysurface,
        preselect=False,
    )
    if not seed_host:
        return

    host_ids = gcu.collect_group_closed_solids(seed_host)
    if not host_ids:
        rs.MessageBox("Selected object/group does not contain closed solids.")
        return

    curve_ids = rs.GetObjects(
        "Select closed planar curves for 1/32 surface recesses",
        rs.filter.curve,
        preselect=False,
    )
    if not curve_ids:
        return

    rs.EnableRedraw(False)
    current_hosts = list(host_ids)
    recesses_cut = 0
    host_touches = 0
    boolean_failures = 0
    skipped = 0
    first_error = None

    try:
        for curve_id in curve_ids:
            cutter_id, error = make_surface_recess_cutter(curve_id)
            if not cutter_id:
                skipped += 1
                if not first_error:
                    first_error = error
                continue

            current_hosts, touched, failed = gcu.boolean_difference_many(
                current_hosts,
                cutter_id,
            )
            boolean_failures += failed

            if touched > 0:
                recesses_cut += 1
                host_touches += touched
            else:
                skipped += 1
    finally:
        rs.EnableRedraw(True)

    if recesses_cut == 0:
        rs.MessageBox(
            "Surface recess boolean failed.\n"
            "No host solids were changed.\n"
            "{} curve(s) skipped.\n{}".format(
                skipped,
                first_error or "",
            )
        )
        return

    rs.MessageBox(
        "Surface recess complete.\n"
        "Recesses cut: {}\n"
        "Hosts touched: {}\n"
        "Curves skipped: {}\n"
        "Boolean failures: {}\n"
        "Cutter span: 1/32 above each curve, 1/32 below each curve.".format(
            recesses_cut,
            host_touches,
            skipped,
            boolean_failures,
        )
    )


if __name__ == "__main__":
    main()
