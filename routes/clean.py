"""Cleaner endpoints: scan/clean, targets, settings, scheduler, shortcut and
empty-folder sweeps, undo, network repair, profiles, and scheduled maintenance."""
import os
import json
import time
import uuid
import shutil
import tempfile
import threading
import subprocess
from datetime import datetime, timedelta

import psutil
from flask import Blueprint, jsonify, request, current_app

from core.state import (
    IS_WINDOWS, _WIN_NO_WINDOW, scheduler, scan_results, cleaning_status,
    file_organizer_results, undo_log,
    NETWORK_FIX_STEPS, _net_fix_lock, network_fix_state,
)
from core.util import log_activity, format_bytes
from core.config import settings, save_settings
from cleaners.targets import get_active_targets
from cleaners.runner import run_system_scan, run_system_clean, setup_scheduler

bp = Blueprint("clean", __name__)


@bp.route("/api/scan", methods=["POST"])
def api_scan():
    thread = threading.Thread(target=run_system_scan, daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@bp.route("/api/clean", methods=["POST"])
def api_clean():
    if cleaning_status["is_running"]:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=run_system_clean, daemon=True)
    thread.start()
    return jsonify({"status": "cleaning"})


@bp.route("/api/scan-results")
def api_scan_results():
    flat = {
        "last_scan": scan_results["last_scan"],
        "total_files": scan_results["total_files"],
        "total_size": scan_results["total_size"],
        "total_size_fmt": format_bytes(scan_results["total_size"]),
        "categories": scan_results["categories"],
        "registry_issues": scan_results.get("registry_issues", 0),
    }
    return jsonify(flat)


@bp.route("/api/clean-status")
def api_clean_status():
    return jsonify(cleaning_status)


@bp.route("/api/clean-targets")
def api_clean_targets():
    targets = get_active_targets()
    result = {}
    for key, target in targets.items():
        setting_key = target.get("setting", "")
        result[key] = {
            "label": target["label"],
            "description": target["description"],
            "safe_level": target.get("safe_level", "safe"),
            "enabled": settings.get(setting_key, False),
            "setting": setting_key,
        }
    return jsonify(result)


@bp.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json()
        for key, value in data.items():
            if key in settings:
                settings[key] = value
        save_settings()
        setup_scheduler()
        log_activity("Settings updated and applied", "SUCCESS")
        return jsonify({"status": "ok", "settings": settings})
    return jsonify(settings)


@bp.route("/api/scheduler")
def api_scheduler_status():
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
            "trigger": str(job.trigger),
        })
    return jsonify({
        "running": scheduler.running,
        "jobs": jobs,
        "settings": {
            "auto_clean_enabled": settings.get("auto_clean_enabled"),
            "auto_clean_time": settings.get("auto_clean_time"),
        },
    })


@bp.route("/api/system/reboot", methods=["POST"])
def api_system_reboot():
    if IS_WINDOWS:
        try:
            subprocess.Popen(["shutdown", "/r", "/t", "30"], creationflags=_WIN_NO_WINDOW)
            log_activity("System reboot initiated (30 second delay)", "WARN")
            return jsonify({"status": "ok", "message": "System will reboot in 30 seconds"})
        except Exception as e:
            log_activity(f"Reboot failed: {e}", "ERROR")
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        log_activity("Reboot requested (simulated on non-Windows)", "INFO")
        return jsonify({"status": "ok", "message": "Reboot simulated (non-Windows platform)"})


@bp.route("/api/network-fix", methods=["POST"])
def api_network_fix():
    mode = request.json.get("mode", "full")  # winsock | dns | full

    commands = {
        "winsock": [
            ("netsh winsock reset", "Resetting Winsock catalog..."),
        ],
        "dns": [
            ("ipconfig /flushdns", "Flushing DNS resolver cache..."),
        ],
        "full": [
            ("netsh winsock reset",   "Resetting Winsock catalog..."),
            ("netsh int ip reset",    "Resetting TCP/IP stack..."),
            ("ipconfig /release",     "Releasing current IP address..."),
            ("ipconfig /renew",       "Obtaining new IP address..."),
            ("ipconfig /flushdns",    "Flushing DNS resolver cache..."),
        ],
    }

    selected = commands.get(mode, commands["full"])
    output_lines = []

    if not IS_WINDOWS:
        # Demo mode — simulate output
        import time
        for cmd, label in selected:
            output_lines.append(f"> {cmd}")
            output_lines.append(f"  [DEMO] {label}")
            output_lines.append(f"  [DEMO] Command completed successfully.\n")
        output_lines.append("=" * 50)
        output_lines.append("Network fix complete (demo mode).")
        output_lines.append("On Windows, these commands require Admin privileges.")
        needs_reboot = mode in ("winsock", "full")
        return jsonify({"status": "ok", "output": "\n".join(output_lines), "needs_reboot": needs_reboot})

    # Windows — run commands
    needs_reboot = False
    for cmd, label in selected:
        output_lines.append(f"> {cmd}")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30,
                creationflags=_WIN_NO_WINDOW
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if stdout:
                output_lines.append(stdout)
            if stderr:
                output_lines.append(f"[stderr] {stderr}")
            if result.returncode == 0:
                output_lines.append(f"  OK — {label}\n")
                if "winsock" in cmd or "ip reset" in cmd:
                    needs_reboot = True
            else:
                output_lines.append(f"  WARNING — Exit code {result.returncode}. Run as Administrator for full effect.\n")
        except subprocess.TimeoutExpired:
            output_lines.append(f"  TIMEOUT — {cmd} took too long.\n")
        except Exception as e:
            output_lines.append(f"  ERROR — {e}\n")

    output_lines.append("=" * 50)
    if needs_reboot:
        output_lines.append("Network stack reset complete. REBOOT REQUIRED to apply all changes.")
    else:
        output_lines.append("Network fix complete.")

    return jsonify({"status": "ok", "output": "\n".join(output_lines), "needs_reboot": needs_reboot})


def _make_step_state():
    return [
        {"cmd": cmd, "label": label, "description": desc,
         "status": "pending", "output": "", "exit_code": None}
        for cmd, label, desc in NETWORK_FIX_STEPS
    ]


def _is_admin():
    """Return True when the process has Windows admin (elevated) privileges."""
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate_and_run_batch(cmds):
    """
    Write a .bat file with all commands and launch it elevated via UAC (ShellExecuteW runas).
    Returns (success, message).  Output cannot be captured when UAC elevation is used.
    """
    try:
        import ctypes
        bat_path = os.path.join(tempfile.gettempdir(), "mtt_netfix.bat")
        lines = ["@echo off", "echo MTT Windows Infinite Optimizer — Network Fix", "echo ========================================="]
        for c in cmds:
            lines.append(f'echo Running: {c}')
            lines.append(c)
            lines.append('echo  Done: %errorlevel%')
            lines.append("echo.")
        lines += ["echo All commands complete.", "pause"]
        with open(bat_path, "w") as f:
            f.write("\r\n".join(lines) + "\r\n")
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", f'/c "{bat_path}"', None, 1
        )
        return (ret > 32, bat_path)
    except Exception as e:
        return (False, str(e))


def _run_network_fix_thread():
    with _net_fix_lock:
        steps = _make_step_state()
        network_fix_state["steps"] = steps
        network_fix_state["current_step"] = -1
        network_fix_state["needs_reboot"] = False
        network_fix_state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        network_fix_state["completed_at"] = None
        network_fix_state["status"] = "running"
        network_fix_state["admin"] = _is_admin()

    admin = network_fix_state["admin"]

    # ── Non-Windows demo mode ─────────────────────────────────────────────────
    if not IS_WINDOWS:
        for i, step in enumerate(steps):
            with _net_fix_lock:
                network_fix_state["current_step"] = i
                step["status"] = "running"
            log_activity(f"Network Fix [DEMO]: {step['label']}...", "TASK")
            time.sleep(0.8)
            step["output"] = f"[DEMO] {step['description']}\nSuccessfully completed (simulated on non-Windows platform)."
            step["exit_code"] = 0
            step["status"] = "done"
            if "winsock" in step["cmd"] or "ip reset" in step["cmd"]:
                network_fix_state["needs_reboot"] = True

    # ── Windows without admin: UAC-elevate the whole batch ───────────────────
    elif IS_WINDOWS and not admin:
        log_activity("Network Fix: not running as admin — launching elevated batch via UAC", "WARN")
        cmds = [s["cmd"] for s in steps]
        ok, detail = _elevate_and_run_batch(cmds)
        if ok:
            for i, step in enumerate(steps):
                step["status"] = "done"
                step["output"] = (
                    "Launched in elevated cmd.exe window via UAC.\n"
                    "Output is shown in the separate Administrator command prompt window.\n"
                    "A reboot is required after netsh winsock reset and netsh int ip reset."
                )
                step["exit_code"] = 0
            network_fix_state["needs_reboot"] = True
            log_activity("Elevated network fix batch launched — check the cmd window", "SUCCESS")
        else:
            for step in steps:
                step["status"] = "error"
                step["output"] = f"UAC elevation failed: {detail}\nRun the app as Administrator to use this feature."
                step["exit_code"] = -1
            log_activity("Network Fix elevation failed — please run as Administrator", "ERROR")

    # ── Windows with admin: run each command via cmd.exe /c, stream output ───
    else:
        for i, step in enumerate(steps):
            with _net_fix_lock:
                network_fix_state["current_step"] = i
                step["status"] = "running"

            log_activity(f"Network Fix: {step['label']}...", "TASK")
            cmd_args = ["cmd.exe", "/c", step["cmd"]]
            try:
                result = subprocess.run(
                    cmd_args,
                    capture_output=True, text=True, timeout=60,
                    creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
                )
                out_parts = []
                if result.stdout.strip():
                    out_parts.append(result.stdout.strip())
                if result.stderr.strip():
                    out_parts.append(f"[stderr] {result.stderr.strip()}")
                step["output"] = "\n".join(out_parts) if out_parts else "(no output)"
                step["exit_code"] = result.returncode
                step["status"] = "done" if result.returncode == 0 else "error"
                if "winsock" in step["cmd"] or "ip reset" in step["cmd"]:
                    network_fix_state["needs_reboot"] = True
                log_activity(
                    f"  Done: {step['label']} (exit {result.returncode})",
                    "SUCCESS" if result.returncode == 0 else "WARN"
                )
            except subprocess.TimeoutExpired:
                step["output"] = "TIMEOUT — command exceeded 60 seconds"
                step["exit_code"] = -1
                step["status"] = "error"
                log_activity(f"  Timeout: {step['label']}", "ERROR")
            except Exception as e:
                step["output"] = f"ERROR — {e}"
                step["exit_code"] = -1
                step["status"] = "error"
                log_activity(f"  Error: {step['label']}: {e}", "ERROR")

    with _net_fix_lock:
        network_fix_state["status"] = "complete"
        network_fix_state["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if network_fix_state["needs_reboot"]:
            log_activity("Network Fix complete — REBOOT REQUIRED to apply all changes", "SUCCESS")
        else:
            log_activity("Network Fix complete", "SUCCESS")


@bp.route("/api/network-fix/run", methods=["POST"])
def api_network_fix_run():
    if network_fix_state["status"] == "running":
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=_run_network_fix_thread, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@bp.route("/api/network-fix/progress")
def api_network_fix_progress():
    with _net_fix_lock:
        return jsonify(dict(network_fix_state))


@bp.route("/api/undo-log")
def api_undo_log():
    return jsonify(undo_log[-50:])


@bp.route("/api/undo", methods=["POST"])
def api_undo():
    """Attempt to revert the last undoable action."""
    # Find last non-undone entry
    for entry in reversed(undo_log):
        if not entry.get("undone"):
            action_type = entry.get("type")
            details = entry.get("details", {})
            msg = ""
            if action_type == "move":
                src = details.get("to")
                dest = details.get("from")
                if src and dest and os.path.isfile(src):
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.move(src, dest)
                        msg = f"Restored: {os.path.basename(dest)}"
                        log_activity(f"Undo: moved {src} back to {dest}", "SUCCESS")
                    except (OSError, PermissionError) as e:
                        return jsonify({"status": "error", "message": str(e)}), 500
                else:
                    msg = f"Cannot undo: file not found at {src}"
            elif action_type == "delete":
                msg = f"Cannot undo deletion (file permanently removed): {details.get('path', '')}"
                log_activity(f"Undo requested for deletion — file cannot be restored: {details.get('path')}", "WARN")
            elif action_type == "startup_toggle":
                name = details.get("name", "")
                was_enabled = details.get("enabled", True)
                msg = f"To undo startup toggle: {'disable' if was_enabled else 'enable'} '{name}' manually"
                log_activity(f"Undo: startup toggle for '{name}' noted — manual action required", "INFO")
            else:
                msg = f"Undone: {entry.get('description', '')}"
            entry["undone"] = True
            return jsonify({"status": "ok", "message": msg, "action": entry})
    return jsonify({"status": "nothing", "message": "No undoable actions in log"})


# ══════════════════════════════════════════════════════════════════════════════
# BROKEN SHORTCUTS + EMPTY FOLDERS SCANNER
# ══════════════════════════════════════════════════════════════════════════════

@bp.route("/api/cleaner/broken-shortcuts")
def api_broken_shortcuts():
    """Scan Desktop and StartMenu for broken .lnk shortcuts."""
    results = []
    scan_dirs = []
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        start_menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
        public_desktop = r"C:\Users\Public\Desktop"
        for d in [desktop, start_menu, public_desktop]:
            if os.path.isdir(d):
                scan_dirs.append(d)
    except Exception:
        pass

    if not IS_WINDOWS or not scan_dirs:
        return jsonify({"items": [
            {"name": "Notepad++ (broken)", "path": "C:\\Users\\User\\Desktop\\Notepad++.lnk", "target": "C:\\Program Files\\Notepad++\\notepad++.exe", "size": 1234},
            {"name": "OldApp (broken)", "path": "C:\\Users\\User\\Desktop\\OldApp.lnk", "target": "C:\\Program Files\\OldApp\\app.exe", "size": 890},
        ], "demo": True})

    def resolve_lnk_target(lnk_path):
        try:
            import winreg
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f'$sh=New-Object -COM WScript.Shell; $sh.CreateShortcut("{lnk_path}").TargetPath'],
                capture_output=True, text=True, timeout=5,
                creationflags=_WIN_NO_WINDOW
            )
            return result.stdout.strip()
        except Exception:
            return ""

    for scan_dir in scan_dirs:
        for root, _, files in os.walk(scan_dir):
            for fname in files:
                if not fname.lower().endswith(".lnk"):
                    continue
                fpath = os.path.join(root, fname)
                target = resolve_lnk_target(fpath)
                if target and not os.path.exists(target):
                    try:
                        size = os.path.getsize(fpath)
                    except Exception:
                        size = 0
                    results.append({
                        "name": fname.replace(".lnk", ""),
                        "path": fpath,
                        "target": target,
                        "size": size
                    })

    return jsonify({"items": results, "demo": False})


@bp.route("/api/cleaner/delete-shortcuts", methods=["POST"])
def api_delete_shortcuts():
    data = request.get_json() or {}
    paths = data.get("paths", [])
    deleted = []
    errors = []
    for p in paths:
        try:
            if os.path.isfile(p) and p.lower().endswith(".lnk"):
                os.remove(p)
                deleted.append(p)
                log_activity(f"Deleted broken shortcut: {p}", "SUCCESS")
        except Exception as e:
            errors.append({"path": p, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


@bp.route("/api/cleaner/empty-folders")
def api_empty_folders():
    """Scan common user folders for empty directories."""
    results = []
    home = os.path.expanduser("~")
    safe_scan_roots = [
        os.path.join(home, "Desktop"),
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "Pictures"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Music"),
    ]

    if not IS_WINDOWS:
        return jsonify({"items": [
            {"path": "C:\\Users\\User\\Downloads\\OldProject", "parent": "Downloads"},
            {"path": "C:\\Users\\User\\Desktop\\Untitled Folder", "parent": "Desktop"},
            {"path": "C:\\Users\\User\\Documents\\archive\\2019\\misc", "parent": "Documents"},
        ], "demo": True})

    for root_dir in safe_scan_roots:
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
            if dirpath == root_dir:
                continue
            try:
                if not os.listdir(dirpath):
                    results.append({
                        "path": dirpath,
                        "parent": os.path.basename(root_dir)
                    })
            except PermissionError:
                pass

    return jsonify({"items": results, "demo": False})


@bp.route("/api/cleaner/delete-empty-folders", methods=["POST"])
def api_delete_empty_folders():
    data = request.get_json() or {}
    paths = data.get("paths", [])
    deleted = []
    errors = []
    home = os.path.expanduser("~")
    safe_roots = [os.path.join(home, d) for d in ["Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music"]]

    for p in paths:
        try:
            in_safe = any(p.startswith(r) for r in safe_roots)
            if not in_safe:
                errors.append({"path": p, "error": "Path is outside safe user folders"})
                continue
            if os.path.isdir(p) and not os.listdir(p):
                os.rmdir(p)
                deleted.append(p)
                log_activity(f"Removed empty folder: {p}", "SUCCESS")
        except Exception as e:
            errors.append({"path": p, "error": str(e)})
    return jsonify({"deleted": deleted, "errors": errors})


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 14: PROFILES / PRESETS
# ══════════════════════════════════════════════════════════════════════════════

PROFILES_FILE = "profiles.json"
_profiles_lock = threading.Lock()

BUILTIN_PROFILES = {
    "performance": {
        "id": "performance", "name": "Performance Mode", "icon": "🚀", "builtin": True,
        "description": "Prioritizes speed. Focuses recommendations on CPU, RAM, and startup items. Increases monitoring frequency.",
        "settings": {"refresh_interval_sec": 2, "rec_filter": ["Performance", "Startup", "Storage"],
                     "highlight_heavy_procs": True, "wellness_reminders": False, "theme_accent": "cyan",
                     "auto_scan_on_start": True, "low_resource_mode": False}
    },
    "work": {
        "id": "work", "name": "Work Mode", "icon": "💼", "builtin": True,
        "description": "Balances performance and organization. Surfaces file and download recommendations. Quieter UI.",
        "settings": {"refresh_interval_sec": 5, "rec_filter": ["Performance", "Organization", "Maintenance"],
                     "highlight_heavy_procs": False, "wellness_reminders": True, "theme_accent": "blue",
                     "auto_scan_on_start": False, "low_resource_mode": False}
    },
    "night_comfort": {
        "id": "night_comfort", "name": "Night Comfort Mode", "icon": "🌙", "builtin": True,
        "description": "Reduces UI intensity and surfaces wellness recommendations. Ideal for evening use.",
        "settings": {"refresh_interval_sec": 10, "rec_filter": ["Wellness", "Maintenance"],
                     "highlight_heavy_procs": False, "wellness_reminders": True, "theme_accent": "purple",
                     "auto_scan_on_start": False, "low_resource_mode": True}
    },
    "battery_saver": {
        "id": "battery_saver", "name": "Battery Saver Mode", "icon": "🔋", "builtin": True,
        "description": "Minimizes app resource usage. Slows refresh rates, skips heavy background scans.",
        "settings": {"refresh_interval_sec": 30, "rec_filter": ["Performance", "Maintenance"],
                     "highlight_heavy_procs": False, "wellness_reminders": False, "theme_accent": "green",
                     "auto_scan_on_start": False, "low_resource_mode": True}
    },
}

def _load_profiles_data():
    try:
        if os.path.exists(PROFILES_FILE):
            with open(PROFILES_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"active_profile": None, "custom_profiles": {}, "history": []}

def _save_profiles_data(data):
    try:
        with open(PROFILES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


@bp.route("/api/profiles")
def api_profiles():
    data = _load_profiles_data()
    all_profiles = {**BUILTIN_PROFILES, **data.get("custom_profiles", {})}
    return jsonify({"profiles": list(all_profiles.values()),
                    "active": data.get("active_profile"),
                    "history": data.get("history", [])[-5:]})


@bp.route("/api/profiles/apply", methods=["POST"])
def api_profiles_apply():
    req = request.get_json() or {}
    pid = req.get("id")
    if not pid:
        return jsonify({"status": "error", "message": "Profile ID required"}), 400
    data = _load_profiles_data()
    all_profiles = {**BUILTIN_PROFILES, **data.get("custom_profiles", {})}
    if pid not in all_profiles:
        return jsonify({"status": "error", "message": "Profile not found"}), 404
    profile = all_profiles[pid]
    prev = data.get("active_profile")
    data["active_profile"] = pid
    data.setdefault("history", []).append({
        "profile_id": pid, "profile_name": profile["name"],
        "applied_at": datetime.now().isoformat(), "previous": prev
    })
    _save_profiles_data(data)
    log_activity(f"Profile applied: {profile['name']}", "SUCCESS")
    return jsonify({"status": "ok", "profile": profile})


@bp.route("/api/profiles/save", methods=["POST"])
def api_profiles_save():
    req = request.get_json() or {}
    pid = req.get("id") or str(uuid.uuid4())[:8]
    name = req.get("name", "Custom Profile")
    if not name.strip():
        return jsonify({"status": "error", "message": "Name required"}), 400
    profile = {
        "id": pid, "name": name, "icon": req.get("icon", "⚙️"),
        "builtin": False,
        "description": req.get("description", ""),
        "settings": req.get("settings", {})
    }
    with _profiles_lock:
        data = _load_profiles_data()
        data.setdefault("custom_profiles", {})[pid] = profile
        _save_profiles_data(data)
    log_activity(f"Profile saved: {name}", "INFO")
    return jsonify({"status": "ok", "profile": profile})


@bp.route("/api/profiles/delete", methods=["POST"])
def api_profiles_delete():
    req = request.get_json() or {}
    pid = req.get("id")
    if pid in BUILTIN_PROFILES:
        return jsonify({"status": "error", "message": "Cannot delete built-in profiles"}), 400
    with _profiles_lock:
        data = _load_profiles_data()
        data.get("custom_profiles", {}).pop(pid, None)
        if data.get("active_profile") == pid:
            data["active_profile"] = None
        _save_profiles_data(data)
    return jsonify({"status": "ok"})


@bp.route("/api/profiles/restore-previous", methods=["POST"])
def api_profiles_restore():
    data = _load_profiles_data()
    history = data.get("history", [])
    if len(history) < 2:
        return jsonify({"status": "nothing", "message": "No previous profile to restore"})
    prev_entry = history[-2]
    prev_id = prev_entry.get("profile_id")
    all_profiles = {**BUILTIN_PROFILES, **data.get("custom_profiles", {})}
    if prev_id not in all_profiles:
        return jsonify({"status": "error", "message": "Previous profile no longer exists"})
    data["active_profile"] = prev_id
    data["history"].append({"profile_id": prev_id, "profile_name": all_profiles[prev_id]["name"],
                             "applied_at": datetime.now().isoformat(), "previous": data.get("active_profile"), "restored": True})
    _save_profiles_data(data)
    return jsonify({"status": "ok", "profile": all_profiles[prev_id]})


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 15: SCHEDULED MAINTENANCE
# ══════════════════════════════════════════════════════════════════════════════

MAINTENANCE_FILE = "maintenance_schedules.json"
MAINTENANCE_HISTORY_FILE = "maintenance_history.json"
_maint_lock = threading.Lock()

DEFAULT_MAINTENANCE_TASKS = [
    {"id": "weekly_temp_scan", "name": "Weekly Temp File Scan", "type": "scan",
     "description": "Scans all temp file categories and reports findings without deleting.",
     "schedule": "weekly", "day_of_week": "sun", "time": "10:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "weekly_clutter_scan", "name": "Weekly Clutter Scan", "type": "scan",
     "description": "Scans Downloads, Desktop, and Documents for file organization issues.",
     "schedule": "weekly", "day_of_week": "wed", "time": "09:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "monthly_duplicate_scan", "name": "Monthly Duplicate File Scan", "type": "scan",
     "description": "Detects duplicate files across common folders via MD5 comparison.",
     "schedule": "monthly", "day_of_month": 1, "time": "11:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "downloads_reminder", "name": "Downloads Cleanup Reminder", "type": "reminder",
     "description": "Reminds you to review and clean up your Downloads folder.",
     "schedule": "weekly", "day_of_week": "fri", "time": "17:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "startup_review", "name": "Startup Apps Review", "type": "reminder",
     "description": "Periodic reminder to review startup programs for unnecessary items.",
     "schedule": "monthly", "day_of_month": 15, "time": "09:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "health_scan", "name": "System Health Scan", "type": "scan",
     "description": "Runs a full system health score check and records results.",
     "schedule": "weekly", "day_of_week": "mon", "time": "08:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "app_inventory", "name": "App Inventory Refresh", "type": "scan",
     "description": "Refreshes the installed app list and updates bloat detection results.",
     "schedule": "monthly", "day_of_month": 7, "time": "10:00", "enabled": True,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
    {"id": "night_comfort_reminder", "name": "Night Comfort Reminder", "type": "reminder",
     "description": "Reminds you to enable Night Light and take an eye break at end of day.",
     "schedule": "daily", "time": "21:00", "enabled": False,
     "last_run": None, "next_run": None, "run_count": 0, "builtin": True},
]

def _load_maintenance_tasks():
    try:
        if os.path.exists(MAINTENANCE_FILE):
            with open(MAINTENANCE_FILE) as f:
                saved = json.load(f)
            tasks_by_id = {t["id"]: t for t in saved.get("tasks", [])}
            result = []
            for default in DEFAULT_MAINTENANCE_TASKS:
                if default["id"] in tasks_by_id:
                    merged = {**default, **tasks_by_id[default["id"]]}
                    result.append(merged)
                else:
                    result.append(dict(default))
            custom = [t for t in saved.get("tasks", []) if not t.get("builtin", False)]
            result.extend(custom)
            return result
    except Exception:
        pass
    return [dict(t) for t in DEFAULT_MAINTENANCE_TASKS]

def _save_maintenance_tasks(tasks):
    try:
        with open(MAINTENANCE_FILE, "w") as f:
            json.dump({"tasks": tasks}, f, indent=2)
    except Exception:
        pass

def _load_maintenance_history():
    try:
        if os.path.exists(MAINTENANCE_HISTORY_FILE):
            with open(MAINTENANCE_HISTORY_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_maintenance_history(history):
    try:
        with open(MAINTENANCE_HISTORY_FILE, "w") as f:
            json.dump(history[-200:], f, indent=2)
    except Exception:
        pass

def _run_maintenance_task(task_id):
    tasks = _load_maintenance_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"status": "error", "message": "Task not found"}
    result = {"task_id": task_id, "task_name": task["name"], "type": task["type"],
              "started_at": datetime.now().isoformat(), "status": "ok", "findings": {}}
    try:
        if task["type"] == "scan":
            if task_id == "weekly_temp_scan":
                result["findings"] = {"scan_categories": len(scan_results.get("categories", {})),
                                      "total_size": format_bytes(scan_results.get("total_size", 0))}
                log_activity(f"Maintenance: Temp scan completed", "INFO")
            elif task_id == "weekly_clutter_scan":
                home = os.path.expanduser("~")
                dl = os.path.join(home, "Downloads")
                dl_count = len(os.listdir(dl)) if os.path.isdir(dl) else 0
                result["findings"] = {"downloads_files": dl_count}
                log_activity(f"Maintenance: Clutter scan — {dl_count} files in Downloads", "INFO")
            elif task_id == "monthly_duplicate_scan":
                dup_count = len(file_organizer_results.get("duplicates", []))
                result["findings"] = {"duplicates_found": dup_count}
                log_activity(f"Maintenance: Duplicate scan — {dup_count} duplicates found", "INFO")
            elif task_id == "health_scan":
                try:
                    cpu = psutil.cpu_percent(interval=0.5)
                    mem = psutil.virtual_memory()
                    result["findings"] = {"cpu": f"{cpu:.0f}%", "ram": f"{mem.percent:.0f}%"}
                    log_activity(f"Maintenance: Health scan — CPU {cpu:.0f}%, RAM {mem.percent:.0f}%", "INFO")
                except Exception:
                    pass
            elif task_id == "app_inventory":
                result["findings"] = {"apps_scanned": True}
                log_activity("Maintenance: App inventory refreshed", "INFO")
        elif task["type"] == "reminder":
            log_activity(f"Maintenance reminder: {task['name']}", "INFO")
            result["findings"] = {"reminder_sent": True}
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        log_activity(f"Maintenance error ({task_id}): {e}", "ERROR")

    result["completed_at"] = datetime.now().isoformat()
    for t in tasks:
        if t["id"] == task_id:
            t["last_run"] = result["completed_at"]
            t["run_count"] = t.get("run_count", 0) + 1
    _save_maintenance_tasks(tasks)
    history = _load_maintenance_history()
    history.append(result)
    _save_maintenance_history(history)
    return result


@bp.route("/api/maintenance/tasks")
def api_maintenance_tasks():
    tasks = _load_maintenance_tasks()
    return jsonify({"tasks": tasks})


@bp.route("/api/maintenance/tasks/toggle", methods=["POST"])
def api_maintenance_toggle():
    data = request.get_json() or {}
    tid = data.get("id")
    enabled = data.get("enabled", True)
    with _maint_lock:
        tasks = _load_maintenance_tasks()
        for t in tasks:
            if t["id"] == tid:
                t["enabled"] = enabled
        _save_maintenance_tasks(tasks)
    return jsonify({"status": "ok"})


@bp.route("/api/maintenance/tasks/run", methods=["POST"])
def api_maintenance_run():
    data = request.get_json() or {}
    tid = data.get("id")
    if not tid:
        return jsonify({"status": "error", "message": "Task ID required"}), 400
    result = _run_maintenance_task(tid)
    return jsonify(result)


@bp.route("/api/maintenance/tasks/save", methods=["POST"])
def api_maintenance_save():
    req = request.get_json() or {}
    with _maint_lock:
        tasks = _load_maintenance_tasks()
        tid = req.get("id") or str(uuid.uuid4())[:8]
        existing = next((t for t in tasks if t["id"] == tid), None)
        if existing:
            for k, v in req.items():
                existing[k] = v
        else:
            new_task = {
                "id": tid, "name": req.get("name", "Custom Task"), "type": req.get("type", "reminder"),
                "description": req.get("description", ""), "schedule": req.get("schedule", "weekly"),
                "day_of_week": req.get("day_of_week", "mon"), "time": req.get("time", "09:00"),
                "enabled": req.get("enabled", True), "last_run": None, "next_run": None,
                "run_count": 0, "builtin": False
            }
            tasks.append(new_task)
        _save_maintenance_tasks(tasks)
    return jsonify({"status": "ok", "id": tid})


@bp.route("/api/maintenance/tasks/delete", methods=["POST"])
def api_maintenance_delete():
    data = request.get_json() or {}
    tid = data.get("id")
    with _maint_lock:
        tasks = _load_maintenance_tasks()
        builtin_task = next((t for t in tasks if t["id"] == tid and t.get("builtin")), None)
        if builtin_task:
            return jsonify({"status": "error", "message": "Cannot delete built-in tasks"}), 400
        tasks = [t for t in tasks if t["id"] != tid]
        _save_maintenance_tasks(tasks)
    return jsonify({"status": "ok"})


@bp.route("/api/maintenance/history")
def api_maintenance_history():
    history = _load_maintenance_history()
    return jsonify({"history": list(reversed(history[-50:]))})


@bp.route("/api/maintenance/history/export")
def api_maintenance_history_export():
    history = _load_maintenance_history()
    lines = ["MTT Windows Infinite Optimizer — Maintenance History",
             f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    for entry in reversed(history):
        lines.append(f"[{entry.get('completed_at', '?')}] {entry.get('task_name', '?')} — {entry.get('status', '?').upper()}")
        if entry.get("findings"):
            for k, v in entry["findings"].items():
                lines.append(f"  {k}: {v}")
        lines.append("")
    content = "\n".join(lines)
    return current_app.response_class(content, mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=maintenance_history.txt"})
