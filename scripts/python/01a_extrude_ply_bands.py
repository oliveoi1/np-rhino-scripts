import rhinoscriptsyntax as rs

TOTAL_DEPTH = 0.75
BAND_COUNT = 11
BAND_THICKNESS = TOTAL_DEPTH / float(BAND_COUNT)

LAYER_LT = "NP-Extrusions-SC-LT"
LAYER_DK = "NP-Extrusions-SC-DK"


def ensure_layer(name):
    if not rs.IsLayer(name):
        rs.AddLayer(name)


def is_valid_curve(curve_id):
    return (
        rs.IsCurve(curve_id)
        and rs.IsCurveClosed(curve_id)
        and rs.IsCurvePlanar(curve_id)
    )


def extrude_curve_into_bands(curve_id):
    created_solids = []

    for band_index in range(BAND_COUNT):
        # Extrusion uses vector direction/length, so create one band thickness first.
        solid = rs.ExtrudeCurveStraight(curve_id, (0, 0, 0), (0, 0, -BAND_THICKNESS))
        if not solid:
            continue

        # Then stack each band downward to build the full 0.75 total thickness.
        if band_index > 0:
            rs.MoveObject(solid, (0, 0, -band_index * BAND_THICKNESS))

        rs.CapPlanarHoles(solid)

        # LT on outer faces: first and last bands are LT.
        layer_name = LAYER_LT if (band_index % 2 == 0) else LAYER_DK
        rs.ObjectLayer(solid, layer_name)
        created_solids.append(solid)

    return created_solids


def main():
    ensure_layer(LAYER_LT)
    ensure_layer(LAYER_DK)

    curves = rs.GetObjects(
        "Select closed planar curves to extrude as ply bands",
        rs.filter.curve,
        preselect=True,
    )
    if not curves:
        return

    valid_curves = 0
    all_created_solids = []

    for curve_id in curves:
        if not is_valid_curve(curve_id):
            continue

        valid_curves += 1
        all_created_solids.extend(extrude_curve_into_bands(curve_id))

    if not all_created_solids:
        rs.MessageBox(
            "No solids were created. Check that selected curves are closed and planar."
        )
        return

    group_name = rs.AddGroup()
    rs.AddObjectsToGroup(all_created_solids, group_name)

    rs.MessageBox(
        "Created {} solids from {} valid curve(s).\n"
        "Depth: {} in {} bands ({:.6f} each).\n"
        "Layers: '{}' and '{}'.\n"
        "Grouped as '{}'.".format(
            len(all_created_solids),
            valid_curves,
            TOTAL_DEPTH,
            BAND_COUNT,
            BAND_THICKNESS,
            LAYER_LT,
            LAYER_DK,
            group_name,
        )
    )


if __name__ == "__main__":
    main()
