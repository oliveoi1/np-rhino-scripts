import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc

SOURCE_BLOCK = "glide_insert"
TARGET_BLOCK = "glide"
TARGET_LAYER = "NP-Fittings"
Z_OFFSET_IN = -0.375

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

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

def main():
    ensure_layer(TARGET_LAYER)

    if not rs.IsBlock(SOURCE_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(SOURCE_BLOCK))
        return

    if not rs.IsBlock(TARGET_BLOCK):
        rs.MessageBox("Block '{}' not found.".format(TARGET_BLOCK))
        return

    z_offset = inches_to_doc_units(Z_OFFSET_IN)

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select glide_insert blocks", rs.filter.instance, preselect=False)
    if not objs:
        return

    source_ids = [obj_id for obj_id in objs if is_block_instance_of(obj_id, SOURCE_BLOCK)]
    if not source_ids:
        rs.MessageBox("No glide_insert blocks found in selection.")
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

            rs.MoveObject(new_id, (0, 0, z_offset))
            rs.ObjectLayer(new_id, TARGET_LAYER)

            placed += 1

        except:
            missed += 1
            continue

    rs.EnableRedraw(True)

    rs.MessageBox("Glides inserted: {}\nMissed: {}".format(placed, missed))

main()