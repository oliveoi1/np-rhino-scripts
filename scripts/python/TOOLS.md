# NP Rhino Tools — Quick Reference

Run tools from the **NP** launcher (`np_launcher.py`) or the **NPM** tool window (`np_menu.py`, see below). For full workflows and standards, use **Guide & Instructions** in the launcher (opens the [NP guide Google Doc](https://docs.google.com/document/d/1-wMRbW0fdt7HhVIuPh7oi6vFMNPt1Xmb1XPxvN63aVc/edit?tab=t.0)).

**Dimensions** below are listed in inch fractions where scripts use inch-based constants. Your Rhino template should use inches (or equivalent scaling) unless noted (e.g. flipper holes in mm).

**Launcher (not scripts):**
- **Guide & Instructions** — opens the Google Doc above.
- **Force Update** — reinstalls/refreshes NP tools from the deploy manifest.

**NP Menu (window)** — alias **NPM**, or the first row of the NP list. An Eto window that lists every tool by category (Joinery, Auto Inserts, Hardware, Blocks, Drawings + Annotation, Export, Templates) with short names and no numbers; the classic NP list keeps the numbered labels with a filter box (Enter runs the first match), a star to mark favourites, a Recent section, Guide and Force Update buttons, and the installed version in the footer. Tools whose first step is a list (Insert Block, Display Modes, Annotation Styles) open as a drawer inside the window: click the tool to show its choices, click a choice to run the tool with that choice already made, so its own list dialog is skipped. The filter box searches those choices too, so typing `screw` lists the four screws directly. It stays open while tools run, cancels a tool that is still waiting for input when you start another, and remembers favourites, recents, open drawers and its position in `_user_data/np_menu_state.json`. Both menus read the same `SCRIPT_CHOICES` table in `np_launcher.py`, so a tool added there appears in both; the window shows it under Other until it is placed in the `CATEGORIES` table in `np_menu.py`. `NP` creates the `NPM` alias the first time it runs.

---

### 01 - Extrude Curves

**What it does:** Extrudes closed planar curves straight downward into solid bands on material-specific extrusion layers.

**Dimensions:** Depth **3/4"** per extrusion.

**Usage:**
1. Choose **material** from the list (maps to `NP-Extrusions-*` layer).
2. Select **closed planar curves** to extrude.

**Requires:** Closed, planar curves.

**Blocks / layers:** No blocks; layers `NP-Extrusions`, `NP-Extrusions-SCMaple`, `NP-Extrusions-SCHPL`, `NP-Extrusions-RCMaple`, `NP-Extrusions-Acrylic`.

---

### 01a - Extrude Ply Bands

**What it does:** Extrudes each closed planar curve as **11 stacked bands** (alternating light/dark ply layers) for a total **3/4"** thickness.

**Dimensions:** Total **3/4"** (11 bands, each ~1/11 of total).

**Usage:**
1. Select **closed planar curves** (preselect allowed).

**Requires:** Closed, planar curves.

**Blocks / layers:** `NP-Extrusions-SC-LT` and `NP-Extrusions-SC-DK`.

---

### 02 - Dado Recess

**What it does:** Cuts a rectangular recess into a panel stack along each centerline (boolean difference from global top).

**Dimensions:** Width **3/8"**, depth **3/8"** (from global top of stack; small top proud offset ~0.01").

**Usage:**
1. Select **one closed solid** (or grouped stack) as the host.
2. Select **centerline curves** — one open line per recess.

**Requires:** Closed polysurface host(s); open curves along recess centers.

**Blocks / layers:** No block insert; uses `group_cut_utils` for stack top.

---

### 02 - Dado Tongue

**What it does:** Cuts a tongue pocket from four picked corner points (planar cutter extruded through the stack).

**Dimensions:** Cut depth **3/8"** below top; cutter raised **1/16"** above top before cut.

**Usage:**
1. Select **one closed solid** (or grouped stack) as the host.
2. Pick **four points** around the tongue outline (in order around the perimeter).

**Requires:** Closed polysurface host(s).

**Blocks / layers:** No block insert.

---

### 02b - Surface Recess

**What it does:** Shallow surface recess along closed planar curves (straight extrude down, boolean subtract).

**Dimensions:** Recess depth **1/32"** (plus **1/32"** safety raise during cut).

**Usage:**
1. Select **one closed solid** (or grouped stack) to subtract from.
2. Select **closed planar curves** for recess locations.

**Requires:** Closed polysurface host; closed planar curves.

**Blocks / layers:** No block insert.

---

### 02c - Engrave

**What it does:** Cuts a centred trench along selected centreline curve(s), then boolean-subtracts from a picked host stack (same cut style as dado tongue).

**Dimensions:** User-entered **width** × **depth**. First-run default is **3/8"** × **3/8"**. Values entered become the default for the next run (remembered in `_user_data/engrave_defaults.json`). Cut depth is measured below the global top of the stack; cutter is raised **1/16"** above the top for a clean boolean.

**Usage:**
1. Select **centreline curve(s)** (open or closed planar; preselect allowed).
2. Enter **width**, then **depth** (Enter keeps the current default).
3. Select **one closed solid** (or grouped stack) as the host.

**Requires:** Closed polysurface host(s); planar centreline curves. Straight lines use a rectangular box cutter; polylines/arcs/closed paths are offset by half-width on each side.

**Blocks / layers:** No block insert; uses `group_cut_utils` for stack top.

---

### 03a - Hole Insert Points Auto

**What it does:** Scans curves in a selection and places `hole_insert` blocks at small round closed loops.

**Dimensions:** Detects circles roughly **3/16"** to **3/8"** diameter (0.15–0.4" bbox).

**Usage:**
1. Select **curves in the area to scan** (preselect allowed).

**Requires:** Block `hole_insert` in file.

**Blocks / layers:** `hole_insert` on `NP-Construction - Setout`.

---

### 03b - Grub Screws + Holes

**What it does:** Drills holes at each `hole_insert` and places `grub_screw` hardware at the same location/orientation.

**Dimensions:** Hole diameter **1/4"**, depth **~5/8"** (0.6") from panel top.

**Usage:**
1. Select **`hole_insert` block instances**.
2. Select **one solid** from the target stack/group.

**Requires:** Blocks `hole_insert`, `grub_screw`; closed host solids.

**Blocks / layers:** Screws on `NP-Fittings`.

---

### 03c - Dimple Hole

**What it does:** Shallow dimple at each `hole_insert` (no hardware inserted).

**Dimensions:** Diameter **~3/16"** (0.184"), depth **1/8"** from global top.

**Usage:**
1. Select **`hole_insert` block instances**.
2. Select **one solid** from the target stack/group.

**Requires:** Block `hole_insert`; closed host solids.

**Blocks / layers:** No hardware insert.

---

### 03d - Custom Holes

**What it does:** Cuts user-sized holes at selected `hole_insert` blocks (no hardware inserted).

**Dimensions:** Presets: **Pilot** = **0.16"** through, **Bolt** = **1/4"** through. **Custom** lets you choose **Through** or a blind **Depth**, then enter **diameter**. Through cuts extend slightly below the selected stack bottom.

**Usage:**
1. Select **`hole_insert` block instances**.
2. Select **one solid** from the target stack/group.
3. Choose **Pilot**, **Bolt**, or **Custom**. Custom then asks for **Through** or **Depth**, followed by **diameter**.

**Requires:** Block `hole_insert`; closed host solids.

**Blocks / layers:** No hardware insert.

---

### 04a - Cam Inserts

**What it does:** Places oriented `caminsert` blocks at cam pocket circles (orange line points toward nearest pocket edge).

**Dimensions:** Cam circles ~**21/32"**–**15/16"** diameter (0.65–0.95" bbox).

**Usage:**
1. Select **cam circles and pocket outline curves** together.

**Requires:** Block `caminsert`; round closed cam loops + outline geometry in selection.

**Blocks / layers:** `caminsert` on `NP-Construction - Setout`.

---

### 04b - Cam Holes + Cams

**What it does:** Drills cam holes at each `caminsert` and inserts `cam` lock blocks.

**Dimensions:** Hole diameter **~25/32"** (0.787"), depth **~9/16"** (0.55") from panel top.

**Usage:**
1. Select **`caminsert` block instances**.
2. Select **one solid** from the target stack/group.

**Requires:** Blocks `caminsert`, `cam`; closed host solids.

**Blocks / layers:** `cam` on `NP-Fittings`.

---

### 05a - Flipper Insert Auto

**What it does:** Scans pocket curves and places oriented `flipper_insert` blocks (circle + tab geometry).

**Dimensions:** Pocket symbols ~**3/8"**–**1-1/4"** bbox range.

**Usage:**
1. Select **curves in the area to scan** (preselect allowed).

**Requires:** Block `flipper_insert`; valid flipper pocket linework.

**Blocks / layers:** `flipper_insert` on `NP-Construction - Setout`.

---

### 05b - Flipper Holes + Flippers

**What it does:** Drills holes at `flipper_insert` locations and inserts `flipper_receptacle` (optional `flipper_pin`).

**Dimensions:** Hole **15 mm** diameter, **10.5 mm** depth (~**19/32"** / **~7/16"**).

**Usage:**
1. Confirm blocks exist (script checks).
2. Answer **Yes/No** for optional `flipper_pin`.
3. Select **`flipper_insert` block instances**.
4. Select **one solid** from the target stack/group.

**Requires:** Blocks `flipper_insert`, `flipper_receptacle`, and `flipper_pin` if pins requested.

**Blocks / layers:** Hardware on `NP-Fittings`.

---

### 05c - Shelf Holes

**What it does:** Drills shelf pin holes at small round marker circles.

**Dimensions:** Hole diameter **1/5"** (0.2"); depth **1/2"** (Regular) or **3/4"** (Full) — chosen at prompt. Markers ~**3/16"**–**5/16"** diameter.

**Usage:**
1. Choose depth: **Yes** = Regular **1/2"**, **No** = Full **3/4"**.
2. Select **small circles** to drill.
3. Select **one solid** from the target stack/group.

**Requires:** Closed host solids; small round closed curves.

**Blocks / layers:** No block insert.

---

### 06a - Castor Insert

**What it does:** Replaces each `castor_insert` setout block with small castor hardware `ACC-CST-SM` (same position/orientation, 180° flip on local X).

**Usage:**
1. Select **area containing `castor_insert` block instances** (preselect allowed).

**Requires:** Blocks `castor_insert`, `ACC-CST-SM`.

**Blocks / layers:** Hardware placement from insert transform.

---

### 06b - Castor Small Insert + Holes

**What it does:** Drills castor mounting holes and inserts `ACC-CST-SM` at each `castor_insert`.

**Dimensions:** Holes **1/4"** diameter; spacing **1-1/4"**; slight overshoot through stack.

**Usage:**
1. Select **`castor_insert` block instances**.
2. Select **one solid** from the target stack/group.

**Requires:** Blocks `castor_insert`, `ACC-CST-SM`; closed host solids.

**Blocks / layers:** Uses stack top/bottom for through holes.

---

### 06b - Castor Large Insert + Holes

**What it does:** Drills large castor mounting holes and inserts `ACC-CST-LG` at each `castor_insert`.

**Dimensions:** Holes **3/8"** diameter; spacing **~2-15/16"** × **~1-25/32"** (2.950" × 1.770"); overshoot through stack.

**Usage:**
1. Select **`castor_insert` block instances**.
2. Select **one solid** from the target stack/group.

**Requires:** Blocks `castor_insert`, `ACC-CST-LG`; closed host solids.

**Blocks / layers:** Uses stack top/bottom for through holes.

---

### 07 - Glides

**What it does:** Places `glide` blocks at each `glide_insert` (offset **3/8"** down in Z from insert).

**Dimensions:** Z offset **3/8"** below insert point.

**Usage:**
1. Select **`glide_insert` block instances**.

**Requires:** Blocks `glide_insert`, `glide`.

**Blocks / layers:** `glide` on `NP-Fittings`.

---

### 17 - Explode Fittings

**What it does:** Pulls selected fitting blocks (screws, grub screws, cams, anything inserted with its axis on local Z) straight out of their face along that axis, for exploded assembly diagrams. Optionally draws a dashed leader from the exploded fitting back to the hole centre on the face.

**Dimensions:** User-entered **distance** along the fitting axis (first-run default **2"**). Distance, Move/Copy and the leader choice are remembered in `_user_data/explode_fittings_defaults.json`.

**Usage:**
1. Select **fitting block instances** (preselect allowed).
2. Enter the **distance**.
3. Choose **Move** or **Copy** (Copy leaves the model intact and adds exploded copies).
4. Choose **Yes** / **No** for the dashed leader.

**Requires:** Block instances whose insertion point is on the face with the shank along local -Z (all NP fitting blocks).

**Blocks / layers:** Leaders on `NP-Assembly - Leaders` with a `Dashed` linetype (added to the file if missing). Fittings keep their own layer.

---

### 18 - Annotation Styles

**What it does:** Applies one dimension style to every annotation (dimensions, leaders, text) in the document, or to the selected ones, clears per-object style overrides, makes that style current, and can delete the dimension styles that are then unused. Use it to make drawings from different people match.

**Dimensions:** None. The chosen style and the purge choice are remembered in `_user_data/annotation_styles_defaults.json`.

**Usage:**
1. Pick the **style** from the list. Styles in the team template (`templates/NP_Annotation_Styles.3dm`) appear as **Team template: name** and are imported on the fly; a same-named style in the file is updated to match.
2. Choose **All** or **Selected**.
3. Choose whether to **delete unused styles** afterwards (only when applying to All).

**Team template:** choose **Save a style to the team template...** to write one of the document's styles into `templates/NP_Annotation_Styles.3dm`, then commit and push it.

**Requires:** Annotations inside block definitions are not changed.

---

### 19 - Display Modes

**What it does:** Imports shared display modes (for example *NP Assembly*, *NP Render*) from `templates/display_modes/*.ini` into this Rhino, or saves one of your current display modes into that folder for the team.

**Dimensions:** None.

**Usage:**
1. Choose **Import: name** (or **Import all team display modes**). A mode with the same id already in Rhino is updated in place, so re-importing refreshes it rather than duplicating it.
2. Say **Yes** to apply it to the active viewport.
3. **Save one of my display modes to the team folder...** exports a mode as `.ini`; commit and push the file so everyone receives it.

**Requires:** `.ini` files in `templates/display_modes/` (the folder ships with the install).

---

### Insert Block

**What it does:** Opens a list of hardware and marker blocks from `blocks/NP_Rhino_Hardware.3dm`. The point you pick is the block's saved insertion point (the end of the line in the library). Each block is placed on its layer: SKU insertion point on `NP-SKU_Insertion`, block insertion point on `NP-Setout`, markers on `NP-Construction - Setout`, fittings on `NP-Fittings`, logo blocks on `NP-Panel-Logo`. Fittings include four #8 wood screws: **1-1/4"** (two flat 3/4" plies, `screw_1-1-4in_pan` / `screw_1-1-4in_csk`) and **1-1/2"** (a piece screwed into another on edge, `screw_1-1-2in_pan` / `screw_1-1-2in_csk`), each as a **pan head** that sits proud or a **countersunk** head that finishes flush. The insertion point is the surface point in both cases (underside of a pan head, top of a countersunk head) and the shank points down -Z. Screws are inserted **perpendicular to the face under the picked point** (a flat face, a hole rim, or a hole centre, found within 1/2" of the pick, including faces inside block instances); with nothing under the point they insert upright on world Z.

**Usage:**
1. Choose **Insert Block**.
2. Choose the item, for example **SKU Insertion Point**.
3. Pick points. Press Enter when done.

**Requires:** `blocks/NP_Rhino_Hardware.3dm` next to the scripts.

---

### Create / Redefine Block + Add Instance

**What it does:** Creates a new block from geometry + name text, or redefines an existing block with the same name. When redefining, existing instances are restored and an additional instance is inserted at the chosen insertion point.

**Usage:**
1. Select **text** for the block name.
2. Select **objects** to include in the block (filtered to allowed NP layers).
3. Pick **insertion point**.
4. If that block name already exists, the definition is replaced, existing instances are updated, and one more copy is inserted.

**Requires:** Valid name text; geometry on allowed layers.

**Blocks / layers:** Additional/new instance on `NP-Furniture`.

---

### Create / Redefine Block Using SKU Insertion Point

**What it does:** Same as **Create / Redefine Block + Add Instance**, but if the selected objects include a `SKUInsertionPt` block, that helper block's insertion point is used automatically.

**Usage:** Same as **Create / Redefine Block + Add Instance**. Include a `SKUInsertionPt` helper block in the selection to avoid manually picking the insertion point.

**Requires:** Valid name text; geometry on allowed layers; optional `SKUInsertionPt` helper block.

---

### Create / Redefine Block

**What it does:** Creates a new block from selected geometry. If that name already exists, every placed instance is replaced with the new geometry. The selected objects are consumed into the block, and one instance is placed at the insertion point so that geometry stays where it was modeled.

**Usage:**
1. Select **text** for the block name.
2. Select **objects** to define the block.
3. Pick **insertion point**.

**Requires:** Allowed layers: `NP-Extrusions*`, `NP-Furniture`, `NP-Fittings`, `NP-SKU_Insertion`, `NP-Setout`.

**Blocks / layers:** Instance on `NP-Furniture` when newly created; existing instances restored when redefining.

---

### 09 - Plan View

**What it does:** Adds plan labels for top-level block instances (name, or name × qty).

**Dimensions:** Label height **1"**; offset **1"** from bbox corner.

**Usage:**
1. Select **top-level block instances** to label.

**Requires:** Block instances in plan view.

**Blocks / layers:** Labels on `NP-Text`.

---

### 10 - Logo Cut

**What it does:** Extrudes logo curves (straight **1/8"**, both sides, solid) and boolean-subtracts from host panel(s).

**Dimensions:** Extrusion **1/8"** total (**1/16"** each side of curve plane).

**Usage:**
1. Select **one closed solid** (panel body from target stack/group).
2. Select **planar logo curves** (open or closed; self-intersecting ok).

**Requires:** Closed polysurface host; planar curves.

**Blocks / layers:** No block insert.

---

### 11 - Export Blocks to SketchUp

**What it does:** Exports each selected block instance to a `.skp` file named after the block; insertion point moved to origin in export.

**Usage:**
1. Select **block instances** to export.
2. Choose **output folder** in the file dialog.

**Requires:** SketchUp export available in Rhino.

**Blocks / layers:** N/A (exports geometry only).

---

### 11a - Export Blocks to Rhino

**What it does:** Exports each selected block instance to an individual `.3dm` file named after the block; insertion point moved to origin in export.

**Usage:**
1. Select **block instances** to export.
2. Choose **output folder** in the file dialog.

**Requires:** Rhino `.3dm` export.

**Blocks / layers:** N/A (exports geometry only).

---

### 12 - Zero SKU Insertion Z

**What it does:** Moves selected block instances vertically so nested `SKUInsertionPt` (or block insertion point) lands at **Z = 0**; X/Y unchanged.

**Usage:**
1. Select **block instances** to align.

**Requires:** Blocks may contain nested `SKUInsertionPt` definition (falls back to instance insertion point).

**Blocks / layers:** N/A.

---

### 13 - Bounding Dimensions

**What it does:** Draws a best-fit plan bounding rectangle, aligned length/width dimensions, optional area leader for closed planar curves, and optional Z height leader.

**Dimensions:** Uses current model units; dimensions are shown with **3 decimal places** via temporary dim style `NP_TEMP_3DEC`.

**Usage:**
1. Select **one object** or block instance to dimension.

**Requires:** Object geometry on allowed NP layers, or a block instance containing allowed geometry.

**Blocks / layers:** Creates temporary dimensions/annotation on `NP-temporary` and groups them as `NP_temporary_group`.

---

### 14 - Numbered Dots

**What it does:** Places sequential Rhino text dots. Starts at the chosen number, then increments by one after every click.

**Dimensions:** Text dot annotation only; no model geometry size change.

**Usage:**
1. Enter a **start number** (default **1**).
2. Click each dot location.
3. Press **Enter/Esc** to finish.

**Requires:** None.

**Blocks / layers:** Dots on `NP-Annotation`.

---

### 16 - Snapshot 2D Export

**What it does:** Restores each chosen snapshot and runs Make2D with Projection set to **View**, so the file is only the view on screen. Other settings: properties from the input objects, tangent edges, scene silhouettes, no hidden lines, grouped output, layer `2d`. The drawing is fitted onto the page. The 2D curves are removed from the model after export.

**Usage:**
1. Choose **Adobe Illustrator (.ai)**, **EPS (.eps)**, or **PDF (.pdf)**.
2. Select the snapshots.
3. Choose the folder.

**Requires:** Snapshots saved in the current file.

**Blocks / layers:** Make2D output uses layer `2d` and is deleted after the file is written. The model is left on the last restored snapshot.
