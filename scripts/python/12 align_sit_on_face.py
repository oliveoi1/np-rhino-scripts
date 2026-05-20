"""
Align Sit On Face: translate selection so a source reference lands on a picked
point on a recess floor face. Translation only (no rotation).

Flow:
  1. Select objects
  2. Enter = auto bottom-center of bbox, or pick source point (trusted exactly)
  3. Select host part, click a point on the recess floor (finds the face)
  4. Click target placement on that face, or Enter = face centroid (projected to plane)
  5. move_vector = target_on_plane - source_reference
"""

from __future__ import print_function

import os
import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
for _p in (os.path.join(_INSTALL_ROOT, "shared"), _SCRIPT_DIR):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import importlib
except ImportError:
    importlib = None

import group_cut_utils as gcu

try:
    if importlib and hasattr(importlib, "reload"):
        gcu = importlib.reload(gcu)
    else:
        gcu = reload(gcu)  # noqa: F821 - IronPython 2.7
except Exception:
    pass


def to_point3d(pt):
    if pt is None:
        return None
    if isinstance(pt, Rhino.Geometry.Point3d):
        return Rhino.Geometry.Point3d(pt)
    return Rhino.Geometry.Point3d(pt[0], pt[1], pt[2])


def object_world_bbox(obj_id):
    rh = rs.coercerhinoobject(obj_id, True, True)
    if rh is None:
        return None
    try:
        geom = rh.Geometry
        if rs.IsBlockInstance(obj_id):
            return geom.GetBoundingBox(rh.InstanceXform)
        return geom.GetBoundingBox(True)
    except Exception:
        return None


def union_world_bbox(obj_ids):
    union = Rhino.Geometry.BoundingBox.Empty
    found = False
    for obj_id in obj_ids:
        bb = object_world_bbox(obj_id)
        if bb is None:
            continue
        if not found:
            union = bb
            found = True
        else:
            union.Union(bb)
    if not found:
        corners = rs.BoundingBox(obj_ids)
        if not corners:
            return None
        pts = [to_point3d(c) for c in corners]
        union = Rhino.Geometry.BoundingBox(pts)
    return union


def bbox_bottom_center(obj_ids):
    bb = union_world_bbox(obj_ids)
    if bb is None or not bb.IsValid:
        return None
    min_z = bb.Min.Z
    tol = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.01
    if tol <= 0:
        tol = 0.01
    cx = 0.5 * (bb.Min.X + bb.Max.X)
    cy = 0.5 * (bb.Min.Y + bb.Max.Y)
    return Rhino.Geometry.Point3d(cx, cy, min_z)


def pick_source_reference(obj_ids):
    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt(
        "Pick exact source point to land on target, or press Enter for auto bottom center"
    )
    gp.EnableTransparentCommands(False)
    gp.Get()
    result = gp.CommandResult()

    if result == Rhino.Commands.Result.Cancel:
        return None

    if result == Rhino.Commands.Result.Nothing:
        center = bbox_bottom_center(obj_ids)
        if center is None:
            rs.MessageBox("Could not compute bottom-center from selection.")
        return center

    picked = get_getpoint_point(gp)
    if picked:
        return to_point3d(picked)

    return bbox_bottom_center(obj_ids)


def write_prompt(msg):
    try:
        Rhino.RhinoApp.WriteLine(msg)
    except Exception:
        pass


def brep_from_obj_ref(obj_ref):
    if obj_ref is None:
        return None
    try:
        face = obj_ref.Face()
        if face is not None:
            return face.Brep
    except Exception:
        pass
    try:
        geom = obj_ref.Geometry()
        if geom is None:
            return None
        brep = Rhino.Geometry.Brep.TryConvertBrep(geom)
        if brep:
            return brep
    except Exception:
        pass
    return None


def closest_face_on_brep(brep, test_pt):
    test_pt = to_point3d(test_pt)
    best_face = None
    best_dist = None
    for i in range(brep.Faces.Count):
        face = brep.Faces[i]
        try:
            rc, u, v = face.ClosestPoint(test_pt)
            if not rc:
                continue
            pt_on = face.PointAt(u, v)
            dist = test_pt.DistanceTo(pt_on)
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_face = face
        except Exception:
            continue
    return best_face


def pick_host_brep():
    """Use rs.filter.polysurface (includes Extrusion + Brep), same as other NP scripts."""
    obj_id = rs.GetObject(
        "Select host part with recess (closed solid / polysurface)",
        rs.filter.polysurface,
        preselect=False,
    )
    if not obj_id:
        return None

    brep = gcu.coerce_brep(obj_id)
    if brep is None:
        write_prompt(
            "Could not read solid from selection. Pick the gray plate (closed solid), not a block instance."
        )
    return brep


def pick_face_from_point_on_brep(brep):
    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt("Click a point on the recess floor inside the pocket")
    try:
        gp.Constrain(brep, False)
    except Exception:
        pass
    gp.Get()

    if gp.CommandResult() != Rhino.Commands.Result.Success:
        return None

    pt = get_getpoint_point(gp)
    if not pt:
        return None

    face = closest_face_on_brep(brep, pt)
    if face is None:
        write_prompt("Could not find a face at that point. Click directly on the pocket floor.")
    return face


def pick_target_face():
    """Host part + click on recess floor (no sub-object face pick required)."""
    brep = pick_host_brep()
    if brep is None:
        return None

    face = pick_face_from_point_on_brep(brep)
    if face is None:
        write_prompt("Align Sit On Face cancelled or face not found.")
    return face


def face_plane(face):
    u0, u1 = face.Domain(0)
    v0, v1 = face.Domain(1)
    um = 0.5 * (u0 + u1)
    vm = 0.5 * (v0 + v1)
    ok, frame = face.FrameAt(um, vm)
    if ok:
        return Rhino.Geometry.Plane(frame)
    pt = face.PointAt(um, vm)
    normal = face.NormalAt(um, vm)
    return Rhino.Geometry.Plane(pt, normal)


def face_centroid_point(face):
    amp = Rhino.Geometry.AreaMassProperties.Compute(face)
    if amp:
        return amp.Centroid
    plane = face_plane(face)
    return plane.Origin


def project_to_plane(point, plane):
    return plane.ClosestPoint(to_point3d(point))


def get_getpoint_point(gp):
    pt = gp.Point
    try:
        if callable(pt):
            return pt()
    except Exception:
        pass
    return pt


def pick_target_point_on_face(face, plane):
    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt(
        "Click target placement point on face (Enter for face centroid)"
    )
    try:
        gp.Constrain(face, False)
    except Exception:
        pass
    gp.Get()
    result = gp.CommandResult()

    if result == Rhino.Commands.Result.Cancel:
        return None

    raw = None
    if result == Rhino.Commands.Result.Nothing:
        raw = face_centroid_point(face)
    elif get_getpoint_point(gp):
        raw = to_point3d(get_getpoint_point(gp))
    else:
        raw = face_centroid_point(face)

    if raw is None:
        return None
    return project_to_plane(raw, plane)


def selection_object_filter():
    """Filter for GetObjects; IronPython lacks rs.filter.anyobject."""
    try:
        if hasattr(rs.filter, "allobjects"):
            return rs.filter.allobjects
    except Exception:
        pass
    try:
        if hasattr(rs.filter, "object"):
            return rs.filter.object
    except Exception:
        pass
    return 0


def move_selection(obj_ids, move_vec):
    for obj_id in obj_ids:
        if rs.IsObjectLocked(obj_id):
            rs.MessageBox("Selection contains a locked object. Unlock and retry.")
            return False, 0, []

    translation = Rhino.Geometry.Transform.Translation(move_vec)

    try:
        result = rs.TransformObjects(obj_ids, translation, copy=False)
        if result:
            return True, len(result), ["transform"]
    except Exception:
        pass

    try:
        delta = (move_vec.X, move_vec.Y, move_vec.Z)
        result = rs.MoveObjects(obj_ids, delta)
        if result:
            return True, len(result), ["move"]
    except Exception:
        pass

    return False, 0, ["failed"]


def main():
    rs.EnableRedraw(False)
    try:
        obj_ids = rs.GetObjects(
            "Select objects to move (block instances, groups, solids)",
            selection_object_filter(),
            preselect=True,
            group=True,
        )
        if not obj_ids:
            return

        obj_ids = [obj_id for obj_id in obj_ids if rs.IsObject(obj_id)]
        if not obj_ids:
            return

        source_ref = pick_source_reference(obj_ids)
        if source_ref is None:
            return

        face = pick_target_face()
        if face is None:
            return

        plane = face_plane(face)
        target_on_plane = pick_target_point_on_face(face, plane)
        if target_on_plane is None:
            return

        move_vec = target_on_plane - source_ref
        if move_vec.Length < 1e-12:
            rs.MessageBox("Source already at target (no move needed).")
            return

        ok, moved_count, methods = move_selection(obj_ids, move_vec)
        if not ok:
            rs.MessageBox(
                "Move failed. Check selection is not locked and try again.",
                0,
                "Align Sit On Face",
            )
            return

        rs.MessageBox(
            "Moved {} object(s).\nMove: {:.4f}, {:.4f}, {:.4f}\nMethods: {}".format(
                moved_count,
                move_vec.X,
                move_vec.Y,
                move_vec.Z,
                ", ".join(methods) if methods else "ok",
            ),
            0,
            "Align Sit On Face",
        )
    finally:
        rs.EnableRedraw(True)
        try:
            sc.doc.Views.Redraw()
        except Exception:
            pass


if __name__ == "__main__":
    main()
