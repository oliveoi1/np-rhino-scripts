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

## File encoding

The `.ini` files here are plain text **without a byte order mark**. Rhino for Mac exports
display modes as UTF-8 with that mark and reads anything; Rhino for Windows can fail on it
("Could not import display mode"), because the first line, the `[DisplayMode\<id>]` header,
is then not recognised. "Save one of my display modes to the team folder" re-saves the export
in the portable form, so do not export into this folder by hand from Rhino's Options. If a
file still fails, tools 19, 20 and 21 try it again as plain text and as UTF-16 before giving up,
and the error message then names the file, its first bytes and the Rhino version.
