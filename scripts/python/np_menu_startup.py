#! python 3
# -*- coding: utf-8 -*-
"""
Runs at Rhino startup (Options > General > 'Run these commands every time
Rhino starts'; NPP adds the line). Registers the NP Tools panel for this
session and reopens it if it was open last time. No update check here; NP
and NPP do that.
"""

import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ""
if THIS_DIR and THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)

import importlib

import np_menu

try:
    np_menu = importlib.reload(np_menu)
except Exception:
    pass

if __name__ == "__main__":
    np_menu.startup()
