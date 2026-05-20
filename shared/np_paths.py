"""Add install shared/ and scripts/python/ to sys.path for NP tool imports."""

import os
import sys


def setup_from_script_file(script_file):
    script_dir = os.path.dirname(script_file) if script_file else ""
    install_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    shared_dir = os.path.join(install_root, "shared")
    for path in (shared_dir, script_dir):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    return install_root, shared_dir, script_dir
