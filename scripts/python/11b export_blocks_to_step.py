"""
Export selected block instances to STEP (.step) files.

For consultants who rebuild the products in other systems (CET, Revit): STEP
carries exact solids, units, layer names and the block structure as an assembly.

Export the first selected instance of each distinct block definition once.
Construction markers are skipped as standalone exports, and they are also
stripped from inside the products together with text, curves and points: STEP
cannot hold text (Rhino would stop on a warning dialog for every product, since
each one carries the "S" of its SKU insertion marker), and setout geometry is
noise to whoever receives the file. Only solids, surfaces and the nested blocks
that contain them are written. The stripping happens on temporary block
definitions; the real blocks are never touched. The export sits with the block
insertion point at the origin. Existing output files are replaced only after a
new export succeeds.
"""

import os
import re
import shutil
import tempfile
import unicodedata
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


HELPER_BLOCKS = set(["hole_insert", "caminsert", "flipper_insert"])
EXTENSION = ".step"
# AP214 keeps colours and layer names; AP203 would drop them.
STEP_SCHEMA = "AP214AutomotiveDesign"
# Temporary cleaned block definitions are called "<block name>__npstep__"; the
# suffix is taken out of the STEP file again, so parts keep their real names.
TEMP_SUFFIX = "__npstep__"
TEMP_PATTERN = re.compile(r"__npstep__\d*")
KEEP_GEOMETRY = (Rhino.Geometry.Brep, Rhino.Geometry.Extrusion,
                 Rhino.Geometry.Surface, Rhino.Geometry.SubD)


class ExportCancelled(Exception):
    pass


class NothingToExport(Exception):
    pass


def check_cancelled():
    Rhino.RhinoApp.Wait()
    if sc.escape_test(False):
        raise ExportCancelled("Export cancelled")


def is_construction_marker(block_name, layer_name):
    if block_name.lower() in HELPER_BLOCKS:
        return True
    # These layers hold insertion/setout helpers, not finished products.
    parts = (layer_name or "").lower().split("::")
    return any(p.startswith("np-construction") or
               p in ("np-sku_insertion", "np-setout", "n_setout")
               for p in parts)


def clean_block_name(name):
    """Same rules as create_or_redefine_block.py for filesystem-safe names."""
    if not name:
        return None

    name = name.strip()
    if not name:
        return None

    bad_chars = ["\\", "/", ":", ";", "*", "?", '"', "<", ">", "|", "=", ",", "[", "]", "(", ")"]
    for ch in bad_chars:
        name = name.replace(ch, "_")

    name = name.strip().rstrip(". ")
    if not name or any(ord(ch) < 32 for ch in name):
        return None
    return name


def path_for_rhino_command(full_path):
    """Use forward slashes in the command string (Rhino accepts them on Windows)."""
    return full_path.replace("\\", "/")


def plan_exports(objs):
    jobs = []
    seen_names = set()
    filenames = {}
    counts = {"duplicates": 0, "helpers": 0, "invalid": 0}
    for index, inst_id in enumerate(objs):
        if index % 50 == 0:
            check_cancelled()
        if not rs.IsObject(inst_id) or not rs.IsBlockInstance(inst_id):
            counts["invalid"] += 1
            continue
        block_name = rs.BlockInstanceName(inst_id)
        if not block_name:
            counts["invalid"] += 1
            continue
        if is_construction_marker(block_name, rs.ObjectLayer(inst_id)):
            counts["helpers"] += 1
            continue
        if block_name in seen_names:
            counts["duplicates"] += 1
            continue
        safe_name = clean_block_name(block_name)
        if not safe_name:
            counts["invalid"] += 1
            continue
        key = unicodedata.normalize("NFC", safe_name).lower()
        if key in filenames:
            raise ValueError("Two block names produce the same filename: {} and {}. "
                             "Rename one before exporting.".format(
                                 filenames[key], block_name))
        seen_names.add(block_name)
        filenames[key] = block_name
        jobs.append((inst_id, safe_name))
    return jobs, counts


def replace_export(staged_path, out_path):
    if hasattr(os, "replace"):
        os.replace(staged_path, out_path)
    elif os.name == "nt" and os.path.exists(out_path):
        # IronPython on Windows does not expose os.replace.
        from System.IO import File
        File.Replace(staged_path, out_path, None)
    else:
        os.rename(staged_path, out_path)


def run_step_export(staged_path):
    """Runs Rhino's STEP export on the selection. The schema is asked for by
    name first; if this Rhino does not offer that option, the plain export
    (Rhino's own default schema) is used instead."""
    cmd_path = path_for_rhino_command(os.path.normpath(staged_path))
    commands = ['_-Export "{}" _Schema=_{} _Enter'.format(cmd_path, STEP_SCHEMA),
                '_-Export "{}" _Enter'.format(cmd_path)]
    for index, command in enumerate(commands):
        if os.path.isfile(staged_path):
            os.remove(staged_path)
        ok = rs.Command(command, echo=False)
        cancelled = rs.LastCommandResult() == 1
        if ok and not cancelled and os.path.isfile(staged_path):
            return True
        # Esc stops the run; a schema option Rhino refused only moves on to the plain export.
        check_cancelled()
        if cancelled and index == len(commands) - 1:
            raise ExportCancelled("Export command cancelled")
    return False


def is_step_file(path):
    with open(path, "rb") as handle:
        return handle.read(64).lstrip().startswith(b"ISO-10303-21")


def temp_definition_name(name):
    base = (name or "block") + TEMP_SUFFIX
    candidate = base
    counter = 2
    while sc.doc.InstanceDefinitions.Find(candidate) is not None:
        candidate = "{}{}".format(base, counter)
        counter += 1
    return candidate


def clean_definition(idef, cache, temp_indices):
    """Index of a block definition holding only what STEP should get from `idef`:
    solids, surfaces and nested blocks that contain some. Construction markers,
    text, curves, points and meshes are left out. Returns `idef`'s own index when
    nothing had to go, the index of a temporary definition otherwise, or None when
    nothing exportable is left."""
    if idef.Index in cache:
        return cache[idef.Index]
    cache[idef.Index] = None   # stops a block that contains itself from looping
    geometries = []
    attributes = []
    changed = False
    for obj in idef.GetObjects():
        if isinstance(obj, Rhino.DocObjects.InstanceObject):
            child = obj.InstanceDefinition
            layer = sc.doc.Layers[obj.Attributes.LayerIndex]
            if child is None or is_construction_marker(child.Name or "", layer.FullPath):
                changed = True
                continue
            child_index = clean_definition(child, cache, temp_indices)
            if child_index is None:
                changed = True
                continue
            if child_index != child.Index:
                changed = True
            child_id = sc.doc.InstanceDefinitions[child_index].Id
            geometries.append(Rhino.Geometry.InstanceReferenceGeometry(child_id, obj.InstanceXform))
            attributes.append(obj.Attributes.Duplicate())
        elif isinstance(obj.Geometry, KEEP_GEOMETRY):
            geometries.append(obj.Geometry.Duplicate())
            attributes.append(obj.Attributes.Duplicate())
        else:
            changed = True
    if not geometries:
        result = None
    elif not changed:
        result = idef.Index
    else:
        result = sc.doc.InstanceDefinitions.Add(
            temp_definition_name(idef.Name), idef.Description or "",
            Rhino.Geometry.Point3d.Origin, geometries, attributes)
        if result < 0:
            raise RuntimeError("Could not build the cleaned copy of block {}".format(idef.Name))
        temp_indices.append(result)
    cache[idef.Index] = result
    return result


def remove_temp_definitions(indices):
    """Deletes the temporary definitions, outermost first."""
    for index in reversed(indices):
        try:
            sc.doc.InstanceDefinitions.Delete(index, True, True)
        except Exception:
            pass
        try:
            sc.doc.InstanceDefinitions.Purge(index)
        except Exception:
            pass


def remove_stale_temp_definitions():
    """Clears temporary definitions a crashed earlier run may have left behind."""
    stale = []
    for idef in sc.doc.InstanceDefinitions:
        if idef is None or idef.IsDeleted:
            continue
        if TEMP_PATTERN.search(idef.Name or ""):
            stale.append(idef.Index)
    remove_temp_definitions(sorted(stale))
    return len(stale)


def restore_names(path):
    """Takes the temporary suffix out of the names in the STEP file."""
    with open(path, "rb") as handle:
        data = handle.read()
    cleaned = re.sub(TEMP_PATTERN.pattern.encode("ascii"), b"", data)
    if cleaned != data:
        with open(path, "wb") as handle:
            handle.write(cleaned)


def export_selected_instance_to_step(inst_id, out_path):
    """
    Add a cleaned copy of the block with its insertion point at the origin,
    export it, remove it again. Returns True on success; raises NothingToExport
    for a block with no solids or surfaces in it.
    """
    instance = sc.doc.Objects.FindId(inst_id)
    if not isinstance(instance, Rhino.DocObjects.InstanceObject):
        return False

    stage_dir = None
    copy_id = None
    temp_indices = []
    try:
        clean_index = clean_definition(instance.InstanceDefinition, {}, temp_indices)
        if clean_index is None:
            raise NothingToExport("no solids or surfaces")

        to_origin = Rhino.Geometry.Transform.Translation(
            Rhino.Geometry.Point3d.Origin - instance.InsertionPoint)
        copy_id = sc.doc.Objects.AddInstanceObject(
            clean_index, to_origin * instance.InstanceXform, instance.Attributes.Duplicate())
        if not copy_id or not rs.IsObject(copy_id):
            return False

        rs.UnselectAllObjects()
        if not rs.SelectObject(copy_id):
            raise RuntimeError("Could not select the temporary export copy")

        stage_dir = tempfile.mkdtemp(prefix=".np-export-", dir=os.path.dirname(out_path))
        staged_path = os.path.join(stage_dir, os.path.basename(out_path))
        check_cancelled()
        if not run_step_export(staged_path):
            raise RuntimeError("Rhino did not create the export file")
        check_cancelled()
        if not is_step_file(staged_path):
            raise RuntimeError("Export file is not a STEP file")
        restore_names(staged_path)
        replace_export(staged_path, out_path)
        return True
    finally:
        try:
            if copy_id and rs.IsObject(copy_id):
                rs.DeleteObject(copy_id)
            remove_temp_definitions(temp_indices)
        finally:
            if stage_dir:
                shutil.rmtree(stage_dir, ignore_errors=True)


def run_export():
    rs.UnselectAllObjects()

    objs = rs.GetObjects(
        "Select block instances to export as STEP (.step)",
        rs.filter.instance,
        preselect=False,
    )
    if not objs:
        return

    # Materialize a fixed list before creating any temporary copies.
    jobs, counts = plan_exports(list(objs))
    print("Selected {} instances: {} unique exports, {} repeated instances, "
          "{} construction markers, {} invalid objects.".format(
              len(objs), len(jobs), counts["duplicates"], counts["helpers"], counts["invalid"]))
    if not jobs:
        rs.MessageBox("No product blocks to export.\nConstruction markers such as "
                      "hole_insert are skipped.\nSelect the finished product blocks.")
        return

    folder = rs.BrowseForFolder(
        message="Choose folder for STEP exports",
        title="Export blocks to STEP",
    )
    if not folder:
        return

    folder = os.path.normpath(folder)
    if not os.path.isdir(folder):
        rs.MessageBox("Output folder is not valid:\n{}".format(folder))
        return

    exported = 0
    empty = []
    stopped = None
    remove_stale_temp_definitions()

    previous_redraw = rs.EnableRedraw(False)
    try:
        for index, (inst_id, safe_name) in enumerate(jobs, 1):
            out_path = os.path.join(folder, safe_name + EXTENSION)
            try:
                check_cancelled()
                print("Export {}/{}: {} (Esc to stop)".format(index, len(jobs), safe_name))
                if export_selected_instance_to_step(inst_id, out_path):
                    exported += 1
                    print("Saved: {}".format(out_path))
                else:
                    raise RuntimeError("Could not prepare export copy")
            except ExportCancelled:
                stopped = "Cancelled by user."
                break
            except NothingToExport:
                empty.append(safe_name)
                print("Skipped {}: no solids or surfaces in it.".format(safe_name))
            except Exception as ex:
                stopped = "Stopped at {}: {}".format(safe_name, ex)
                break
    finally:
        rs.EnableRedraw(previous_redraw)

    msg = ("Exported: {} of {} unique blocks\nRepeated instances skipped: {}\n"
           "Construction markers skipped: {}\nInvalid objects skipped: {}\nFolder:\n{}").format(
               exported, len(jobs), counts["duplicates"], counts["helpers"], counts["invalid"], folder)
    if empty:
        msg += "\n\nNo solids or surfaces, skipped: {}".format(", ".join(empty[:12]))
        if len(empty) > 12:
            msg += " and {} more".format(len(empty) - 12)
    if stopped:
        msg += "\n\n" + stopped
    rs.MessageBox(msg)


def main():
    initial_sel = list(rs.SelectedObjects() or [])
    try:
        run_export()
    except ExportCancelled:
        print("Export cancelled. No further files will be written.")
    except Exception as ex:
        rs.MessageBox("Export stopped:\n{}".format(ex))
    finally:
        rs.UnselectAllObjects()
        remaining = [obj for obj in initial_sel if rs.IsObject(obj)]
        if remaining:
            rs.SelectObjects(remaining)


if __name__ == "__main__":
    main()
