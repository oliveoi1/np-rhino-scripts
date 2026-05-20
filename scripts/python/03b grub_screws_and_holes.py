import rhinoscriptsyntax as rs
import os
import sys
import traceback
try:
    import importlib
except:
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
except:
    pass

SOURCE_BLOCK = "hole_insert"
SCREW_BLOCK = "grub_screw"
FITTINGS_LAYER = "NP-Fittings"

HOLE_DIAMETER = 0.25
HOLE_DEPTH = 0.6

SEARCH_DROP = 0.02
INSIDE_TOL = 0.01

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def is_block_instance_of(obj_id, block_name):
    return rs.IsBlockInstance(obj_id) and rs.BlockInstanceName(obj_id) == block_name

def get_instance_xform(obj_id):
    rhobj = rs.coercerhinoobject(obj_id, True, True)
    if not rhobj:
        return None
    try:
        return rhobj.InstanceXform
    except:
        return None

def insert_block_with_xform(block_name, xform):
    new_id = rs.InsertBlock(block_name, (0, 0, 0))
    if not new_id:
        return None
    rs.TransformObject(new_id, xform, copy=False)
    return new_id

def merge_host_updates(current_hosts, target_hosts, updated_hosts):
    target_set = set(str(obj_id) for obj_id in target_hosts)
    kept = [obj_id for obj_id in current_hosts if str(obj_id) not in target_set]
    kept.extend(updated_hosts)
    return kept

def main():
    ensure_layer(FITTINGS_LAYER)

    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    if not rs.IsBlock(SCREW_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SCREW_BLOCK))
        return

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select hole_insert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    hole_inserts = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not hole_inserts:
        rs.MessageBox("No hole_insert blocks selected.")
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
    screw_count = 0
    missed = 0
    miss_no_host = 0
    miss_no_cutter = 0
    miss_boolean = 0
    miss_no_insert = 0
    miss_no_xform = 0
    miss_exception = 0
    exception_samples = []

    rs.EnableRedraw(False)

    for src_id in hole_inserts:
        try:
            insert_pt = rs.BlockInstanceInsertPoint(src_id)
            if not insert_pt:
                miss_no_insert += 1
                missed += 1
                continue

            xform = get_instance_xform(src_id)
            if not xform:
                miss_no_xform += 1
                missed += 1
                continue

            target_hosts = gcu.filter_hosts_under_point(current_hosts, insert_pt, SEARCH_DROP, INSIDE_TOL)
            if not target_hosts:
                miss_no_host += 1
                missed += 1
                continue

            cutter_id = gcu.make_global_depth_cylinder(insert_pt, HOLE_DIAMETER, global_top_z, HOLE_DEPTH)
            if not cutter_id:
                miss_no_cutter += 1
                missed += 1
                continue

            updated_subset, touched, failed = gcu.boolean_difference_many(target_hosts, cutter_id)
            if touched == 0:
                miss_boolean += 1
                missed += 1
                continue

            cut_count += 1
            touched_hosts += touched
            missed += failed
            current_hosts = merge_host_updates(current_hosts, target_hosts, updated_subset)

            screw_id = insert_block_with_xform(SCREW_BLOCK, xform)
            if screw_id:
                rs.ObjectLayer(screw_id, FITTINGS_LAYER)
                screw_count += 1

        except:
            miss_exception += 1
            if len(exception_samples) < 3:
                exception_samples.append(traceback.format_exc())
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox(
        (
            "Holes cut: {}\nHosts touched: {}\nGrub screws inserted: {}\nMissed: {}\n"
            "(miss detail) no insert point: {}, no xform: {}, no host match: {}, no cutter: {}, boolean failed: {}, exceptions: {}\n{}"
        ).format(
            cut_count, touched_hosts, screw_count, missed,
            miss_no_insert, miss_no_xform, miss_no_host, miss_no_cutter, miss_boolean, miss_exception,
            ("\n".join(exception_samples) if exception_samples else "")
        )
    )

main()