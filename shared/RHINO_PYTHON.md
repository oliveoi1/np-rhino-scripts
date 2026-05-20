# Rhino 8 Python runtime

NP tools target **Rhino 8** with the embedded **Python 3 (CPython)** environment used by:

- `RunPythonScript`
- `import rhinoscriptsyntax as rs`
- `import Rhino`

`run_np_launcher.py` and `scripts/python/*.py` are written for this environment (`.format()`, stdlib `urllib`, `json`, `zipfile`).

**Not supported:** IronPython 2.7 (Rhino 6/7 legacy). If a machine still uses legacy Python in Rhino, these scripts may fail on syntax or imports.

**Confirm on each machine:** Rhino 8 → command `ScriptEditor` or `EditPythonScript` → check Python version shows 3.x.

Installers use **system Python 3** only for first-time file copy, not for running tools inside Rhino.
