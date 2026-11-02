"""
Custom hole cutter at selected hole_insert blocks.

Choose a preset hole size or enter a custom through/blind hole, then cut all
selected hole_insert points into a picked solid stack/group. No hardware is inserted.
"""

import os
import sys
import traceback

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
        gcu = reload(gcu)  # noqa: F821 - IronPython 2.7
except Exception:
    pass

SOURCE_BLOCK = "hole_insert"

DEFAULT_DIAMETER = 0.25
DEFAULT_DEPTH = 0.125
THROUGH_OVERSHOOT = 0.1

PRESETS = {
    "pilot": ("Pilot", None, 0.16, "through"),
    "bolt": ("Bolt", None, 0.25, "through"),
}

SEARCH_DROP = 0.02
INSIDE_TOL = 0.01


def is_block_instance_of(obj_id, block_name):
    return rs.IsBlockInstance(obj_id) and rs.BlockInstanceName(obj_id) == block_name


def merge_host_updates(current_hosts, target_hosts, updated_hosts):
    target_set = set(str(obj_id) for obj_id in target_hosts)
    kept = [obj_id for obj_id in current_hosts if str(obj_id) not in target_set]
    kept.extend(updated_hosts)
    return kept


def prompt_cut_settings():
    preset = rs.GetString(
        "Hole preset",
        "Custom",
        ["Pilot", "Bolt", "Custom"],
    )
    if not preset:
        return None

    preset_key = preset.strip().lower()
    if preset_key in PRESETS:
        return PRESETS[preset_key]

    mode = rs.GetString(
        "Hole depth type",
        "Through",
        ["Through", "Depth"],
    )
    if not mode:
        return None

    mode = mode.strip().lower()
    if mode == "through":
        depth = None
        depth_label = "through"
    else:
        depth = rs.GetReal("Hole depth into stack", DEFAULT_DEPTH, 0.001)
        if depth is None:
            return None
        if depth <= 0:
            rs.MessageBox("Hole depth must be greater than zero.")
            return None
        depth_label = "{:.3f}".format(depth)

    diameter = rs.GetReal("Hole diameter", DEFAULT_DIAMETER, 0.001)
    if diameter is None:
        return None
    if diameter <= 0:
        rs.MessageBox("Hole diameter must be greater than zero.")
        return None

    return "Custom", depth, diameter, depth_label


def main():
    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    settings = prompt_cut_settings()
    if not settings:
        return
    preset_label, hole_depth, hole_diameter, depth_label = settings

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select hole_insert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    hole_inserts = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not hole_inserts:
        rs.MessageBox("No hole_insert blocks selected.")
        return

    seed_host = rs.GetObject(
        "Select one solid from target stack/group",
        rs.filter.polysurface,
        preselect=False,
    )
    if not seed_host:
        return

    current_hosts = gcu.collect_group_closed_solids(seed_host)
    if not current_hosts:
        rs.MessageBox("Selected object/group does not contain closed solids.")
        return

    global_top_z = gcu.compute_global_stack_top_z(current_hosts)
    global_bottom_z = gcu.compute_global_stack_bottom_z(current_hosts)
    if global_top_z is None or global_bottom_z is None:
        rs.MessageBox("Could not determine selected stack height.")
        return

    if hole_depth is None:
        hole_depth = (global_top_z - global_bottom_z) + THROUGH_OVERSHOOT

    cut_count = 0
    touched_hosts = 0
    missed = 0
    miss_no_host = 0
    miss_no_cutter = 0
    miss_boolean = 0
    miss_no_insert = 0
    miss_exception = 0
    exception_samples = []

    rs.EnableRedraw(False)
    try:
        for src_id in hole_inserts:
            try:
                insert_pt = rs.BlockInstanceInsertPoint(src_id)
                if not insert_pt:
                    miss_no_insert += 1
                    missed += 1
                    continue

                target_hosts = gcu.filter_hosts_under_point(
                    current_hosts,
                    insert_pt,
                    SEARCH_DROP,
                    INSIDE_TOL,
                )
                if not target_hosts:
                    miss_no_host += 1
                    missed += 1
                    continue

                cutter_id = gcu.make_global_depth_cylinder(
                    insert_pt,
                    hole_diameter,
                    global_top_z,
                    hole_depth,
                )
                if not cutter_id:
                    miss_no_cutter += 1
                    missed += 1
                    continue

                updated_subset, touched, failed = gcu.boolean_difference_many(
                    target_hosts,
                    cutter_id,
                )
                if touched == 0:
                    miss_boolean += 1
                    missed += 1
                    continue

                cut_count += 1
                touched_hosts += touched
                missed += failed
                current_hosts = merge_host_updates(
                    current_hosts,
                    target_hosts,
                    updated_subset,
                )

            except Exception:
                miss_exception += 1
                if len(exception_samples) < 3:
                    exception_samples.append(traceback.format_exc())
                missed += 1
                continue
    finally:
        rs.EnableRedraw(True)

    rs.MessageBox(
        (
            "Preset: {}\nHoles cut: {}\nDiameter: {:.3f}\nDepth: {}\nHosts touched: {}\nMissed: {}\n"
            "(miss detail) no insert point: {}, no host match: {}, no cutter: {}, boolean failed: {}, exceptions: {}\n{}"
        ).format(
            preset_label,
            cut_count,
            hole_diameter,
            depth_label,
            touched_hosts,
            missed,
            miss_no_insert,
            miss_no_host,
            miss_no_cutter,
            miss_boolean,
            miss_exception,
            ("\n".join(exception_samples) if exception_samples else ""),
        )
    )


if __name__ == "__main__":
    main()
