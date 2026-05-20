import rhinoscriptsyntax as rs
import Rhino

TEXT_HEIGHT = 1.0
X_OFFSET = 1.0
Y_OFFSET = 1.0
LABEL_LAYER = "NP-Text"

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def get_block_name(obj_id):
    if rs.IsBlockInstance(obj_id):
        try:
            return rs.BlockInstanceName(obj_id)
        except:
            return None
    return None

def get_bottom_left_point_xy(obj_id):
    bb = rs.BoundingBox(obj_id)
    if not bb:
        return None

    minx = min(pt.X for pt in bb)
    miny = min(pt.Y for pt in bb)

    return Rhino.Geometry.Point3d(minx, miny, 0.0)

def make_label_text(block_name, qty):
    if qty == 1:
        return block_name
    else:
        return "{} x{}".format(block_name, qty)

def add_label(pt, text_string, height):
    plane = Rhino.Geometry.Plane.WorldXY
    plane.Origin = Rhino.Geometry.Point3d(pt.X + X_OFFSET, pt.Y - Y_OFFSET, 0.0)
    return rs.AddText(text_string, plane, height)

def main():
    ensure_layer(LABEL_LAYER)

    rs.UnselectAllObjects()
    objs = rs.GetObjects("Select top level block instances to label", rs.filter.instance, preselect=False)
    if not objs:
        return

    block_groups = {}

    for obj_id in objs:
        if not rs.IsBlockInstance(obj_id):
            continue

        block_name = get_block_name(obj_id)
        if not block_name:
            continue

        if block_name not in block_groups:
            block_groups[block_name] = []

        block_groups[block_name].append(obj_id)

    if not block_groups:
        rs.MessageBox("No block instances found in selection.")
        return

    made = 0

    rs.EnableRedraw(False)

    for block_name, ids in block_groups.items():
        first_id = ids[0]
        qty = len(ids)

        pt = get_bottom_left_point_xy(first_id)
        if not pt:
            continue

        label = make_label_text(block_name, qty)
        text_id = add_label(pt, label, TEXT_HEIGHT)

        if text_id:
            rs.ObjectLayer(text_id, LABEL_LAYER)
            made += 1

    rs.EnableRedraw(True)

    rs.MessageBox("{} label(s) created.".format(made))

main()