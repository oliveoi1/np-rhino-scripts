"""
NP Rhino Scripts deployment utilities.
Works in Rhino Python 3 (Rhino 8) and standalone Python 3 for installers.
"""

from __future__ import print_function

import json
import os
import platform
import shutil
import sys
import time
import traceback
import zipfile

try:
    from urllib.error import URLError
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request, URLError

# --- Configuration ---
UPDATE_CHECK_INTERVAL_HOURS = 24
VERSION_CHECK_TIMEOUT_SECONDS = 2
BRANCH = "main"

APP_FILES = ["manifest.json", "README.md"]
PROTECTED_DIRS = ("_user_data", "_logs", "_temp", "_backup", "_staging")
RUNTIME_DIRS = PROTECTED_DIRS

DEFAULT_GITHUB_REPO = ""  # Set in _user_data/github_config.json or installers


def get_user_install_root():
    """Return the standard user Documents install path for this OS."""
    home = os.path.expanduser("~")
    if platform.system() == "Windows":
        docs = os.path.join(os.environ.get("USERPROFILE", home), "Documents")
    else:
        docs = os.path.join(home, "Documents")
    return os.path.join(docs, "NP Rhino Scripts")


def get_install_root(script_file=None):
    """
    Resolve install root. If script_file is inside an install, use its directory.
    Otherwise use the standard user Documents path.
    """
    if script_file:
        candidate = os.path.dirname(os.path.abspath(script_file))
        if os.path.isfile(os.path.join(candidate, "manifest.json")):
            return candidate
    env_root = os.environ.get("NP_INSTALL_ROOT", "").strip()
    if env_root and os.path.isdir(env_root):
        return os.path.abspath(env_root)
    return get_user_install_root()


def ensure_runtime_folders(install_root):
    for name in RUNTIME_DIRS:
        path = os.path.join(install_root, name)
        if not os.path.isdir(path):
            os.makedirs(path)


def log_message(install_root, message, level="INFO"):
    ensure_runtime_folders(install_root)
    log_dir = os.path.join(install_root, "_logs")
    log_path = os.path.join(log_dir, "np_deploy.log")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = "[{}] [{}] {}\n".format(stamp, level, message)
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:
        pass


def load_github_config(install_root):
    config_path = os.path.join(install_root, "_user_data", "github_config.json")
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if data.get("repo"):
                return data
        except Exception:
            pass
    example = {
        "repo": "YOUR_GITHUB_USERNAME/np-rhino-scripts",
        "branch": BRANCH,
    }
    return example


def save_github_config_example(install_root):
    ensure_runtime_folders(install_root)
    config_path = os.path.join(install_root, "_user_data", "github_config.json")
    if os.path.isfile(config_path):
        return
    example_path = os.path.join(install_root, "_user_data", "github_config.json.example")
    example = {
        "repo": "YOUR_GITHUB_USERNAME/np-rhino-scripts",
        "branch": "main",
        "note": "Copy to github_config.json and set your repo slug (owner/name).",
    }
    try:
        with open(example_path, "w", encoding="utf-8") as handle:
            json.dump(example, handle, indent=2)
    except Exception:
        pass


def github_urls(repo, branch):
    repo = repo.strip().strip("/")
    branch = branch or BRANCH
    manifest_url = "https://raw.githubusercontent.com/{}/{}/manifest.json".format(repo, branch)
    zip_url = "https://github.com/{}/archive/refs/heads/{}.zip".format(repo, branch)
    return manifest_url, zip_url


def http_get_bytes(url, timeout=30):
    request = Request(url, headers={"User-Agent": "NP-Rhino-Deploy/1.0"})
    response = urlopen(request, timeout=timeout)
    return response.read()


def http_get_json(url, timeout=VERSION_CHECK_TIMEOUT_SECONDS):
    raw = http_get_bytes(url, timeout=timeout)
    return json.loads(raw.decode("utf-8"))


def load_local_manifest(install_root):
    path = os.path.join(install_root, "manifest.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_version(version_str):
    """Simple tuple comparison for semver-like strings."""
    if not version_str:
        return (0,)
    parts = []
    for piece in str(version_str).replace("-", ".").split("."):
        piece = piece.strip()
        if not piece:
            continue
        num = ""
        for ch in piece:
            if ch.isdigit():
                num += ch
            else:
                break
        if num:
            parts.append(int(num))
        else:
            parts.append(0)
    return tuple(parts) if parts else (0,)


def is_remote_newer(local_manifest, remote_manifest):
    if not remote_manifest:
        return False
    if not local_manifest:
        return True
    local_v = parse_version(local_manifest.get("version"))
    remote_v = parse_version(remote_manifest.get("version"))
    if remote_v > local_v:
        return True
    if remote_v == local_v:
        local_updated = (local_manifest.get("updated") or "").strip()
        remote_updated = (remote_manifest.get("updated") or "").strip()
        if remote_updated and remote_updated != local_updated:
            return True
    return False


def metadata_path(install_root):
    return os.path.join(install_root, ".last_launch.json")


def load_metadata(install_root):
    path = metadata_path(install_root)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def save_metadata(install_root, data):
    ensure_runtime_folders(install_root)
    path = metadata_path(install_root)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def should_skip_update(install_root):
    if os.environ.get("NP_SKIP_UPDATE", "").strip() in ("1", "true", "yes"):
        return True
    flag = os.path.join(install_root, "_user_data", "skip_update.txt")
    return os.path.isfile(flag)


def last_successful_check_within_interval(install_root):
    meta = load_metadata(install_root)
    last_ok = meta.get("last_successful_update_check")
    if not last_ok:
        return False
    try:
        elapsed = time.time() - float(last_ok)
        return elapsed < (UPDATE_CHECK_INTERVAL_HOURS * 3600)
    except Exception:
        return False


def record_update_check(install_root, success, details=None):
    meta = load_metadata(install_root)
    meta["last_update_attempt"] = time.time()
    meta["last_update_check_success"] = bool(success)
    if details:
        meta["last_update_check_details"] = details
    if success:
        meta["last_successful_update_check"] = time.time()
    save_metadata(install_root, meta)


def get_app_items_from_manifest(manifest):
    items = list(APP_FILES)
    for folder in manifest.get("appFolders") or []:
        items.append(folder)
    return items


def validate_package_root(package_root, manifest):
    if not manifest:
        return False, "Missing manifest in package"
    manifest_path = os.path.join(package_root, "manifest.json")
    if not os.path.isfile(manifest_path):
        return False, "manifest.json not found in package"
    for rel in manifest.get("requiredFiles") or []:
        if not os.path.isfile(os.path.join(package_root, rel)):
            return False, "Required file missing: {}".format(rel)
    for folder in manifest.get("appFolders") or []:
        if not os.path.isdir(os.path.join(package_root, folder)):
            return False, "Required folder missing: {}".format(folder)
    return True, None


def find_package_root(extracted_dir):
    """GitHub ZIP extracts to repo-branch/ subfolder."""
    if os.path.isfile(os.path.join(extracted_dir, "manifest.json")):
        return extracted_dir
    for name in os.listdir(extracted_dir):
        sub = os.path.join(extracted_dir, name)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "manifest.json")):
            return sub
    return None


def clear_directory(path):
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        else:
            try:
                os.remove(full)
            except Exception:
                pass


def copy_app_item(src_root, dst_root, rel_item):
    src = os.path.join(src_root, rel_item)
    dst = os.path.join(dst_root, rel_item)
    if os.path.isdir(src):
        if os.path.exists(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
    elif os.path.isfile(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    else:
        raise IOError("App item not found: {}".format(rel_item))


def backup_app_files(install_root, manifest):
    backup_root = os.path.join(install_root, "_backup")
    clear_directory(backup_root)
    os.makedirs(backup_root, exist_ok=True)
    for item in get_app_items_from_manifest(manifest):
        src = os.path.join(install_root, item)
        if os.path.exists(src):
            copy_app_item(install_root, backup_root, item)


def restore_app_files_from_backup(install_root, manifest):
    backup_root = os.path.join(install_root, "_backup")
    if not os.path.isdir(backup_root):
        return False
    for item in get_app_items_from_manifest(manifest):
        src = os.path.join(backup_root, item)
        if os.path.exists(src):
            copy_app_item(backup_root, install_root, item)
    return True


def stage_app_files(package_root, install_root, manifest):
    staging_root = os.path.join(install_root, "_staging")
    clear_directory(staging_root)
    os.makedirs(staging_root, exist_ok=True)
    for item in get_app_items_from_manifest(manifest):
        copy_app_item(package_root, staging_root, item)
    return staging_root


def replace_live_app_files(install_root, manifest):
    staging_root = os.path.join(install_root, "_staging")
    locked = []
    for item in get_app_items_from_manifest(manifest):
        src = os.path.join(staging_root, item)
        dst = os.path.join(install_root, item)
        if not os.path.exists(src):
            raise IOError("Staged item missing: {}".format(item))
        try:
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            elif os.path.isfile(dst):
                os.remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        except Exception as exc:
            locked.append((item, str(exc)))
    if locked:
        raise IOError("Locked or failed replacements: {}".format(locked))
    return True


def download_and_extract_zip(zip_url, install_root):
    ensure_runtime_folders(install_root)
    temp_dir = os.path.join(install_root, "_temp")
    clear_directory(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = os.path.join(temp_dir, "update.zip")
    log_message(install_root, "Downloading ZIP from {}".format(zip_url))
    data = http_get_bytes(zip_url, timeout=120)
    with open(zip_path, "wb") as handle:
        handle.write(data)
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)
    package_root = find_package_root(extract_dir)
    if not package_root:
        raise IOError("Could not find package root in downloaded ZIP")
    return package_root


def apply_atomic_update(install_root, package_root, manifest):
    ok, err = validate_package_root(package_root, manifest)
    if not ok:
        raise IOError(err)
    stage_app_files(package_root, install_root, manifest)
    backup_app_files(install_root, manifest)
    try:
        replace_live_app_files(install_root, manifest)
    except Exception:
        restore_app_files_from_backup(install_root, manifest)
        raise
    return True


def fetch_remote_manifest(install_root):
    config = load_github_config(install_root)
    repo = (config.get("repo") or DEFAULT_GITHUB_REPO).strip()
    if not repo or "YOUR_GITHUB" in repo:
        return None, "GitHub repo not configured. Edit _user_data/github_config.json"
    branch = config.get("branch") or BRANCH
    manifest_url, _ = github_urls(repo, branch)
    try:
        remote = http_get_json(manifest_url, timeout=VERSION_CHECK_TIMEOUT_SECONDS)
        return remote, None
    except Exception as exc:
        return None, str(exc)


def check_and_update(install_root, force=False):
    """
    Returns dict with keys: updated, error, message, remote_manifest, local_manifest
    Failed checks do NOT count as successful daily check.
    """
    result = {
        "updated": False,
        "error": None,
        "message": "",
        "skipped": False,
    }
    ensure_runtime_folders(install_root)
    save_github_config_example(install_root)

    if should_skip_update(install_root):
        result["skipped"] = True
        result["message"] = "Update skipped by user setting"
        return result

    if not force and last_successful_check_within_interval(install_root):
        result["skipped"] = True
        result["message"] = "Update check not due yet (24h interval)"
        return result

    local_manifest = load_local_manifest(install_root)
    remote_manifest, fetch_err = fetch_remote_manifest(install_root)

    if fetch_err:
        result["error"] = fetch_err
        result["message"] = "Remote manifest check failed"
        log_message(install_root, fetch_err, "WARN")
        record_update_check(install_root, False, fetch_err)
        return result

    record_update_check(install_root, True, "manifest_ok")

    if not is_remote_newer(local_manifest, remote_manifest):
        result["message"] = "Already up to date ({})".format(
            (local_manifest or {}).get("version", "?")
        )
        return result

    config = load_github_config(install_root)
    repo = config.get("repo", "").strip()
    branch = config.get("branch") or BRANCH
    _, zip_url = github_urls(repo, branch)

    try:
        package_root = download_and_extract_zip(zip_url, install_root)
        apply_atomic_update(install_root, package_root, remote_manifest)
        result["updated"] = True
        result["message"] = "Updated to version {}".format(remote_manifest.get("version"))
        log_message(install_root, result["message"], "INFO")
        meta = load_metadata(install_root)
        meta["installed_version"] = remote_manifest.get("version")
        meta["installed_updated"] = remote_manifest.get("updated")
        save_metadata(install_root, meta)
    except Exception as exc:
        result["error"] = str(exc)
        result["message"] = "Update failed"
        log_message(install_root, traceback.format_exc(), "ERROR")
        try:
            restore_app_files_from_backup(install_root, local_manifest or remote_manifest)
        except Exception:
            pass

    return result


def get_rhino_version_string():
    try:
        import Rhino
        ver = Rhino.RhinoApp.Version
        return "{}.{}.{}".format(ver.Major, ver.Minor, ver.Revision)
    except Exception:
        return "unknown"


def record_launch(install_root, success=True, error=None):
    meta = load_metadata(install_root)
    meta["last_successful_launch"] = time.time() if success else meta.get("last_successful_launch")
    meta["os"] = platform.system()
    meta["rhino_version"] = get_rhino_version_string()
    local = load_local_manifest(install_root) or {}
    meta["installed_version"] = local.get("version")
    meta["installed_updated"] = local.get("updated")
    meta["branch"] = local.get("branch", BRANCH)
    if error:
        meta["last_launch_error"] = error
    save_metadata(install_root, meta)


def get_version_display(install_root):
    local = load_local_manifest(install_root) or {}
    meta = load_metadata(install_root)
    version = local.get("version") or meta.get("installed_version") or "unknown"
    updated = local.get("updated") or meta.get("installed_updated") or "unknown"
    return version, updated


def build_np_alias_command(install_root):
    script_path = os.path.join(install_root, "run_np_launcher.py")
    script_path = os.path.abspath(script_path)
    return '-_RunPythonScript "{}"'.format(script_path)


def install_from_zip_url(zip_url, install_root, repo_hint=None):
    """Used by installers for first-time setup."""
    ensure_runtime_folders(install_root)
    os.makedirs(install_root, exist_ok=True)
    package_root = download_and_extract_zip(zip_url, install_root)
    with open(os.path.join(package_root, "manifest.json"), "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    ok, err = validate_package_root(package_root, manifest)
    if not ok:
        raise IOError(err)
    for item in get_app_items_from_manifest(manifest):
        copy_app_item(package_root, install_root, item)
    if os.path.isfile(os.path.join(package_root, "run_np_launcher.py")):
        shutil.copy2(
            os.path.join(package_root, "run_np_launcher.py"),
            os.path.join(install_root, "run_np_launcher.py"),
        )
    if repo_hint:
        ensure_runtime_folders(install_root)
        config_path = os.path.join(install_root, "_user_data", "github_config.json")
        if not os.path.isfile(config_path):
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump({"repo": repo_hint, "branch": manifest.get("branch", BRANCH)}, handle, indent=2)
    return manifest
