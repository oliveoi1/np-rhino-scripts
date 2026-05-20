import rhinoscriptsyntax as rs

DEPTH = 0.75

MATERIAL_TO_LAYER = {
    "Signature Core | Maple Veneer": "NP-Extrusions-SCMaple",
    "Signature Core | Maple HPL": "NP-Extrusions-SCHPL",
    "Refined Core | Maple Veneer": "NP-Extrusions-RCMaple",
    "Acrylic": "NP-Extrusions-Acrylic",
}

def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)

def choose_material():
    options = list(MATERIAL_TO_LAYER.keys())
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

main()