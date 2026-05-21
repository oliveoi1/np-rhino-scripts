from __future__ import print_function

import math

import rhinoscriptsyntax as rs
import scriptcontext as sc

BLOCK_NAME = "caminsert"
TARGET_LAYER = "NP-Construction - Setout"

CIRCLE_MIN_SIZE = 0.65
CIRCLE_MAX_SIZE = 0.95
SHORT_LINE_MIN_LEN = 0.2
SHORT_LINE_MAX_LEN = 1.0
CENTER_TO_LINE_END_TOL = 0.08
TOUCH_TOL = 0.03
ROUND_RATIO_TOL = 0.18
CIRCUMFERENCE_TOL = 0.15

BLOCK_ANGLE_OFFSET = 180.0
DELETE_SOURCE = False

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def bbox_info(obj_id):
    bb = rs.BoundingBox(obj_id)
    if not bb or len(bb) < 8:
        return None

    minx = min(p.X for p in bb)
    maxx = max(p.X for p in bb)
    miny = min(p.Y for p in bb)
    maxy = max(p.Y for p in bb)
    minz = min(p.Z for p in bb)
    maxz = max(p.Z for p in bb)

    return {
        "center": ((minx + maxx) / 2.0, (miny + maxy) / 2.0, (minz + maxz) / 2.0),
        "width": maxx - minx,
        "height": maxy - miny
    }

def normalize_angle(a):
    return a % 360.0

def angle_from_pts(p0, p1):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    return math.degrees(math.atan2(dy, dx))

def point_distance(a, b):
    return rs.Distance(a, b)


def closure_tolerance():
    tol = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.01
    return max(tol * 100.0, 1e-4)


def is_effectively_closed(obj_id):
    """PolyCurves from arcs often have micro-gaps but are geometrically closed."""
    if rs.IsCurveClosed(obj_id):
        return True
    start = rs.CurveStartPoint(obj_id)
    end = rs.CurveEndPoint(obj_id)
    if not start or not end:
        return False
    return point_distance(start, end) <= closure_tolerance()


def is_round_closed_curve(obj_id):
    if not rs.IsCurve(obj_id):
        return False, None, "not_curve"

    if not is_effectively_closed(obj_id):
        return False, None, "not_closed"

    info = bbox_info(obj_id)
    if not info:
        return False, None, "no_bbox"

    w = info["width"]
    h = info["height"]

    if w < CIRCLE_MIN_SIZE or h < CIRCLE_MIN_SIZE:
        return False, None, "too_small"

    if w > CIRCLE_MAX_SIZE or h > CIRCLE_MAX_SIZE:
        return False, None, "too_large"

    ratio = w / h if h != 0 else 999999
    if ratio < (1.0 - ROUND_RATIO_TOL) or ratio > (1.0 + ROUND_RATIO_TOL):
        return False, None, "not_round"

    avg_dia = (w + h) / 2.0
    expected = math.pi * avg_dia
    actual = rs.CurveLength(obj_id)

    if not actual or expected == 0:
        return False, None, "no_length"

    lr = actual / expected
    if lr < (1.0 - CIRCUMFERENCE_TOL) or lr > (1.0 + CIRCUMFERENCE_TOL):
        return False, None, "bad_circumference"

    return True, info["center"], None

def get_short_line_data(obj_id):
    if not rs.IsCurve(obj_id):
        return None

    if rs.IsCurveClosed(obj_id):
        return None

    start = rs.CurveStartPoint(obj_id)
    end = rs.CurveEndPoint(obj_id)
    if not start or not end:
        return None

    length = rs.Distance(start, end)
    if length < SHORT_LINE_MIN_LEN or length > SHORT_LINE_MAX_LEN:
        return None

    return {
        "id": obj_id,
        "start": start,
        "end": end,
        "length": length
    }

def find_short_line_for_circle(center, line_data_list):
    best = None
    best_dist = 1e9

    for seg in line_data_list:
        d0 = point_distance(center, seg["start"])
        d1 = point_distance(center, seg["end"])

        if d0 <= CENTER_TO_LINE_END_TOL and d1 > d0:
            outer_pt = seg["end"]
            dist = d0
        elif d1 <= CENTER_TO_LINE_END_TOL and d0 > d1:
            outer_pt = seg["start"]
            dist = d1
        else:
            continue

        if dist < best_dist:
            best_dist = dist
            best = (seg, outer_pt)

    return best

def nearest_touching_curve_direction(circle_id, center, radius, all_curve_ids):
    best_curve = None
    best_pt_on_edge = None
    best_dist = 1e9

    for cid in all_curve_ids:
        if cid == circle_id:
            continue
        if not rs.IsCurve(cid):
            continue

        try:
            param = rs.CurveClosestPoint(cid, center)
            if param is None:
                continue

            pt_on_edge = rs.EvaluateCurve(cid, param)
            if not pt_on_edge:
                continue

            d = rs.Distance(pt_on_edge, center)
            touch_tol = max(TOUCH_TOL, radius * 0.2)

            if abs(d - radius) > touch_tol:
                continue

            if d < best_dist:
                best_dist = d
                best_curve = cid
                best_pt_on_edge = pt_on_edge

        except:
            continue

    if not best_curve or not best_pt_on_edge:
        return None

    return angle_from_pts(best_pt_on_edge, center)


def nearest_wall_direction(center, circle_id, all_curve_ids):
    """Fallback: aim toward closest point on any other curve (e.g. pocket outline)."""
    best_pt = None
    best_dist = None

    for cid in all_curve_ids:
        if cid == circle_id:
            continue
        if not rs.IsCurve(cid):
            continue
        try:
            param = rs.CurveClosestPoint(cid, center)
            if param is None:
                continue
            pt_on = rs.EvaluateCurve(cid, param)
            if not pt_on:
                continue
            d = point_distance(center, pt_on)
            if d < 1e-6:
                continue
            if best_dist is None or d < best_dist:
                best_dist = d
                best_pt = pt_on
        except Exception:
            continue

    if best_pt is None:
        return None
    return angle_from_pts(center, best_pt)


def insert_oriented_block(block_name, insert_pt, angle_deg, layer_name):
    new_id = rs.InsertBlock(block_name, insert_pt)
    if not new_id:
        return None

    rs.RotateObject(new_id, insert_pt, angle_deg)
    rs.ObjectLayer(new_id, layer_name)
    return new_id

def get_symbol_direction(circle_id, center, short_lines, all_curve_ids):
    short_match = find_short_line_for_circle(center, short_lines)
    if short_match:
        seg, outer_pt = short_match
        return angle_from_pts(center, outer_pt), "short_line"

    info = bbox_info(circle_id)
    if not info:
        return None, None

    radius = (info["width"] + info["height"]) / 4.0

    edge_dir = nearest_touching_curve_direction(circle_id, center, radius, all_curve_ids)
    if edge_dir is not None:
        return edge_dir, "edge_touch"

    wall_dir = nearest_wall_direction(center, circle_id, all_curve_ids)
    if wall_dir is not None:
        return wall_dir, "nearest_wall"

    return None, None

def main():
    ensure_layer(TARGET_LAYER)

    if not rs.IsBlock(BLOCK_NAME):
        rs.MessageBox("Block '{}' not found.".format(BLOCK_NAME))
        return

    objs = rs.GetObjects(
        "Select cam circles and pocket outline curves",
        rs.filter.curve,
        preselect=True,
    )
    if not objs:
        return

    circles = []
    short_lines = []
    all_curves = []
    reject_counts = {}

    for obj in objs:
        if rs.IsCurve(obj):
            all_curves.append(obj)

        ok, center, reason = is_round_closed_curve(obj)
        if ok:
            circles.append((obj, center))
            continue

        if reason:
            reject_counts[reason] = reject_counts.get(reason, 0) + 1

        line_data = get_short_line_data(obj)
        if line_data:
            short_lines.append(line_data)

    if not circles:
        detail = ""
        if reject_counts:
            parts = ["{}: {}".format(k, v) for k, v in sorted(reject_counts.items())]
            detail = "\nRejected:\n" + "\n".join(parts)
        rs.MessageBox(
            "No valid cam circles found.\n"
            "Need closed round loops (~0.65-0.95 wide) plus outline curves."
            + detail
        )
        return

    placed = 0
    skipped = 0

    rs.EnableRedraw(False)

    for circle_id, center in circles:
        base_dir, symbol_type = get_symbol_direction(circle_id, center, short_lines, all_curves)
        if base_dir is None:
            skipped += 1
            continue

        # nearest_wall: base_dir is center->outline; BLOCK_ANGLE_OFFSET flips to cam facing.
        # edge_touch: base_dir is outline->center; add 180 so it matches short_line logic.
        extra_offset = 180.0 if symbol_type == "edge_touch" else 0.0
        final_angle = normalize_angle(base_dir + BLOCK_ANGLE_OFFSET + extra_offset)

        new_id = insert_oriented_block(BLOCK_NAME, center, final_angle, TARGET_LAYER)
        if new_id:
            placed += 1
            if DELETE_SOURCE:
                rs.DeleteObject(circle_id)
        else:
            skipped += 1

    rs.EnableRedraw(True)

    rs.MessageBox("{} caminsert block(s) placed.\n{} skipped.".format(placed, skipped))

main()