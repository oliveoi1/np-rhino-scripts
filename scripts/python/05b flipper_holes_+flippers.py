import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino
import os
import sys

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

import group_cut_utils as gcu

SOURCE_BLOCK = "flipper_insert"
RECEPTACLE_BLOCK = "flipper_receptacle"
PIN_BLOCK = "flipper_pin"

FITTINGS_LAYER = "NP-Fittings"

HOLE_DIAMETER_MM = 15.0
HOLE_DEPTH_MM = 10.5

# receptacle flat side perpendicular to insert tail
RECEPTACLE_ANGLE_OFFSET = 0

# pin follows insert direction
PIN_ANGLE_OFFSET = 0

SEARCH_DROP = 0.02
INSIDE_TOL = 0.01

DELETE_FLIPPER_INSERT = False

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def mm_to_doc_units(val_mm):
    scale = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Millimeters, sc.doc.ModelUnitSystem)
    return val_mm * scale

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

def insert_block_with_xform_and_offset(block_name, xform, insert_pt, angle_offset, layer_name):
    new_id = insert_block_with_xform(block_name, xform)
    if not new_id:
        return None
    if angle_offset != 0.0:
        rs.RotateObject(new_id, insert_pt, angle_offset)
    rs.ObjectLayer(new_id, layer_name)
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

    if not rs.IsBlock(RECEPTACLE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(RECEPTACLE_BLOCK))
        return

    add_pin = rs.MessageBox("Also insert flipper_pin?", 4, "Flipper Hardware")
    insert_pin = (add_pin == 6)

    if insert_pin and not rs.IsBlock(PIN_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(PIN_BLOCK))
        return

    hole_diameter = mm_to_doc_units(HOLE_DIAMETER_MM)
    hole_depth = mm_to_doc_units(HOLE_DEPTH_MM)

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select flipper_insert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    inserts = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not inserts:
        rs.MessageBox("No flipper_insert blocks selected.")
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
    receptacle_count = 0
    pin_count = 0
    deleted_count = 0
    missed = 0

    rs.EnableRedraw(False)

    for src_id in inserts:
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

            cutter_id = gcu.make_global_depth_cylinder(insert_pt, hole_diameter, global_top_z, hole_depth)
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

            rid = insert_block_with_xform_and_offset(
                RECEPTACLE_BLOCK,
                xform,
                insert_pt,
                RECEPTACLE_ANGLE_OFFSET,
                FITTINGS_LAYER
            )
            if rid:
                receptacle_count += 1

            if insert_pin:
                pid = insert_block_with_xform_and_offset(
                    PIN_BLOCK,
                    xform,
                    insert_pt,
                    PIN_ANGLE_OFFSET,
                    FITTINGS_LAYER
                )
                if pid:
                    pin_count += 1

            if DELETE_FLIPPER_INSERT and rs.IsObject(src_id):
                rs.DeleteObject(src_id)
                deleted_count += 1

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox(
        "Holes cut: {}\nHosts touched: {}\nFlipper receptacles inserted: {}\nFlipper pins inserted: {}\nFlipper inserts deleted: {}\nMissed: {}".format(
            cut_count, touched_hosts, receptacle_count, pin_count, deleted_count, missed
        )
    )

main()