#! python 3
# -*- coding: utf-8 -*-
"""
19 - Display Modes

Share display modes across the team. Modes live as .ini files in
templates/display_modes (for example NP Assembly.ini, NP Render.ini).

Import: adds the chosen mode to this Rhino, or updates it if a mode with the
same id already exists, and optionally applies it to the active viewport.
Save: exports one of your current display modes into the team folder so it
can be committed and pushed.
"""

import os
import re
import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
import System

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
MODES_FOLDER = os.path.join(_INSTALL_ROOT, "templates", "display_modes")

TITLE = "NP Display Modes"
IMPORT_ALL_LABEL = "Import all team display modes"
SAVE_LABEL = "Save one of my display modes to the team folder..."
IMPORT_PREFIX = "Import: "


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


# --- display mode files ---------------------------------------------------------
#
# Rhino for Mac writes display mode .ini files as UTF-8 with a byte order mark and
# reads any encoding. Rhino for Windows can trip over that mark: the first line,
# the [DisplayMode\<id>] header, is then not recognised and the import returns
# nothing. Team files are therefore kept as plain text without the mark, and a
# failed import is tried again in the other encodings Rhino has used.

def read_mode_file(path):
    """Text of a display mode .ini, whichever encoding it was saved in."""
    with open(path, "rb") as handle:
        raw = handle.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


def mode_file_bytes(text, encoding):
    if encoding == "UTF-16":
        return b"\xff\xfe" + text.encode("utf-16-le")
    if encoding == "UTF-8 with a byte order mark":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    return text.encode("utf-8")          # "plain text": no byte order mark


def portable_mode_bytes(text):
    """Bytes for a team file: plain text when it is all ASCII (every Rhino reads
    that), UTF-16 when a name has other characters."""
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        return mode_file_bytes(text, "UTF-16")
    return mode_file_bytes(text, "plain text")


def import_mode_id(path):
    try:
        mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    except Exception:
        return None
    if mode_id is None or mode_id == System.Guid.Empty:
        return None
    return mode_id


def import_mode_file(path):
    """Imports a display mode .ini; returns the DisplayModeDescription or None.
    When Rhino refuses the file as it is, the same content is tried in the other
    encodings."""
    mode_id = import_mode_id(path)
    if mode_id is None:
        import shutil
        import tempfile
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            text = read_mode_file(path)
        except Exception:
            return None
        folder = tempfile.mkdtemp(prefix="np-mode-")
        try:
            for encoding in ("plain text", "UTF-16", "UTF-8 with a byte order mark"):
                data = mode_file_bytes(text, encoding)
                if data == raw:
                    continue
                temp_path = os.path.join(folder, os.path.basename(path))
                with open(temp_path, "wb") as handle:
                    handle.write(data)
                mode_id = import_mode_id(temp_path)
                if mode_id is not None:
                    print("Display mode file '{}' was read after re-saving it as {}.".format(
                        os.path.basename(path), encoding))
                    break
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    if mode_id is None:
        return None
    return Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)


def mode_import_report(path):
    """Details for the message when a display mode file will not import."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        start = " ".join("{:02x}".format(b) for b in raw[:4])
        detail = "{} bytes, starts with {}".format(len(raw), start)
    except Exception as ex:
        detail = "could not be read: {}".format(ex)
    system = "Windows" if Rhino.Runtime.HostUtils.RunningOnWindows else "Mac"
    return "File: {}\n({})\nRhino {} on {}. Tried as saved, as plain text and as UTF-16.".format(
        path, detail, Rhino.RhinoApp.Version, system)


def mode_files():
    if not os.path.isdir(MODES_FOLDER):
        return []
    files = [os.path.join(MODES_FOLDER, f) for f in os.listdir(MODES_FOLDER)
             if f.lower().endswith(".ini")]
    files.sort(key=lambda p: os.path.basename(p).lower())
    return files


def mode_name_from_file(path):
    try:
        for line in read_mode_file(path).splitlines():
            if line.strip().lower().startswith("name="):
                return line.strip()[5:]
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]


def import_mode(path):
    """Returns the DisplayModeDescription that was added or updated, or None."""
    return import_mode_file(path)


def apply_to_active_viewport(mode):
    view = sc.doc.Views.ActiveView
    if view is None or mode is None:
        return False
    view.ActiveViewport.DisplayMode = mode
    view.Redraw()
    return True


def safe_filename(name):
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", name).strip()
    return (cleaned or "display mode") + ".ini"


def save_mode():
    modes = sorted(Rhino.Display.DisplayModeDescription.GetDisplayModes(),
                   key=lambda m: m.EnglishName.lower())
    names = [m.EnglishName for m in modes]
    current = sc.doc.Views.ActiveView.ActiveViewport.DisplayMode.EnglishName
    choice = rs.ListBox(names, "Display mode to save for the team", TITLE,
                        current if current in names else None)
    if not choice:
        return
    mode = [m for m in modes if m.EnglishName == choice][0]
    if not os.path.isdir(MODES_FOLDER):
        os.makedirs(MODES_FOLDER)
    path = os.path.join(MODES_FOLDER, safe_filename(choice))
    if os.path.isfile(path):
        answer = rs.GetString("'{}' already exists in the team folder. Replace it".format(
            os.path.basename(path)), "No", ["Yes", "No"])
        if not answer or not answer.lower().startswith("y"):
            return
    if Rhino.Display.DisplayModeDescription.ExportToFile(mode, path):
        # Rhino for Mac and for Windows export in different encodings; the team
        # copy is re-saved in the one both of them read.
        try:
            text = read_mode_file(path)
            with open(path, "wb") as handle:
                handle.write(portable_mode_bytes(text))
        except Exception as ex:
            print("Could not re-save {} as plain text: {}".format(os.path.basename(path), ex))
        rs.MessageBox(
            "Saved '{}' to:\n{}\n\nCommit and push that file so the team receives it."
            .format(choice, path), 0, TITLE)
    else:
        rs.MessageBox("Could not export '{}'.".format(choice), 0, TITLE)


def menu_items():
    """Choices offered by the list dialog and by the NP Menu drawer."""
    files = mode_files()
    items = [IMPORT_PREFIX + mode_name_from_file(p) for p in files]
    if len(files) > 1:
        items.append(IMPORT_ALL_LABEL)
    items.append(SAVE_LABEL)
    return items


def main():
    files = mode_files()
    items = menu_items()
    choice = take_menu_choice(items)
    if not choice:
        message = ("Team display modes" if files
                   else "No team display modes yet. Save one of yours to start the set.")
        choice = rs.ListBox(items, message, TITLE, items[0])
    if not choice:
        return

    if choice == SAVE_LABEL:
        save_mode()
        return

    if choice == IMPORT_ALL_LABEL:
        targets = files
    else:
        name = choice[len(IMPORT_PREFIX):]
        targets = [p for p in files if mode_name_from_file(p) == name][:1]

    imported = []
    for path in targets:
        mode = import_mode(path)
        if mode is not None:
            imported.append(mode)
        else:
            print("Could not import {}\n{}".format(os.path.basename(path), mode_import_report(path)))
    if not imported:
        rs.MessageBox("No display modes were imported.", 0, TITLE)
        return

    if len(imported) == 1:
        answer = rs.GetString("Apply '{}' to the active viewport".format(
            imported[0].EnglishName), "Yes", ["Yes", "No"])
        if answer and answer.lower().startswith("y"):
            apply_to_active_viewport(imported[0])

    names = ", ".join(m.EnglishName for m in imported)
    print("Imported display modes: {}".format(names))
    rs.MessageBox("Imported: {}\n\nThey are now in the viewport display mode list.".format(names),
                  0, TITLE)


if __name__ == "__main__":
    main()
