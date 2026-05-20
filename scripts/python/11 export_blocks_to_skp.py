"""
Export selected block instances to SketchUp (.skp) files.

For each instance: file name = block definition name (sanitized). A temporary copy
is moved so the block insertion point sits at world origin in the export, then
deleted. Duplicate block names in one run overwrite the same output file.
"""

import os
import rhinoscriptsyntax as rs


def clean_block_name(name):
    """Same rules as 08b create_block.py for filesystem-safe names."""
    if not name:
        return None

    name = name.strip()
    if not name:
        return None

    bad_chars = ["\\", "/", ":", ";", "*", "?", '"', "<", ">", "|", "=", ",", "[", "]", "(", ")"]
    for ch in bad_chars:
        name = name.replace(ch, "_")

    return name.strip()


def path_for_rhino_command(full_path):
    """Use forward slashes in the command string (Rhino accepts them on Windows)."""
    return full_path.replace("\\", "/")


def safe_remove(path):
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def export_selected_instance_to_skp(inst_id, out_path):
    """
    Copy block instance, move copy so insertion point is at origin, export, delete copy.
    Returns True on success.
    """
    insert_pt = rs.BlockInstanceInsertPoint(inst_id)
    if not insert_pt:
        return False

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
        rs.SelectObject(copy_id)

        safe_remove(out_path)
        cmd_path = path_for_rhino_command(os.path.normpath(out_path))
        # Hyphen prefix suppresses dialogs where possible.
        ok = rs.Command('_-Export "{}" _Enter'.format(cmd_path), echo=False)
        return bool(ok)
    finally:
        if rs.IsObject(copy_id):
            rs.DeleteObject(copy_id)


def main():
    initial_sel = rs.SelectedObjects() or []

    rs.UnselectAllObjects()

    objs = rs.GetObjects(
        "Select block instances to export as SketchUp (.skp)",
        rs.filter.instance,
        preselect=False,
    )
    if not objs:
        if initial_sel:
            rs.SelectObjects(initial_sel)
        return

    folder = rs.BrowseForFolder(
        message="Choose folder for SketchUp exports",
        title="Export blocks to SketchUp",
    )
    if not folder:
        if initial_sel:
            rs.SelectObjects(initial_sel)
        return

    folder = os.path.normpath(folder)
    if not os.path.isdir(folder):
        rs.MessageBox("Output folder is not valid:\n{}".format(folder))
        if initial_sel:
            rs.SelectObjects(initial_sel)
        return

    exported = 0
    skipped = 0
    skip_reasons = []

    rs.EnableRedraw(False)
    try:
        for inst_id in objs:
            if not rs.IsObject(inst_id) or not rs.IsBlockInstance(inst_id):
                skipped += 1
                if len(skip_reasons) < 8:
                    skip_reasons.append("Not a block instance: {}".format(inst_id))
                continue

            block_name = None
            try:
                block_name = rs.BlockInstanceName(inst_id)
            except Exception:
                block_name = None

            if not block_name:
                skipped += 1
                if len(skip_reasons) < 8:
                    skip_reasons.append("No block name for object {}".format(inst_id))
                continue

            safe_name = clean_block_name(block_name)
            if not safe_name:
                skipped += 1
                if len(skip_reasons) < 8:
                    skip_reasons.append("Invalid file name for block: {}".format(block_name))
                continue

            out_path = os.path.join(folder, safe_name + ".skp")

            try:
                if export_selected_instance_to_skp(inst_id, out_path):
                    exported += 1
                else:
                    skipped += 1
                    if len(skip_reasons) < 8:
                        skip_reasons.append("Export failed: {}".format(safe_name))
            except Exception as ex:
                skipped += 1
                if len(skip_reasons) < 8:
                    skip_reasons.append("{}: {}".format(safe_name, ex))
    finally:
        rs.EnableRedraw(True)
        rs.UnselectAllObjects()
        if initial_sel:
            rs.SelectObjects(initial_sel)

    msg = "Exported: {}\nSkipped: {}\nFolder:\n{}".format(exported, skipped, folder)
    if skip_reasons:
        msg += "\n\nFirst issues:\n" + "\n".join(skip_reasons)
    rs.MessageBox(msg)


if __name__ == "__main__":
    main()
