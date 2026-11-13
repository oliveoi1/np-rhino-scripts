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
# Blocks listed in HOLE_FITTINGS below are placed in a hole you click instead.
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
    ("Table leg bolt and nut (pick a hole)", "table_leg_bolt", "NP-Fittings"),
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

# Fittings placed in a hole you click, instead of at a point: the bolt goes in
# on the hole's axis with its head on the side you clicked, and its nut (when
# asked for) goes on the far end of the hole. Bolt block -> nut block.
#   table_leg_bolt  #10-32 x 1-3/4in square drive round head machine screw (Fastenal 29895)
#   table_leg_nut   #10-32 nylon insert lock nut, 3/8in hex x 0.249in (Fastenal 37015)
# Both follow the fitting convention: insertion point on the face the fitting
# sits on, local +Z out of that face (the bolt's shank and the nut's far side
# of the stack are down -Z), so Explode Fittings pulls them apart correctly.
HOLE_FITTINGS = {"table_leg_bolt": "table_leg_nut"}
FITTINGS_LAYER = "NP-Fittings"
BOLT_DIAMETER = 0.190       # #10 thread
BOLT_STACK = 1.5            # two 3/4in plies: where the nut goes when the stack cannot be measured
HOLE_MIN_RADIUS = 0.03      # model units: round faces outside this range are not bolt holes
HOLE_MAX_RADIUS = 0.3
HOLE_SEARCH_RADIUS = 0.5    # how far from the click to look for a hole
HOLE_JOIN_GAP = 0.03        # plies of one stack may sit this far apart, or their holes this far out of line
HOLE_PROBE = 0.02           # step past a hole end when testing whether it is open

DEFAULTS_FILENAME = "insert_block_defaults.json"
STICKY_KEY = "np_insert_block"
FALLBACK = {"nut": True}


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


def document_layer_index(model, library_index):
    """Index in this document of the layer a library object sits on (made when
    missing), or -1. Layer indexes differ from file to file, so the layer is
    matched by name."""
    for layer in model.AllLayers:
        if layer.Index != library_index:
            continue
        index = sc.doc.Layers.FindByFullPath(layer.FullPath, -1)
        if index < 0:
            rs.AddLayer(layer.FullPath, layer.Color)
            index = sc.doc.Layers.FindByFullPath(layer.FullPath, -1)
        return index
    return -1


def objects_for_definition(model, idef):
    wanted = set(idef.GetObjectIds())
    geometry = []
    attributes = []
    for obj in model.Objects:
        if obj.Attributes.ObjectId not in wanted:
            continue
        if obj.Geometry is None:
            continue
        copied = obj.Attributes.Duplicate()
        layer_index = document_layer_index(model, copied.LayerIndex)
        if layer_index >= 0:
            copied.LayerIndex = layer_index
        geometry.append(obj.Geometry)
        attributes.append(copied)
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


# --- fittings placed in a clicked hole ----------------------------------------

def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    import json
    data = dict(FALLBACK)
    saved = sc.sticky.get(STICKY_KEY)
    if not saved and os.path.isfile(defaults_path()):
        try:
            with open(defaults_path(), "r") as handle:
                saved = json.load(handle)
        except Exception:
            saved = None
    if isinstance(saved, dict):
        data["nut"] = bool(saved.get("nut", data["nut"]))
    return data


def save_defaults(data):
    import json
    sc.sticky[STICKY_KEY] = dict(data)
    folder = os.path.join(_INSTALL_ROOT, "_user_data")
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump(data, handle)
    except Exception:
        pass


def _moved(point, xform):
    moved = Rhino.Geometry.Point3d(point)
    moved.Transform(xform)
    return moved


def _is_part(attributes):
    """True for a shown object that is not itself a fitting (a bolt's own bore is not a hole)."""
    layer = sc.doc.Layers[attributes.LayerIndex]
    return attributes.Visible and layer.IsVisible and layer.FullPath != FITTINGS_LAYER


def _collect_parts(geometry, attributes, xform, line, point, out):
    """Gather (brep, world transform, inverse) for part surfaces near the line
    (or, without one, the point), looking inside block instances."""
    if not _is_part(attributes):
        return
    if isinstance(geometry, Rhino.Geometry.InstanceReferenceGeometry):
        idef = sc.doc.InstanceDefinitions.FindId(geometry.ParentIdefId)
        if idef is None:
            return
        child_xform = xform * geometry.Xform
        for child in idef.GetObjects():
            _collect_parts(child.Geometry, child.Attributes, child_xform, line, point, out)
        return
    if not isinstance(geometry, (Rhino.Geometry.Brep, Rhino.Geometry.Extrusion)):
        return
    ok, inverse = xform.TryGetInverse()
    if not ok:
        return
    box = geometry.GetBoundingBox(False)
    box.Inflate(HOLE_SEARCH_RADIUS + HOLE_MAX_RADIUS)
    if line is not None:
        local_line = Rhino.Geometry.Line(_moved(line.From, inverse), _moved(line.To, inverse))
        hit = Rhino.Geometry.Intersect.Intersection.LineBox(local_line, box, sc.doc.ModelAbsoluteTolerance)
        if not hit[0]:
            return
    elif not box.Contains(_moved(point, inverse)):
        return
    brep = geometry if isinstance(geometry, Rhino.Geometry.Brep) else geometry.ToBrep()
    if brep is not None:
        out.append((brep, xform, inverse))


def _holes_in(brep, tol):
    """Round holes in a brep as (start, end, radius) along each hole's axis, in
    the brep's own coordinates. A hole wall may be one face or several (two
    halves); faces are joined when they share an axis, radius and depth, and
    only walls that go the whole way round count, so fillets are left out."""
    import math
    slack = max(tol * 5.0, 0.002)
    groups = []   # [plane on the axis, radius, low, high, set of 30 degree sectors]
    for face in brep.Faces:
        ok, cylinder = face.TryGetCylinder(tol)
        if not ok or not HOLE_MIN_RADIUS <= cylinder.Radius <= HOLE_MAX_RADIUS:
            continue
        axis = cylinder.Axis
        if not axis.Unitize():
            continue
        centre = cylinder.Center
        if brep.IsSolid:
            # a hole wall faces its own axis; a dowel or a rounded corner faces away
            u, v = face.Domain(0).Mid, face.Domain(1).Mid
            at = face.PointAt(u, v)
            radial = at - (centre + axis * ((at - centre) * axis))
            if radial * face.NormalAt(u, v) >= 0:
                continue
        points = []
        for trim in face.OuterLoop.Trims:
            edge = trim.Edge
            if edge is None:
                continue
            for t in edge.DivideByCount(24, True) or []:
                points.append(edge.PointAt(t))
        if not points:
            continue
        group = None
        for candidate in groups:
            plane, radius = candidate[0], candidate[1]
            if abs(radius - cylinder.Radius) > slack or abs(plane.ZAxis * axis) < 0.9999:
                continue
            offset = centre - plane.Origin
            if (offset - plane.ZAxis * (offset * plane.ZAxis)).Length > slack:
                continue
            depths = [(p - plane.Origin) * plane.ZAxis for p in points]
            if min(depths) < candidate[3] - tol and max(depths) > candidate[2] + tol:
                group = candidate
                break
        if group is None:
            group = [Rhino.Geometry.Plane(centre, axis), cylinder.Radius, None, None, set()]
            groups.append(group)
        plane = group[0]
        for p in points:
            offset = p - plane.Origin
            depth = offset * plane.ZAxis
            group[2] = depth if group[2] is None else min(group[2], depth)
            group[3] = depth if group[3] is None else max(group[3], depth)
            angle = math.atan2(offset * plane.YAxis, offset * plane.XAxis)
            group[4].add(int((angle + math.pi) / (math.pi / 6.0)) % 12)
    holes = []
    for plane, radius, low, high, sectors in groups:
        if len(sectors) >= 11 and high - low > tol:
            holes.append((plane.Origin + plane.ZAxis * low, plane.Origin + plane.ZAxis * high, radius))
    return holes


def _holes_near(line, point):
    """World-space holes [(start, end, radius)] in the parts near the line (or
    the point), and those parts [(brep, transform, inverse)]."""
    tol = sc.doc.ModelAbsoluteTolerance
    parts = []
    for obj in sc.doc.Objects:
        if obj.Visible:
            _collect_parts(obj.Geometry, obj.Attributes, Rhino.Geometry.Transform.Identity, line, point, parts)
    holes = []
    for brep, xform, _inverse in parts:
        for start, end, radius in _holes_in(brep, tol):
            length = start.DistanceTo(end)
            world_start, world_end = _moved(start, xform), _moved(end, xform)
            holes.append((world_start, world_end, radius * world_start.DistanceTo(world_end) / length))
    return holes, parts


def _inside_a_part(point, parts):
    tol = sc.doc.ModelAbsoluteTolerance
    for brep, _xform, inverse in parts:
        if brep.IsSolid and brep.IsPointInside(_moved(point, inverse), tol, True):
            return True
    return False


def _pick_mouth(holes, parts, point, line, camera):
    """The open hole end a click means: (centre, unit axis out of the hole, radius), or None.

    With a `line` (through the click, along the view) the end must face the
    viewer: a click inside a hole takes the nearest such end, otherwise the end
    closest to the line. Without one, the end nearest `point` is taken."""
    ranked = []
    for start, end, radius in holes:
        axis = end - start
        if not axis.Unitize():
            continue
        for centre, outward in ((start, -axis), (end, axis)):
            facing = True
            if camera is not None:
                eye, direction = camera
                toward = (eye - centre) if eye is not None else -direction
                toward.Unitize()
                facing = outward * toward > 0.02
            if line is None:
                reach = centre.DistanceTo(point)
                if reach > HOLE_SEARCH_RADIUS + radius:
                    continue
                rank = (round(reach, 3), 0 if facing else 1)
            else:
                if not facing:
                    continue
                off = line.DistanceTo(centre, False)
                if off > HOLE_SEARCH_RADIUS + radius:
                    continue
                if off <= radius * 1.2:
                    rank = (0, line.ClosestParameter(centre) * line.Length)
                else:
                    rank = (1, off)
            ranked.append((rank, centre, outward, radius))
    ranked.sort(key=lambda item: item[0])
    for _rank, centre, outward, radius in ranked:
        # a blind hole's bottom, or an end closed off by another part, is not a way in
        if not _inside_a_part(centre + outward * HOLE_PROBE, parts):
            return centre, outward, radius
    return None


def find_hole(point, line=None, camera=None, snapped=False):
    """The hole under a click and the side clicked: (centre of the hole's
    mouth, unit axis out of the hole there, radius), or None.

    `line` runs through the click along the view and `camera` is (eye point or
    None, view direction). A point that was object-snapped (hole centre, rim)
    is trusted first; a free click lands on the construction plane, so there
    the view line decides and the point is only a last resort (typed
    coordinates, or a hole seen edge on)."""
    point = Rhino.Geometry.Point3d(point[0], point[1], point[2])
    if line is None:
        passes = [None]
    elif snapped:
        passes = [None, line]
    else:
        passes = [line, None]
    for by_line in passes:
        holes, parts = _holes_near(by_line, point)
        mouth = _pick_mouth(holes, parts, point, by_line, camera)
        if mouth is not None:
            return mouth
    return None


def measure_stack(centre, outward):
    """How far the hole runs from the mouth at `centre` before it comes out
    the far side, counting holes drilled in line through parts stacked on each
    other: (length, True when the far end is closed off)."""
    tol = sc.doc.ModelAbsoluteTolerance
    inward = -outward
    holes, parts = _holes_near(Rhino.Geometry.Line(centre, centre + inward), centre)
    spans = []
    for start, end, radius in holes:
        axis = end - start
        if not axis.Unitize() or abs(axis * inward) < 0.999:
            continue
        slack = max(HOLE_JOIN_GAP, radius * 0.5)
        in_line = True
        for p in (start, end):
            offset = p - centre
            if (offset - inward * (offset * inward)).Length > slack:
                in_line = False
        if in_line:
            a, b = (start - centre) * inward, (end - centre) * inward
            spans.append((min(a, b), max(a, b)))
    spans.sort()
    depth = 0.0
    for low, high in spans:
        if low <= depth + HOLE_JOIN_GAP and high > depth:
            depth = high
    if depth <= tol:
        return 0.0, True
    return depth, _inside_a_part(centre + inward * (depth + HOLE_PROBE), parts)


def _inches(value):
    text = "{:.3f}".format(value).rstrip("0").rstrip(".")
    return text + '"'


def insert_in_hole(block_name, nut_name, layer_name, point, line=None, camera=None, snapped=False):
    """Insert a bolt in the hole under a click, head on the clicked side, and
    its nut on the far side when nut_name is given. Returns (ids, message)."""
    mouth = find_hole(point, line, camera, snapped)
    if mouth is None:
        return [], "No hole found there: click in a round hole, or on its rim."
    centre, outward, radius = mouth
    ids = []
    notes = []
    bolt_id = rs.InsertBlock2(block_name, insert_transform(centre, outward))
    if not bolt_id:
        return [], "Could not insert '{}'.".format(block_name)
    rs.ObjectLayer(bolt_id, layer_name)
    ids.append(bolt_id)
    if radius * 2.0 < BOLT_DIAMETER - sc.doc.ModelAbsoluteTolerance:
        notes.append("the hole is {} across, smaller than the {} bolt".format(
            _inches(radius * 2.0), _inches(BOLT_DIAMETER)))
    if nut_name:
        depth, closed = measure_stack(centre, outward)
        if closed:
            stack = BOLT_STACK
            notes.append("the hole does not come out the far side, so the nut is {} from the head".format(
                _inches(stack)))
        else:
            stack = depth
            notes.append("nut on the far face, {} from the head".format(_inches(stack)))
            if depth > BOLT_STACK + 0.01:
                notes.append("that is more than the {} the 1-3/4\" bolt can reach a nut through".format(
                    _inches(BOLT_STACK)))
        nut_id = rs.InsertBlock2(nut_name, insert_transform(centre - outward * stack, -outward))
        if nut_id:
            rs.ObjectLayer(nut_id, layer_name)
            ids.append(nut_id)
        else:
            notes.append("could not insert '{}'".format(nut_name))
    message = "Bolt placed in a {} hole".format(_inches(radius * 2.0))
    if notes:
        message += "; " + "; ".join(notes)
    return ids, message + "."


def _click_view(view, point):
    """(line through a clicked point along the view, (eye point or None, view direction))."""
    view = view or sc.doc.Views.ActiveView
    if view is None:
        return None, None
    viewport = view.ActiveViewport
    direction = Rhino.Geometry.Vector3d(viewport.CameraDirection)
    if not direction.Unitize():
        return None, None
    if viewport.IsPerspectiveProjection:
        eye = viewport.CameraLocation
        if eye.DistanceTo(point) <= sc.doc.ModelAbsoluteTolerance:
            return None, None
        return Rhino.Geometry.Line(eye, point), (eye, direction)
    return Rhino.Geometry.Line(point - direction, point + direction), (None, direction)


def place_in_holes(label, block_name, layer_name):
    """Click holes to put a bolt in each; Nut=Yes/No on the command line is remembered."""
    nut_name = HOLE_FITTINGS[block_name]
    if not ensure_definition(block_name) or not ensure_definition(nut_name):
        return
    ensure_layer(layer_name)
    defaults = load_defaults()
    bolts = 0
    nuts = 0
    while True:
        getter = Rhino.Input.Custom.GetPoint()
        getter.SetCommandPrompt("Click a hole, on the side the bolt head goes. Enter when done")
        toggle = Rhino.Input.Custom.OptionToggle(bool(defaults["nut"]), "No", "Yes")
        getter.AddOptionToggle("Nut", toggle)
        getter.AcceptNothing(True)
        result = getter.Get()
        if bool(toggle.CurrentValue) != defaults["nut"]:
            defaults["nut"] = bool(toggle.CurrentValue)
            save_defaults(defaults)
        if result == Rhino.Input.GetResult.Option:
            continue
        if result != Rhino.Input.GetResult.Point:
            break
        point = getter.Point()
        line, camera = _click_view(getter.View(), point)
        try:
            snapped = str(getter.OsnapEventType) != "None"
        except Exception:
            snapped = False
        ids, message = insert_in_hole(block_name, nut_name if defaults["nut"] else None,
                                      layer_name, point, line, camera, snapped)
        if ids:
            bolts += 1
            nuts += len(ids) - 1
        print(message)
        sc.doc.Views.Redraw()

    if bolts:
        rs.MessageBox(
            "Inserted {} '{}' and {} '{}' on {}.".format(bolts, block_name, nuts, nut_name, layer_name),
            0,
            "Insert Block",
        )


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
    if block_name in HOLE_FITTINGS:
        place_in_holes(choice, block_name, layer_name)
        return
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
