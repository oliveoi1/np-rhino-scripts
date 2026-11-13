# Team display modes

Rhino display mode exports (`.ini`) shared across the team.

- `NP Assembly.ini` — cartoon look for assembly instructions: off-white parts (RGB 245, 242, 235),
  2 px dark grey edges (RGB 40, 40, 40), no isocurves, white background, flat ambient-occlusion
  lighting without shadows. Built on the Shaded pipeline (a copy of Arctic) so it can also be
  assigned to single objects.
- `NP Assembly - Active.ini` — the same look in orange (RGB 232, 128, 58) for the piece being placed.
- `NP Assembly - Fittings.ini` — flat dark grey (RGB 120, 120, 120) without edges, for screws and hardware.
- `NP Assembly - Arrows.ini` — green (RGB 112, 190, 72) with dark edges, for the arrows from **21 - Assembly Symbols**.
- `NP Assembly - Glue.ini` — pale glue yellow (RGB 245, 225, 130) without edges, for glue beads.
- `NP Assembly - Cross.ini` — red (RGB 222, 80, 64) for the cross icon.
- `NP Assembly - Blanket.ini` — dark blue (RGB 56, 66, 96) for the moving blanket.
  **20 - Assembly Steps** and **21 - Assembly Symbols** import them as needed.

- **Import** them in Rhino with **19 - Display Modes** (Templates section of the NP menu).
- **Add or update** one from Rhino with the same tool: "Save one of my display modes to the team folder",
  then commit and push the `.ini` file.

Importing a mode whose id already exists updates it in place, so re-importing after a
change refreshes everyone's copy rather than creating duplicates.

## If a mode will not import

Two things have gone wrong with these files, and the tools work around both:

- **Encoding.** The `.ini` files here are plain text **without a byte order mark**. Rhino for Mac
  exports display modes as UTF-8 with that mark and reads anything; a reader that takes the mark for
  text no longer recognises the first line, the `[DisplayMode\<id>]` header. "Save one of my display
  modes to the team folder" re-saves the export in the portable form, so do not export into this
  folder by hand from Rhino's Options.
- **Script engine.** In Rhino 8 for Windows before 8.13, importing a display mode from a Python 3
  script silently did nothing (McNeel RH-83960). Updating Rhino cures it.

Tools 19, 20 and 21 try an import four ways: as saved, in other encodings, through a small
IronPython script, and with the script's undo record closed. If all fail, the message names the
file, its first bytes and the Rhino version. **19 - Display Modes → Check display mode import
(report)** tests each route on throwaway copies and writes the result to
`_logs/display_mode_check.txt` and the clipboard; send that report along with the problem.

**To carry on without waiting for a fix, import the modes by hand.** In Rhino open Options
(Settings on Mac) > View > Display Modes, press Import, and pick each `.ini` file in this folder
(on a team install: `Documents/NP Rhino Scripts/templates/display_modes`). There are seven: `NP
Assembly` and its six colours. Once they are in the display mode list the tools find them by name
and no longer try to import anything. If Rhino's own Import refuses the files too, say so with the
report: that points at the files, not at the script.
