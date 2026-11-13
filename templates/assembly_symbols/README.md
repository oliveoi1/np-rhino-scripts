# Assembly symbols for InDesign

The tool and instruction symbols for assembly instructions, as artwork to add in
InDesign instead of in the Rhino picture. A symbol drawn in Rhino comes out a
different size in every capture; these are drawn at their size on the page, so
placed at 100% they are the same size in every drawing.

| Symbol | Files | Size at 100% |
| --- | --- | --- |
| Glue bottle (nozzle down to the left; rotate it to aim) | `GlueBottle` | 10.7 x 10.7 mm |
| Screwdriver bit with a Phillips screw head | `PhillipsBit` | 7.9 x 10.2 mm |
| Screwdriver bit with a Robertson screw head | `RobertsonBit` | 7.9 x 10.2 mm |
| Rubber mallet | `Mallet` | 9.6 x 11.2 mm |
| Hammer | `Hammer` | 8.9 x 11.0 mm |
| Tick | `Tick` | 8.7 x 8.7 mm |
| Cross | `Cross` | 6.6 x 6.6 mm |
| Flip the product (arrow turning to the right) | `Flip` | 15.2 x 13.5 mm |
| Flip the product (arrow turning to the left) | `FlipLeft` | 15.2 x 13.5 mm |

Each symbol is here as a `.pdf` and an `.svg` with the same artwork. Use one
format, not both.

## Put them in the shared CC Library (once)

1. In InDesign open **Window → CC Libraries** and choose the team library.
2. Drag the nine files of one format from this folder into the panel.

From then on the library copy is the master. Everyone with the library has the
symbols, and nobody needs this folder.

## Add a symbol to a page

Drag it from the CC Libraries panel onto the page. It comes in linked to the
library at 100%. Move and rotate it; do not scale it.

## Change a symbol for everyone

Right-click it in the CC Libraries panel and choose **Edit**. Save, and every
document that uses it updates. This is also the place to change a symbol's size
for good: scale the artwork in the library copy.

## Starting over

`make_symbols.py` writes these files again from the shapes and colours the Rhino
Tool call-out uses (`python3 make_symbols.py`; sizes are at the top of the file).
