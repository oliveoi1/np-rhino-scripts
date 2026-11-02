# Team display modes

Rhino display mode exports (`.ini`) shared across the team, for example
`NP Assembly.ini` or `NP Render.ini`.

- **Import** them in Rhino with **19 - Display Modes** (Templates section of the NP menu).
- **Add or update** one from Rhino with the same tool: "Save one of my display modes to the team folder",
  then commit and push the `.ini` file.

Importing a mode whose id already exists updates it in place, so re-importing after a
change refreshes everyone's copy rather than creating duplicates.
