import os

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

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
    ("Cam", "cam", "NP-Fittings"),
    ("Glide", "glide", "NP-Fittings"),
    ("Flipper pin", "flipper_pin", "NP-Fittings"),
    ("Flipper receptacle", "flipper_receptacle", "NP-Fittings"),
    ("Castor small", "ACC-CST-SM", "NP-Fittings"),
    ("Castor large", "ACC-CST-LG", "NP-Fittings"),
    ("Logo", "Logo", "NP-Panel-Logo"),
    ("Logo outline", "Logo_outline", "NP-Panel-Logo"),
]


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
        source.BasePoint,
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


def main():
    labels = [row[0] for row in CATALOG]
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
        instance_id = rs.InsertBlock(block_name, point)
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


main()
