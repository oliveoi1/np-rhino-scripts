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

_THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
_INSTALL_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
MODES_FOLDER = os.path.join(_INSTALL_ROOT, "templates", "display_modes")

TITLE = "NP Display Modes"
IMPORT_ALL_LABEL = "Import all team display modes"
SAVE_LABEL = "Save one of my display modes to the team folder..."
IMPORT_PREFIX = "Import: "


def mode_files():
    if not os.path.isdir(MODES_FOLDER):
        return []
    files = [os.path.join(MODES_FOLDER, f) for f in os.listdir(MODES_FOLDER)
             if f.lower().endswith(".ini")]
    files.sort(key=lambda p: os.path.basename(p).lower())
    return files


def mode_name_from_file(path):
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as handle:
            for line in handle:
                if line.strip().lower().startswith("name="):
                    return line.strip()[5:]
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]


def import_mode(path):
    """Returns the DisplayModeDescription that was added or updated, or None."""
    mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    if mode_id is None or mode_id == System_empty_guid():
        return None
    return Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)


def System_empty_guid():
    import System
    return System.Guid.Empty


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
        rs.MessageBox(
            "Saved '{}' to:\n{}\n\nCommit and push that file so the team receives it."
            .format(choice, path), 0, TITLE)
    else:
        rs.MessageBox("Could not export '{}'.".format(choice), 0, TITLE)


def main():
    files = mode_files()
    items = [IMPORT_PREFIX + mode_name_from_file(p) for p in files]
    if len(files) > 1:
        items.append(IMPORT_ALL_LABEL)
    items.append(SAVE_LABEL)
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
            print("Could not import {}".format(os.path.basename(path)))
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
