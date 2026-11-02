import os

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

LIBRARY_FILENAME = "NP_Rhino_Hardware.3dm"

# Menu label, block definition name, layer for the inserted instance.
# The block's own insertion point (the end of the line in the library) is
# what lands on the point you pick.
CATALOG = [
    ("SKU Insertion Point", "SKUInsertionPt", "NP-SKU_Insertion"),
    ("Block Insertion Point", "BlkInsertionPt", "NP-Setout"),
    ("Hole insert", "hole_insert", "NP-Construction - Setout"),
    ("Hole grub", "hole_grub", "NP-Construction - Setout"),
    ("Cam insert", "caminsert", "NP-Construction - Setout"),
    ("Cam hole", "Cam_Hole", "NP-Construction - Setout"),
    ("Flipper insert", "flipper_insert", "NP-Construction - Setout"),
    ("Glide insert", "glide_insert", "NP-Construction - Setout"),
    ("Castor insert", "castor_insert", "NP-Construction - Setout"),
    ("Logo insert", "logo_insert", "NP-Construction - Setout"),
    ("Pilot hole", "Pilot Hole", "NP-Construction - Setout"),
    ("Grub screw", "grub_screw", "NP-Fittings"),
    ("Screw 1-1/4in pan head (two flat plies)", "screw_1-1-4in_pan", "NP-Fittings"),
    ("Screw 1-1/4in countersunk (two flat plies)", "screw_1-1-4in_csk", "NP-Fittings"),
    ("Screw 1-1/2in pan head (into an edge)", "screw_1-1-2in_pan", "NP-Fittings"),
    ("Screw 1-1/2in countersunk (into an edge)", "screw_1-1-2in_csk", "NP-Fittings"),
    ("Cam", "cam", "NP-Fittings"),
    ("Glide", "glide", "NP-Fittings"),
    ("Flipper pin", "flipper_pin", "NP-Fittings"),
    ("Flipper receptacle", "flipper_receptacle", "NP-Fittings"),
    ("Castor small", "ACC-CST-SM", "NP-Fittings"),
    ("Castor large", "ACC-CST-LG", "NP-Fittings"),
    ("Logo", "Logo", "NP-Panel-Logo"),
    ("Logo outline", "Logo_outline", "NP-Panel-Logo"),
]


# --- choice handed over by the NP Menu window --------------------------------
# The window writes _user_data/np_menu_choice.json just before launching this
# script; when the entry is recent and meant for this script, its list dialog
# is skipped. A file is used (not sc.sticky) so it works across interpreters.

def take_menu_choice(valid_choices):
    import json
    import time
    path = os.path.join(_INSTALL_ROOT, "_user_data", "np_menu_choice.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as handle:
            data = json.load(handle)
    except Exception:
        data = None
    try:
        os.remove(path)
    except Exception:
        pass
    if not isinstance(data, dict):
        return None
    if data.get("script") != os.path.basename(__file__):
        return None
    if time.time() - float(data.get("time", 0)) > 120:
        return None
    choice = data.get("choice")
    return choice if choice in valid_choices else None


# Blocks inserted perpendicular to the face under the picked point. Their
# insertion point sits on the face and the shank runs down local -Z, so local
# +Z is aligned with the outward face normal. Other blocks stay world-aligned.
ORIENT_TO_FACE = {
    "screw_1-1-4in_pan",
    "screw_1-1-4in_csk",
    "screw_1-1-2in_pan",
    "screw_1-1-2in_csk",
}
FACE_SEARCH_RADIUS = 0.5  # model units: how far from the pick to look for a face or hole wall


def library_path():
    here = os.path.dirname(__file__) if "__file__" in globals() else ""
    return os.path.abspath(os.path.join(here, "..", "..", "blocks", LIBRARY_FILENAME))


def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)


def definition_exists(name):
    idef = sc.doc.InstanceDefinitions.Find(name)
    return idef is not None and not idef.IsDeleted


def find_library_definition(model, name):
    for candidate in model.AllInstanceDefinitions:
        if candidate.Name == name:
            return candidate
    return None


def objects_for_definition(model, idef):
    wanted = set(idef.GetObjectIds())
    geometry = []
    attributes = []
    for obj in model.Objects:
        if obj.Attributes.ObjectId not in wanted:
            continue
        if obj.Geometry is None:
            continue
        geometry.append(obj.Geometry)
        attributes.append(obj.Attributes.Duplicate())
    return geometry, attributes


def nested_definition_names(model, idef):
    names = []
    geometry, _attributes = objects_for_definition(model, idef)
    for geom in geometry:
        if geom.ObjectType != Rhino.DocObjects.ObjectType.InstanceReference:
            continue
        for candidate in model.AllInstanceDefinitions:
            if candidate.Id == geom.ParentIdefId and candidate.Name not in names:
                names.append(candidate.Name)
    return names


def import_definition(model, name, imported):
    if name in imported or definition_exists(name):
        imported.add(name)
        return True

    source = find_library_definition(model, name)
    if source is None:
        return False

    for child_name in nested_definition_names(model, source):
        if not import_definition(model, child_name, imported):
            return False

    geometry, attributes = objects_for_definition(model, source)
    if not geometry:
        return False

    index = sc.doc.InstanceDefinitions.Add(
        source.Name,
        source.Description or "",
        # File3dm definitions do not expose a base point; library blocks are
        # authored with their insertion point at the origin.
        Rhino.Geometry.Point3d.Origin,
        geometry,
        attributes,
    )
    if index < 0:
        return False
    imported.add(name)
    return True


def ensure_definition(name):
    if definition_exists(name):
        return True

    path = library_path()
    if not os.path.isfile(path):
        rs.MessageBox("Hardware library not found:\n{}".format(path), 0, "Insert Block")
        return False

    model = Rhino.FileIO.File3dm.Read(path)
    if model is None:
        rs.MessageBox("Could not read the hardware library.", 0, "Insert Block")
        return False

    if not import_definition(model, name, set()):
        rs.MessageBox("Block '{}' is not in the hardware library.".format(name), 0, "Insert Block")
        return False
    return True


def _hit_candidates(geometry, point, xform, max_dist, found):
    """Collect (distance, brep, component, local_point, xform) for faces near point."""
    if isinstance(geometry, Rhino.Geometry.InstanceReferenceGeometry):
        idef = sc.doc.InstanceDefinitions.FindId(geometry.ParentIdefId)
        if idef is None:
            return
        child_xform = xform * geometry.Xform
        for child in idef.GetObjects():
            _hit_candidates(child.Geometry, point, child_xform, max_dist, found)
        return

    brep = None
    if isinstance(geometry, Rhino.Geometry.Brep):
        brep = geometry
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        brep = geometry.ToBrep()
    if brep is None:
        return

    inverse = Rhino.Geometry.Transform.Identity
    if not xform.IsIdentity:
        ok, inverse = xform.TryGetInverse()
        if not ok:
            return
    local_point = Rhino.Geometry.Point3d(point)
    local_point.Transform(inverse)
    box = brep.GetBoundingBox(False)
    box.Inflate(max_dist)
    if not box.Contains(local_point):
        return
    result = brep.ClosestPoint(local_point, max_dist)
    if not result or not result[0]:
        return
    closest, component = result[1], result[2]
    found.append((closest.DistanceTo(local_point), brep, component, local_point, xform))


def _hole_axis_outward(face, local_point, tol):
    """If face is the wall of a hole around local_point, return the unit axis pointing out of the hole."""
    ok, cylinder = face.TryGetCylinder(tol)
    if not ok:
        return None
    axis = cylinder.Axis
    axis.Unitize()
    centre = cylinder.Center
    offset = local_point - centre
    along = offset * axis
    radial = (offset - axis * along).Length
    if radial > cylinder.Radius * 0.9:
        return None  # pick is on the cylinder surface, not over its mouth
    curve = face.OuterLoop.To3dCurve()
    params = curve.DivideByCount(48, True)
    if not params:
        return None
    ts = [(curve.PointAt(t) - centre) * axis for t in params]
    mid = (min(ts) + max(ts)) / 2.0
    return axis if along >= mid else -axis


def _normal_from_hit(hit, world_point, tol):
    """Outward unit normal (world) for a hit, or None."""
    distance, brep, component, local_point, xform = hit
    ctype = component.ComponentIndexType
    faces = []
    if ctype == Rhino.Geometry.ComponentIndexType.BrepFace:
        faces = [brep.Faces[component.Index]]
    elif ctype == Rhino.Geometry.ComponentIndexType.BrepEdge:
        faces = [brep.Faces[i] for i in brep.Edges[component.Index].AdjacentFaces()]
    elif ctype == Rhino.Geometry.ComponentIndexType.BrepVertex:
        edges = brep.Vertices[component.Index].EdgeIndices()
        seen = set()
        for edge_index in edges:
            for face_index in brep.Edges[edge_index].AdjacentFaces():
                if face_index not in seen:
                    seen.add(face_index)
                    faces.append(brep.Faces[face_index])
    if not faces:
        return None

    normal = None
    # a direct hit on a flat face wins; an edge or vertex snap on a hole rim
    # also has a flat face adjacent to it
    for face in faces:
        if face.IsPlanar(tol):
            ok, u, v = face.ClosestPoint(local_point)
            if ok:
                normal = face.NormalAt(u, v)  # already adjusted for face orientation
                break
    if normal is None:
        # over a hole: use the hole axis, pointing out of the material
        for face in faces:
            normal = _hole_axis_outward(face, local_point, tol)
            if normal is not None:
                break
    if normal is None:
        face = faces[0]
        ok, u, v = face.ClosestPoint(local_point)
        if not ok:
            return None
        normal = face.NormalAt(u, v)

    normal = Rhino.Geometry.Vector3d(normal)
    normal.Transform(xform)
    normal.Unitize()
    if not brep.IsSolid:
        # an open surface has no inside: face the normal toward the viewer
        camera = sc.doc.Views.ActiveView.ActiveViewport.CameraLocation
        if (camera - world_point) * normal < 0:
            normal = -normal
    return normal


def face_normal_at_point(point, max_dist=FACE_SEARCH_RADIUS):
    """Outward unit normal of the face under a picked point, or None.

    Handles a pick on a flat face, on the rim of a hole, or at the centre of a
    hole (where the nearest geometry is the hole wall, whose axis is used)."""
    point = Rhino.Geometry.Point3d(point[0], point[1], point[2])
    tol = sc.doc.ModelAbsoluteTolerance
    found = []
    for obj in sc.doc.Objects:
        if not obj.Visible:
            continue
        box = obj.Geometry.GetBoundingBox(True)
        box.Inflate(max_dist)
        if not box.Contains(point):
            continue
        _hit_candidates(obj.Geometry, point, Rhino.Geometry.Transform.Identity, max_dist, found)
    found.sort(key=lambda item: item[0])
    for hit in found:
        normal = _normal_from_hit(hit, point, tol)
        if normal is not None:
            return normal
    return None


def insert_transform(point, normal):
    plane = Rhino.Geometry.Plane(Rhino.Geometry.Point3d(point[0], point[1], point[2]), normal)
    return Rhino.Geometry.Transform.PlaneToPlane(Rhino.Geometry.Plane.WorldXY, plane)


def insert_block_at(block_name, point):
    """Insert the block at point; oriented to the face under it when the block asks for that."""
    if block_name in ORIENT_TO_FACE:
        normal = face_normal_at_point(point)
        if normal is not None:
            return rs.InsertBlock2(block_name, insert_transform(point, normal))
    return rs.InsertBlock(block_name, point)


def menu_items():
    """Labels offered by the list dialog and by the NP Menu drawer."""
    return [row[0] for row in CATALOG]


def main():
    labels = menu_items()
    choice = take_menu_choice(labels)
    if not choice:
        choice = rs.ListBox(labels, "Choose what to insert", "Insert Block")
    if not choice:
        return

    selected = None
    for row in CATALOG:
        if row[0] == choice:
            selected = row
            break
    if not selected:
        return

    _label, block_name, layer_name = selected
    if not ensure_definition(block_name):
        return

    ensure_layer(layer_name)
    placed = 0

    while True:
        point = rs.GetPoint("Pick insertion point for {}. Enter when done.".format(choice))
        if not point:
            break
        instance_id = insert_block_at(block_name, point)
        if not instance_id:
            rs.MessageBox("Could not insert '{}'.".format(block_name), 0, "Insert Block")
            break
        rs.ObjectLayer(instance_id, layer_name)
        placed += 1

    sc.doc.Views.Redraw()
    if placed:
        rs.MessageBox(
            "Inserted {} '{}' on {}.".format(placed, block_name, layer_name),
            0,
            "Insert Block",
        )


if __name__ == "__main__":
    main()
