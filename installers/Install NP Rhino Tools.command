#!/bin/bash
set -euo pipefail

INSTALL_ROOT="${HOME}/Documents/NP Rhino Scripts"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Configuration: edit before distributing ---
GITHUB_REPO="${NP_GITHUB_REPO:-oliveoi1/np-rhino-scripts}"
BRANCH="${NP_GITHUB_BRANCH:-main}"

echo "=========================================="
echo "  NP Rhino Tools - Installer (Mac)"
echo "=========================================="
echo ""
echo "This downloads and installs tools to:"
echo "  ${INSTALL_ROOT}"
echo ""
echo "No GitHub account needed."
echo ""

mkdir -p "${INSTALL_ROOT}"
for dir in _user_data _logs _temp _backup _staging; do
  mkdir -p "${INSTALL_ROOT}/${dir}"
done

if [[ "${GITHUB_REPO}" == *"YOUR_GITHUB"* ]]; then
  echo "Installing from local developer folder (no GitHub download)..."
  if command -v python3 >/dev/null 2>&1; then
    export REPO_ROOT="${REPO_ROOT}"
    export GITHUB_REPO="${GITHUB_REPO}"
    python3 - <<'PY'
import os, shutil, json, sys
install_root = os.path.expanduser("~/Documents/NP Rhino Scripts")
repo_root = os.environ.get("REPO_ROOT", "")
if not repo_root:
    sys.exit(1)
manifest_path = os.path.join(repo_root, "manifest.json")
with open(manifest_path) as f:
    manifest = json.load(f)
items = ["manifest.json", "README.md", "run_np_launcher.py"] + manifest.get("appFolders", [])
for item in items:
    src = os.path.join(repo_root, item)
    dst = os.path.join(install_root, item)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    elif os.path.isfile(src):
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copy2(src, dst)
config = os.path.join(install_root, "_user_data", "github_config.json")
if not os.path.isfile(config):
    with open(config, "w") as f:
        json.dump({"repo": os.environ.get("GITHUB_REPO", ""), "branch": "main"}, f, indent=2)
print("Local install complete.")
PY
  else
    echo "python3 not found. Copy files manually to ${INSTALL_ROOT}"
    exit 1
  fi
else
  ZIP_URL="https://github.com/${GITHUB_REPO}/archive/refs/heads/${BRANCH}.zip"
  echo "Downloading ${ZIP_URL}..."
  TMP_ZIP="$(mktemp /tmp/np_rhino_XXXX.zip)"
  curl -fsSL -o "${TMP_ZIP}" "${ZIP_URL}"
  TMP_DIR="$(mktemp -d /tmp/np_rhino_extract_XXXX)"
  unzip -q "${TMP_ZIP}" -d "${TMP_DIR}"
  PACKAGE_DIR="$(find "${TMP_DIR}" -maxdepth 2 -name manifest.json -print -quit | xargs dirname)"
  if [[ -z "${PACKAGE_DIR}" || ! -f "${PACKAGE_DIR}/manifest.json" ]]; then
    echo "ERROR: Could not find package in ZIP."
    exit 1
  fi
  REPO_ROOT="${PACKAGE_DIR}" GITHUB_REPO="${GITHUB_REPO}" python3 - <<'PY'
import os, shutil, json, sys
install_root = os.path.expanduser("~/Documents/NP Rhino Scripts")
repo_root = os.environ["REPO_ROOT"]
manifest_path = os.path.join(repo_root, "manifest.json")
with open(manifest_path) as f:
    manifest = json.load(f)
items = ["manifest.json", "README.md", "run_np_launcher.py"] + manifest.get("appFolders", [])
for item in items:
    src = os.path.join(repo_root, item)
    dst = os.path.join(install_root, item)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    elif os.path.isfile(src):
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copy2(src, dst)
config = os.path.join(install_root, "_user_data", "github_config.json")
with open(config, "w") as f:
    json.dump({"repo": os.environ["GITHUB_REPO"], "branch": manifest.get("branch", "main")}, f, indent=2)
print("GitHub install complete.")
PY
  rm -f "${TMP_ZIP}"
  rm -rf "${TMP_DIR}"
fi

ALIAS_CMD="-_RunPythonScript \"${INSTALL_ROOT}/run_np_launcher.py\""
echo ""
echo "SUCCESS: NP Rhino Scripts installed."
echo ""
echo "NEXT STEP - Rhino (one time):"
echo "  1. Open Rhino 8"
echo "  2. Preferences -> Aliases"
echo "  3. Create alias: NP"
echo "  4. Paste this command:"
echo ""
echo "${ALIAS_CMD}"
echo ""
echo "${ALIAS_CMD}" | pbcopy 2>/dev/null && echo "(Copied to clipboard - paste into Rhino alias NP)" || true
echo ""
echo "Then type NP in Rhino and press Enter for the tool menu."
read -r -p "Press Enter to close..."
