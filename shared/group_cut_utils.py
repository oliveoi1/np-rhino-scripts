import rhinoscriptsyntax as rs
import Rhino
import scriptcontext as sc


def coerce_brep(obj_id):
    try:
        geo = rs.coercegeometry(obj_id)
        if geo is None:
            return None
        return Rhino.Geometry.Brep.TryConvertBrep(geo)
    except:
        return None


def world_breps_from_object(obj_id):
    """
    Breps in world coordinates for a solid or block instance (duplicated).
    Block definitions are transformed by the instance xform.
    """
    rh = rs.coercerhinoobject(obj_id, True, True)
    if rh is None:
        return []

    breps = []
    try:
        if rs.IsBlockInstance(obj_id):
            idef = rh.InstanceDefinition
            if idef is None:
                return []
            xform = rh.InstanceXform
            if hasattr(idef, "GetObjectCount"):
                count = idef.GetObjectCount()
            else:
                count = idef.ObjectCount
            for i in range(count):
                if hasattr(idef, "GetObject"):
                    robj = idef.GetObject(i)
                else:
                    objs = idef.GetObjects()
                    robj = objs[i] if objs and i < len(objs) else None
                if robj is None:
                    continue
                geo = robj.Geometry
                if geo is None:
                    continue
                brep = Rhino.Geometry.Brep.TryConvertBrep(geo)
                if brep is None:
                    continue
                dup = brep.DuplicateBrep()
                dup.Transform(xform)
                if dup and dup.IsValid:
                    breps.append(dup)
            return breps
    except Exception:
        pass

    brep = coerce_brep(obj_id)
    if brep is None:
        return []
    try:
        dup = brep.DuplicateBrep()
    except Exception:
        dup = brep
    if dup and dup.IsValid:
        breps.append(dup)
    return breps


def replace_extrusion_with_brep_if_needed(obj_id):
    """
    ExtrudeCrv often creates Extrusion objects; Brep.CreateBooleanDifference is unreliable
    on them. Replace with a normal Brep in the document when possible.
    """
    if not rs.IsObject(obj_id):
        return obj_id
    try:
        geo = rs.coercegeometry(obj_id)
        if geo is None:
            return obj_id
        is_extrusion = False
        try:
            is_extrusion = isinstance(geo, Rhino.Geometry.Extrusion)
        except Exception:
            try:
                is_extrusion = geo.GetType().Name == "Extrusion"
            except Exception:
                is_extrusion = False
        if not is_extrusion:
            return obj_id
        brep = geo.ToBrep()
        if brep is None or not brep.IsValid:
            return obj_id
        layer = rs.ObjectLayer(obj_id)
        groups = object_groups(obj_id)
        rs.DeleteObject(obj_id)
        new_id = sc.doc.Objects.AddBrep(brep)
        if not new_id:
            return obj_id
        if layer:
            rs.ObjectLayer(new_id, layer)
        for group_name in groups:
            try:
                rs.AddObjectToGroup(new_id, group_name)
            except Exception:
                pass
        return new_id
    except Exception:
        return obj_id


def is_closed_solid(obj_id):
    brep = coerce_brep(obj_id)
    return bool(brep and brep.IsSolid)


def object_bbox(obj_id):
    return rs.BoundingBox(obj_id)


def bbox_top_z(obj_id):
    bb = object_bbox(obj_id)
    if not bb:
        return None
    return max(pt.Z for pt in bb)


def bbox_bottom_z(obj_id):
    bb = object_bbox(obj_id)
    if not bb:
        return None
    return min(pt.Z for pt in bb)


def object_groups(obj_id):
    groups = rs.ObjectGroups(obj_id)
    return groups or []


def collect_group_closed_solids(seed_obj_id):
    group_names = object_groups(seed_obj_id)

    candidates = []
    if group_names:
        for group_name in group_names:
            members = rs.ObjectsByGroup(group_name) or []
            candidates.extend(members)
    else:
        candidates.append(seed_obj_id)

    seen = set()
    solids = []
    for obj_id in candidates:
        if obj_id in seen:
            continue
        seen.add(obj_id)
        if is_closed_solid(obj_id):
            solids.append(obj_id)

    return solids


def compute_global_stack_top_z(host_ids):
    tops = [bbox_top_z(obj_id) for obj_id in host_ids]
    tops = [z for z in tops if z is not None]
    return max(tops) if tops else None


def compute_global_stack_bottom_z(host_ids):
    bottoms = [bbox_bottom_z(obj_id) for obj_id in host_ids]
    bottoms = [z for z in bottoms if z is not None]
    return min(bottoms) if bottoms else None


def bbox_xy_contains(obj_id, pt, xy_tol=0.0):
    bb = object_bbox(obj_id)
    if not bb:
        return False
    minx = min(p.X for p in bb)
    maxx = max(p.X for p in bb)
    miny = min(p.Y for p in bb)
    maxy = max(p.Y for p in bb)
    return (minx - xy_tol <= pt.X <= maxx + xy_tol) and (miny - xy_tol <= pt.Y <= maxy + xy_tol)


def point_inside_candidate(obj_id, pt, inside_tol):
    brep = coerce_brep(obj_id)
    if not brep:
        return False
    try:
        return brep.IsPointInside(pt, inside_tol, False)
    except:
        return False


def filter_hosts_under_point(host_ids, world_point, search_drop, inside_tol):
    xy_tol = max(float(inside_tol or 0.0), 1e-4)
    xy_candidates = []
    for host_id in host_ids:
        if not bbox_xy_contains(host_id, world_point, xy_tol):
            continue
        xy_candidates.append(host_id)

    if not xy_candidates:
        return []

    probe_offsets = [
        max(search_drop, inside_tol),
        max(search_drop * 0.5, inside_tol),
        max(search_drop * 2.0, inside_tol * 2.0),
    ]

    inside_hits = set()
    for host_id in xy_candidates:
        bb = object_bbox(host_id)
        sample_zs = [world_point.Z - offset for offset in probe_offsets]
        if bb:
            top_z = max(p.Z for p in bb)
            bottom_z = min(p.Z for p in bb)
            sample_zs.append(top_z - max(inside_tol * 0.5, 1e-4))
            sample_zs.append((top_z + bottom_z) * 0.5)

        for z_value in sample_zs:
            test_pt = Rhino.Geometry.Point3d(world_point.X, world_point.Y, z_value)
            if point_inside_candidate(host_id, test_pt, inside_tol):
                inside_hits.add(host_id)
                break

    if inside_hits and (len(xy_candidates) - len(inside_hits) <= 1):
        return [host_id for host_id in xy_candidates if host_id in inside_hits]

    # Fallback for thin ply stacks: keep full XY-aligned host set.
    return xy_candidates


def make_global_depth_cylinder(world_point, diameter, global_top_z, depth, top_proud=0.01):
    center_pt = rs.coerce3dpoint(world_point)
    if not center_pt:
        return None

    radius = diameter / 2.0
    start_z = global_top_z + max(top_proud, 0.0)
    end_z = global_top_z - depth

    plane = rs.WorldXYPlane()
    plane.Origin = Rhino.Geometry.Point3d(center_pt.X, center_pt.Y, start_z)
    circle = rs.AddCircle(plane, radius)
    if not circle:
        return None

    start_pt = Rhino.Geometry.Point3d(center_pt.X, center_pt.Y, start_z)
    end_pt = Rhino.Geometry.Point3d(center_pt.X, center_pt.Y, end_z)
    cutter = rs.ExtrudeCurveStraight(
        circle,
        start_pt,
        end_pt,
    )
    rs.DeleteObject(circle)

    if cutter:
        rs.CapPlanarHoles(cutter)
    return cutter


def boolean_difference_many(host_ids, cutter_id):
    if not cutter_id:
        return host_ids, 0, len(host_ids)

    cutter_id = replace_extrusion_with_brep_if_needed(cutter_id)

    cutter_brep = coerce_brep(cutter_id)
    if not cutter_brep:
        if rs.IsObject(cutter_id):
            rs.DeleteObject(cutter_id)
        return host_ids, 0, len(host_ids)

    model_tol = 0.01
    try:
        if sc.doc and sc.doc.ModelAbsoluteTolerance > 0:
            model_tol = sc.doc.ModelAbsoluteTolerance
    except Exception:
        pass

    def apply_layer_groups_to_results(new_ids, host_layer, host_groups):
        for obj_id in new_ids:
            try:
                if host_layer:
                    rs.ObjectLayer(obj_id, host_layer)
                for group_name in host_groups:
                    rs.AddObjectToGroup(obj_id, group_name)
            except Exception:
                pass
        try:
            sc.doc.Views.Redraw()
        except Exception:
            pass

    def try_rs_boolean_difference(host_id, cutter_doc_id, host_layer, host_groups):
        """Fallback: same engine path as manual BooleanDifference in the UI.

        Run it on a host copy first. Only delete/replace the real host after
        Rhino has returned valid result objects, so failed booleans cannot make
        the user's base solid disappear.
        """
        if not rs.IsObject(host_id):
            return None, False
        host_copy = rs.CopyObject(host_id)
        if not host_copy:
            return None, False
        cutter_copy = rs.CopyObject(cutter_doc_id)
        if not cutter_copy:
            if rs.IsObject(host_copy):
                rs.DeleteObject(host_copy)
            return None, False
        try:
            rd = rs.BooleanDifference(host_copy, cutter_copy, delete_input=True)
        except Exception:
            rd = None
        if not rd:
            if rs.IsObject(host_copy):
                rs.DeleteObject(host_copy)
            if rs.IsObject(cutter_copy):
                rs.DeleteObject(cutter_copy)
            return None, False
        new_ids = rd if isinstance(rd, list) else [rd]
        new_ids = [n for n in new_ids if n and rs.IsObject(n)]
        if not new_ids:
            if rs.IsObject(host_copy):
                rs.DeleteObject(host_copy)
            return None, False
        if rs.IsObject(host_id):
            rs.DeleteObject(host_id)
        apply_layer_groups_to_results(new_ids, host_layer, host_groups)
        return new_ids, True

    updated_hosts = []
    touched = 0
    failed = 0

    for host_id in host_ids:
        try:
            if not rs.IsObject(host_id):
                continue

            host_layer = rs.ObjectLayer(host_id)
            host_groups = object_groups(host_id)
            host_brep = coerce_brep(host_id)
            if not host_brep:
                updated_hosts.append(host_id)
                failed += 1
                continue

            try:
                host_copy = host_brep.DuplicateBrep()
                cutter_copy = cutter_brep.DuplicateBrep()
            except Exception:
                updated_hosts.append(host_id)
                failed += 1
                continue

            result = None
            try:
                result = Rhino.Geometry.Brep.CreateBooleanDifference(
                    host_copy, cutter_copy, model_tol
                )
            except Exception:
                result = None

            new_ids = []
            if result:
                for brep in result:
                    try:
                        new_id = sc.doc.Objects.AddBrep(brep)
                    except Exception:
                        new_id = None
                    if new_id and rs.IsObject(new_id):
                        new_ids.append(new_id)

            if new_ids:
                if rs.IsObject(host_id):
                    rs.DeleteObject(host_id)
                apply_layer_groups_to_results(new_ids, host_layer, host_groups)
                updated_hosts.extend(new_ids)
                touched += 1
                continue

            rs_ids, ok = try_rs_boolean_difference(
                host_id, cutter_id, host_layer, host_groups
            )
            if ok and rs_ids:
                updated_hosts.extend(rs_ids)
                touched += 1
            else:
                updated_hosts.append(host_id)
                failed += 1

        except Exception:
            updated_hosts.append(host_id)
            failed += 1
            continue

    if rs.IsObject(cutter_id):
        rs.DeleteObject(cutter_id)

    return updated_hosts, touched, failed
