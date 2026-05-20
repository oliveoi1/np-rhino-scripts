"""
Align Sit On Face: translate selection so a source reference lands on a picked
point on a recess floor face. Translation only (no rotation).

Flow:
  1. Select objects
  2. Enter = auto bottom-center of bbox, or pick source point (trusted exactly)
  3. Select target face
  4. Click target point on face, or Enter = face centroid (projected to plane)
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


def to_point3d(pt):
    if pt is None:
        return None
    if isinstance(pt, Rhino.Geometry.Point3d):
        return Rhino.Geometry.Point3d(pt)
    return Rhino.Geometry.Point3d(pt[0], pt[1], pt[2])


def bbox_bottom_center(obj_ids):
    corners = rs.BoundingBox(obj_ids)
    if not corners:
        return None
    pts = [to_point3d(c) for c in corners]
    min_z = min(p.Z for p in pts)
    tol = sc.doc.ModelAbsoluteTolerance if sc.doc else 0.01
    if tol <= 0:
        tol = 0.01
    bottom = [p for p in pts if abs(p.Z - min_z) <= tol * 10.0]
    if not bottom:
        bottom = pts
    cx = sum(p.X for p in bottom) / float(len(bottom))
    cy = sum(p.Y for p in bottom) / float(len(bottom))
    return Rhino.Geometry.Point3d(cx, cy, min_z)


def pick_source_reference(obj_ids):
    gp = Rhino.Input.Custom.GetPoint()
    gp.SetCommandPrompt(
        "Pick source reference point (Enter for auto bottom-center of selection)"
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


def pick_target_face():
    go = Rhino.Input.Custom.GetObject()
    go.SetCommandPrompt("Select recess floor face")
    go.GeometryFilter = (
        Rhino.DocObjects.ObjectType.Surface | Rhino.DocObjects.ObjectType.Polysurface
    )
    go.SubObjectSelect = True
    go.EnablePreSelect(False, True)
    go.DeselectAllBeforePostSelect = False
    go.Get()

    if go.CommandResult() != Rhino.Commands.Result.Success:
        return None, None

    obj_ref = go.Object(0)
    face = obj_ref.Face()
    if face is None:
        rs.MessageBox("Please select a face (sub-object selection).")
        return None, None

    return face, obj_ref


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


def move_selection(obj_ids, move_vec):
    xform = Rhino.Geometry.Transform.Translation(move_vec)
    moved = 0
    for obj_id in obj_ids:
        if not rs.IsObject(obj_id):
            continue
        if rs.IsObjectLocked(obj_id):
            rs.MessageBox("Selection contains a locked object. Unlock and retry.")
            return False
        rs.TransformObject(obj_id, xform, copy=False)
        moved += 1
    return moved > 0


def main():
    rs.EnableRedraw(False)
    try:
        obj_ids = rs.GetObjects(
            "Select objects to move (blocks, groups, solids)",
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

        face, _obj_ref = pick_target_face()
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

        if not move_selection(obj_ids, move_vec):
            return

        rs.MessageBox(
            "Moved {} object(s).\nMove: {:.4f}, {:.4f}, {:.4f}".format(
                len(obj_ids), move_vec.X, move_vec.Y, move_vec.Z
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
