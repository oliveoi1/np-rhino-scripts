#! python 3
# -*- coding: utf-8 -*-
"""
Explode fittings for assembly diagrams.

Select fitting block instances (screws, grub screws, cams...) and pull each one
out of its face along its own axis by a set distance. Optionally draws a dashed
leader from the exploded fitting back to the hole centre on the face, on a
layer of its own. Distance, Move/Copy and leader choice are remembered as the
next-run defaults.

Each fitting block is authored with its insertion point on the face and its
shank running down local -Z, so local +Z is "out of the face".
"""

import json
import os
import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

_SCRIPT_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))

LEADER_LAYER = "NP-Assembly - Leaders"
LEADER_COLOR = (110, 110, 110)
LINETYPE_NAME = "Dashed"
LINETYPE_SEGMENTS = [0.25, -0.125]  # model units; negative = gap

STICKY_KEY = "np_explode_fittings"
DEFAULTS_FILENAME = "explode_fittings_defaults.json"
FALLBACK = {"distance": 2.0, "mode": "Move", "leader": True}
MIN_DISTANCE = 0.001


def defaults_path():
    return os.path.join(_INSTALL_ROOT, "_user_data", DEFAULTS_FILENAME)


def load_defaults():
    data = dict(FALLBACK)
    saved = sc.sticky.get(STICKY_KEY)
    if not saved:
        path = defaults_path()
        if os.path.isfile(path):
            try:
                with open(path, "r") as handle:
                    saved = json.load(handle)
            except Exception:
                saved = None
    if isinstance(saved, dict):
        try:
            data["distance"] = float(saved.get("distance", data["distance"]))
        except Exception:
            pass
        if saved.get("mode") in ("Move", "Copy"):
            data["mode"] = saved["mode"]
        data["leader"] = bool(saved.get("leader", data["leader"]))
    return data


def save_defaults(data):
    sc.sticky[STICKY_KEY] = dict(data)
    folder = os.path.join(_INSTALL_ROOT, "_user_data")
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(defaults_path(), "w") as handle:
            json.dump(data, handle)
    except Exception:
        pass


def ensure_dashed_linetype():
    table = sc.doc.Linetypes
    index = table.Find(LINETYPE_NAME)
    if index >= 0:
        return index
    try:
        return table.Add(LINETYPE_NAME, LINETYPE_SEGMENTS)
    except Exception:
        return -1


def ensure_leader_layer():
    if not rs.IsLayer(LEADER_LAYER):
        rs.AddLayer(LEADER_LAYER, LEADER_COLOR)
    linetype_index = ensure_dashed_linetype()
    if linetype_index >= 0:
        layer = sc.doc.Layers.FindByFullPath(LEADER_LAYER, -1)
        if layer >= 0:
            sc.doc.Layers[layer].LinetypeIndex = linetype_index
    return LEADER_LAYER


def instance_axis(obj_id):
    """Insertion point and unit local +Z of a block instance, in world space."""
    rhobj = rs.coercerhinoobject(obj_id, True, True)
    xform = rhobj.InstanceXform
    origin = Rhino.Geometry.Point3d(xform.M03, xform.M13, xform.M23)
    axis = Rhino.Geometry.Vector3d(xform.M02, xform.M12, xform.M22)
    if not axis.Unitize():
        return None, None
    return origin, axis


def explode_instances(instance_ids, distance, mode="Move", leader=True):
    """Core operation; returns (moved_ids, leader_ids)."""
    layer_name = ensure_leader_layer() if leader else None
    moved = []
    leaders = []
    for obj_id in instance_ids:
        origin, axis = instance_axis(obj_id)
        if origin is None:
            continue
        offset = axis * distance
        target = origin + offset
        if mode == "Copy":
            new_id = rs.CopyObject(obj_id, offset)
        else:
            new_id = rs.MoveObject(obj_id, offset)
        if not new_id:
            continue
        moved.append(new_id)
        if leader:
            line_id = rs.AddLine(target, origin)
            if line_id:
                rs.ObjectLayer(line_id, layer_name)
                rs.ObjectName(line_id, "assembly leader")
                leaders.append(line_id)
    return moved, leaders


def prompt_settings(defaults):
    distance = rs.GetReal("Explode distance along fitting axis", defaults["distance"], MIN_DISTANCE)
    if distance is None:
        return None
    mode = rs.GetString("Move or copy the fittings", defaults["mode"], ["Move", "Copy"])
    if not mode:
        return None
    mode = "Copy" if mode.strip().lower().startswith("c") else "Move"
    leader_default = "Yes" if defaults["leader"] else "No"
    leader = rs.GetString("Draw dashed leader back to the hole centre", leader_default, ["Yes", "No"])
    if not leader:
        return None
    return {"distance": float(distance), "mode": mode, "leader": leader.strip().lower().startswith("y")}


def main():
    objs = rs.GetObjects("Select fitting blocks to explode", rs.filter.instance, preselect=True)
    if not objs:
        return
    settings = prompt_settings(load_defaults())
    if not settings:
        return
    save_defaults(settings)

    rs.EnableRedraw(False)
    undo = sc.doc.BeginUndoRecord("Explode fittings")
    try:
        moved, leaders = explode_instances(objs, settings["distance"], settings["mode"], settings["leader"])
    finally:
        if undo:
            sc.doc.EndUndoRecord(undo)
        rs.EnableRedraw(True)

    rs.UnselectAllObjects()
    rs.SelectObjects(moved + leaders)
    print("Exploded {} fitting(s) by {} ({}); {} leader line(s) on '{}'.".format(
        len(moved), settings["distance"], settings["mode"].lower() + "d", len(leaders), LEADER_LAYER))


if __name__ == "__main__":
    main()
