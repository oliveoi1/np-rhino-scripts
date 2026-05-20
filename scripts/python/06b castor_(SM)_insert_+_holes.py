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

SOURCE_BLOCK = "castor_insert"
TARGET_BLOCK = "ACC-CST-SM"

HOLE_SPACING_IN = 1.25
HOLE_DIAMETER_IN = 0.25
HOLE_OVERSHOOT_IN = 0.05

def inches_to_doc_units(val_in):
    scale = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Inches, sc.doc.ModelUnitSystem)
    return val_in * scale

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

def get_local_axis_world(xform, axis_name):
    p0 = Rhino.Geometry.Point3d(0, 0, 0)

    if axis_name.upper() == "X":
        p1 = Rhino.Geometry.Point3d(1, 0, 0)
    elif axis_name.upper() == "Y":
        p1 = Rhino.Geometry.Point3d(0, 1, 0)
    else:
        p1 = Rhino.Geometry.Point3d(0, 0, 1)

    p0w = xform * p0
    p1w = xform * p1
    axis_vec = p1w - p0w

    return p0w, axis_vec

def local_offset_point(insert_pt, xform, off_x, off_y):
    _, x_axis = get_local_axis_world(xform, "X")
    _, y_axis = get_local_axis_world(xform, "Y")

    x_axis.Unitize()
    y_axis.Unitize()

    vx = Rhino.Geometry.Vector3d(x_axis)
    vy = Rhino.Geometry.Vector3d(y_axis)

    vx *= off_x
    vy *= off_y

    pt = Rhino.Geometry.Point3d(insert_pt.X, insert_pt.Y, insert_pt.Z)
    pt += vx
    pt += vy
    return pt

def merge_host_updates(current_hosts, target_hosts, updated_hosts):
    target_set = set(target_hosts)
    kept = [obj_id for obj_id in current_hosts if obj_id not in target_set]
    kept.extend(updated_hosts)
    return kept

def main():
    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    if not rs.IsBlock(TARGET_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(TARGET_BLOCK))
        return

    search_drop = inches_to_doc_units(0.02)
    hole_spacing = inches_to_doc_units(HOLE_SPACING_IN)
    hole_diameter = inches_to_doc_units(HOLE_DIAMETER_IN)
    hole_overshoot = inches_to_doc_units(HOLE_OVERSHOOT_IN)

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select castor_insert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    source_ids = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not source_ids:
        rs.MessageBox("No castor_insert blocks found in selection.")
        return

    seed_host = rs.GetObject("Select one solid from target stack/group", rs.filter.polysurface, preselect=False)
    if not seed_host:
        return

    current_hosts = gcu.collect_group_closed_solids(seed_host)
    if not current_hosts:
        rs.MessageBox("Selected object/group does not contain closed solids.")
        return

    global_top_z = gcu.compute_global_stack_top_z(current_hosts)
    global_bottom_z = gcu.compute_global_stack_bottom_z(current_hosts)
    if global_top_z is None or global_bottom_z is None:
        rs.MessageBox("Could not determine stack top/bottom.")
        return

    global_hole_depth = (global_top_z - global_bottom_z) + hole_overshoot

    placed = 0
    cut_count = 0
    touched_hosts = 0
    missed = 0

    rs.EnableRedraw(False)

    for src_id in source_ids:
        try:
            xform = get_instance_xform(src_id)
            if not xform:
                missed += 1
                continue

            insert_pt = rs.BlockInstanceInsertPoint(src_id)
            if not insert_pt:
                missed += 1
                continue

            target_hosts = gcu.filter_hosts_under_point(current_hosts, insert_pt, search_drop, 0.01)
            if not target_hosts:
                missed += 1
                continue

            new_id = insert_block_with_xform(TARGET_BLOCK, xform)
            if not new_id:
                missed += 1
                continue

            insert_pt_x, axis_x = get_local_axis_world(xform, "X")
            flip_rot = Rhino.Geometry.Transform.Rotation(
                math.radians(180.0),
                axis_x,
                insert_pt_x
            )
            rs.TransformObject(new_id, flip_rot, copy=False)

            insert_pt_z, axis_z = get_local_axis_world(xform, "Z")
            cw_rot = Rhino.Geometry.Transform.Rotation(
                math.radians(-90.0),
                axis_z,
                insert_pt_z
            )
            rs.TransformObject(new_id, cw_rot, copy=False)

            rs.ObjectLayer(new_id, rs.ObjectLayer(src_id))
            placed += 1

            half = hole_spacing / 2.0

            hole_points = [
                local_offset_point(insert_pt, xform,  half,  half),
                local_offset_point(insert_pt, xform, -half,  half),
                local_offset_point(insert_pt, xform, -half, -half),
                local_offset_point(insert_pt, xform,  half, -half),
            ]

            cutter_ids = []
            for hp in hole_points:
                cid = gcu.make_global_depth_cylinder(hp, hole_diameter, global_top_z, global_hole_depth)
                if cid:
                    cutter_ids.append(cid)

            if len(cutter_ids) != 4:
                for cid in cutter_ids:
                    if rs.IsObject(cid):
                        rs.DeleteObject(cid)
                missed += 1
                continue

            subset_hosts = target_hosts
            touched_local = 0
            failed_local = 0
            for cid in cutter_ids:
                subset_hosts, touched, failed = gcu.boolean_difference_many(subset_hosts, cid)
                touched_local += touched
                failed_local += failed

            if touched_local > 0:
                current_hosts = merge_host_updates(current_hosts, target_hosts, subset_hosts)
                cut_count += 1
                touched_hosts += touched_local
                missed += failed_local
            else:
                missed += 1

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox(
        "Castors inserted: {}\nHole sets cut: {}\nHosts touched: {}\nMissed: {}".format(
            placed, cut_count, touched_hosts, missed
        )
    )

main()