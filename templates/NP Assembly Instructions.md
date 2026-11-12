# NP assembly instructions — how to make the step images

Cartoon-style pictures of a product going together, straight from Rhino: the whole
piece in off-white with dark outlines, the part being placed in orange.

## One-time setup (two minutes)

1. Run **Force Update** from the NP launcher or the NP Tools panel, so you have
   `20 - Assembly Steps` and the two display modes in `templates/display_modes`.
2. Open any model and run **Assembly Steps → Highlight selected piece** once. It
   imports the display modes `NP Assembly`, `NP Assembly - Active` and
   `NP Assembly - Fittings` into your
   Rhino. (Or import them with **19 - Display Modes**.) They now appear in the
   viewport's display mode list like Shaded or Arctic.

The colours, line weights and background all live in those two modes, so the
pictures look the same on everyone's machine. Do not edit layer colours or blocks
for the pictures.

## Each step

1. **Set up the view.** Perspective viewport, camera where you want it. Save it as a
   named view (`NamedView`) the first time and restore it for every step so all
   pictures line up.
2. **Position the parts.** Pull the piece being placed out along the direction it
   goes in. Capture (step 5) saves the layout as a snapshot, so you can come back
   to it.
3. **Highlight.** Select the piece (a block instance is fine) and run
   **Assembly Steps → Highlight selected piece**. It turns orange, the rest turns
   off-white, and the viewport switches to `NP Assembly`. Highlighting a new piece
   restores the previous one.
4. **Arrows and glue.** **Assembly Symbols** (next to Assembly Steps in the panel)
   makes them as small solids that keep their colour in the drawing:
   - **Push / move arrow**: click what the arrow points at, then move the mouse to
     the side it comes from and click. The arrow has a set length and snaps to the
     model's axes; `Length`, `Width`, `Gap` and `Plane` on the command line change
     the size and which plane it lies flat in, and are remembered.
   - **Rotate arrow (screw)**: click the screw, cam or grub screw; two curved green
     arrows appear above it, Tighten or Loosen. It also works on a fitting that sits
     inside a panel block: click the fitting itself, not the bare panel.
   - **Glue bead**: select a curve or click along the joint; a pale yellow bead with
     round ends, on its own layer `NP-Assembly - Glue`.
   - **Tool call-out**: a flat icon: glue bottle, screwdriver bit, rubber mallet,
     hammer, green tick or red cross. For the four tools, click where the tip (or the
     striking face) goes, then click where the body or handle should lie, and the
     icon turns to match; Enter instead of the second click gives the standard
     orientation. Each is one group; scale or move it like any object.
   - **Moving blanket**: for the "clean surface" step. Press Enter to fit it under
     everything in view, or click two corners. Dark blue with a quilt pattern.
   Put step numbers in with `TextDot` or the annotation styles from
   **18 - Annotation Styles**. The symbols can stay where they are: Capture notes
   which symbols were visible for the step, and Restore step shows only those and
   hides the rest. (A snapshot alone would not do this, since it knows nothing
   about symbols made after it was saved.)
5. **Capture.** **Assembly Steps → Capture step**. Accept the step number (it offers
   the next free one) and the scale (3 = three times the viewport, crisp at print
   size). The PNG lands in an `Assembly Steps` folder next to the model, named
   `<model> step 01.png` and so on. The step is also saved in the file as the
   snapshot `Assembly step 01` (positions, visibility and view) together with a
   note of which pieces were orange and which symbols were showing. Save the model
   so the snapshots are kept.
6. **Clear.** **Assembly Steps → Clear highlight** puts the original piece back.
   If you moved or rotated the orange piece while it was highlighted (flipping a part upside down, say), the original follows it.

## Steps side by side instead

If you would rather see every step at once, lay them out in a row:

1. Build and capture step 1 as above.
2. Select the whole stage (or just press Enter for everything visible) and run
   **Assembly Steps → Copy stage**. Give a distance (it suggests one a little
   wider than the stage; `Direction` picks Right, Left, Forward or Back, `Symbols`
   chooses whether the arrows and glue come along, normally they stay). The copy
   lands that far from the original and the camera moves the same distance, so the
   picture looks identical but you are now looking at the copy, which is selected.
   That camera is saved: after orbiting around to work on the stage, **Assembly
   Steps → Back to stage view** returns to it without moving any pieces.
3. The copy is clean: the orange piece comes across as the real part, in the pose
   you left it. The stage you left behind keeps its orange piece as a plain orange
   object, so the row reads as a storyboard.
4. Highlight the next piece in the copy, add symbols, **Capture step** with the next
   number, then **Copy stage** again. Capture saves the camera with each
   step, so Restore step and Re-capture all still work; nothing needs hiding,
   because the other stages are out of frame.

## When the assembly changes

- Fix the model, then run **Assembly Steps → Re-capture all steps**. Every step
  snapshot is restored in turn, its highlight put back, and all the PNGs are
  written again with the same names.
- To rework one step: **Assembly Steps → Restore step...**, pick it, move things
  or change the highlight, then **Capture step** with the same number. That
  replaces the image and the snapshot.
- The Snapshots panel shows the same `Assembly step` entries; restoring one there
  gives you the positions but not the orange piece or the right symbols, so prefer
  **Restore step...**. After a restore, **Show all symbols** brings every hidden
  symbol back if you want them all on screen again.

## Good to know

- **One construction plane for all steps.** A snapshot keeps the viewport's CPlane
  with the view. If you change the CPlane for one job (to flip a part, say) it would
  stay in that step and the view would orbit differently from then on. So the file
  remembers the plane from your first capture, and **Capture step** and **Copy stage** put it back each time. To change it on purpose, set the CPlane you want
  and run **Assembly Steps → Use current CPlane for all steps**, then **Re-capture
  all steps** to bring the earlier steps onto it. The pictures do not change.

- Screws and other hardware on the `NP-Fittings` layer come out dark grey in the
  captures (a third mode, `NP Assembly - Fittings`). On screen they stay off-white;
  only the saved picture swaps them.

- Highlight works by adding a plain copy of the piece's solids on the layer
  `NP-Assembly - Highlight` and hiding the original. Rhino cannot give a block
  instance its own display mode, which is why the copy exists. Clear removes it;
  if a file is ever left with orange copies in it, Clear tidies it up.
- Hidden lines are off on purpose: the pictures read as drawings, not X-rays.
  For a see-through step, give the viewport `Ghosted` temporarily and capture with
  `ViewCaptureToFile` instead.
- To change the look for everyone, edit the mode in Options → View → Display Modes,
  save it to the team folder with **19 - Display Modes → Save one of my display
  modes**, and commit. Re-importing updates the mode in place.
