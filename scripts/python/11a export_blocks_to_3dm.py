"""
Export selected block instances to Rhino (.3dm) files.

Export the first selected instance of each distinct block definition once.
Construction markers are skipped as standalone exports; nested contents stay
intact. A temporary copy is moved to the origin and removed after export.
Existing output files are replaced only after a new export succeeds.
"""

import os
import shutil
import tempfile
import unicodedata
import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc


HELPER_BLOCKS = set(["hole_insert", "caminsert", "flipper_insert"])


class ExportCancelled(Exception):
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


def export_selected_instance_to_3dm(inst_id, out_path):
    """
    Copy block instance, move copy so insertion point is at origin, export, delete copy.
    Returns True on success.
    """
    insert_pt = rs.BlockInstanceInsertPoint(inst_id)
    if not insert_pt:
        return False

    stage_dir = None
    try:
        ox, oy, oz = float(insert_pt.X), float(insert_pt.Y), float(insert_pt.Z)
    except AttributeError:
        try:
            ox, oy, oz = float(insert_pt[0]), float(insert_pt[1]), float(insert_pt[2])
        except (TypeError, ValueError, IndexError):
            return False

    copy_id = rs.CopyObject(inst_id)
    if not copy_id:
        return False

    try:
        if not rs.MoveObject(copy_id, (-ox, -oy, -oz)):
            return False

        rs.UnselectAllObjects()
        if not rs.SelectObject(copy_id):
            raise RuntimeError("Could not select the temporary export copy")

        stage_dir = tempfile.mkdtemp(prefix=".np-export-", dir=os.path.dirname(out_path))
        staged_path = os.path.join(stage_dir, os.path.basename(out_path))
        cmd_path = path_for_rhino_command(os.path.normpath(staged_path))
        check_cancelled()
        # Hyphen prefix suppresses dialogs where possible.
        ok = rs.Command('_-Export "{}" _Enter'.format(cmd_path), echo=False)
        if rs.LastCommandResult() == 1:
            raise ExportCancelled("Export command cancelled")
        check_cancelled()
        if not ok or not os.path.isfile(staged_path):
            raise RuntimeError("Rhino did not create the export file")
        with open(staged_path, "rb") as handle:
            if not handle.read(24).startswith(b"3D Geometry File Format"):
                raise RuntimeError("Export file is not a Rhino 3dm file")
        replace_export(staged_path, out_path)
        return True
    finally:
        try:
            if rs.IsObject(copy_id):
                rs.DeleteObject(copy_id)
        finally:
            if stage_dir:
                shutil.rmtree(stage_dir, ignore_errors=True)


def run_export():
    rs.UnselectAllObjects()

    objs = rs.GetObjects(
        "Select block instances to export as Rhino (.3dm)",
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
        message="Choose folder for Rhino exports",
        title="Export blocks to Rhino",
    )
    if not folder:
        return

    folder = os.path.normpath(folder)
    if not os.path.isdir(folder):
        rs.MessageBox("Output folder is not valid:\n{}".format(folder))
        return

    exported = 0
    stopped = None

    previous_redraw = rs.EnableRedraw(False)
    try:
        for index, (inst_id, safe_name) in enumerate(jobs, 1):
            out_path = os.path.join(folder, safe_name + ".3dm")
            try:
                check_cancelled()
                print("Export {}/{}: {} (Esc to stop)".format(index, len(jobs), safe_name))
                if export_selected_instance_to_3dm(inst_id, out_path):
                    exported += 1
                    print("Saved: {}".format(out_path))
                else:
                    raise RuntimeError("Could not prepare export copy")
            except ExportCancelled:
                stopped = "Cancelled by user."
                break
            except Exception as ex:
                stopped = "Stopped at {}: {}".format(safe_name, ex)
                break
    finally:
        rs.EnableRedraw(previous_redraw)

    msg = ("Exported: {} of {} unique blocks\nRepeated instances skipped: {}\n"
           "Construction markers skipped: {}\nInvalid objects skipped: {}\nFolder:\n{}").format(
               exported, len(jobs), counts["duplicates"], counts["helpers"], counts["invalid"], folder)
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
