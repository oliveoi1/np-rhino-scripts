import os

import rhinoscriptsyntax as rs

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

DEPTH = 0.75

# (material label, layer) in the order the list shows them.
MATERIALS = [
    ("Signature Core | Maple Veneer", "NP-Extrusions-SCMaple"),
    ("Signature Core | Maple HPL", "NP-Extrusions-SCHPL"),
    ("Refined Core | Maple Veneer", "NP-Extrusions-RCMaple"),
    ("Acrylic", "NP-Extrusions-Acrylic"),
]
MATERIAL_TO_LAYER = dict(MATERIALS)


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


def menu_items():
    """Choices offered by the list dialog and by the NP Menu drawer."""
    return [label for label, _ in MATERIALS]

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def choose_material():
    options = menu_items()
    choice = take_menu_choice(options)
    if choice:
        return choice
    return rs.ListBox(options, "Choose material for extrusion", "Material")

def main():
    material = choose_material()
    if not material:
        return

    layer_name = MATERIAL_TO_LAYER[material]
    ensure_layer(layer_name)

    curves = rs.GetObjects(
        "Select closed planar curves to extrude downward",
        rs.filter.curve,
        preselect=True
    )
    if not curves:
        return

    made = 0

    for crv in curves:
        if not rs.IsCurve(crv):
            continue
        if not rs.IsCurveClosed(crv):
            continue
        if not rs.IsCurvePlanar(crv):
            continue

        solid = rs.ExtrudeCurveStraight(crv, (0, 0, 0), (0, 0, -DEPTH))
        if solid:
            rs.CapPlanarHoles(solid)
            rs.ObjectLayer(solid, layer_name)
            made += 1

    rs.MessageBox("{} solid(s) created on layer '{}'.".format(made, layer_name))

if __name__ == "__main__":
    main()
