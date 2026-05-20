import rhinoscriptsyntax as rs

ALLOWED_LAYERS = [
    "NP-Extrusions",
    "NP-Extrusions-RCMaple",
    "NP-Extrusions-SCMaple",
    "NP-Extrusions-SCHPL",
    "NP-Extrusions-Acrylic",
    "NP-Furniture",
    "NP-Fittings",
    "NP-SKU_Insertion",
    "NP-Setout"
]

FURNITURE_LAYER = "NP-Furniture"
INSERTION_HELPER_BLOCK = "SKUInsertionPt"

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def is_allowed_layer(layer_name):
    if not layer_name:
        return False

    for allowed in ALLOWED_LAYERS:
        if layer_name == allowed:
            return True
        if layer_name.startswith(allowed + "::"):
            return True

    return False

def get_text_string(obj_id):
    if not obj_id:
        return None

    if rs.IsText(obj_id):
        try:
            return rs.TextObjectText(obj_id)
        except:
            pass

    if rs.IsTextDot(obj_id):
        try:
            return rs.TextDotText(obj_id)
        except:
            pass

    try:
        rhobj = rs.coercerhinoobject(obj_id, True, True)
        if rhobj and hasattr(rhobj.Geometry, "Text"):
            return rhobj.Geometry.Text
    except:
        pass

    return None

def clean_block_name(name):
    if not name:
        return None

    name = name.strip()
    if not name:
        return None

    bad_chars = ['\\', '/', ':', ';', '*', '?', '"', '<', '>', '|', '=', ',', '[', ']', '(', ')']
    for ch in bad_chars:
        name = name.replace(ch, "_")

    return name.strip()

def get_instance_xform(obj_id):
    rhobj = rs.coercerhinoobject(obj_id, True, True)
    if not rhobj:
        return None
    try:
        return rhobj.InstanceXform
    except:
        return None

def insert_block_with_xform(block_name, xform):
    new_id = rs.InsertBlock(block_name, (0, 0, 0))
    if not new_id:
        return None
    rs.TransformObject(new_id, xform, copy=False)
    return new_id

def collect_existing_instances(block_name):
    saved = []

    try:
        instance_ids = rs.BlockInstances(block_name)
    except:
        instance_ids = None

    if not instance_ids:
        return saved

    for inst_id in instance_ids:
        if not rs.IsObject(inst_id):
            continue

        xform = get_instance_xform(inst_id)
        layer = rs.ObjectLayer(inst_id)
        if not xform:
            continue

        saved.append({
            "id": inst_id,
            "xform": xform,
            "layer": layer
        })

    return saved

def delete_saved_instances(saved_instances):
    for item in saved_instances:
        inst_id = item.get("id")
        if rs.IsObject(inst_id):
            rs.DeleteObject(inst_id)

def restore_saved_instances(block_name, saved_instances):
    restored = 0

    for item in saved_instances:
        xform = item.get("xform")
        layer = item.get("layer")

        new_id = insert_block_with_xform(block_name, xform)
        if not new_id:
            continue

        if layer:
            rs.ObjectLayer(new_id, layer)

        restored += 1

    return restored

def delete_block_definition(block_name):
    try:
        return rs.DeleteBlock(block_name)
    except:
        return False

def is_valid_source_object(obj_id, text_obj, target_block_name):
    if not obj_id:
        return False, "invalid"

    if obj_id == text_obj:
        return False, "text"

    if not rs.IsObject(obj_id):
        return False, "invalid"

    layer = rs.ObjectLayer(obj_id)
    if not is_allowed_layer(layer):
        return False, "layer"

    if rs.IsBlockInstance(obj_id):
        inst_name = rs.BlockInstanceName(obj_id)
        if inst_name == target_block_name:
            return False, "self_block"
        if inst_name == INSERTION_HELPER_BLOCK:
            return True, "helper_block"
        return True, "nested_block"

    return True, "geometry"

def filter_valid_objects(objs, text_obj, target_block_name):
    valid = []
    counts = {
        "text": 0,
        "invalid": 0,
        "layer": 0,
        "self_block": 0,
        "helper_block": 0,
        "nested_block": 0,
        "geometry": 0
    }

    for obj in objs:
        ok, reason = is_valid_source_object(obj, text_obj, target_block_name)
        if ok:
            valid.append(obj)
            counts[reason] += 1
        else:
            counts[reason] += 1

    print(
        "Valid total: {}\nGeometry: {}\nNested blocks: {}\nHelper blocks: {}\nSkipped text: {}\nSkipped invalid: {}\nSkipped wrong layer: {}\nSkipped self block: {}".format(
            len(valid),
            counts["geometry"],
            counts["nested_block"],
            counts["helper_block"],
            counts["text"],
            counts["invalid"],
            counts["layer"],
            counts["self_block"]
        )
    )

    return valid

def find_helper_insertion_point(objs):
    for obj in objs:
        if not rs.IsObject(obj):
            continue
        if not rs.IsBlockInstance(obj):
            continue

        try:
            inst_name = rs.BlockInstanceName(obj)
        except:
            inst_name = None

        if inst_name == INSERTION_HELPER_BLOCK:
            try:
                pt = rs.BlockInstanceInsertPoint(obj)
                if pt:
                    return pt
            except:
                pass

    return None

def main():
    rs.UnselectAllObjects()

    text_obj = rs.GetObject("Select text for block name", preselect=False)
    if not text_obj:
        return

    block_name = get_text_string(text_obj)
    block_name = clean_block_name(block_name)

    if not block_name:
        rs.MessageBox("Invalid text for block name.")
        return

    objs = rs.GetObjects("Select objects to define block", preselect=False)
    if not objs:
        return

    insert_pt = find_helper_insertion_point(objs)
    if not insert_pt:
        insert_pt = rs.GetPoint("Pick insertion point")
        if not insert_pt:
            return

    objs = filter_valid_objects(objs, text_obj, block_name)

    if not objs:
        rs.MessageBox("No valid objects found to make block.")
        return

    saved_instances = []
    restored_count = 0

    if rs.IsBlock(block_name):
        saved_instances = collect_existing_instances(block_name)
        delete_saved_instances(saved_instances)

        if rs.IsBlock(block_name):
            ok = delete_block_definition(block_name)
            if not ok and rs.IsBlock(block_name):
                rs.MessageBox("Could not delete existing block definition.")
                return

    result = rs.AddBlock(objs, insert_pt, block_name, delete_input=True)
    if not result:
        rs.MessageBox("Block creation failed.")
        return

    if saved_instances:
        restored_count = restore_saved_instances(block_name, saved_instances)

    instance_id = rs.InsertBlock(block_name, insert_pt)

    if instance_id:
        ensure_layer(FURNITURE_LAYER)
        rs.ObjectLayer(instance_id, FURNITURE_LAYER)
        rs.SelectObject(instance_id)

    if saved_instances:
        rs.MessageBox(
            "Block '{}' updated.\nRestored instances: {}\nAdditional instance inserted.".format(
                block_name,
                restored_count
            )
        )
    else:
        rs.MessageBox("Block '{}' created and inserted.".format(block_name))

main()