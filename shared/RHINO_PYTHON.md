# Rhino 8 Python runtime

NP tools target **Rhino 8** with the embedded **Python 3 (CPython)** environment used by:

- `RunPythonScript`
- `import rhinoscriptsyntax as rs`
- `import Rhino`

`run_np_launcher.py` and `scripts/python/*.py` are written for this environment (`.format()`, stdlib `urllib`, `json`, `zipfile`).

**IronPython 2.7 (Rhino 6/7 or legacy mode):** `np_deploy.py` uses `io.open` for UTF-8 files because builtin `open(encoding=...)` is not supported. Other scripts still need Rhino 8-style `import Rhino` / `rhinoscriptsyntax`.

**Confirm on each machine:** Rhino 8 → command `ScriptEditor` or `EditPythonScript` → check Python version shows 3.x.

Installers use **system Python 3** only for first-time file copy, not for running tools inside Rhino.
