import rhinoscriptsyntax as rs

# FIXED SETTINGS
BLOCK_NAME = "hole_insert"
TARGET_LAYER = "NP-Construction - Setout"

MAX_SIZE = 0.4
MIN_SIZE = 0.15
DELETE_SOURCE = False

def bbox_center(obj_id):
    bb = rs.BoundingBox(obj_id)
    if not bb or len(bb) < 8:
        return None, None, None
    minx = min(pt.X for pt in bb)
    maxx = max(pt.X for pt in bb)
    miny = min(pt.Y for pt in bb)
    maxy = max(pt.Y for pt in bb)
    minz = min(pt.Z for pt in bb)
    maxz = max(pt.Z for pt in bb)
    center = ((minx + maxx) / 2.0, (miny + maxy) / 2.0, (minz + maxz) / 2.0)
    width = maxx - minx
    height = maxy - miny
    return center, width, height

def is_small_round_curve(obj_id):
    if not rs.IsCurve(obj_id):
        return False, None

    if not rs.IsCurveClosed(obj_id):
        return False, None

    center, width, height = bbox_center(obj_id)
    if center is None:
        return False, None

    if width < MIN_SIZE or height < MIN_SIZE:
        return False, None

    if width > MAX_SIZE or height > MAX_SIZE:
        return False, None

    ratio = width / height if height != 0 else 999999
    if ratio < 0.85 or ratio > 1.15:
        return False, None

    avg_diameter = (width + height) / 2.0
    expected = 3.141592653589793 * avg_diameter
    actual = rs.CurveLength(obj_id)

    if not actual or expected == 0:
        return False, None

    length_ratio = actual / expected
    if length_ratio < 0.9 or length_ratio > 1.1:
        return False, None

    return True, center

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def main():
    ensure_layer(TARGET_LAYER)

    if not rs.IsBlock(BLOCK_NAME):
        rs.MessageBox("Block '{}' not found.".format(BLOCK_NAME))
        return

    objs = rs.GetObjects("Select area to scan", rs.filter.curve, preselect=True)
    if not objs:
        return

    count = 0

    for obj in objs:
        ok, center = is_small_round_curve(obj)
        if ok and center:
            new_id = rs.InsertBlock(BLOCK_NAME, center)
            if new_id:
                rs.ObjectLayer(new_id, TARGET_LAYER)
                count += 1
                if DELETE_SOURCE:
                    rs.DeleteObject(obj)

    rs.MessageBox("{} inserts placed.".format(count))

main()