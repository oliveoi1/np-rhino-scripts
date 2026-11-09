# Python Scripts

Deployment: run **`np_launcher.py`** from Rhino (alias **NP**), or **`np_menu.py`** (alias **NPP**) for the categorised NP Tools panel. Both read the same `SCRIPT_CHOICES` table. Updates via `shared/np_deploy.py`. See repo root [README.md](../../README.md).

## Documentation

- **[TOOLS.md](TOOLS.md)** — quick reference per tool: dimensions (inch fractions), usage steps, blocks/layers.
- **Guide & Instructions** (first item in the NP launcher) — [full NP guide on Google Docs](https://docs.google.com/document/d/1-wMRbW0fdt7HhVIuPh7oi6vFMNPt1Xmb1XPxvN63aVc/edit?tab=t.0).

## Script inventory

Matches `SCRIPT_CHOICES` in `np_launcher.py`:

- `01 extrude_curves.py`
- `01a_extrude_ply_bands.py`
- `02 dado_recess.py`
- `02 dado_tongue.py`
- `02b Surface recess.py`
- `02c engrave.py`
- `03a hole_insertpoints_auto.py`
- `03b grub_screws_and_holes.py`
- `03c dimple_hole.py`
- `03d custom_holes.py`
- `04a cam_inserts.py`
- `04b cam_holes_+_cams.py`
- `05a flipper_insert_auto.py`
- `05b flipper_holes_+flippers.py`
- `05c shelf_holes.py`
- `06a castor_insert.py`
- `06b castor_(SM)_insert_+_holes.py`
- `06b castor_(LG)_insert_+_holes.py`
- `07 Glides.py`
- `15 insert_block.py`
- `create_or_redefine_block.py`
- `create_or_redefine_block_and_insert_copy.py`
- `create_or_redefine_block_from_sku_insert_point.py`
- `09 plan view.py`
- `10 logo_cut.py`
- `11 export_blocks_to_skp.py`
- `11a export_blocks_to_3dm.py`
- `11b export_blocks_to_step.py`
- `12 zero_sku_insertion_z.py`
- `13 bounding_dimensions.py`
- `14 numbered_dots.py`
- `16 snapshot_2d_export.py`
- `17 explode_fittings.py`
- `18 annotation_styles.py`
- `19 display_modes.py`
- `20 assembly_steps.py`
- `21 assembly_symbols.py`
- `np_menu.py` (NP Tools panel, alias NPP)
- `np_menu_startup.py` (re-registers the panel at Rhino startup; NPP adds it to the startup commands)

## Notes

- Keep original filenames for now to avoid breaking existing workflows.
- For new scripts, prefer lowercase with underscores and no spaces.
- Add a row to `SCRIPT_CHOICES` in `np_launcher.py` and a section in `TOOLS.md` when adding tools.
