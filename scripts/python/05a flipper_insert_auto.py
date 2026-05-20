import rhinoscriptsyntax as rs
import Rhino
import math

BLOCK_NAME = "flipper_insert"
TARGET_LAYER = "NP-Construction - Setout"

MIN_SIZE = 0.4
MAX_SIZE = 1.2
MIN_ARC_SEGMENTS = 3
MIN_LINE_SEGMENTS = 2
ANGLE_OFFSET = 0.0
DELETE_SOURCE = False

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def avg_point(pts):
    if not pts:
        return None
    x = sum(p.X for p in pts) / float(len(pts))
    y = sum(p.Y for p in pts) / float(len(pts))
    z = sum(p.Z for p in pts) / float(len(pts))
    return Rhino.Geometry.Point3d(x, y, z)

def angle_from_pts(p0, p1):
    dx = p1.X - p0.X
    dy = p1.Y - p0.Y
    return math.degrees(math.atan2(dy, dx))

def bbox_size_ok(obj_id):
    bb = rs.BoundingBox(obj_id)
    if not bb:
        return False
    minx = min(p.X for p in bb)
    maxx = max(p.X for p in bb)
    miny = min(p.Y for p in bb)
    maxy = max(p.Y for p in bb)
    w = maxx - minx
    h = maxy - miny
    return (MIN_SIZE <= w <= MAX_SIZE) and (MIN_SIZE <= h <= MAX_SIZE)

def get_segment_curve_ids(obj_id):
    seg_ids = rs.ExplodeCurves(obj_id, delete_input=False)
    if seg_ids:
        return seg_ids, True
    dup = rs.CopyObject(obj_id)
    if dup:
        return [dup], True
    return [], False

def get_symbol_data(obj_id):
    if not rs.IsCurve(obj_id):
        return None
    if not rs.IsCurveClosed(obj_id):
        return None
    if not bbox_size_ok(obj_id):
        return None

    seg_ids, made_temp = get_segment_curve_ids(obj_id)
    if not seg_ids:
        return None

    arc_centers = []
    line_mids = []

    try:
        for sid in seg_ids:
            if rs.IsLine(sid):
                start = rs.CurveStartPoint(sid)
                end = rs.CurveEndPoint(sid)
                if start and end:
                    mid = Rhino.Geometry.Point3d(
                        (start.X + end.X) / 2.0,
                        (start.Y + end.Y) / 2.0,
                        (start.Z + end.Z) / 2.0
                    )
                    line_mids.append(mid)
                continue

            center = rs.ArcCenterPoint(sid)
            if center:
                arc_centers.append(center)
                continue

    finally:
        if made_temp:
            for sid in seg_ids:
                if rs.IsObject(sid):
                    rs.DeleteObject(sid)

    if len(arc_centers) < MIN_ARC_SEGMENTS:
        return None
    if len(line_mids) < MIN_LINE_SEGMENTS:
        return None

    circle_center = avg_point(arc_centers)
    tab_center = avg_point(line_mids)

    if circle_center is None or tab_center is None:
        return None

    return {
        "center": circle_center,
        "tab_center": tab_center
    }

def insert_oriented_block(block_name, insert_pt, angle_deg, layer_name):
    new_id = rs.InsertBlock(block_name, insert_pt)
    if not new_id:
        return None
    rs.RotateObject(new_id, insert_pt, angle_deg)
    rs.ObjectLayer(new_id, layer_name)
    return new_id

def main():
    ensure_layer(TARGET_LAYER)

    if not rs.IsBlock(BLOCK_NAME):
        rs.MessageBox("Block '{}' not found.".format(BLOCK_NAME))
        return

    objs = rs.GetObjects("Select area to scan", rs.filter.curve, preselect=True)
    if not objs:
        return

    placed = 0

    for obj in objs:
        data = get_symbol_data(obj)
        if not data:
            continue

        center = data["center"]
        tab_center = data["tab_center"]

        angle_deg = angle_from_pts(center, tab_center) + ANGLE_OFFSET

        new_id = insert_oriented_block(BLOCK_NAME, center, angle_deg, TARGET_LAYER)
        if new_id:
            placed += 1
            if DELETE_SOURCE:
                rs.DeleteObject(obj)

    rs.MessageBox("{} flipper_insert block(s) placed.".format(placed))

main()