import os
import sys
import Rhino
import rhinoscriptsyntax as rs

THIS_DIR = os.path.dirname(__file__) if "__file__" in globals() else ""
INSTALL_ROOT = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
SHARED_DIR = os.path.join(INSTALL_ROOT, "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

try:
    import importlib
except ImportError:
    importlib = None

try:
    import np_deploy
    try:
        if importlib and hasattr(importlib, "reload"):
            np_deploy = importlib.reload(np_deploy)
        else:
            reload(np_deploy)  # noqa: F821 - IronPython 2.7
    except Exception:
        pass
except ImportError:
    np_deploy = None


SCRIPT_CHOICES = [
    ("NP Menu (panel)", "np_menu.py"),
    ("01 - Extrude Curves", "01 extrude_curves.py"),
    ("01a - Extrude Ply Bands", "01a_extrude_ply_bands.py"),
    ("02 - Dado Recess", "02 dado_recess.py"),
    ("02 - Dado Tongue", "02 dado_tongue.py"),
    ("02b - Surface Recess", "02b Surface recess.py"),
    ("02c - Engrave", "02c engrave.py"),
    ("03a - Hole Insert Points Auto", "03a hole_insertpoints_auto.py"),
    ("03b - Grub Screws + Holes", "03b grub_screws_and_holes.py"),
    ("03c - Dimple Hole", "03c dimple_hole.py"),
    ("03d - Custom Holes", "03d custom_holes.py"),
    ("04a - Cam Inserts", "04a cam_inserts.py"),
    ("04b - Cam Holes + Cams", "04b cam_holes_+_cams.py"),
    ("05a - Flipper Insert Auto", "05a flipper_insert_auto.py"),
    ("05b - Flipper Holes + Flippers", "05b flipper_holes_+flippers.py"),
    ("05c - Shelf Holes", "05c shelf_holes.py"),
    ("06a - Castor Insert", "06a castor_insert.py"),
    ("06b - Castor Small Insert + Holes", "06b castor_(SM)_insert_+_holes.py"),
    ("06b - Castor Large Insert + Holes", "06b castor_(LG)_insert_+_holes.py"),
    ("07 - Glides", "07 Glides.py"),
    ("Insert Block", "15 insert_block.py"),
    ("Create / Redefine Block", "create_or_redefine_block.py"),
    ("Create / Redefine Block + Add Instance", "create_or_redefine_block_and_insert_copy.py"),
    ("Create / Redefine Block Using SKU Insertion Point", "create_or_redefine_block_from_sku_insert_point.py"),
    ("09 - Plan View", "09 plan view.py"),
    ("10 - Logo Cut", "10 logo_cut.py"),
    ("11 - Export Blocks to SketchUp", "11 export_blocks_to_skp.py"),
    ("11a - Export Blocks to Rhino", "11a export_blocks_to_3dm.py"),
    ("12 - Zero SKU Insertion Z", "12 zero_sku_insertion_z.py"),
    ("13 - Bounding Dimensions", "13 bounding_dimensions.py"),
    ("14 - Numbered Dots", "14 numbered_dots.py"),
    ("16 - Snapshot 2D Export", "16 snapshot_2d_export.py"),
    ("17 - Explode Fittings", "17 explode_fittings.py"),
    ("18 - Annotation Styles", "18 annotation_styles.py"),
    ("19 - Display Modes", "19 display_modes.py"),
]

GUIDE_LABEL = "Guide & Instructions"
GUIDE_URL = (
    "https://docs.google.com/document/d/1-wMRbW0fdt7HhVIuPh7oi6vFMNPt1Xmb1XPxvN63aVc/edit?tab=t.0"
)
FORCE_UPDATE_LABEL = "Force Update"


def get_launcher_title():
    version = "unknown"
    updated = "unknown"
    if np_deploy:
        try:
            root = np_deploy.get_install_root(INSTALL_ROOT)
            version, updated = np_deploy.get_version_display(root)
        except Exception:
            pass
    else:
        manifest_path = os.path.join(INSTALL_ROOT, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                import json
                with open(manifest_path, "r") as handle:
                    data = json.load(handle)
                version = data.get("version", version)
                updated = data.get("updated", updated)
            except Exception:
                pass
    return "NP Rhino Tools\nVersion: {}\nUpdated: {}".format(version, updated)


def open_guide_url():
    """Open GUIDE_URL in the default browser (Rhino IronPython-safe)."""
    url = GUIDE_URL
    errors = []

    # 1) macOS: os.system + open (works when subprocess/webbrowser do not)
    try:
        import sys
        if sys.platform == "darwin":
            status = os.system("open " + repr(url))
            if status == 0:
                return
            errors.append("macOS open exit {}".format(status))
    except Exception as ex:
        errors.append("macOS open: {}".format(ex))

    # 2) Rhino built-in command
    try:
        cmd = '_-OpenURL "{}" _Enter'.format(url.replace('"', '\\"'))
        Rhino.RhinoApp.RunScript(cmd, False)
        return
    except Exception as ex:
        errors.append("Rhino OpenURL: {}".format(ex))

    # 3) Windows default handler
    try:
        import sys
        if sys.platform.startswith("win"):
            os.startfile(url)
            return
    except Exception as ex:
        errors.append("startfile: {}".format(ex))

    # 4) .NET Process (IronPython)
    try:
        import clr
        clr.AddReference("System")
        from System.Diagnostics import Process
        import sys
        if sys.platform == "darwin":
            Process.Start("open", url)
        else:
            Process.Start(url)
        return
    except Exception as ex:
        errors.append("Process.Start: {}".format(ex))

    # 5) subprocess
    try:
        import subprocess
        import sys
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
            return
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
            return
    except Exception as ex:
        errors.append("subprocess: {}".format(ex))

    # 6) webbrowser (return value unreliable on macOS; still try)
    try:
        import webbrowser
        webbrowser.open(url)
        return
    except Exception as ex:
        errors.append("webbrowser: {}".format(ex))

    detail = "\n".join(errors) if errors else "unknown"
    rs.MessageBox(
        "Could not open the guide in a browser. Copy this URL:\n\n{}\n\n({})".format(
            url, detail
        ),
        0,
        "NP Guide",
    )


def run_force_update():
    if not np_deploy:
        rs.MessageBox("Update module not available.", 0, "NP Update")
        return
    install_root = np_deploy.get_install_root(INSTALL_ROOT)
    result = np_deploy.check_and_update(install_root, force=True)
    lines = []
    if result.get("updated"):
        lines.append("Update installed successfully.")
    elif result.get("error"):
        lines.append("Update failed:")
        lines.append(result["error"])
    else:
        lines.append(result.get("message") or "No changes.")
    rs.MessageBox("\n".join(lines), 0, "NP Force Update")


def run_script_file(script_filename):
    script_dir = os.path.dirname(__file__) if "__file__" in globals() else ""
    script_path = os.path.join(script_dir, script_filename)

    if not os.path.isfile(script_path):
        rs.MessageBox("Script file not found:\n{}".format(script_path), 0, "NP Launcher")
        return False

    command = '-_RunPythonScript "{}"'.format(script_path)
    return Rhino.RhinoApp.RunScript(command, False)


def ensure_menu_alias():
    """Give users the NPP alias for the tool panel the first time they run NP."""
    if not np_deploy or not hasattr(np_deploy, "ensure_command_alias"):
        return
    try:
        np_deploy.ensure_command_alias("NPP", np_deploy.build_np_menu_alias_command(INSTALL_ROOT))
    except Exception:
        pass


def main():
    ensure_menu_alias()
    title = get_launcher_title()
    labels = [GUIDE_LABEL]
    labels.extend(label for label, _ in SCRIPT_CHOICES)
    labels.append(FORCE_UPDATE_LABEL)
    selected = rs.ListBox(labels, title, "NP Launcher")
    if not selected:
        return

    if selected == GUIDE_LABEL:
        open_guide_url()
        return

    if selected == FORCE_UPDATE_LABEL:
        run_force_update()
        return

    selected_file = None
    for label, filename in SCRIPT_CHOICES:
        if label == selected:
            selected_file = filename
            break

    if not selected_file:
        rs.MessageBox("Could not resolve selected script.", 0, "NP Launcher")
        return

    ok = run_script_file(selected_file)
    if not ok:
        rs.MessageBox("Failed to run script:\n{}".format(selected_file), 0, "NP Launcher")


if __name__ == "__main__":
    main()
