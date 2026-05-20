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
    import np_deploy
except ImportError:
    np_deploy = None


SCRIPT_CHOICES = [
    ("01 - Extrude Curves", "01 extrude_curves.py"),
    ("01a - Extrude Ply Bands", "01a_extrude_ply_bands.py"),
    ("02 - Dado Recess", "02 dado_recess.py"),
    ("02 - Dado Tongue", "02 dado_tongue.py"),
    ("02b - Surface Recess", "02b Surface recess.py"),
    ("03a - Hole Insert Points Auto", "03a hole_insertpoints_auto.py"),
    ("03b - Grub Screws + Holes", "03b grub_screws_and_holes.py"),
    ("03c - Dimple Hole", "03c dimple_hole.py"),
    ("04a - Cam Inserts", "04a cam_inserts.py"),
    ("04b - Cam Holes + Cams", "04b cam_holes_+_cams.py"),
    ("05a - Flipper Insert Auto", "05a flipper_insert_auto.py"),
    ("05b - Flipper Holes + Flippers", "05b flipper_holes_+flippers.py"),
    ("05c - Shelf Holes", "05c shelf_holes.py"),
    ("06a - Castor Insert", "06a castor_insert.py"),
    ("06b - Castor Small Insert + Holes", "06b castor_(SM)_insert_+_holes.py"),
    ("06b - Castor Large Insert + Holes", "06b castor_(LG)_insert_+_holes.py"),
    ("07 - Glides", "07 Glides.py"),
    ("08a - Create Block 1st", "08a create_block 1st.py"),
    ("08a - Create Block 1st Copy", "08a create_block 1st copy.py"),
    ("08b - Create Block", "08b create_block.py"),
    ("09 - Plan View", "09 plan view.py"),
    ("10 - Logo Cut", "10 logo_cut.py"),
    ("11 - Export Blocks to SketchUp", "11 export_blocks_to_skp.py"),
]


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


def run_script_file(script_filename):
    script_dir = os.path.dirname(__file__) if "__file__" in globals() else ""
    script_path = os.path.join(script_dir, script_filename)

    if not os.path.isfile(script_path):
        rs.MessageBox("Script file not found:\n{}".format(script_path), 0, "NP Launcher")
        return False

    command = '-_RunPythonScript "{}"'.format(script_path)
    return Rhino.RhinoApp.RunScript(command, False)


def main():
    title = get_launcher_title()
    labels = [label for label, _ in SCRIPT_CHOICES]
    selected = rs.ListBox(labels, title, "NP Launcher")
    if not selected:
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
