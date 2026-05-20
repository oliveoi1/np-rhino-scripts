"""
NP Rhino Tools bootstrap.
Run from Rhino via alias NP or toolbar button.

Rhino 8: uses embedded CPython 3 with Rhino and rhinoscriptsyntax available.
"""

from __future__ import print_function

import os
import sys
import traceback

INSTALL_ROOT = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
SHARED_DIR = os.path.join(INSTALL_ROOT, "shared")
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

import np_deploy


def _message(text, title="NP Rhino Tools"):
    try:
        import rhinoscriptsyntax as rs
        rs.MessageBox(text, 0, title)
    except Exception:
        print("{}: {}".format(title, text))


def launch_np_launcher(install_root):
    launcher_path = os.path.join(install_root, "scripts", "python", "np_launcher.py")
    if not os.path.isfile(launcher_path):
        raise IOError("Launcher not found:\n{}".format(launcher_path))
    import Rhino
    command = '-_RunPythonScript "{}"'.format(launcher_path)
    return Rhino.RhinoApp.RunScript(command, False)


def main():
    install_root = np_deploy.get_install_root(__file__)
    np_deploy.ensure_runtime_folders(install_root)
    np_deploy.save_github_config_example(install_root)

    update_result = None
    try:
        update_result = np_deploy.check_and_update(install_root)
        if update_result.get("error") and not update_result.get("skipped"):
            _message(
                "Update check failed (using local tools):\n{}".format(update_result["error"]),
                "NP Update",
            )
        elif update_result.get("updated"):
            np_deploy.log_message(install_root, "Update applied: " + update_result.get("message", ""))
    except Exception:
        np_deploy.log_message(install_root, traceback.format_exc(), "ERROR")

    local_manifest = np_deploy.load_local_manifest(install_root) or {}
    launch_ok = False
    launch_error = None
    try:
        launch_ok = launch_np_launcher(install_root)
    except Exception as exc:
        launch_error = str(exc)
        np_deploy.log_message(install_root, traceback.format_exc(), "ERROR")

    if not launch_ok and launch_error:
        np_deploy.log_message(install_root, "Launch failed, attempting rollback", "WARN")
        try:
            np_deploy.restore_app_files_from_backup(install_root, local_manifest)
            launch_ok = launch_np_launcher(install_root)
            if launch_ok:
                _message("Previous version restored and launched.", "NP Rollback")
        except Exception:
            np_deploy.log_message(install_root, traceback.format_exc(), "ERROR")
            _message(
                "Could not launch NP tools.\n{}\nSee _logs/np_deploy.log".format(launch_error),
                "NP Error",
            )

    np_deploy.record_launch(install_root, success=bool(launch_ok), error=launch_error)


if __name__ == "__main__":
    main()
