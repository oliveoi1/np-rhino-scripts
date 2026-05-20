import rhinoscriptsyntax as rs
import Rhino
import math

SOURCE_BLOCK = "castor_insert"
TARGET_BLOCK = "ACC-CST-SM"

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

def main():
    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    if not rs.IsBlock(TARGET_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(TARGET_BLOCK))
        return

    objs = rs.GetObjects("Select area containing castor_insert blocks", rs.filter.instance, preselect=True)
    if not objs:
        return

    source_ids = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not source_ids:
        rs.MessageBox("No castor_insert blocks found in selection.")
        return

    placed = 0
    missed = 0

    rs.EnableRedraw(False)

    for src_id in source_ids:
        try:
            xform = get_instance_xform(src_id)
            if not xform:
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

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox("Inserted: {}\nMissed: {}".format(placed, missed))

main()