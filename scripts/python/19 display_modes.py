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
CHECK_LABEL = "Check display mode import (report)"


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
# Team display modes travel as .ini files, and importing them has two known traps:
#
# * Encoding. Rhino for Mac exports UTF-8 with a byte order mark and reads anything.
#   A reader that takes the mark for text no longer recognises the first line, the
#   [DisplayMode\<id>] header. Team files are kept as plain text without the mark.
# * Script engine. In Rhino 8 for Windows before 8.13, ImportFromFile did nothing
#   when called from the Python 3 engine (McNeel RH-83960: the engine's open undo
#   record got in the way); from IronPython it worked.
#
# import_mode_file therefore tries the file as saved, re-saved in other encodings,
# through a tiny IronPython script, and with the script's undo record closed, in
# that order, and says which one worked.

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


def mode_file_id(path):
    """The id in the header line of a display mode file, or None."""
    import re as _re
    try:
        match = _re.search(r"\[DisplayMode\\([0-9a-fA-F-]{36})\]", read_mode_file(path))
        return System.Guid(match.group(1)) if match else None
    except Exception:
        return None


def listed_mode(mode_id):
    """The display mode with this id as Rhino lists it (the list behind the
    viewport's display mode menu), or None.

    Asking Rhino for a mode by id is not enough: Rhino for Windows can hold an
    imported mode that it hands out by id yet neither lists nor shows, and a
    viewport set to such a mode falls back to Wireframe."""
    if mode_id is None or mode_id == System.Guid.Empty:
        return None
    for mode in Rhino.Display.DisplayModeDescription.GetDisplayModes():
        if mode.Id == mode_id:
            return mode
    return None


def held_mode(mode_id):
    """The mode Rhino hands out for this id, listed or not; None when it has none."""
    if mode_id is None or mode_id == System.Guid.Empty:
        return None
    try:
        return Rhino.Display.DisplayModeDescription.GetDisplayMode(mode_id)
    except Exception:
        return None


def imported_mode(path, returned_id=None):
    """The display mode this Rhino lists for the file `path`: looked up by the id
    the import returned, else by the id in the file. None when it is not listed."""
    for mode_id in (returned_id, mode_file_id(path)):
        mode = listed_mode(mode_id)
        if mode is not None:
            return mode
    return None


def import_direct(path):
    try:
        mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    except Exception:
        mode_id = None
    return imported_mode(path, mode_id)


def import_reencoded(path):
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
            mode = import_direct(temp_path)
            if mode is not None:
                return mode
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return None


def import_with_ironpython(path):
    """Runs the import in the IronPython engine, where it also works in the Rhino 8
    builds whose Python 3 engine cannot do it."""
    import shutil
    import tempfile
    folder = tempfile.mkdtemp(prefix="np-mode-")
    try:
        script = os.path.join(folder, "np_import_mode.py")
        literal = path.replace("\\", "\\\\").replace('"', '\\"')
        with open(script, "wb") as handle:
            handle.write(('# -*- coding: utf-8 -*-\nimport Rhino\n'
                          'Rhino.Display.DisplayModeDescription.ImportFromFile(u"{}")\n'
                          .format(literal)).encode("utf-8"))
        Rhino.RhinoApp.RunScript('_-RunPythonScript "{}"'.format(script), False)
        Rhino.RhinoApp.Wait()
    except Exception:
        pass
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return imported_mode(path)


def import_outside_undo(path):
    """Closes the undo record the script engine opened, then imports."""
    try:
        serial = sc.doc.CurrentUndoRecordSerialNumber
        if serial:
            sc.doc.EndUndoRecord(serial)
    except Exception:
        pass
    return import_direct(path)


def import_without_undo(path):
    """Imports with the document's undo recording switched off."""
    try:
        before = sc.doc.UndoRecordingEnabled
        sc.doc.UndoRecordingEnabled = False
    except Exception:
        return None
    try:
        return import_direct(path)
    finally:
        try:
            sc.doc.UndoRecordingEnabled = before
        except Exception:
            pass


def import_then_update(path):
    """Imports, then tells Rhino the mode has changed: a mode Rhino holds without
    listing it may be registered properly by that."""
    try:
        mode_id = Rhino.Display.DisplayModeDescription.ImportFromFile(path)
    except Exception:
        mode_id = None
    for candidate in (mode_id, mode_file_id(path)):
        held = held_mode(candidate)
        if held is None:
            continue
        try:
            Rhino.Display.DisplayModeDescription.UpdateDisplayMode(held)
        except Exception:
            pass
    return imported_mode(path, mode_id)


IMPORT_ROUTES = [
    ("as saved", import_direct),
    ("re-saved in another encoding", import_reencoded),
    ("through IronPython", import_with_ironpython),
    ("with the script's undo record closed", import_outside_undo),
    ("with undo recording switched off", import_without_undo),
    ("followed by an update of the mode", import_then_update),
]


def import_mode_file(path):
    """Imports a display mode .ini; returns the DisplayModeDescription or None."""
    for index, (label, route) in enumerate(IMPORT_ROUTES):
        mode = route(path)
        if mode is not None:
            if index:
                print("Display mode file '{}' was imported {}.".format(os.path.basename(path), label))
            return mode
    return None


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
    return ("File: {}\n({})\nRhino {} on {}.\n\n"
            "Tried it as saved, in other encodings, through IronPython, outside the undo record,\n"
            "with undo off and with an update afterwards; Rhino did not list the mode after any.\n"
            "Rhino 8 for Windows older than 8.13 has a bug here, so update Rhino first.\n"
            "Then run Display Modes > Check display mode import and send the report.\n\n"
            "To carry on now, import the modes by hand: Rhino Options (Settings on Mac) > View > "
            "Display Modes > Import, and pick each .ini file in\n{}\n"
            "The tools find the modes by name after that and stop trying to import them.").format(
                path, detail, Rhino.RhinoApp.Version, system, os.path.dirname(path))


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


def check_import():
    """Tries every import route on throwaway copies of a team mode and writes a
    report, for working out why a Rhino will not take the team display modes."""
    import datetime
    import json
    import shutil
    import tempfile
    import uuid
    DMD = Rhino.Display.DisplayModeDescription
    lines = ["NP display mode import check, {}".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))]
    system = "Windows" if Rhino.Runtime.HostUtils.RunningOnWindows else "Mac"
    lines.append("Rhino {} on {}; Python {}".format(Rhino.RhinoApp.Version, system, sys.version.split()[0]))
    lines.append("Install folder: {}".format(_INSTALL_ROOT))
    try:
        with open(os.path.join(_INSTALL_ROOT, "manifest.json"), "r") as handle:
            lines.append("NP tools version: {}".format(json.load(handle).get("version")))
    except Exception as ex:
        lines.append("NP tools version: unknown ({})".format(ex))
    try:
        lines.append("Undo: recording {}, open record {}".format(
            sc.doc.UndoRecordingEnabled, sc.doc.CurrentUndoRecordSerialNumber))
    except Exception as ex:
        lines.append("Undo: {}".format(ex))

    files = mode_files()
    lines.append("")
    lines.append("Team files:")
    for path in files:
        with open(path, "rb") as handle:
            raw = handle.read()
        file_id = mode_file_id(path)
        listed = listed_mode(file_id) is not None
        held = held_mode(file_id) is not None
        state = "listed" if listed else ("HELD BY ID BUT NOT LISTED (not in the menu)" if held else "not there")
        lines.append("  {}: {} bytes, starts with {}, mode in this Rhino: {}".format(
            os.path.basename(path), len(raw), " ".join("{:02x}".format(b) for b in raw[:4]), state))
    lines.append("Display modes in this Rhino: {}".format(
        ", ".join(sorted(m.EnglishName for m in DMD.GetDisplayModes()))))

    lines.append("")
    lines.append("Import routes, each on a throwaway copy:")
    source = files[0]
    text = read_mode_file(source)
    source_id = str(mode_file_id(source))
    source_name = mode_name_from_file(source)
    folder = tempfile.mkdtemp(prefix="np-mode-check-")
    probes = []

    def probe_file(label, encoding):
        new_id = str(uuid.uuid4())
        name = "NP Import Probe {}".format(len(probes) + 1)
        body = text.replace(source_id, new_id).replace("Name=" + source_name, "Name=" + name)
        path = os.path.join(folder, "probe {}.ini".format(len(probes) + 1))
        with open(path, "wb") as handle:
            handle.write(mode_file_bytes(body, encoding))
        probes.append(System.Guid(new_id))
        return path

    def run(label, route, encoding="plain text"):
        path = probe_file(label, encoding)
        try:
            mode = route(path)
            if mode is not None:
                result = "worked"
            elif held_mode(probes[-1]) is not None:
                result = "FAILED: Rhino holds the mode by id but does not list it"
            else:
                result = "FAILED: no mode at all"
        except Exception as ex:
            result = "ERROR {}".format(ex)
        lines.append("  {}: {}".format(label, result))
        return path, result

    try:
        run("direct, plain text file", import_direct)
        run("direct, UTF-8 with byte order mark", import_direct, "UTF-8 with a byte order mark")
        run("direct, UTF-16", import_direct, "UTF-16")
        again_path, first = run("direct, then the same file a second time (1st)", import_direct)
        if first == "worked":
            try:
                returned = DMD.ImportFromFile(again_path)
                still = DMD.GetDisplayMode(probes[-1]) is not None
                lines.append("  second import of the same file: returned {}, mode still there: {}".format(returned, still))
            except Exception as ex:
                lines.append("  second import of the same file: ERROR {}".format(ex))
        run("through IronPython", import_with_ironpython)
        run("with undo recording switched off", import_without_undo)
        run("followed by an update of the mode", import_then_update)
        # last: it closes the script's own undo record, which later routes would then run without
        run("with the script's undo record closed", import_outside_undo)
    finally:
        removed = 0
        for probe_id in probes:
            try:
                if held_mode(probe_id) is not None and DMD.DeleteDiplayMode(probe_id):
                    removed += 1
            except Exception:
                pass
        left = [m.EnglishName for m in DMD.GetDisplayModes() if m.EnglishName.startswith("NP Import Probe")]
        still_held = sum(1 for probe_id in probes if held_mode(probe_id) is not None)
        lines.append("Probe modes removed: {}; left in the list: {}; still held by id: {}".format(
            removed, ", ".join(left) or "none", still_held))
        shutil.rmtree(folder, ignore_errors=True)

    lines.append("")
    try:
        from System.Diagnostics import Process as _Process   # not "import System...": that would shadow System here
        # the process is "Rhino" on Windows and "Rhinoceros" on the Mac
        running = sum(len(_Process.GetProcessesByName(name)) for name in ("Rhino", "Rhinoceros"))
        lines.append("Rhino windows running on this computer right now: {}".format(running or "could not tell"))
    except Exception as ex:
        lines.append("Rhino windows running: {}".format(ex))
    try:
        with open(os.path.join(_INSTALL_ROOT, "_logs", "assembly_modes.log"), "r") as handle:
            history = [line.rstrip() for line in handle.readlines() if line.strip()][-25:]
        lines.append("Times the assembly tools found the modes gone and brought them back (latest last):")
        lines.extend("  " + line for line in history)
    except Exception:
        lines.append("The assembly tools have not recorded the modes going missing.")

    report = "\n".join(lines)
    saved_to = ""
    try:
        logs = os.path.join(_INSTALL_ROOT, "_logs")
        if not os.path.isdir(logs):
            os.makedirs(logs)
        report_path = os.path.join(logs, "display_mode_check.txt")
        with open(report_path, "w", encoding="utf-8") as handle:
            handle.write(report)
        saved_to = report_path
    except Exception as ex:
        saved_to = "(could not save: {})".format(ex)
    try:
        rs.ClipboardText(report)
        clip = "It is also on the clipboard: paste it into a message."
    except Exception:
        clip = ""
    print(report)
    rs.MessageBox("Display mode check finished.\n\nReport saved to:\n{}\n\n{}".format(saved_to, clip), 0, TITLE)


def menu_items():
    """Choices offered by the list dialog and by the NP Menu drawer."""
    files = mode_files()
    items = [IMPORT_PREFIX + mode_name_from_file(p) for p in files]
    if len(files) > 1:
        items.append(IMPORT_ALL_LABEL)
    items.append(SAVE_LABEL)
    if files:
        items.append(CHECK_LABEL)
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

    if choice == CHECK_LABEL:
        check_import()
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
