import rhinoscriptsyntax as rs
import os
import sys

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

SOURCE_BLOCK = "caminsert"
TARGET_BLOCK = "cam"
FITTINGS_LAYER = "NP-Fittings"

HOLE_DIAMETER = 0.787
HOLE_DEPTH = 0.55

SEARCH_DROP = 0.02
INSIDE_TOL = 0.01

DELETE_CAMINSERT = False

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
    target_set = set(target_hosts)
    kept = [obj_id for obj_id in current_hosts if obj_id not in target_set]
    kept.extend(updated_hosts)
    return kept

def main():
    ensure_layer(FITTINGS_LAYER)

    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    if not rs.IsBlock(TARGET_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(TARGET_BLOCK))
        return

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select caminsert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    caminserts = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not caminserts:
        rs.MessageBox("No caminsert blocks selected.")
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
    lock_count = 0
    missed = 0
    deleted_count = 0

    rs.EnableRedraw(False)

    for src_id in caminserts:
        try:
            insert_pt = rs.BlockInstanceInsertPoint(src_id)
            if not insert_pt:
                missed += 1
                continue

            xform = get_instance_xform(src_id)
            if not xform:
                missed += 1
                continue

            target_hosts = gcu.filter_hosts_under_point(current_hosts, insert_pt, SEARCH_DROP, INSIDE_TOL)
            if not target_hosts:
                missed += 1
                continue

            cutter_id = gcu.make_global_depth_cylinder(insert_pt, HOLE_DIAMETER, global_top_z, HOLE_DEPTH)
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

            lock_id = insert_block_with_xform(TARGET_BLOCK, xform)
            if lock_id:
                rs.ObjectLayer(lock_id, FITTINGS_LAYER)
                lock_count += 1

            if DELETE_CAMINSERT and rs.IsObject(src_id):
                rs.DeleteObject(src_id)
                deleted_count += 1

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox(
        "Holes cut: {}\nHosts touched: {}\nCams inserted: {}\nCaminserts deleted: {}\nMissed: {}".format(
            cut_count, touched_hosts, lock_count, deleted_count, missed
        )
    )

main()