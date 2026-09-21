"""App & Bloat Manager endpoints plus startup-item inventory and scoring."""
import os
import subprocess

from flask import Blueprint, jsonify, request, current_app

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import log_activity, log_undo
from core.startup import RUN_PATH, StartupToggleError, read_approved_states, set_startup_enabled
from scanners.apps import (
    _scan_apps_from_registry, _build_uninstall_invocation, _registry_has_display_name,
)

bp = Blueprint("apps", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# APP & BLOAT MANAGER
# ══════════════════════════════════════════════════════════════════════════════


@bp.route("/api/apps/list")
def api_apps_list():
    try:
        apps = _scan_apps_from_registry()
    except Exception as e:
        log_activity(f"App Manager: registry scan failed: {e}", "ERROR")
        return jsonify({"ok": False, "error": f"Could not read installed apps from the registry: {e}"}), 500
    return jsonify({"ok": True, "apps": apps, "demo": not IS_WINDOWS})


@bp.route("/api/apps/export", methods=["POST"])
def api_apps_export():
    try:
        apps = _scan_apps_from_registry()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not read installed apps: {e}"}), 500
    import csv
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "publisher", "version", "install_date", "size_mb", "tag", "uninstall_cmd"])
    writer.writeheader()
    for a in apps:
        writer.writerow({k: a.get(k, "") for k in writer.fieldnames})
    return current_app.response_class(buf.getvalue(), mimetype="text/csv",
                               headers={"Content-Disposition": "attachment;filename=installed_apps.csv"})


@bp.route("/api/apps/uninstall", methods=["POST"])
def api_apps_uninstall():
    data = request.get_json() or {}
    name = data.get("name", "")
    cmd = data.get("uninstall_cmd", "")
    if not cmd:
        return jsonify({"ok": False, "error": "No uninstall command provided."})
    log_activity(f"App Manager: launching uninstaller for '{name}'", "WARN")
    if not IS_WINDOWS:
        return jsonify({"ok": True, "demo": True, "msg": f"[DEMO] Would run: {cmd}"})

    import ctypes
    try:
        exe, args = _build_uninstall_invocation(cmd)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not parse the uninstall command: {e}"})

    working_dir = None
    try:
        exe_dir = os.path.dirname(exe)
        if exe_dir and os.path.isdir(exe_dir):
            working_dir = exe_dir
    except Exception:
        working_dir = None

    # ShellExecuteW with the "runas" verb triggers a UAC elevation prompt, and
    # SW_SHOWNORMAL (1) keeps the uninstaller's own UI visible.
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args or None, working_dir, 1)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to launch the uninstaller: {e}"})

    if isinstance(ret, int) and ret <= 32:
        errors = {
            2:  "The uninstaller could not be found. The app may already be removed.",
            3:  "The uninstaller path is invalid.",
            5:  "Access denied — the UAC elevation prompt was declined.",
            31: "No application is associated with this uninstaller.",
        }
        msg = errors.get(ret, f"Could not launch the uninstaller (ShellExecute code {ret}).")
        log_activity(f"App Manager: uninstaller for '{name}' failed (code {ret})", "ERROR")
        return jsonify({"ok": False, "error": msg})

    return jsonify({"ok": True, "msg": f"Uninstaller launched for {name}. Follow the prompts, then click Verify."})


@bp.route("/api/apps/verify-uninstall", methods=["POST"])
def api_apps_verify_uninstall():
    """Re-read the registry to confirm whether an app is still installed."""
    data = request.get_json() or {}
    name = data.get("name", "")
    if not name:
        return jsonify({"ok": False, "error": "No app name provided."})
    if not IS_WINDOWS:
        return jsonify({"ok": True, "demo": True, "still_present": False})
    try:
        present = _registry_has_display_name(name)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not read the registry: {e}"})
    if not present:
        log_activity(f"App Manager: confirmed '{name}' removed", "SUCCESS")
    return jsonify({"ok": True, "still_present": present})


@bp.route("/api/apps/open-folder", methods=["POST"])
def api_apps_open_folder():
    data = request.get_json() or {}
    path = data.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "error": "Folder does not exist or path not provided."})
    if IS_WINDOWS:
        subprocess.Popen(["explorer", path])
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP ITEMS
# ══════════════════════════════════════════════════════════════════════════════

@bp.route("/api/startup-items")
def api_startup():
    items = []
    if IS_WINDOWS:
        try:
            import winreg
        except ImportError as e:
            # On Windows this is a real failure — report it, don't fabricate data.
            log_activity(f"Startup scan failed: {e}", "ERROR")
            return jsonify({"ok": False, "error": f"Registry access is unavailable: {e}"}), 500
        for hive, hive_name in [
            (winreg.HKEY_CURRENT_USER, "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
        ]:
            approved = read_approved_states(winreg, hive_name)
            try:
                key = winreg.OpenKey(hive, RUN_PATH)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append({
                            "name": name,
                            "path": value,
                            "hive": hive_name,
                            "enabled": approved.get(name, True),
                        })
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except OSError:
                pass
    else:
        items = _get_demo_startup_items()
    items.sort(key=lambda x: x["name"])
    for item in items:
        scoring = _score_startup_item(item)
        item.update(scoring)
    return jsonify({"ok": True, "items": items, "demo": not IS_WINDOWS})


def _get_demo_startup_items():
    return [
        {"name": "OneDrive", "path": "C:\\Program Files\\Microsoft OneDrive\\OneDrive.exe", "hive": "HKCU", "enabled": True},
        {"name": "SecurityHealth", "path": "C:\\Windows\\System32\\SecurityHealthSystray.exe", "hive": "HKLM", "enabled": True},
        {"name": "Discord", "path": "C:\\Users\\User\\AppData\\Local\\Discord\\Update.exe --processStart Discord.exe", "hive": "HKCU", "enabled": True},
        {"name": "Spotify", "path": "C:\\Users\\User\\AppData\\Roaming\\Spotify\\Spotify.exe /minimized", "hive": "HKCU", "enabled": True},
        {"name": "Steam", "path": "C:\\Program Files (x86)\\Steam\\steam.exe -silent", "hive": "HKCU", "enabled": True},
        {"name": "NVIDIA Settings", "path": "C:\\Program Files\\NVIDIA Corporation\\Display.NvContainer\\NVDisplay.Container.exe", "hive": "HKLM", "enabled": True},
        {"name": "RealTek Audio", "path": "C:\\Program Files\\Realtek\\Audio\\HDA\\RtkNGUI64.exe", "hive": "HKLM", "enabled": True},
    ]


@bp.route("/api/startup-items/toggle", methods=["POST"])
def api_startup_toggle():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    hive = data.get("hive", "HKCU")
    enabled = bool(data.get("enabled", True))
    state = "enabled" if enabled else "disabled"

    if not name:
        return jsonify({"status": "error", "message": "Name is required"}), 400
    if hive not in ("HKCU", "HKLM"):
        return jsonify({"status": "error", "message": f"Unsupported startup location: {hive}"}), 400

    if IS_WINDOWS:
        try:
            # Reversible: flags the item in StartupApproved, never deletes the Run entry.
            set_startup_enabled(name, hive, enabled, data.get("path", ""))
        except StartupToggleError as e:
            log_activity(f"Startup toggle failed for {name} ({hive}): {e.message}", "ERROR")
            return jsonify({"status": "error", "message": e.message}), e.status
        except ImportError as e:
            log_activity(f"Startup toggle failed: {e}", "ERROR")
            return jsonify({"status": "error", "message": f"Registry access is unavailable: {e}"}), 500
        log_activity(f"{'Enabled' if enabled else 'Disabled'} startup item: {name} ({hive})", "SUCCESS")
    else:
        log_activity(f"Simulated toggle startup item: {name} -> {state}", "INFO")

    log_undo("startup_toggle", f"{'Enabled' if enabled else 'Disabled'} startup item: {name}",
             {"name": name, "hive": hive, "enabled": enabled, "path": data.get("path", "")})
    return jsonify({"status": "ok", "name": name, "hive": hive, "enabled": enabled})


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP IMPACT SCORING
# ══════════════════════════════════════════════════════════════════════════════

_STARTUP_IMPACT_DB = {
    "discord":       {"score": 40, "category": "safe_to_disable", "rec": "Disable — launch Discord manually when needed. Saves ~400ms boot time."},
    "spotify":       {"score": 35, "category": "safe_to_disable", "rec": "Disable — Spotify doesn't need to autostart. Launch it when you want music."},
    "steam":         {"score": 45, "category": "safe_to_disable", "rec": "Disable — Steam autostart adds significant boot time. Launch games from shortcut."},
    "onedrive":      {"score": 25, "category": "review",          "rec": "Review — Disable if you sync infrequently. Files still sync when you open it."},
    "dropbox":       {"score": 25, "category": "review",          "rec": "Review — Disable if you sync infrequently."},
    "google drive":  {"score": 25, "category": "review",          "rec": "Review — Disable Google Drive File Stream if not actively syncing."},
    "googledrive":   {"score": 25, "category": "review",          "rec": "Review — Disable if not actively syncing with Google Drive."},
    "skype":         {"score": 30, "category": "safe_to_disable", "rec": "Disable — Launch Skype manually before calls. No need to autostart."},
    "zoom":          {"score": 30, "category": "safe_to_disable", "rec": "Disable — Zoom doesn't need to autostart. Launch it before meetings."},
    "teams":         {"score": 35, "category": "review",          "rec": "Review — Disable if you don't use Teams for work daily."},
    "slack":         {"score": 30, "category": "review",          "rec": "Review — Disable if Slack is not your primary work chat."},
    "adobe":         {"score": 45, "category": "safe_to_disable", "rec": "Disable — Adobe update/helper services add overhead. Disable safely."},
    "autodesk":      {"score": 40, "category": "safe_to_disable", "rec": "Disable — Autodesk startup services significantly slow boot time."},
    "ccleaner":      {"score": 20, "category": "safe_to_disable", "rec": "Disable — CCleaner monitoring service is not essential at startup."},
    "itunes":        {"score": 30, "category": "safe_to_disable", "rec": "Disable — iTunes helper doesn't need to run at startup."},
    "realplayer":    {"score": 35, "category": "safe_to_disable", "rec": "Disable — RealPlayer update checker is not needed at startup."},
    "vlc":           {"score": 10, "category": "safe_to_disable", "rec": "Disable — VLC rarely needs to autostart."},
    "torrent":       {"score": 20, "category": "safe_to_disable", "rec": "Disable — Torrent client autostart is not necessary."},
    "qbittorrent":   {"score": 20, "category": "safe_to_disable", "rec": "Disable — Launch manually when you need it."},
    "winrar":        {"score": 5,  "category": "safe_to_disable", "rec": "Disable — WinRAR startup helper is not needed."},
}

_STARTUP_SYSTEM_KEYWORDS = [
    "securityhealth", "windowsdefender", "windows security", "realtek", "intel hd",
    "amd", "nvidia", "nvsvc", "logitech", "synaptics", "touchpad", "iastoriconlaunch",
    "microsoft", "ctfmon", "onedrivesetup", "inputpersonalization"
]

def _score_startup_item(item):
    """Compute impact score and category for a startup item."""
    name_lower = item["name"].lower()
    path_lower = item.get("path", "").lower()

    # Check system keywords first
    for kw in _STARTUP_SYSTEM_KEYWORDS:
        if kw in name_lower or kw in path_lower:
            return {"impact": "Low", "impact_score": 10, "category": "system_related",
                    "recommendation": "Caution — This appears to be a system or driver service. Disable only if you know what it does."}

    # Check known apps
    for kw, info in _STARTUP_IMPACT_DB.items():
        if kw in name_lower or kw in path_lower:
            impact = "High" if info["score"] >= 35 else "Medium" if info["score"] >= 20 else "Low"
            return {"impact": impact, "impact_score": info["score"],
                    "category": info["category"], "recommendation": info["rec"]}

    # Heuristic: estimate from path
    score = 20
    try:
        exe_path = path_lower.split('"')[1] if '"' in path_lower else path_lower.split()[0]
        exe_path = exe_path.strip()
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            if size_mb > 50:
                score += 20
            elif size_mb > 10:
                score += 10
    except Exception:
        pass

    if "update" in name_lower or "helper" in name_lower or "daemon" in name_lower:
        score += 10
    if "appdata\\local" in path_lower or "appdata\\roaming" in path_lower:
        score += 5

    impact = "High" if score >= 35 else "Medium" if score >= 20 else "Low"
    return {"impact": impact, "impact_score": score,
            "category": "review",
            "recommendation": "Review — Check if this program needs to run at startup. Disable if not essential."}


@bp.route("/api/startup-items/export")
def api_startup_export():
    """Export startup items to JSON."""
    items_resp = api_startup()
    return current_app.response_class(
        items_resp.get_data(as_text=True),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=startup_items.json"}
    )
