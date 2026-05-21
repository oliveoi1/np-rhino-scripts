"""
Zero SKU Insertion Z: move selected block instances vertically so the nested
SKUInsertionPt (or block insertion point) lands at world Z=0. X/Y unchanged.
"""

from __future__ import print_function

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

SKU_INSERTION_BLOCK = "SKUInsertionPt"


def model_tolerance():
    tol = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.01
    if tol <= 0:
        tol = 0.01
    return tol


def to_point3d(pt):
    if pt is None:
        return None
    if isinstance(pt, Rhino.Geometry.Point3d):
        return Rhino.Geometry.Point3d(pt)
    return Rhino.Geometry.Point3d(pt[0], pt[1], pt[2])


def get_instance_xform(obj_id):
    rhobj = rs.coercerhinoobject(obj_id, True, True)
    if not rhobj:
        return None
    try:
        return rhobj.InstanceXform
    except Exception:
        return None


def nested_block_name(robj):
    if robj is None:
        return None
    try:
        idef = robj.InstanceDefinition
        if idef is not None:
            return idef.Name
    except Exception:
        pass
    try:
        geo = robj.Geometry
        if geo is not None and hasattr(geo, "InstanceDefinition"):
            idef = geo.InstanceDefinition
            if idef is not None:
                return idef.Name
    except Exception:
        pass
    return None


def nested_instance_xform(robj):
    if robj is None:
        return None
    try:
        xf = robj.InstanceXform
        if xf is not None:
            return xf
    except Exception:
        pass
    return None


def iter_definition_objects(idef):
    if idef is None:
        return
    try:
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
            if robj is not None:
                yield robj
    except Exception:
        return


def sku_point_from_definition(rh):
    parent_xform = rh.InstanceXform
    idef = rh.InstanceDefinition
    if parent_xform is None or idef is None:
        return None, False

    found_multiple = False
    best_pt = None
    for robj in iter_definition_objects(idef):
        name = nested_block_name(robj)
        if name != SKU_INSERTION_BLOCK:
            continue
        nested_xform = nested_instance_xform(robj)
        if nested_xform is None:
            continue
        pt = Rhino.Geometry.Point3d.Origin
        pt.Transform(nested_xform)
        pt.Transform(parent_xform)
        if best_pt is not None:
            found_multiple = True
        else:
            best_pt = pt
    return best_pt, found_multiple


def sku_point_world(inst_id):
    """
    World reference point: nested SKUInsertionPt if present, else insertion point.
    Returns (point3d, used_fallback, multiple_helpers).
    """
    rh = rs.coercerhinoobject(inst_id, True, True)
    if rh is None:
        insert_pt = rs.BlockInstanceInsertPoint(inst_id)
        if insert_pt:
            return to_point3d(insert_pt), True, False
        return None, True, False

    pt, multiple = sku_point_from_definition(rh)
    if pt is not None:
        return pt, False, multiple

    insert_pt = rs.BlockInstanceInsertPoint(inst_id)
    if insert_pt:
        return to_point3d(insert_pt), True, False
    return None, True, False


def z_only_move_to_world_zero(inst_id):
    ref, used_fallback, multiple = sku_point_world(inst_id)
    if ref is None:
        return False, "no_reference", used_fallback, multiple

    dz = -ref.Z
    tol = model_tolerance()
    if abs(dz) <= tol:
        return False, "already_at_z0", used_fallback, multiple

    moved = rs.MoveObject(inst_id, (0.0, 0.0, dz))
    if not moved:
        return False, "move_failed", used_fallback, multiple
    return True, "moved", used_fallback, multiple


def main():
    objs = rs.GetObjects(
        "Select block instances to set SKU insertion to Z=0",
        rs.filter.instance,
        preselect=True,
    )
    if not objs:
        return

    moved = 0
    skipped = 0
    fallback_count = 0
    already_z0 = 0
    locked = 0
    failed = 0
    warned_multiple = False

    rs.EnableRedraw(False)
    try:
        for obj_id in objs:
            if not rs.IsObject(obj_id):
                skipped += 1
                continue
            if not rs.IsBlockInstance(obj_id):
                skipped += 1
                continue
            if rs.IsObjectLocked(obj_id):
                locked += 1
                continue

            try:
                ok, status, used_fallback, multiple = z_only_move_to_world_zero(obj_id)
                if multiple and not warned_multiple:
                    try:
                        Rhino.RhinoApp.WriteLine(
                            "Warning: multiple {} in a block; using first.".format(
                                SKU_INSERTION_BLOCK
                            )
                        )
                    except Exception:
                        pass
                    warned_multiple = True

                if ok:
                    moved += 1
                    if used_fallback:
                        fallback_count += 1
                elif status == "already_at_z0":
                    already_z0 += 1
                    if used_fallback:
                        fallback_count += 1
                elif status == "no_reference":
                    failed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    finally:
        rs.EnableRedraw(True)
        try:
            sc.doc.Views.Redraw()
        except Exception:
            pass

    lines = [
        "Moved to world Z=0: {}".format(moved),
        "Already at Z=0: {}".format(already_z0),
    ]
    if fallback_count:
        lines.append("Used insertion point (no {}): {}".format(
            SKU_INSERTION_BLOCK, fallback_count
        ))
    if locked:
        lines.append("Skipped locked: {}".format(locked))
    if skipped:
        lines.append("Skipped non-blocks: {}".format(skipped))
    if failed:
        lines.append("Failed: {}".format(failed))

    rs.MessageBox("\n".join(lines), 0, "Zero SKU Insertion Z")


if __name__ == "__main__":
    main()
