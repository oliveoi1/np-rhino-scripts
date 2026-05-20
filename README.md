# NP Rhino Tools

Production scripts for Rhino 8 (Mac and Windows).

## Team install (start here)

**See [INSTALL.md](INSTALL.md)** for simple download links and step-by-step setup.  
No GitHub knowledge required.

| | Download |
|---|----------|
| **Mac** | [Install NP Rhino Tools.command](https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/Install%20NP%20Rhino%20Tools.command) |
| **Windows** | [Install NP Rhino Tools.ps1](https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/Install%20NP%20Rhino%20Tools.ps1) |

After install: create Rhino alias **NP**, then type `NP` in Rhino.

## How updates work

- Running `NP` checks for updates once per day.
- Use **Force Update** at the bottom of the menu for an immediate update.
- Works offline with the last installed version.

## Troubleshooting

| Problem | What to do |
|--------|------------|
| `NP` does nothing | Confirm alias points to `run_np_launcher.py` in Documents |
| Update errors | Check `Documents/NP Rhino Scripts/_logs/np_deploy.log` |
| Skip updates | Create `_user_data/skip_update.txt` |

## Developers

Repo: https://github.com/oliveoi1/np-rhino-scripts  
Edit scripts in this workspace, bump `manifest.json` version, push to `main`. Team receives updates via `NP`.
