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
   - **Push / move arrow**: click the tail, then the tip. Green block arrow facing
     the camera.
   - **Rotate arrow (screw)**: click the screw block; two curved green arrows appear
     above its head, Tighten or Loosen.
   - **Glue bead**: select a curve or click along the joint; a pale yellow bead with
     round ends, on its own layer `NP-Assembly - Glue`.
   - **Tool call-out**: a flat icon at a clicked point: glue bottle, screwdriver bit,
     rubber mallet, hammer, green tick or red cross. Each is one group; scale or move
     it like any object.
   - **Moving blanket**: for the "clean surface" step. Press Enter to fit it under
     everything in view, or click two corners. Dark blue with a quilt pattern.
   Put step numbers in with `TextDot` or the annotation styles from
   **18 - Annotation Styles**. Hide or delete the symbols before the next step; the
   step snapshot remembers what was visible.
5. **Capture.** **Assembly Steps → Capture step**. Accept the step number (it offers
   the next free one) and the scale (3 = three times the viewport, crisp at print
   size). The PNG lands in an `Assembly Steps` folder next to the model, named
   `<model> step 01.png` and so on. The step is also saved in the file as the
   snapshot `Assembly step 01` (positions, visibility and view) together with a
   note of which pieces were orange. Save the model so the snapshots are kept.
6. **Clear.** **Assembly Steps → Clear highlight** puts the original piece back.
   If you moved or rotated the orange piece while it was highlighted (flipping a part upside down, say), the original follows it.

## When the assembly changes

- Fix the model, then run **Assembly Steps → Re-capture all steps**. Every step
  snapshot is restored in turn, its highlight put back, and all the PNGs are
  written again with the same names.
- To rework one step: **Assembly Steps → Restore step...**, pick it, move things
  or change the highlight, then **Capture step** with the same number. That
  replaces the image and the snapshot.
- The Snapshots panel shows the same `Assembly step` entries; restoring one there
  gives you the positions but not the orange piece, so prefer **Restore step...**.

## Good to know

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
