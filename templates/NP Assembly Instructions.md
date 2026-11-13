# NP assembly instructions — how to make the step images

Cartoon-style pictures of a product going together, straight from Rhino: the whole
piece in off-white with dark outlines, the part being placed in orange.

Everything is done with two tools in the NP Tools panel: **Assembly Steps**
(highlight, capture, restore) and **Assembly Symbols** (arrows, glue, tools).
This page opens from **Assembly Steps → Instructions**.

## How the tools think

Three things explain nearly every surprise.

- **Only one orange piece is live at a time, in the whole model.** The piece you
  made orange with Highlight stays orange only until the next Highlight or Restore
  step anywhere in the model, even on another stage. Then it goes back to
  off-white. **Copy stage is what makes a stage's orange piece permanent**: the
  stage you leave behind keeps it as a plain orange object.
- **Capture step is what saves a step.** It writes the picture and stores, in the
  file, where everything was, the camera, which pieces were orange and which arrows
  were showing. Anything changed after Capture is not in the step until you capture
  again **with the same step number**.
- **Restore step shows one step and hides the arrows of all the others.** The
  arrows on your other stages are hidden, not deleted. **Show all symbols** brings
  them back.

## Six rules

1. **Capture before you Copy stage, and before you go back to an earlier stage.**
   Capture is the only thing that remembers which piece was orange on the stage you
   are leaving.
2. **Go back with Assembly Steps → Restore step..., never with Rhino's Snapshots
   panel.** The panel brings back positions only; the orange piece and the arrows
   come out wrong.
3. **After Restore step, finish with Show all symbols.** Otherwise the arrows on
   the other stages stay hidden and look deleted.
4. **Re-capture with the step's own number.** Capture offers the next free number;
   accepting it while fixing an old step makes an extra step.
5. **Never delete an arrow to tidy up; never delete the orange piece.** A deleted
   arrow cannot come back into its step. The orange piece has the real part hidden
   underneath it; use **Clear highlight** to take the orange off.
6. **Save the model after every Capture.** The steps live in the file. Close without
   saving and the steps captured since the last save are gone, although their
   pictures are still in the folder.

Also:

- Move and rotate the live orange piece as much as you like. It stands in for the
  real part, and the real part follows it when the orange comes off.
- Do not use Rhino's `Show` command while a piece is orange. It brings the hidden
  real part back on top of the orange one, and every hidden arrow with it.
- Avoid Undo straight after Highlight, Capture step, Restore step or Copy stage.
  Undo steps back through the tool's own housekeeping (the orange copy, the hidden
  part), not only through your last move. If the model looks wrong, run
  **Restore step...** for the step you want instead.

## One-time setup (two minutes)

1. Run **Force Update** from the NP launcher or the NP Tools panel, so you have
   the tools and the display modes in `templates/display_modes`.
2. Open any model and run **Assembly Steps → Highlight selected piece** once. It
   imports the display modes `NP Assembly`, `NP Assembly - Active` and
   `NP Assembly - Fittings` into your Rhino. (**19 - Display Modes → Import all
   team display modes** imports the whole set.) They now appear in the viewport's
   display mode list like Shaded or Arctic.

The colours, line weights and background all live in those modes, so the
pictures look the same on everyone's machine. Do not edit layer colours or blocks
for the pictures.

## The normal run: one stage per step, in a row

1. **Set up the view.** Perspective viewport, camera where you want it.
2. **Position the parts.** Pull the piece being placed out along the direction it
   goes in.
3. **Highlight.** Select the piece (a block instance is fine) and run
   **Assembly Steps → Highlight selected piece**. It turns orange, the rest turns
   off-white, and the viewport switches to `NP Assembly`. For two orange pieces in
   one step, select both and Highlight once.
4. **Arrows, glue and tools.** Add them with **Assembly Symbols** (each one is
   described under "What each command does" below).
5. **Capture.** **Assembly Steps → Capture step**. Accept the step number (it offers
   the next free one) and the scale (3 = three times the viewport, crisp at print
   size). The PNG lands in an `Assembly Steps` folder next to the model, named
   `<model> step 01.png` and so on. The step is stored in the file as the snapshot
   `Assembly step 01`.
6. **Save the model.**
7. **Copy stage.** Select the whole stage (or press Enter for everything visible)
   and run **Assembly Steps → Copy stage**. Give a distance (it suggests one a
   little wider than the stage; `Direction` picks Right, Left, Forward or Back;
   `Symbols` chooses whether the arrows and glue come along, normally they stay).
   The copy lands that far away and the camera moves with it, so the picture looks
   the same but you are now on the new stage.
   - The stage you left keeps its orange piece for good, as a plain orange object.
   - On the new stage that piece is the real part again, off-white, in the pose you
     left it. Push it home.
8. Go back to step 2 on the new stage: pull out the next piece, Highlight, add
   symbols, Capture with the next number, Save, Copy stage.

After orbiting around on the newest stage, **Assembly Steps → Back to stage view**
returns the camera to where Copy stage left it, without moving any pieces.

When the last step is captured, run **Assembly Steps → Clear highlight** so the
last orange piece becomes the real part again.

## Going back to an earlier stage

First **Capture the stage you are on** (rule 1). Then:

### To add or change arrows, glue or notes on an earlier stage

1. **Assembly Steps → Restore step...** and pick the step. The camera goes back to
   that stage exactly as it was captured. The arrows of other stages are hidden for
   now. The command line may say that a highlighted piece no longer exists; on a stage you have
   copied from that is expected, because its orange piece is now a plain object.
2. Add, move or hide the symbols.
3. **Capture step** and **type that step's number**.
4. **Show all symbols**, then Save.

### To change which piece is orange on an earlier stage

1. **Restore step...** and pick the step.
2. To make another piece orange: select it and **Highlight selected piece**.
3. To take the orange off the piece that was orange before: select it, run Rhino's
   `SetObjectDisplayMode` and choose `UseView`. (On a stage you have copied from,
   that piece is a plain orange object, so Clear highlight does not reach it.)
4. **Capture step** and **type that step's number**.
5. **Show all symbols**, then Save.

The newly orange piece on that earlier stage is live (see "How the tools think"):
it goes back to off-white on screen as soon as you highlight something on another
stage. Its picture is already saved, and Restore step and Re-capture all steps
bring the orange back for that step, so nothing is lost.

### To get back to the stage you were working on

**Restore step...** and pick its number, then **Show all symbols**. If you had not
captured it before leaving, its orange piece will be off-white: select it and
Highlight again.

### A step captured by mistake

Delete its PNG in the `Assembly Steps` folder and delete `Assembly step NN` in
Rhino's Snapshots panel. Deleting there is fine; restoring there is not (rule 2).

## When the assembly changes

Fix the model, then run **Assembly Steps → Re-capture all steps**. Every step is
restored in turn and all the PNGs are written again with the same names. Finish
with **Show all symbols**.

- The summary lists "highlighted piece(s) no longer exist" for every stage you have
  copied from. That is expected: those stages show their orange piece as a plain
  object, and it is in the picture.
- An arrow that was deleted cannot come back, so its step is re-captured without it.
- The orange piece a stage keeps after Copy stage is a plain copy. It does not
  follow a later change to the part; on that stage, restore the step, highlight
  the changed part again and capture with the step's number.

## If something looks wrong

| What you see | Why | What to do |
| --- | --- | --- |
| The orange piece on my stage turned off-white when I highlighted a piece somewhere else | Only one orange piece is live in the whole model | Capture a stage before leaving it. To get it back: **Restore step...** for that stage, or select the piece and Highlight again |
| I need two orange pieces in one step | Highlight replaces the live orange piece | Select both pieces and Highlight once |
| My arrows or glue have gone from the other stages | Restore step (and Re-capture all) hides the symbols of other steps | **Show all symbols** |
| I went back to a step and nothing is orange, the wrong piece is orange, or the piece looks plain | The step was restored from Rhino's Snapshots panel | **Restore step...** and pick the step |
| Restore step says a highlighted piece no longer exists | That stage was copied from, so its orange piece is a plain object now | Nothing; the orange piece is still there |
| I cannot take the orange off a piece on an earlier stage | Same reason: Clear highlight only reaches the live orange piece | Select it, `SetObjectDisplayMode`, `UseView` |
| An arrow I deleted is missing from a re-captured picture | A deleted arrow cannot come back | Restore the step, add it again, Capture with that step's number |
| A step I made is not in the Restore step list | The model was closed without saving after that Capture, or Undo was used after it | Go to that stage, set it up again and Capture with its number |
| There is a step too many | Capture was accepted with the next free number while reworking a step | Delete the extra PNG and its `Assembly step NN` snapshot |
| A piece has vanished from the model | Its orange stand-in was deleted or undone, so the real part is still hidden | Run `ShowSelected`, click the piece, Enter |
| The view turned to wireframe, or the NP Assembly modes left the display mode menu | Rhino for Windows sometimes drops the imported modes in the middle of a session. The cause is not known yet | See the next section |
| The pictures do not line up from step to step | The camera moved between captures | Use **Back to stage view** before Capture, or **Restore step...** to get a step's own camera back |

A piece that vanishes altogether when you highlight the next one, without anything
having been deleted or undone, is not expected. Note what you did just before and
send it with the model.

### If the display modes disappear (Windows)

1. Run **Assembly Steps → Highlight selected piece** or **Capture step** again. Both
   check for missing modes, import them again and put the view back in `NP Assembly`.
   Capture step also checks during the capture, so a picture is not taken in
   wireframe.
2. If they do not come back, run **19 - Display Modes → Import all team display
   modes**.
3. If that fails too, import them by hand: Rhino Options > View > Display Modes >
   Import, and pick each `.ini` file in
   `Documents/NP Rhino Scripts/templates/display_modes` (seven files).
4. Make sure Rhino 8 is version 8.13 or newer; older versions cannot import
   display modes from these tools.

Your steps are not affected: the modes only change how the model is drawn. Each
time the tools find the modes gone they add a line to
`_logs/assembly_modes.log` in the NP tools folder. Send that file, and the report
from **19 - Display Modes → Check display mode import (report)**, so the cause can
be found.

## What each command does

### Assembly Steps

- **Instructions**: opens this page.
- **Highlight selected piece**: turns the piece you selected orange and everything
  else off-white. Any piece that was orange before goes back to off-white.
- **Clear highlight**: takes the orange off and gives you the real part back, in
  the place you moved the orange one to.
- **Capture step**: saves the picture of what is in the view, and remembers the
  step in the file: where everything is, the camera, the orange piece and the
  arrows that are showing.
- **Restore step...**: puts a captured step back on screen with its positions,
  camera, orange piece and arrows. The arrows of other steps are hidden.
- **Re-capture all steps**: goes through every captured step and saves all the
  pictures again. For when the model has changed.
- **Copy stage**: copies the stage to one side and moves the camera with it, ready
  for the next step. The stage left behind keeps its orange piece.
- **Back to stage view**: moves the camera back to where the last Copy stage left
  it. Nothing in the model moves.
- **Show all symbols**: shows every hidden arrow, glue bead and tool icon again.
- **Use current CPlane for all steps**: makes the construction plane you have now
  the one every step uses.

### Assembly Symbols

Each one is a small solid that keeps its colour in the drawing.

- **Push / move arrow**: click what the arrow points at, then move the mouse to
  the side it comes from and click. The arrow has a set length and snaps to the
  model's axes; `Length`, `Width`, `Gap` and `Plane` on the command line change
  the size and which plane it lies flat in, and are remembered.
- **Rotate arrow (screw)**: click the screw, cam or grub screw; two curved green
  arrows appear above it, Tighten or Loosen. It also works on a fitting that sits
  inside a panel block: click the fitting itself, not the bare panel.
- **Glue bead**: select a curve or click along the joint; a pale yellow bead with
  round ends, on its own layer `NP-Assembly - Glue`.
- **Tool call-out**: a flat icon: glue bottle, screwdriver bit (`PhillipsBit` or
  `RobertsonBit`), rubber mallet, hammer, green tick or red cross. For a bit, click
  the screw or cam it drives and the bit stands straight out from it, with the
  screw head symbol beside it. For the other tools (or a bit after Enter), click
  where the tip or the striking face goes, then click where the body or handle
  should lie, and the icon turns to match; Enter instead of the second click
  gives the standard orientation. Each is one group; scale or move it like any
  object.
  An icon drawn here comes out a different size in every picture. For symbols
  that are the same size on every page, leave them out in Rhino and add them in
  InDesign from the shared CC Library instead: see
  `templates/assembly_symbols/README.md`.
- **Moving blanket**: for the "clean surface" step. Press Enter to fit it under
  everything in view, or click two corners. Dark blue with a quilt pattern.

Put step numbers in with `TextDot` or the annotation styles from
**18 - Annotation Styles**.

## Working on one stage instead

Every step can also be built on top of the same model, without Copy stage. The
order then is:

1. Position, Highlight, add symbols, **Capture step**, Save.
2. Push the orange piece home.
3. Select the arrows and glue of the step you just captured and run `Hide`.
   Capture puts every symbol that is showing into the picture, so an arrow left on
   screen ends up in the next step as well. Hide, do not delete.
4. Pull out the next piece and Highlight it. The piece that was orange goes back
   to off-white where you left it.
5. Add this step's symbols, Capture with the next number, Save.

Save the camera as a named view (`NamedView`) the first time and restore it for
every step so all pictures line up. **Restore step...** brings any step back with
its own orange piece and its own arrows.

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
