# Install NP Rhino Tools (team guide)

No GitHub account or technical setup required. Download one file, run it, then add one Rhino shortcut.

---

## Mac — 3 steps

### 1. Download the installer

**Download link:**  
https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/Install%20NP%20Rhino%20Tools.command

(Save the file to your **Downloads** folder.)

### 2. Run the installer

- **First time only:** Right-click the file → **Open** → **Open** again (macOS may block unknown downloads).
- Or double-click if your Mac allows it.

Wait until you see **SUCCESS** and the window says the command was copied to your clipboard.

Tools are installed here:

`Documents/NP Rhino Scripts`

### 3. Set up Rhino (one time)

1. Open **Rhino 8**.
2. Menu: **Rhino → Settings → Aliases** (or search “Aliases” in Preferences).
3. Click **New** (or add alias).
4. **Name:** `NP`
5. **Command:** Paste from clipboard (installer copied it), or paste exactly:

   `-_RunPythonScript "~/Documents/NP Rhino Scripts/run_np_launcher.py"`

6. Click OK.

**Done.** In any Rhino file, type `NP` and press Enter to open the tool menu.

---

## Windows — 3 steps

### 1. Download the installer

**Download link:**  
https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/Install%20NP%20Rhino%20Tools.ps1

(Save the file to your **Downloads** folder.)

### 2. Run the installer

1. Right-click `Install NP Rhino Tools.ps1`
2. Choose **Run with PowerShell**
3. If asked about security, choose **Run once** or **Yes**

Wait until you see **SUCCESS** and the command was copied to your clipboard.

Tools are installed here:

`Documents\NP Rhino Scripts`

### 3. Set up Rhino (one time)

1. Open **Rhino 8**.
2. Menu: **Tools → Options → Aliases**.
3. Add alias **NP**.
4. **Command:** Paste from clipboard, or paste exactly:

   `-_RunPythonScript "%USERPROFILE%\Documents\NP Rhino Scripts\run_np_launcher.py"`

   (Use your real username path if the installer printed a full path — paste what the installer showed.)

5. Click OK.

**Done.** Type `NP` in Rhino and press Enter.

---

## After install

- **Updates:** Automatic when you run `NP` (checked once per day). Use **Force Update** at the bottom of the menu if you need the latest tools immediately.
- **Offline:** Tools still work without internet; updates retry later.
- **Problems:** Ask your shop lead, or check `Documents/NP Rhino Scripts/_logs/np_deploy.log`

---

## Alternate Mac installer filename

If the link above does not work, try:

https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/install_mac.command

(Same installer, different filename.)

## Alternate Windows installer filename

https://github.com/oliveoi1/np-rhino-scripts/raw/main/installers/install_windows.ps1

---

## For IT / admin

- Repo: https://github.com/oliveoi1/np-rhino-scripts  
- Requires Rhino 8 with Python scripting (Rhino `RunPythonScript`).
- Installers download the latest tools from GitHub; users do not need git installed.
