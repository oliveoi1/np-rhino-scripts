# Python Scripts Inventory

Deployment: use `run_np_launcher.py` at repo root (alias **NP**). Updates via `shared/np_deploy.py`. See root `README.md`.

Current scripts in this folder:

- `01 extrude_curves.py`
- `02 dado_recess.py`
- `02 dado_tongue.py`
- `02b Surface recess.py`
- `03a hole_insertpoints_auto.py`
- `03b grub_screws_and_holes.py`
- `03c dimple_hole.py`
- `04a cam_inserts.py`
- `04b cam_holes_+_cams.py`
- `05a flipper_insert_auto.py`
- `05b flipper_holes_+flippers.py`
- `05c shelf_holes.py`
- `06a castor_insert.py`
- `06b castor_(LG)_insert_+_holes.py`
- `06b castor_(SM)_insert_+_holes.py`
- `07 Glides.py`
- `08a create_block 1st.py`
- `08a create_block 1st copy.py`
- `08b create_block.py`
- `09 plan view.py`
- `10 logo_cut.py`
- `12 align_sit_on_face.py`

## Notes

- This list is for quick browsing and planning refactors.
- Keep original filenames for now to avoid breaking existing workflows.
- For new scripts, prefer lowercase with underscores and no spaces.

## Suggested next cleanup pass

- remove spaces and symbols (`+`, parentheses) from filenames,
- use consistent numbering prefixes,
- merge duplicate variants where possible (`08a` files).
