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
SLOT_LINE_MIN_LEN = 0.5
SLOT_LINE_MAX_LEN = 8.0
SLOT_LINE_MAX_DIST = 1.0
EDGE_APPROACH_RATIO = 1.25
CENTER_TO_LINE_END_TOL = 0.08
TOUCH_TOL = 0.03
ROUND_RATIO_TOL = 0.18
CIRCUMFERENCE_TOL = 0.15
FACE_PERP_WEIGHT = 12.0
MAX_FACE_PERP = 0.75

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


def point_xyz(pt):
    if pt is None:
        return None
    if hasattr(pt, "X"):
        return (pt.X, pt.Y, pt.Z)
    return (pt[0], pt[1], pt[2])


def xy_tuple(pt):
    x, y, z = point_xyz(pt)
    return (x, y)


def unit_xy(vec):
    x, y = vec[0], vec[1]
    length = math.hypot(x, y)
    if length < 1e-12:
        return None
    return (x / length, y / length)


def perpendicularity(approach_xy, tangent_xy):
    a = unit_xy(approach_xy)
    t = unit_xy(tangent_xy)
    if not a or not t:
        return 1.0
    return abs(a[0] * t[0] + a[1] * t[1])


def pocket_outline_bbox(all_curve_ids, circle_ids):
    minx = miny = 1e9
    maxx = maxy = -1e9
    found = False
    circle_set = set(circle_ids or [])

    for cid in all_curve_ids:
        if cid in circle_set:
            continue
        if not rs.IsCurve(cid):
            continue

        bb = rs.BoundingBox(cid)
        if not bb:
            continue

        for p in bb:
            px, py, pz = point_xyz(p)
            minx = min(minx, px)
            maxx = max(maxx, px)
            miny = min(miny, py)
            maxy = max(maxy, py)
            found = True

    if not found:
        return None

    return (minx, maxx, miny, maxy)


def dominant_open_edge(center, bbox):
    if not bbox:
        return None

    minx, maxx, miny, maxy = bbox
    cx, cy = xy_tuple(center)

    dists = {
        "left": cx - minx,
        "right": maxx - cx,
        "bottom": cy - miny,
        "top": maxy - cy
    }

    return min(dists, key=dists.get)


def pocket_interior_point(bbox):
    if not bbox:
        return None

    minx, maxx, miny, maxy = bbox
    return ((minx + maxx) / 2.0, (miny + maxy) / 2.0, 0.0)


def approach_matches_edge(center, pt_on, edge_name):
    if not edge_name:
        return True

    cx, cy = xy_tuple(center)
    px, py = xy_tuple(pt_on)

    dx = abs(px - cx)
    dy = abs(py - cy)

    if edge_name in ("left", "right"):
        return dx >= dy * EDGE_APPROACH_RATIO

    if edge_name in ("top", "bottom"):
        return dy >= dx * EDGE_APPROACH_RATIO

    return True


def curve_tangent_xy(cid, param):
    try:
        tan = rs.CurveTangent(cid, param)
        if tan:
            return xy_tuple(tan)
    except Exception:
        pass

    try:
        start = rs.CurveStartPoint(cid)
        end = rs.CurveEndPoint(cid)
        if start and end:
            sx, sy, sz = point_xyz(start)
            ex, ey, ez = point_xyz(end)
            return (ex - sx, ey - sy)
    except Exception:
        pass

    return None


def closure_tolerance():
    tol = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.01
    return max(tol * 100.0, 1e-4)


def is_effectively_closed(obj_id):
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


def slot_line_aim_point(center, all_curve_ids, circle_id):
    best_pt = None
    best_dist = None

    for cid in all_curve_ids:
        if cid == circle_id:
            continue
        if not rs.IsCurve(cid):
            continue
        if rs.IsCurveClosed(cid):
            continue

        try:
            length = rs.CurveLength(cid)

            if not length or length < SLOT_LINE_MIN_LEN or length > SLOT_LINE_MAX_LEN:
                continue

            param = rs.CurveClosestPoint(cid, center)
            if param is None:
                continue

            pt_on = rs.EvaluateCurve(cid, param)
            if not pt_on:
                continue

            d = point_distance(center, pt_on)

            if d > SLOT_LINE_MAX_DIST:
                continue

            if best_dist is None or d < best_dist:
                best_dist = d
                best_pt = pt_on

        except Exception:
            continue

    return best_pt


def nearest_touching_curve_direction(circle_id, center, radius, all_curve_ids):
    best_pt_on_edge = None
    best_dist = 1e9
    touch_tol = max(TOUCH_TOL, radius * 0.2)

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

            if abs(d - radius) > touch_tol:
                continue

            if d < best_dist:
                best_dist = d
                best_pt_on_edge = pt_on_edge

        except Exception:
            continue

    if not best_pt_on_edge:
        return None, None

    return angle_from_pts(best_pt_on_edge, center), best_pt_on_edge


def outward_angle_at_wall_hit(center, cid, param, pt_on, interior_pt):
    cx, cy = xy_tuple(center)
    px, py = xy_tuple(pt_on)

    to_wall = (px - cx, py - cy)

    tangent_xy = curve_tangent_xy(cid, param)
    t = unit_xy(tangent_xy)

    if t and interior_pt:
        n1 = (-t[1], t[0])
        n2 = (t[1], -t[0])

        ix, iy = xy_tuple(interior_pt)
        ext = (px - ix, py - iy)

        if n1[0] * ext[0] + n1[1] * ext[1] >= n2[0] * ext[0] + n2[1] * ext[1]:
            n = n1
        else:
            n = n2

        if n[0] * to_wall[0] + n[1] * to_wall[1] < 0:
            n = (-n[0], -n[1])

        return math.degrees(math.atan2(n[1], n[0]))

    return angle_from_pts(center, pt_on)


def nearest_wall_direction(center, circle_id, all_curve_ids, circle_ids=None):
    best = None

    bbox = pocket_outline_bbox(all_curve_ids, circle_ids)
    edge_name = dominant_open_edge(center, bbox)
    interior_pt = pocket_interior_point(bbox)

    def make_hit(cid, param, pt_on, max_perp):
        d = point_distance(center, pt_on)
        if d < 1e-6:
            return None

        cx, cy = xy_tuple(center)
        px, py = xy_tuple(pt_on)

        approach_xy = (px - cx, py - cy)
        tangent_xy = curve_tangent_xy(cid, param)
        perp = perpendicularity(approach_xy, tangent_xy)

        if perp > max_perp:
            return None

        if not approach_matches_edge(center, pt_on, edge_name):
            return None

        score = d * (1.0 + FACE_PERP_WEIGHT * perp * perp)
        return (score, cid, param, pt_on)

    for max_perp in (MAX_FACE_PERP, 0.95):
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

                hit = make_hit(cid, param, pt_on, max_perp)

                if hit and (best is None or hit[0] < best[0]):
                    best = hit

            except Exception:
                continue

        if best is not None:
            break

    if best is None:
        return None, None

    score, best_cid, best_param, best_pt = best

    angle = outward_angle_at_wall_hit(
        center,
        best_cid,
        best_param,
        best_pt,
        interior_pt
    )

    return angle, best_pt


def facing_vector(rotation_deg, block_offset_deg):
    rad = math.radians(rotation_deg + block_offset_deg)
    return (math.cos(rad), math.sin(rad))


def pick_rotation_toward_target(center, aim_angle, aim_point):
    if aim_point is None:
        return normalize_angle(aim_angle + BLOCK_ANGLE_OFFSET)

    cx, cy = xy_tuple(center)
    tx, ty = xy_tuple(aim_point)

    vx = tx - cx
    vy = ty - cy

    vlen = math.hypot(vx, vy)

    if vlen < 1e-9:
        return normalize_angle(aim_angle + BLOCK_ANGLE_OFFSET)

    vx /= vlen
    vy /= vlen

    best_rot = None
    best_dot = -999999.0

    for rot in (
        normalize_angle(aim_angle + BLOCK_ANGLE_OFFSET),
        normalize_angle(aim_angle + BLOCK_ANGLE_OFFSET + 180.0)
    ):
        fx, fy = facing_vector(rot, 0.0)
        dot = fx * vx + fy * vy

        if dot > best_dot:
            best_dot = dot
            best_rot = rot

    return normalize_angle(best_rot)


def final_cam_angle(base_dir, symbol_type, center=None, aim_point=None):
    if symbol_type == "edge_touch":
        aim_angle = normalize_angle(base_dir + 180.0)
    else:
        aim_angle = normalize_angle(base_dir)

    return pick_rotation_toward_target(center, aim_angle, aim_point)


def insert_oriented_block(block_name, insert_pt, angle_deg, layer_name):
    new_id = rs.InsertBlock(block_name, insert_pt)

    if not new_id:
        return None

    rs.RotateObject(new_id, insert_pt, angle_deg)
    rs.ObjectLayer(new_id, layer_name)

    return new_id


def get_symbol_direction(circle_id, center, short_lines, all_curve_ids, circle_ids=None):
    short_match = find_short_line_for_circle(center, short_lines)

    if short_match:
        seg, outer_pt = short_match
        return angle_from_pts(center, outer_pt), "short_line", outer_pt

    info = bbox_info(circle_id)

    if not info:
        return None, None, None

    radius = (info["width"] + info["height"]) / 4.0

    edge_dir, edge_pt = nearest_touching_curve_direction(
        circle_id,
        center,
        radius,
        all_curve_ids
    )

    if edge_dir is not None:
        return edge_dir, "edge_touch", edge_pt

    wall_dir, wall_pt = nearest_wall_direction(
        center,
        circle_id,
        all_curve_ids,
        circle_ids=circle_ids
    )

    if wall_dir is not None:
        return wall_dir, "nearest_wall", wall_pt

    slot_pt = slot_line_aim_point(center, all_curve_ids, circle_id)

    if slot_pt is not None:
        return angle_from_pts(center, slot_pt), "slot_line", slot_pt

    return None, None, None


def main():
    ensure_layer(TARGET_LAYER)

    if not rs.IsBlock(BLOCK_NAME):
        rs.MessageBox("Block '{}' not found.".format(BLOCK_NAME))
        return

    objs = rs.GetObjects(
        "Select cam circles and pocket outline curves",
        rs.filter.curve,
        preselect=True
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
            "Need closed round loops approximately 0.65 to 0.95 wide plus outline curves."
            + detail
        )

        return

    placed = 0
    skipped = 0
    circle_ids = [cid for cid, center in circles]

    rs.EnableRedraw(False)

    try:
        for circle_id, center in circles:
            base_dir, symbol_type, aim_point = get_symbol_direction(
                circle_id,
                center,
                short_lines,
                all_curves,
                circle_ids=circle_ids
            )

            if base_dir is None:
                skipped += 1
                continue

            final_angle = final_cam_angle(
                base_dir,
                symbol_type,
                center=center,
                aim_point=aim_point
            )

            new_id = insert_oriented_block(
                BLOCK_NAME,
                center,
                final_angle,
                TARGET_LAYER
            )

            if new_id:
                placed += 1

                if DELETE_SOURCE:
                    rs.DeleteObject(circle_id)
            else:
                skipped += 1
    finally:
        rs.EnableRedraw(True)
        try:
            sc.doc.Views.Redraw()
        except Exception:
            pass

    rs.MessageBox("{} caminsert block(s) placed.\n{} skipped.".format(placed, skipped))


if __name__ == "__main__":
    main()
