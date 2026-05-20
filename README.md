# NP Rhino Tools

Production scripts for Rhino 8 (Mac and Windows).

## Installation

### Mac

1. Double-click `installers/install_mac.command`.
2. If macOS blocks it: right-click → Open.
3. Tools install to `Documents/NP Rhino Scripts`.

### Windows

1. Right-click `installers/install_windows.ps1` → **Run with PowerShell**.
2. Tools install to `Documents\NP Rhino Scripts`.

### GitHub repo (for your team)

Before distributing installers, set your GitHub repo in the installer or set environment variable:

```bash
export NP_GITHUB_REPO="your-org/np-rhino-scripts"
```

On first install, edit `Documents/NP Rhino Scripts/_user_data/github_config.json` if needed.

## Rhino setup (alias NP)

The installer prints the exact command and copies it to your clipboard.

1. Open Rhino.
2. Go to **Rhino → Preferences → Aliases** (Mac) or **Options → Aliases** (Windows).
3. Create alias: `NP`
4. Paste the command shown by the installer (full path to `run_np_launcher.py`).
5. In Rhino, type `NP` and press Enter.

## How updates work

- When you run `NP`, the tool checks for updates **once per day**.
- It downloads a new version only if GitHub has a newer `manifest.json` version.
- Updates are silent when possible.
- Your local data in `_user_data/` is never overwritten.

## Offline behavior

If you are offline or GitHub is unavailable:

- You still get your local tools immediately.
- A failed check does **not** count as “checked today” — it will retry next launch.

## Troubleshooting

| Problem | What to do |
|--------|------------|
| `NP` does nothing | Confirm alias points to `run_np_launcher.py` in Documents |
| Update errors | Check `_logs/np_deploy.log` in install folder |
| Skip updates | Create `_user_data/skip_update.txt` or set `NP_SKIP_UPDATE=1` |
| Wrong GitHub repo | Edit `_user_data/github_config.json` |

## Support

Contact your shop lead or the person who maintains the NP Rhino Scripts GitHub repo.

---

*Developer workspace: keep editing scripts here, push to GitHub, and team members receive updates via `NP`.*
