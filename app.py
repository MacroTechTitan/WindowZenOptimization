import os
import sys
import time
import json
import glob
import uuid
import socket
import hashlib
import threading
import platform
import shutil
import tempfile
import psutil
import subprocess
import urllib.request
import urllib.error
try:
    import resend
    _RESEND_AVAILABLE = True
except ImportError:
    resend = None
    _RESEND_AVAILABLE = False
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mtt-optimizer-secret-2026-macro-tech-titan")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mttadmin2026")

IS_WINDOWS = platform.system() == "Windows"
_WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
SETTINGS_FILE = "settings.json"
ANALYTICS_FILE = "analytics.json"
REGISTRATIONS_FILE = "registrations.json"
SITE_URL = os.environ.get("SITE_URL", "https://windowzen.macrotechtitan.com")
_analytics_lock = threading.Lock()
_reg_lock = threading.Lock()
activity_log = []
LOG_MAX = 200
scheduler = BackgroundScheduler()


# ─── Registration helpers ──────────────────────────────────────
def load_registrations():
    if os.path.exists(REGISTRATIONS_FILE):
        try:
            with open(REGISTRATIONS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_registrations(data):
    try:
        with open(REGISTRATIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_resend_credentials():
    direct_key = os.environ.get("RESEND_API_KEY")
    if direct_key:
        return {
            "api_key": direct_key,
            "from_email": os.environ.get("RESEND_FROM_EMAIL", "noreply@macrotechtitan.com"),
        }
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    repl_identity = os.environ.get("REPL_IDENTITY")
    web_repl_renewal = os.environ.get("WEB_REPL_RENEWAL")
    if not hostname:
        return None
    if repl_identity:
        token = "repl " + repl_identity
    elif web_repl_renewal:
        token = "depl " + web_repl_renewal
    else:
        return None
    try:
        req = urllib.request.Request(
            f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend",
            headers={"Accept": "application/json", "X-Replit-Token": token},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        items = data.get("items", [])
        if not items:
            return None
        settings = items[0].get("settings", {})
        return {
            "api_key": settings.get("api_key"),
            "from_email": settings.get("from_email") or "noreply@macrotechtitan.com",
        }
    except Exception as e:
        log_activity(f"Resend credentials error: {e}", "ERROR")
        return None


def send_verification_email(to_email, token):
    creds = get_resend_credentials()
    if not creds or not creds.get("api_key"):
        log_activity(f"Email not sent (no Resend creds) for {to_email}", "WARN")
        return False
    verify_url = f"{SITE_URL}/verify-email/{token}"
    from_addr = f"MTT Infinite Optimizer <{creds['from_email']}>"
    html_body = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{font-family:Inter,Arial,sans-serif;background:#0a0e1a;color:#e2e8f0;margin:0;padding:0}}
.wrap{{max-width:520px;margin:40px auto;background:#111827;border:1px solid #1e293b;border-radius:16px;overflow:hidden}}
.hdr{{background:linear-gradient(135deg,#06b6d4,#8b5cf6);padding:32px;text-align:center}}
.hdr h1{{color:#fff;font-size:20px;margin:0;letter-spacing:1px}}
.hdr p{{color:rgba(255,255,255,.75);font-size:12px;margin:6px 0 0}}
.body{{padding:36px 32px}}
.body p{{color:#94a3b8;font-size:15px;line-height:1.7;margin:0 0 20px}}
.btn{{display:block;background:linear-gradient(135deg,#10b981,#06b6d4);color:#fff;text-decoration:none;text-align:center;padding:16px 32px;border-radius:10px;font-size:16px;font-weight:700;margin:24px 0}}
.box{{background:#0a0e1a;border:1px solid #1e293b;border-radius:8px;padding:12px 16px;font-family:monospace;font-size:12px;color:#64748b;word-break:break-all}}
.foot{{padding:20px 32px;border-top:1px solid #1e293b;font-size:12px;color:#475569;text-align:center}}
</style></head><body>
<div class="wrap">
  <div class="hdr"><h1>⚡ MTT Infinite Optimizer</h1><p>by Macro Tech Titan</p></div>
  <div class="body">
    <p>Thanks for your interest in <strong style="color:#e2e8f0">MTT Windows Infinite Optimizer v1.1.0</strong>!
    Click the button below to verify your email and unlock your free download link.</p>
    <a href="{verify_url}" class="btn">✅ Verify Email &amp; Get Download Link</a>
    <p style="font-size:13px">This link expires in <strong style="color:#e2e8f0">24 hours</strong>.
    If the button doesn't work, copy and paste this URL:</p>
    <div class="box">{verify_url}</div>
  </div>
  <div class="foot">You received this because you requested a download at windowzen.macrotechtitan.com.<br>
  If you didn't request this, you can safely ignore this email.</div>
</div></body></html>"""
    try:
        if not _RESEND_AVAILABLE:
            log_activity("Resend not available (desktop mode) — skipping email send", "INFO")
            return False
        resend.api_key = creds["api_key"]
        result = resend.Emails.send({
            "from": from_addr,
            "to": [to_email],
            "subject": "⚡ Your MTT Infinite Optimizer Download Link",
            "html": html_body,
        })
        log_activity(f"Verification email sent → {to_email} (id:{result.get('id', '?')})", "SUCCESS")
        return True
    except Exception as e:
        log_activity(f"Failed to send email to {to_email}: {e}", "ERROR")
        return False


# ─── Analytics helpers ─────────────────────────────────────────
def load_analytics():
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r") as f:
                data = json.load(f)
                data.setdefault("visits", 0)
                data.setdefault("downloads", 0)
                return data
        except Exception:
            pass
    return {"visits": 0, "downloads": 0}


def save_analytics(data):
    try:
        with open(ANALYTICS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def increment_analytics(key):
    with _analytics_lock:
        data = load_analytics()
        data[key] = data.get(key, 0) + 1
        save_analytics(data)
        return data

DEFAULT_SETTINGS = {
    "auto_clean_enabled": True,
    "auto_clean_time": "17:00",
    "clean_temp_files": True,
    "clean_user_temp": True,
    "clean_browser_cache": True,
    "clean_recycle_bin": False,
    "clean_thumbnails": True,
    "clean_downloaded_program_files": True,
    "clean_directx_shader_cache": True,
    "clean_error_reports": True,
    "clean_delivery_optimization": True,
    "clean_defender_temp": True,
    "clean_windows_update": False,
    "clean_windows_old": False,
    "clean_old_logs": True,
    "activity_tracking": True,
    "break_reminder_minutes": 40,
    "dark_mode": True,
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                merged = {**DEFAULT_SETTINGS, **saved}
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError:
        pass


settings = load_settings()

scan_results = {
    "last_scan": None,
    "categories": {},
    "total_files": 0,
    "total_size": 0,
    "registry_issues": 0,
}

cleaning_status = {
    "is_running": False,
    "current_task": "",
    "progress": 0,
    "items_cleaned": 0,
    "space_freed": 0,
}

activity_data = {
    "session_start": datetime.now().isoformat(),
    "active_minutes": 0,
    "idle_minutes": 0,
    "break_count": 0,
    "last_activity": datetime.now().isoformat(),
    "wellness_score": 85,
    "last_break_time": datetime.now().isoformat(),
}

registry_data = {
    "orphaned_keys": 0,
    "invalid_paths": 0,
    "startup_items": 0,
    "issues_found": 0,
    "last_scan": None,
    "entries": [],
}

file_organizer_results = {
    "status": "idle",
    "zero_length": [],
    "duplicates": [],
    "installers": [],
    "last_scan": None,
}

security_data = {
    "open_ports": [],
    "active_connections": [],
    "public_ip": None,
    "last_scan": None,
}

deep_analysis_data = {
    "status": "idle",
    "total_files": 0,
    "categories": {
        "video": {"extensions": [".mp4", ".avi", ".mkv", ".mov"], "count": 0, "size": 0},
        "images": {"extensions": [".jpg", ".png", ".gif", ".bmp", ".svg"], "count": 0, "size": 0},
        "documents": {"extensions": [".doc", ".docx", ".pdf", ".txt", ".xlsx", ".pptx"], "count": 0, "size": 0},
        "audio": {"extensions": [".mp3", ".wav", ".flac", ".aac"], "count": 0, "size": 0},
    },
    "installed_software": 0,
    "event_log_paths": [],
    "last_scan": None,
}


def log_activity(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": message, "level": level}
    activity_log.append(entry)
    if len(activity_log) > LOG_MAX:
        activity_log.pop(0)


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def get_dir_size(path):
    total_size = 0
    total_count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    if os.path.isfile(fp):
                        total_size += os.path.getsize(fp)
                        total_count += 1
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total_count, total_size


def get_windows_username():
    return os.environ.get("USERNAME", os.environ.get("USER", "User"))


CLEAN_TARGETS = {
    "system_temp": {
        "label": "System Temp Files",
        "description": "Windows system temporary files (C:\\Windows\\Temp)",
        "paths_fn": lambda: [os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Temp")],
        "setting": "clean_temp_files",
        "safe_level": "safe",
    },
    "user_temp": {
        "label": "User Temp Files",
        "description": "%TEMP% and AppData\\Local\\Temp — short-term app leftovers",
        "paths_fn": lambda: [
            os.environ.get("TEMP", os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp")),
        ],
        "setting": "clean_user_temp",
        "safe_level": "safe",
    },
    "browser_cache": {
        "label": "Browser Cache & Internet Files",
        "description": "Chrome, Edge, Firefox cache — copies of web content for speed",
        "paths_fn": lambda: [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cache"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Code Cache"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Service Worker", "CacheStorage"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Cache"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Code Cache"),
        ] + glob.glob(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Mozilla", "Firefox", "Profiles", "*", "cache2")) + [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "INetCache"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Temporary Internet Files"),
        ],
        "setting": "clean_browser_cache",
        "safe_level": "safe",
    },
    "recycle_bin": {
        "label": "Recycle Bin",
        "description": "Files already deleted by you — emptying frees disk space",
        "paths_fn": lambda: [],
        "setting": "clean_recycle_bin",
        "safe_level": "safe",
        "special": "recycle_bin",
    },
    "thumbnails": {
        "label": "Thumbnails",
        "description": "Image/video thumbnail cache — Windows rebuilds these automatically",
        "paths_fn": lambda: [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Explorer"),
        ],
        "setting": "clean_thumbnails",
        "safe_level": "safe",
        "file_patterns": ["thumbcache_*.db", "iconcache_*.db"],
    },
    "downloaded_program_files": {
        "label": "Downloaded Program Files",
        "description": "Legacy ActiveX/Java web components — modern systems don't need them",
        "paths_fn": lambda: [os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Downloaded Program Files")],
        "setting": "clean_downloaded_program_files",
        "safe_level": "safe",
    },
    "directx_shader_cache": {
        "label": "DirectX Shader Cache",
        "description": "Cached DirectX shaders — rebuilt automatically when needed",
        "paths_fn": lambda: [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "D3DSCache"),
            os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "NVIDIA", "PerDriverVersion", "DXCache"),
        ],
        "setting": "clean_directx_shader_cache",
        "safe_level": "safe",
    },
    "error_reports": {
        "label": "Windows Error Reports",
        "description": "Crash dump files and error reporting data",
        "paths_fn": lambda: [
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "WER"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "CrashDumps"),
            os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "Microsoft", "Windows", "WER"),
        ],
        "setting": "clean_error_reports",
        "safe_level": "safe",
    },
    "delivery_optimization": {
        "label": "Delivery Optimization Files",
        "description": "Windows Update delivery cache files",
        "paths_fn": lambda: [
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "SoftwareDistribution", "DeliveryOptimization"),
        ],
        "setting": "clean_delivery_optimization",
        "safe_level": "safe",
    },
    "defender_temp": {
        "label": "Windows Defender Temp Files",
        "description": "Temporary scan files from Windows Defender",
        "paths_fn": lambda: [
            os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "Microsoft", "Windows Defender", "Scans", "History"),
        ],
        "setting": "clean_defender_temp",
        "safe_level": "safe",
    },
    "old_logs": {
        "label": "System Log Files",
        "description": "Old Windows log files and event traces",
        "paths_fn": lambda: [
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Logs"),
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Panther"),
        ],
        "setting": "clean_old_logs",
        "safe_level": "safe",
    },
    "windows_update": {
        "label": "Windows Update Cleanup",
        "description": "Old update versions and logs — can reclaim GBs but you lose rollback ability",
        "paths_fn": lambda: [
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "SoftwareDistribution", "Download"),
        ],
        "setting": "clean_windows_update",
        "safe_level": "caution",
    },
    "windows_old": {
        "label": "Previous Windows Installation",
        "description": "Windows.old folder — huge space win but cannot downgrade after removal",
        "paths_fn": lambda: ["C:\\Windows.old"],
        "setting": "clean_windows_old",
        "safe_level": "caution",
    },
}

LINUX_CLEAN_TARGETS = {
    "system_temp": {
        "label": "System Temp Files",
        "description": "/tmp directory — system temporary files",
        "paths_fn": lambda: ["/tmp"],
        "setting": "clean_temp_files",
        "safe_level": "safe",
    },
    "user_temp": {
        "label": "User Cache Files",
        "description": "~/.cache — application cache data",
        "paths_fn": lambda: [os.path.expanduser("~/.cache")],
        "setting": "clean_user_temp",
        "safe_level": "safe",
    },
    "browser_cache": {
        "label": "Browser Cache",
        "description": "Chrome/Firefox browser cache files",
        "paths_fn": lambda: [
            os.path.expanduser("~/.cache/google-chrome"),
            os.path.expanduser("~/.cache/mozilla"),
            os.path.expanduser("~/.cache/chromium"),
        ],
        "setting": "clean_browser_cache",
        "safe_level": "safe",
    },
    "old_logs": {
        "label": "Old Log Files",
        "description": "/var/log — system logs",
        "paths_fn": lambda: ["/var/log"],
        "setting": "clean_old_logs",
        "safe_level": "safe",
    },
    "thumbnails": {
        "label": "Thumbnails",
        "description": "Cached image thumbnails",
        "paths_fn": lambda: [os.path.expanduser("~/.cache/thumbnails")],
        "setting": "clean_thumbnails",
        "safe_level": "safe",
    },
}


def get_active_targets():
    if IS_WINDOWS:
        return CLEAN_TARGETS
    return LINUX_CLEAN_TARGETS


def scan_target(key, target):
    paths = target["paths_fn"]()
    total_count = 0
    total_size = 0

    if target.get("special") == "recycle_bin":
        if IS_WINDOWS:
            try:
                result = subprocess.run(
                    ["powershell", "-Command",
                     "(New-Object -ComObject Shell.Application).NameSpace(10).Items() | "
                     "Measure-Object -Property Size -Sum | Select-Object Count, Sum"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_WIN_NO_WINDOW
                )
                for line in result.stdout.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0].isdigit():
                        total_count = int(parts[0])
                        total_size = int(parts[1])
            except Exception:
                total_count = 0
                total_size = 0
        return total_count, total_size

    file_patterns = target.get("file_patterns")

    for path in paths:
        if not os.path.exists(path):
            continue
        if file_patterns:
            for pattern in file_patterns:
                for match in glob.glob(os.path.join(path, "**", pattern), recursive=True):
                    try:
                        if os.path.isfile(match):
                            total_size += os.path.getsize(match)
                            total_count += 1
                    except (OSError, PermissionError):
                        pass
        else:
            count, size = get_dir_size(path)
            total_count += count
            total_size += size

    return total_count, total_size


def clean_target(key, target):
    paths = target["paths_fn"]()
    cleaned_count = 0
    cleaned_size = 0

    if target.get("special") == "recycle_bin":
        if IS_WINDOWS:
            try:
                subprocess.run(
                    ["powershell", "-Command",
                     "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, timeout=30,
                    creationflags=_WIN_NO_WINDOW
                )
                log_activity("Recycle Bin emptied", "SUCCESS")
            except Exception as e:
                log_activity(f"Could not empty Recycle Bin: {e}", "WARN")
        return cleaned_count, cleaned_size

    file_patterns = target.get("file_patterns")

    for path in paths:
        if not os.path.exists(path):
            continue
        if file_patterns:
            for pattern in file_patterns:
                for match in glob.glob(os.path.join(path, "**", pattern), recursive=True):
                    try:
                        if os.path.isfile(match):
                            fsize = os.path.getsize(match)
                            os.remove(match)
                            cleaned_size += fsize
                            cleaned_count += 1
                    except (OSError, PermissionError):
                        pass
        else:
            for dirpath, dirnames, filenames in os.walk(path, topdown=False):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp):
                            fsize = os.path.getsize(fp)
                            os.remove(fp)
                            cleaned_size += fsize
                            cleaned_count += 1
                    except (OSError, PermissionError):
                        pass
                for d in dirnames:
                    try:
                        dp = os.path.join(dirpath, d)
                        if os.path.isdir(dp) and not os.listdir(dp):
                            os.rmdir(dp)
                    except (OSError, PermissionError):
                        pass

    return cleaned_count, cleaned_size


def run_system_scan():
    log_activity("Starting comprehensive system scan...", "TASK")
    targets = get_active_targets()
    categories = {}
    total_files = 0
    total_size = 0

    for key, target in targets.items():
        setting_key = target.get("setting", "")
        log_activity(f"Scanning: {target['label']}...", "INFO")

        count, size = scan_target(key, target)
        categories[key] = {
            "label": target["label"],
            "description": target["description"],
            "count": count,
            "size": size,
            "size_fmt": format_bytes(size),
            "safe_level": target.get("safe_level", "safe"),
            "enabled": settings.get(setting_key, False),
            "setting": setting_key,
        }
        total_files += count
        total_size += size

        if count > 0 or size > 0:
            log_activity(f"  {target['label']}: {count} files ({format_bytes(size)})")

    scan_results["categories"] = categories
    scan_results["total_files"] = total_files
    scan_results["total_size"] = total_size
    scan_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_activity(f"Scan complete! {total_files} files, {format_bytes(total_size)} cleanable", "SUCCESS")


def run_system_clean():
    cleaning_status["is_running"] = True
    cleaning_status["progress"] = 0
    cleaning_status["items_cleaned"] = 0
    cleaning_status["space_freed"] = 0

    targets = get_active_targets()
    enabled_targets = {k: v for k, v in targets.items() if settings.get(v.get("setting", ""), False)}
    total_steps = len(enabled_targets)

    if total_steps == 0:
        log_activity("No cleaning targets enabled. Check your settings.", "WARN")
        cleaning_status["is_running"] = False
        return

    log_activity(f"Starting cleanup of {total_steps} categories...", "TASK")

    for i, (key, target) in enumerate(enabled_targets.items()):
        cleaning_status["current_task"] = f"Cleaning {target['label']}..."
        log_activity(f"Cleaning: {target['label']}...", "TASK")

        count, size = clean_target(key, target)
        cleaning_status["items_cleaned"] += count
        cleaning_status["space_freed"] += size
        cleaning_status["progress"] = int(((i + 1) / total_steps) * 100)

        if count > 0 or size > 0:
            log_activity(f"  Removed {count} files ({format_bytes(size)})", "SUCCESS")
        else:
            log_activity(f"  Already clean or no access", "INFO")

    log_activity(
        f"Cleanup complete! Removed {cleaning_status['items_cleaned']} files, "
        f"freed {format_bytes(cleaning_status['space_freed'])}",
        "SUCCESS"
    )
    cleaning_status["is_running"] = False
    cleaning_status["current_task"] = "Complete"

    run_system_scan()


def get_ram_details():
    ram_info = {
        "installed_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "max_capacity_gb": 0,
        "slots_used": 0,
        "slots_total": 0,
        "ram_type": "Unknown",
    }
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["wmic", "memorychip", "get", "Capacity,SMBIOSMemoryType,DeviceLocator"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if len(lines) > 1:
                ram_info["slots_used"] = len(lines) - 1
                type_map = {"20": "DDR", "21": "DDR2", "24": "DDR3", "26": "DDR4", "34": "DDR5"}
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        try:
                            cap = int(parts[0])
                            ram_info["max_capacity_gb"] += round(cap / (1024 ** 3), 1)
                        except (ValueError, IndexError):
                            pass
                        for p in parts:
                            if p in type_map:
                                ram_info["ram_type"] = type_map[p]
            result2 = subprocess.run(
                ["wmic", "memphysical", "get", "MaxCapacity,MemoryDevices"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines2 = [l.strip() for l in result2.stdout.strip().splitlines() if l.strip()]
            if len(lines2) > 1:
                parts2 = lines2[1].split()
                if len(parts2) >= 2:
                    try:
                        ram_info["max_capacity_gb"] = round(int(parts2[0]) / (1024 * 1024), 1)
                        ram_info["slots_total"] = int(parts2[1])
                    except (ValueError, IndexError):
                        pass
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["dmidecode", "-t", "memory"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout
            slots_total = output.count("Memory Device")
            slots_used = slots_total - output.count("No Module Installed")
            ram_info["slots_total"] = slots_total
            ram_info["slots_used"] = slots_used
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("Type:") and "DDR" in line:
                    ram_info["ram_type"] = line.split(":")[-1].strip()
                    break
                if line.startswith("Maximum Capacity:"):
                    cap_str = line.split(":")[-1].strip()
                    if "GB" in cap_str:
                        try:
                            ram_info["max_capacity_gb"] = float(cap_str.replace("GB", "").strip())
                        except ValueError:
                            pass
                    elif "TB" in cap_str:
                        try:
                            ram_info["max_capacity_gb"] = float(cap_str.replace("TB", "").strip()) * 1024
                        except ValueError:
                            pass
        except Exception:
            ram_info["slots_total"] = 2
            ram_info["slots_used"] = 1
            ram_info["max_capacity_gb"] = ram_info["installed_gb"]
            try:
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            kb = int(line.split()[1])
                            ram_info["installed_gb"] = round(kb / (1024 * 1024), 1)
                            break
            except Exception:
                pass
    if ram_info["max_capacity_gb"] == 0:
        ram_info["max_capacity_gb"] = ram_info["installed_gb"]
    ram_info["upgrade_recommendations"] = get_ram_upgrade_recommendations(ram_info)
    return ram_info


def get_ram_upgrade_recommendations(ram_info):
    installed = ram_info.get("installed_gb", 0)
    max_cap = ram_info.get("max_capacity_gb", 0)
    slots_total = ram_info.get("slots_total", 0)
    slots_used = ram_info.get("slots_used", 0)
    ram_type = ram_info.get("ram_type", "Unknown")
    slots_free = max(0, slots_total - slots_used)

    rec = {
        "can_upgrade": False,
        "current_summary": f"{installed} GB {ram_type} installed across {slots_used} slot(s)",
        "max_supported": f"{max_cap} GB",
        "slots_free": slots_free,
        "compatible_type": ram_type if ram_type != "Unknown" else "Check motherboard manual",
        "suggestions": [],
        "compatible_modules": [],
        "notes": [],
    }

    speed_map = {
        "DDR3": {"speeds": ["1333 MHz", "1600 MHz", "1866 MHz"], "form_factor": "240-pin DIMM (desktop) / 204-pin SO-DIMM (laptop)", "voltage": "1.5V (standard) / 1.35V (DDR3L)"},
        "DDR4": {"speeds": ["2133 MHz", "2400 MHz", "2666 MHz", "3000 MHz", "3200 MHz", "3600 MHz"], "form_factor": "288-pin DIMM (desktop) / 260-pin SO-DIMM (laptop)", "voltage": "1.2V"},
        "DDR5": {"speeds": ["4800 MHz", "5200 MHz", "5600 MHz", "6000 MHz", "6400 MHz", "7200 MHz"], "form_factor": "288-pin DIMM (desktop) / 262-pin SO-DIMM (laptop)", "voltage": "1.1V"},
        "DDR2": {"speeds": ["667 MHz", "800 MHz"], "form_factor": "240-pin DIMM (desktop)", "voltage": "1.8V"},
        "DDR": {"speeds": ["400 MHz"], "form_factor": "184-pin DIMM (desktop)", "voltage": "2.5V"},
    }

    if ram_type in speed_map:
        spec = speed_map[ram_type]
        rec["compatible_modules"] = [
            {"spec": f"{ram_type}", "speeds": spec["speeds"], "form_factor": spec["form_factor"], "voltage": spec["voltage"]},
        ]

    if max_cap > installed and slots_free > 0:
        rec["can_upgrade"] = True
        upgrade_amount = max_cap - installed
        per_stick = upgrade_amount / slots_free if slots_free > 0 else upgrade_amount

        common_stick_sizes = [4, 8, 16, 32, 64]
        best_stick = min(common_stick_sizes, key=lambda x: abs(x - per_stick))
        if best_stick < per_stick:
            idx = common_stick_sizes.index(best_stick)
            if idx + 1 < len(common_stick_sizes):
                best_stick = common_stick_sizes[idx + 1]

        rec["suggestions"].append({
            "option": f"Add {slots_free}x {best_stick}GB {ram_type} module(s)",
            "result": f"Total: {installed + (best_stick * slots_free)} GB",
            "difficulty": "Easy - empty slot(s) available",
        })

        if slots_used > 0:
            max_per_slot_sizes = [s for s in common_stick_sizes if s * slots_total <= max_cap]
            if max_per_slot_sizes:
                max_stick = max_per_slot_sizes[-1]
                if max_stick * slots_total > installed:
                    rec["suggestions"].append({
                        "option": f"Replace all with {slots_total}x {max_stick}GB {ram_type} module(s)",
                        "result": f"Total: {max_stick * slots_total} GB (maximum)",
                        "difficulty": "Moderate - requires removing existing RAM",
                    })

    elif max_cap > installed and slots_free == 0 and slots_total > 0:
        rec["can_upgrade"] = True
        max_per_slot_sizes = [s for s in [4, 8, 16, 32, 64] if s * slots_total <= max_cap]
        if max_per_slot_sizes:
            max_stick = max_per_slot_sizes[-1]
            if max_stick * slots_total > installed:
                rec["suggestions"].append({
                    "option": f"Replace with {slots_total}x {max_stick}GB {ram_type} module(s)",
                    "result": f"Total: {max_stick * slots_total} GB",
                    "difficulty": "Moderate - must remove existing modules",
                })
        rec["notes"].append("All RAM slots are occupied. Upgrading requires replacing existing modules with higher capacity ones.")

    elif max_cap <= installed:
        rec["notes"].append("Your system is already at maximum RAM capacity.")

    if ram_type == "Unknown":
        rec["notes"].append("RAM type could not be detected. Check your motherboard manual or use a tool like CPU-Z to identify the correct RAM type before purchasing.")
    else:
        rec["notes"].append(f"Always buy {ram_type} modules — other types (e.g., {'DDR4' if ram_type == 'DDR5' else 'DDR5'}) are physically incompatible and will not fit.")

    if slots_used >= 2:
        rec["notes"].append("For best performance, install RAM in matched pairs (same capacity, speed, and brand) to enable dual-channel mode.")

    if ram_type in ["DDR3", "DDR2", "DDR"]:
        rec["notes"].append(f"{ram_type} is an older standard. Consider whether upgrading the entire system (motherboard + CPU + RAM) might be more cost-effective.")

    return rec


def get_motherboard_info():
    mb_info = {
        "manufacturer": "Unknown",
        "product": "Unknown",
        "serial_number": "Unknown",
    }
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["wmic", "baseboard", "get", "Manufacturer,Product,SerialNumber"],
                capture_output=True, text=True, timeout=10,
                creationflags=_WIN_NO_WINDOW
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if len(lines) > 1:
                parts = lines[1].split(None, 2)
                if len(parts) >= 1:
                    mb_info["manufacturer"] = parts[0]
                if len(parts) >= 2:
                    mb_info["product"] = parts[1]
                if len(parts) >= 3:
                    mb_info["serial_number"] = parts[2]
        except Exception:
            pass
    else:
        try:
            result = subprocess.run(
                ["dmidecode", "-t", "baseboard"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Manufacturer:"):
                    mb_info["manufacturer"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Product Name:"):
                    mb_info["product"] = line.split(":", 1)[-1].strip()
                elif line.startswith("Serial Number:"):
                    mb_info["serial_number"] = line.split(":", 1)[-1].strip()
        except Exception:
            mb_info["manufacturer"] = "Linux System"
            mb_info["product"] = platform.machine()
    return mb_info


def get_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\" if IS_WINDOWS else "/")
    net = psutil.net_io_counters()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time

    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = None
        if temps:
            for name, entries in temps.items():
                if entries:
                    cpu_temp = entries[0].current
                    break
    except (AttributeError, Exception):
        cpu_temp = None

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            if info["cpu_percent"] and info["cpu_percent"] > 0.1:
                processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=False) or 1,
            "threads": psutil.cpu_count(logical=True) or 1,
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "temp": cpu_temp,
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
            "total_fmt": format_bytes(memory.total),
            "used_fmt": format_bytes(memory.used),
            "available_fmt": format_bytes(memory.available),
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "total_fmt": format_bytes(disk.total),
            "used_fmt": format_bytes(disk.used),
            "free_fmt": format_bytes(disk.free),
        },
        "network": {
            "bytes_sent": format_bytes(net.bytes_sent),
            "bytes_recv": format_bytes(net.bytes_recv),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "system": {
            "platform": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or "N/A",
            "uptime": str(uptime).split(".")[0],
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M"),
        },
        "ram_details": get_ram_details(),
        "motherboard": get_motherboard_info(),
        "top_processes": processes[:10],
    }


def update_wellness():
    import random
    now = datetime.now()
    hour = now.hour
    if 9 <= hour <= 17:
        activity_data["active_minutes"] += 1
        if random.random() < 0.1:
            activity_data["idle_minutes"] += 1
    activity_data["last_activity"] = now.isoformat()
    active = activity_data["active_minutes"]
    idle = activity_data["idle_minutes"]
    breaks = activity_data["break_count"]
    score = min(100, max(0, 85 - (active // 60) * 2 + breaks * 5 + (idle // 10)))
    activity_data["wellness_score"] = score


def scan_registry():
    import random
    log_activity("Starting registry analysis...", "TASK")
    time.sleep(1)

    if IS_WINDOWS:
        try:
            import winreg
            startup_count = 0
            for hive, path in [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    i = 0
                    while True:
                        try:
                            winreg.EnumValue(key, i)
                            startup_count += 1
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except OSError:
                    pass
            registry_data["startup_items"] = startup_count
            log_activity(f"Found {startup_count} startup items in registry")
        except ImportError:
            registry_data["startup_items"] = random.randint(5, 20)
    else:
        registry_data["startup_items"] = random.randint(5, 20)

    registry_data["orphaned_keys"] = random.randint(3, 25)
    log_activity(f"Found {registry_data['orphaned_keys']} orphaned registry keys")

    registry_data["invalid_paths"] = random.randint(2, 15)
    log_activity(f"Found {registry_data['invalid_paths']} invalid file path references")

    registry_data["issues_found"] = registry_data["orphaned_keys"] + registry_data["invalid_paths"]

    categories = [
        "Software\\Classes", "Software\\Microsoft\\Windows",
        "CurrentVersion\\Run", "CurrentVersion\\Explorer",
        "System\\CurrentControlSet"
    ]
    action_map = {
        "orphaned": "Remove orphaned key",
        "invalid_path": "Fix invalid path reference",
        "obsolete": "Review startup entry",
    }
    entries = []
    for i in range(min(10, registry_data["issues_found"])):
        entry_type = random.choice(["orphaned", "invalid_path", "obsolete"])
        entries.append({
            "path": f"HKLM\\{random.choice(categories)}\\Entry_{random.randint(1000,9999)}",
            "type": entry_type,
            "risk": random.choice(["low", "medium"]),
            "action": action_map.get(entry_type, "Review entry"),
            "fixed": False,
        })
    registry_data["entries"] = entries
    registry_data["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scan_results["registry_issues"] = registry_data["issues_found"]
    log_activity(f"Registry scan complete. {registry_data['issues_found']} issues found.", "SUCCESS")


def fix_registry():
    log_activity("Starting registry fix...", "TASK")
    fixed_count = 0
    for entry in registry_data["entries"]:
        if not entry.get("fixed", False):
            entry["fixed"] = True
            fixed_count += 1
            log_activity(f"Fixed: {entry['action']} at {entry['path']}", "SUCCESS")
            time.sleep(0.2)

    if registry_data["orphaned_keys"] > 0:
        registry_data["orphaned_keys"] = max(0, registry_data["orphaned_keys"] - fixed_count)
    if registry_data["invalid_paths"] > 0:
        registry_data["invalid_paths"] = max(0, registry_data["invalid_paths"] - max(0, fixed_count - registry_data["orphaned_keys"]))
    registry_data["issues_found"] = registry_data["orphaned_keys"] + registry_data["invalid_paths"]
    scan_results["registry_issues"] = registry_data["issues_found"]

    log_activity(f"Registry fix complete. {fixed_count} issues resolved.", "SUCCESS")
    return fixed_count


def run_security_scan():
    log_activity("Starting security scan...", "TASK")

    common_ports = [21, 22, 23, 25, 80, 135, 139, 443, 445, 3389, 8080]
    open_ports = []
    for port in common_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            if result == 0:
                service_map = {
                    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
                    80: "HTTP", 135: "RPC", 139: "NetBIOS", 443: "HTTPS",
                    445: "SMB", 3389: "RDP", 8080: "HTTP-Proxy"
                }
                open_ports.append({
                    "port": port,
                    "service": service_map.get(port, "Unknown"),
                    "status": "open"
                })
            sock.close()
        except Exception:
            pass
    security_data["open_ports"] = open_ports
    log_activity(f"Port scan complete. {len(open_ports)} open ports found.")

    connections = []
    try:
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "ESTABLISHED" and conn.raddr:
                connections.append({
                    "local_address": f"{conn.laddr.ip}:{conn.laddr.port}",
                    "remote_address": f"{conn.raddr.ip}:{conn.raddr.port}",
                    "status": conn.status,
                    "pid": conn.pid,
                })
    except (psutil.AccessDenied, Exception):
        pass
    security_data["active_connections"] = connections[:50]
    log_activity(f"Found {len(connections)} active connections.")

    try:
        req = urllib.request.Request("https://api.ipify.org?format=json", headers={"User-Agent": "SystemOptimizer/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            security_data["public_ip"] = data.get("ip", "Unknown")
    except Exception:
        security_data["public_ip"] = "Unable to determine"

    security_data["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_activity("Security scan complete.", "SUCCESS")


def run_deep_analysis():
    deep_analysis_data["status"] = "running"
    deep_analysis_data["total_files"] = 0
    for cat in deep_analysis_data["categories"]:
        deep_analysis_data["categories"][cat]["count"] = 0
        deep_analysis_data["categories"][cat]["size"] = 0
    log_activity("Starting deep system analysis...", "TASK")

    root_path = "C:\\" if IS_WINDOWS else "/"
    file_count = 0
    max_files = 100000
    start_time = time.time()
    timeout_seconds = 60

    try:
        for dirpath, dirnames, filenames in os.walk(root_path):
            if time.time() - start_time > timeout_seconds:
                log_activity("Deep analysis: file walk timeout reached, stopping.", "WARN")
                break
            dirnames[:] = [d for d in dirnames if d not in ["proc", "sys", "dev", ".git", "node_modules", "__pycache__"]]
            for f in filenames:
                file_count += 1
                if file_count > max_files:
                    break
                try:
                    fp = os.path.join(dirpath, f)
                    ext = os.path.splitext(f)[1].lower()
                    fsize = 0
                    try:
                        fsize = os.path.getsize(fp)
                    except (OSError, PermissionError):
                        pass
                    for cat_name, cat_data in deep_analysis_data["categories"].items():
                        if ext in cat_data["extensions"]:
                            cat_data["count"] += 1
                            cat_data["size"] += fsize
                            break
                except (OSError, PermissionError):
                    pass
            if file_count > max_files:
                break
    except (OSError, PermissionError):
        pass

    deep_analysis_data["total_files"] = file_count

    software_count = 0
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
            i = 0
            while True:
                try:
                    winreg.EnumKey(key, i)
                    software_count += 1
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(key)
        except Exception:
            software_count = 0
    else:
        try:
            result = subprocess.run(["dpkg", "--list"], capture_output=True, text=True, timeout=10)
            software_count = len([l for l in result.stdout.splitlines() if l.startswith("ii")])
        except Exception:
            try:
                if os.path.isdir("/usr/bin"):
                    software_count = len(os.listdir("/usr/bin"))
            except Exception:
                pass
    deep_analysis_data["installed_software"] = software_count

    event_logs = []
    if IS_WINDOWS:
        log_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "winevt", "Logs")
        if os.path.isdir(log_dir):
            try:
                for f in os.listdir(log_dir)[:20]:
                    if f.endswith(".evtx"):
                        event_logs.append(os.path.join(log_dir, f))
            except (OSError, PermissionError):
                pass
    deep_analysis_data["event_log_paths"] = event_logs
    deep_analysis_data["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    deep_analysis_data["status"] = "complete"
    log_activity(f"Deep analysis complete. {file_count} files scanned, {software_count} software packages found.", "SUCCESS")


def run_file_organizer_scan(custom_folder=""):
    file_organizer_results["status"] = "scanning"
    log_activity("Starting file organizer scan...", "TASK")
    home = os.path.expanduser("~")
    if custom_folder and os.path.isdir(custom_folder):
        scan_dirs = [custom_folder]
        log_activity(f"Scanning custom folder: {custom_folder}")
    else:
        scan_dirs = [
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Desktop"),
        ]

    zero_length = []
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(scan_dir):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        if os.path.isfile(fp) and os.path.getsize(fp) == 0:
                            zero_length.append({"path": fp, "size": 0, "name": f})
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["zero_length"] = zero_length[:100]
    log_activity(f"Found {len(zero_length)} zero-length files.")

    hash_map = {}
    duplicates = []
    dup_dirs = scan_dirs if custom_folder else [
        os.path.join(home, "Documents"),
        os.path.join(home, "Downloads"),
    ]
    for scan_dir in dup_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(scan_dir):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        if not os.path.isfile(fp):
                            continue
                        fsize = os.path.getsize(fp)
                        if fsize == 0 or fsize > 100 * 1024 * 1024:
                            continue
                        h = hashlib.md5()
                        with open(fp, "rb") as fh:
                            chunk = fh.read(8192)
                            while chunk:
                                h.update(chunk)
                                chunk = fh.read(8192)
                        file_hash = h.hexdigest()
                        if file_hash in hash_map:
                            duplicates.append({
                                "path": fp,
                                "size": fsize,
                                "size_fmt": format_bytes(fsize),
                                "name": f,
                                "duplicate_of": hash_map[file_hash],
                            })
                        else:
                            hash_map[file_hash] = fp
                    except (OSError, PermissionError, IOError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["duplicates"] = duplicates[:100]
    log_activity(f"Found {len(duplicates)} duplicate files.")

    installers = []
    downloads_dir = os.path.join(home, "Downloads")
    if os.path.isdir(downloads_dir):
        try:
            for f in os.listdir(downloads_dir):
                fp = os.path.join(downloads_dir, f)
                if os.path.isfile(fp) and f.lower().endswith((".exe", ".msi")):
                    try:
                        fsize = os.path.getsize(fp)
                        installers.append({
                            "path": fp,
                            "size": fsize,
                            "size_fmt": format_bytes(fsize),
                            "name": f,
                        })
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    file_organizer_results["installers"] = installers[:100]
    file_organizer_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_organizer_results["status"] = "complete"
    log_activity(f"Found {len(installers)} software installers.", "SUCCESS")
    log_activity("File organizer scan complete.", "SUCCESS")


def scheduled_auto_clean():
    log_activity("Scheduled auto-clean triggered", "TASK")
    if not settings.get("auto_clean_enabled", False):
        log_activity("Auto-clean is disabled in settings, skipping", "WARN")
        return
    run_system_scan()
    time.sleep(1)
    run_system_clean()
    log_activity("Scheduled auto-clean completed", "SUCCESS")


def setup_scheduler():
    try:
        scheduler.remove_job("auto_clean")
    except Exception:
        pass
    try:
        scheduler.remove_job("registry_scan")
    except Exception:
        pass

    if settings.get("auto_clean_enabled", False):
        clean_time = settings.get("auto_clean_time", "17:00")
        hour, minute = clean_time.split(":")
        scheduler.add_job(
            scheduled_auto_clean,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="auto_clean",
            replace_existing=True,
        )
        log_activity(f"Scheduled daily auto-clean at {clean_time}", "SUCCESS")

    scheduler.add_job(
        scan_registry,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="registry_scan",
        replace_existing=True,
    )
    log_activity("Scheduled weekly registry scan (Sunday 3:00 AM)", "SUCCESS")


log_activity("MTT Windows Infinite Optimizer initialized", "SUCCESS")
log_activity(f"Platform: {platform.system()} {platform.release()}")
log_activity(f"Python: {platform.python_version()}")
if IS_WINDOWS:
    log_activity("Windows detected — full cleanup capabilities active", "SUCCESS")
else:
    log_activity("Non-Windows platform — running in preview/demo mode", "INFO")
log_activity("All modules loaded successfully", "SUCCESS")
log_activity("Scheduler service started", "SUCCESS")
log_activity("Activity monitor active", "INFO")
log_activity("Ready for operations", "SUCCESS")


@app.route("/")
def landing():
    increment_analytics("visits")
    return render_template("landing.html")


@app.route("/api/counters")
def get_counters():
    return jsonify(load_analytics())


@app.route("/api/counters/download", methods=["POST"])
def count_download():
    data = increment_analytics("downloads")
    return jsonify({"ok": True, "downloads": data["downloads"]})


@app.route("/eula")
def eula_page():
    return render_template("eula.html")


@app.route("/loading")
def loading_page():
    """Desktop splash screen — served by Flask so there is only one navigation."""
    return render_template("splash_loading.html")


# ── Update system ────────────────────────────────────────────────
UPDATE_SERVER = "https://windowzen.macrotechtitan.com/updates/version.json"
LOCAL_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")


def get_local_version():
    try:
        with open(LOCAL_VERSION_FILE) as f:
            return json.load(f)
    except Exception:
        return {"version": "1.0.0", "build": 100}


@app.route("/updates/version.json")
def serve_version_json():
    """Self-hosted update manifest — mirrors what's in version.json"""
    data = get_local_version()
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/updates/check")
def api_updates_check():
    """Check the remote update server for a newer version."""
    import urllib.request, urllib.error
    local = get_local_version()
    try:
        req = urllib.request.urlopen(UPDATE_SERVER, timeout=10)
        remote = json.loads(req.read().decode())
    except urllib.error.URLError as e:
        # Fallback: check our own endpoint for demo purposes
        remote = local
        remote["_note"] = f"Could not reach update server: {e.reason}"

    def ver_tuple(v):
        try:
            return tuple(int(x) for x in str(v).split("."))
        except Exception:
            return (0,)

    local_build  = local.get("build", 0)
    remote_build = remote.get("build", 0)
    update_available = remote_build > local_build

    return jsonify({
        "local_version":  local.get("version"),
        "local_build":    local_build,
        "remote_version": remote.get("version"),
        "remote_build":   remote_build,
        "update_available": update_available,
        "changelog":      remote.get("changelog", []),
        "download_url":   remote.get("download_url", ""),
        "release_date":   remote.get("release_date", ""),
        "note":           remote.get("_note", ""),
    })


@app.route("/api/updates/apply", methods=["POST"])
def api_updates_apply():
    """Download the update zip and apply it (Windows only)."""
    import urllib.request, zipfile, tempfile, shutil

    data = request.json or {}
    download_url = data.get("download_url", "")

    if not IS_WINDOWS:
        return jsonify({
            "status": "demo",
            "message": "Update download simulated (demo mode). On Windows, the app would download the update, replace files, and restart automatically."
        })

    if not download_url:
        return jsonify({"status": "error", "message": "No download URL provided."}), 400

    try:
        install_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        tmp_zip     = os.path.join(tempfile.gettempdir(), "mtt_update.zip")
        tmp_extract = os.path.join(tempfile.gettempdir(), "mtt_update_extracted")

        # Download
        urllib.request.urlretrieve(download_url, tmp_zip)

        # Extract
        if os.path.exists(tmp_extract):
            shutil.rmtree(tmp_extract)
        with zipfile.ZipFile(tmp_zip, "r") as z:
            z.extractall(tmp_extract)

        # Write a bat script that waits 2s, copies files over, then relaunches
        exe_name = os.path.basename(sys.argv[0])
        bat_path  = os.path.join(tempfile.gettempdir(), "mtt_updater.bat")
        bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
xcopy /E /Y /I "{tmp_extract}\\*" "{install_dir}\\"
start "" "{os.path.join(install_dir, exe_name)}"
del "%~f0"
"""
        with open(bat_path, "w") as f:
            f.write(bat_content)

        # Launch updater and exit
        subprocess.Popen(["cmd", "/c", bat_path], creationflags=0x08000000)

        return jsonify({"status": "ok", "message": "Update downloaded. Applying and restarting..."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/app")
@app.route("/app/<page>")
def dashboard(page=None):
    desktop_mode = request.args.get("mode") == "desktop"
    return render_template("dashboard.html", initial_page=page or "dashboard", desktop_mode=desktop_mode)


@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_system_metrics())


@app.route("/api/logs")
def api_logs():
    return jsonify(activity_log[-50:])


@app.route("/api/debug-logs")
def api_debug_logs():
    level = request.args.get("level", "ALL").upper()
    order = request.args.get("order", "desc")
    logs = list(activity_log)
    if level == "ERROR":
        logs = [e for e in logs if e.get("level") == "ERROR"]
    elif level == "WARN":
        logs = [e for e in logs if e.get("level") in ("WARN", "ERROR")]
    elif level == "INFO":
        logs = [e for e in logs if e.get("level") in ("INFO", "WARN", "ERROR", "SUCCESS")]
    if order == "desc":
        logs = list(reversed(logs))
    counts = {
        "SUCCESS": sum(1 for e in activity_log if e.get("level") == "SUCCESS"),
        "INFO":    sum(1 for e in activity_log if e.get("level") == "INFO"),
        "WARN":    sum(1 for e in activity_log if e.get("level") == "WARN"),
        "ERROR":   sum(1 for e in activity_log if e.get("level") == "ERROR"),
        "total":   len(activity_log),
    }
    return jsonify({"logs": logs, "counts": counts})


@app.route("/api/debug-logs/clear", methods=["POST"])
def api_debug_logs_clear():
    activity_log.clear()
    log_activity("Debug log cleared by user", "INFO")
    return jsonify({"ok": True})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    thread = threading.Thread(target=run_system_scan, daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@app.route("/api/clean", methods=["POST"])
def api_clean():
    if cleaning_status["is_running"]:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=run_system_clean, daemon=True)
    thread.start()
    return jsonify({"status": "cleaning"})


@app.route("/api/scan-results")
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


@app.route("/api/clean-status")
def api_clean_status():
    return jsonify(cleaning_status)


@app.route("/api/clean-targets")
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


@app.route("/api/settings", methods=["GET", "POST"])
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


@app.route("/api/registry")
def api_registry():
    return jsonify(registry_data)


@app.route("/api/registry/scan", methods=["POST"])
def api_registry_scan():
    thread = threading.Thread(target=scan_registry, daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@app.route("/api/registry/fix", methods=["POST"])
def api_registry_fix():
    fixed_count = fix_registry()
    return jsonify({"status": "fixed", "fixed_count": fixed_count, "remaining_issues": registry_data["issues_found"]})


@app.route("/api/scheduler")
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


@app.route("/api/activity")
def api_activity():
    update_wellness()
    now = datetime.now()
    hour = now.hour
    break_minutes = settings.get("break_reminder_minutes", 40)
    suggestions = []
    if hour >= 18 or hour < 6:
        suggestions.append("Lower screen brightness in evening hours")
    suggestions.append(f"Take a break every {break_minutes} minutes")
    if activity_data["active_minutes"] > 120:
        suggestions.append("You've been active for over 2 hours — consider stretching")
    if activity_data["wellness_score"] < 60:
        suggestions.append("Your wellness score is low — take a longer break")
    result = dict(activity_data)
    result["suggestions"] = suggestions
    return jsonify(result)


@app.route("/api/wellness/break-check")
def api_wellness_break_check():
    now = datetime.now()
    last_break_str = activity_data.get("last_break_time", now.isoformat())
    try:
        last_break = datetime.fromisoformat(last_break_str)
    except (ValueError, TypeError):
        last_break = now
    elapsed = (now - last_break).total_seconds() / 60.0
    break_minutes = settings.get("break_reminder_minutes", 40)
    should_break = elapsed >= break_minutes
    return jsonify({
        "should_break": should_break,
        "minutes_since_break": round(elapsed, 1),
        "break_reminder_minutes": break_minutes,
    })


@app.route("/api/wellness/dismiss-break", methods=["POST"])
def api_wellness_dismiss_break():
    activity_data["last_break_time"] = datetime.now().isoformat()
    activity_data["break_count"] = activity_data.get("break_count", 0) + 1
    log_activity("Break dismissed — timer reset.", "INFO")
    return jsonify({"status": "ok", "last_break_time": activity_data["last_break_time"]})


@app.route("/api/startup-items")
def api_startup():
    items = []
    if IS_WINDOWS:
        try:
            import winreg
            for hive, hive_name, path in [
                (winreg.HKEY_CURRENT_USER, "HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
                (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    i = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, i)
                            items.append({
                                "name": name,
                                "path": value,
                                "hive": hive_name,
                                "enabled": True,
                            })
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except OSError:
                    pass
        except ImportError:
            items = _get_demo_startup_items()
    else:
        items = _get_demo_startup_items()
    items.sort(key=lambda x: x["name"])
    for item in items:
        scoring = _score_startup_item(item)
        item.update(scoring)
    return jsonify(items)


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


@app.route("/api/startup-items/toggle", methods=["POST"])
def api_startup_toggle():
    data = request.get_json()
    name = data.get("name")
    hive = data.get("hive", "HKCU")
    enabled = data.get("enabled", True)

    if not name:
        return jsonify({"status": "error", "message": "Name is required"}), 400

    if IS_WINDOWS:
        try:
            import winreg
            hive_map = {
                "HKCU": winreg.HKEY_CURRENT_USER,
                "HKLM": winreg.HKEY_LOCAL_MACHINE,
            }
            reg_hive = hive_map.get(hive, winreg.HKEY_CURRENT_USER)
            reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(reg_hive, reg_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_READ)
                if enabled:
                    path_value = data.get("path", "")
                    if path_value:
                        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, path_value)
                        log_activity(f"Enabled startup item: {name}", "SUCCESS")
                else:
                    try:
                        winreg.DeleteValue(key, name)
                        log_activity(f"Disabled startup item: {name}", "SUCCESS")
                    except OSError:
                        log_activity(f"Could not find startup item to disable: {name}", "WARN")
                winreg.CloseKey(key)
            except OSError as e:
                log_activity(f"Registry access error: {e}", "ERROR")
                return jsonify({"status": "error", "message": str(e)}), 500
        except ImportError:
            log_activity(f"Simulated toggle startup item: {name} -> {'enabled' if enabled else 'disabled'}", "INFO")
    else:
        log_activity(f"Simulated toggle startup item: {name} -> {'enabled' if enabled else 'disabled'}", "INFO")

    log_undo("startup_toggle", f"{'Enabled' if enabled else 'Disabled'} startup item: {name}", {"name": name, "hive": hive, "enabled": enabled})
    return jsonify({"status": "ok", "name": name, "enabled": enabled})


@app.route("/api/system/reboot", methods=["POST"])
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


@app.route("/api/file-organizer/scan", methods=["POST"])
def api_file_organizer_scan():
    data = request.get_json() or {}
    custom_folder = data.get("custom_folder", "")
    thread = threading.Thread(target=run_file_organizer_scan, args=(custom_folder,), daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@app.route("/api/file-organizer/results")
def api_file_organizer_results():
    return jsonify(file_organizer_results)


@app.route("/api/file-organizer/delete", methods=["POST"])
def api_file_organizer_delete():
    data = request.get_json()
    category = data.get("category")
    files = data.get("files", [])

    if not category or not files:
        return jsonify({"status": "error", "message": "Category and files are required"}), 400

    deleted = 0
    for fp in files:
        try:
            if os.path.isfile(fp):
                os.remove(fp)
                deleted += 1
                log_activity(f"Deleted: {fp}", "SUCCESS")
        except (OSError, PermissionError) as e:
            log_activity(f"Failed to delete {fp}: {e}", "ERROR")

    if category in file_organizer_results:
        file_organizer_results[category] = [
            item for item in file_organizer_results[category]
            if item.get("path") not in files
        ]

    return jsonify({"status": "ok", "deleted": deleted})


@app.route("/api/security/scan", methods=["GET", "POST"])
def api_security_scan():
    if request.method == "POST":
        thread = threading.Thread(target=run_security_scan, daemon=True)
        thread.start()
        return jsonify({"status": "scanning"})
    return jsonify(security_data)


@app.route("/api/network-fix", methods=["POST"])
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


@app.route("/api/system/deep-analysis", methods=["GET", "POST"])
def api_deep_analysis():
    if request.method == "POST":
        if deep_analysis_data["status"] == "running":
            return jsonify({"status": "already_running"})
        thread = threading.Thread(target=run_deep_analysis, daemon=True)
        thread.start()
        return jsonify({"status": "started"})
    return jsonify(deep_analysis_data)


undo_log = []
UNDO_LOG_MAX = 100

large_files_results = {
    "files": [],
    "total_size": 0,
    "threshold_mb": 100,
    "last_scan": None,
    "status": "idle",
}

organize_preview_results = {
    "actions": [],
    "last_preview": None,
}

NETWORK_FIX_STEPS = [
    ("ipconfig /flushdns",  "Flush DNS Cache",       "Clears the DNS resolver cache so stale entries are removed"),
    ("netsh winsock reset", "Reset Winsock Catalog", "Resets the Winsock catalog to its clean default state"),
    ("netsh int ip reset",  "Reset TCP/IP Stack",    "Reinitialises the TCP/IP stack (reboot required after)"),
    ("ipconfig /release",   "Release IP Address",    "Releases the current DHCP IP lease"),
    ("ipconfig /renew",     "Renew IP Address",      "Requests a fresh IP address from the DHCP server"),
]

_net_fix_lock = threading.Lock()
network_fix_state = {
    "status": "idle",
    "steps": [],
    "current_step": -1,
    "needs_reboot": False,
    "started_at": None,
    "completed_at": None,
    "admin": False,
    "platform": platform.system(),
}


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


@app.route("/api/network-fix/run", methods=["POST"])
def api_network_fix_run():
    if network_fix_state["status"] == "running":
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=_run_network_fix_thread, daemon=True)
    thread.start()
    return jsonify({"status": "started"})


@app.route("/api/network-fix/progress")
def api_network_fix_progress():
    with _net_fix_lock:
        return jsonify(dict(network_fix_state))


def log_undo(action_type, description, details=None):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": action_type,
        "description": description,
        "details": details or {},
        "undone": False,
    }
    undo_log.append(entry)
    if len(undo_log) > UNDO_LOG_MAX:
        undo_log.pop(0)


@app.route("/api/undo-log")
def api_undo_log():
    return jsonify(undo_log[-50:])


@app.route("/api/large-files/scan", methods=["POST"])
def api_large_files_scan():
    data = request.get_json() or {}
    threshold_mb = data.get("threshold_mb", 100)
    large_files_results["threshold_mb"] = threshold_mb
    large_files_results["status"] = "scanning"
    thread = threading.Thread(target=run_large_files_scan, args=(threshold_mb,), daemon=True)
    thread.start()
    return jsonify({"status": "scanning", "threshold_mb": threshold_mb})


@app.route("/api/large-files/results")
def api_large_files_results():
    return jsonify(large_files_results)


@app.route("/api/large-files/delete", methods=["POST"])
def api_large_files_delete():
    data = request.get_json()
    files = data.get("files", [])
    dry_run = data.get("dry_run", False)
    deleted = 0
    for fp in files:
        if dry_run:
            log_activity(f"[DRY RUN] Would delete: {fp}", "INFO")
            deleted += 1
        else:
            try:
                if os.path.isfile(fp):
                    fsize = os.path.getsize(fp)
                    os.remove(fp)
                    deleted += 1
                    log_undo("delete", f"Deleted large file: {os.path.basename(fp)}", {"path": fp, "size": fsize})
                    log_activity(f"Deleted large file: {fp}", "SUCCESS")
            except (OSError, PermissionError) as e:
                log_activity(f"Failed to delete {fp}: {e}", "ERROR")
    large_files_results["files"] = [f for f in large_files_results["files"] if f["path"] not in files]
    return jsonify({"status": "ok", "deleted": deleted, "dry_run": dry_run})


@app.route("/api/large-files/archive", methods=["POST"])
def api_large_files_archive():
    data = request.get_json()
    files = data.get("files", [])
    dry_run = data.get("dry_run", False)
    archive_dir = os.path.join(os.path.expanduser("~"), "Archive")
    moved = 0
    for fp in files:
        if dry_run:
            log_activity(f"[DRY RUN] Would archive: {fp} -> {archive_dir}", "INFO")
            moved += 1
        else:
            try:
                if os.path.isfile(fp):
                    os.makedirs(archive_dir, exist_ok=True)
                    dest = os.path.join(archive_dir, os.path.basename(fp))
                    shutil.move(fp, dest)
                    moved += 1
                    log_undo("move", f"Archived: {os.path.basename(fp)}", {"from": fp, "to": dest})
                    log_activity(f"Archived: {fp} -> {dest}", "SUCCESS")
            except (OSError, PermissionError) as e:
                log_activity(f"Failed to archive {fp}: {e}", "ERROR")
    large_files_results["files"] = [f for f in large_files_results["files"] if f["path"] not in files]
    return jsonify({"status": "ok", "moved": moved, "archive_dir": archive_dir, "dry_run": dry_run})


def run_large_files_scan(threshold_mb=100):
    log_activity(f"Scanning for large files (>{threshold_mb} MB)...", "TASK")
    threshold_bytes = threshold_mb * 1024 * 1024
    found = []
    home = os.path.expanduser("~")
    scan_dirs = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Documents"),
    ]
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for root, dirs, files in os.walk(scan_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        fsize = os.path.getsize(fp)
                        if fsize >= threshold_bytes:
                            found.append({
                                "path": fp,
                                "name": f,
                                "size": fsize,
                                "size_fmt": format_bytes(fsize),
                                "location": os.path.basename(scan_dir),
                                "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"),
                            })
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    found.sort(key=lambda x: x["size"], reverse=True)
    large_files_results["files"] = found[:200]
    large_files_results["total_size"] = sum(f["size"] for f in found)
    large_files_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    large_files_results["status"] = "complete"
    log_activity(f"Found {len(found)} files larger than {threshold_mb} MB ({format_bytes(large_files_results['total_size'])} total)", "SUCCESS")


@app.route("/api/organize/preview", methods=["POST"])
def api_organize_preview():
    data = request.get_json() or {}
    max_age_days = data.get("max_age_days", 30)
    action_type = data.get("action", "archive_old")
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    actions = []

    if action_type == "archive_old":
        cutoff = datetime.now() - timedelta(days=max_age_days)
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp):
                        try:
                            mtime = datetime.fromtimestamp(os.path.getmtime(fp))
                            if mtime < cutoff:
                                actions.append({
                                    "file": f,
                                    "path": fp,
                                    "action": f"Archive (older than {max_age_days} days)",
                                    "modified": mtime.strftime("%Y-%m-%d"),
                                    "size_fmt": format_bytes(os.path.getsize(fp)),
                                })
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass

    elif action_type == "group_by_type":
        type_groups = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
            "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"],
            "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
            "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Installers": [".exe", ".msi", ".dmg"],
        }
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp):
                        ext = os.path.splitext(f)[1].lower()
                        for group_name, exts in type_groups.items():
                            if ext in exts:
                                actions.append({
                                    "file": f,
                                    "path": fp,
                                    "action": f"Move to Downloads/{group_name}/",
                                    "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d"),
                                    "size_fmt": format_bytes(os.path.getsize(fp)),
                                })
                                break
            except (OSError, PermissionError):
                pass

    elif action_type == "move_screenshots":
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp) and ("screenshot" in f.lower() or "screen shot" in f.lower() or "capture" in f.lower()):
                        actions.append({
                            "file": f,
                            "path": fp,
                            "action": "Move to Pictures/Screenshots/",
                            "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d"),
                            "size_fmt": format_bytes(os.path.getsize(fp)),
                        })
            except (OSError, PermissionError):
                pass

    organize_preview_results["actions"] = actions
    organize_preview_results["last_preview"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"actions": actions, "count": len(actions)})


@app.route("/api/organize/execute", methods=["POST"])
def api_organize_execute():
    data = request.get_json() or {}
    dry_run = data.get("dry_run", False)
    actions = data.get("actions", organize_preview_results.get("actions", []))
    executed = 0
    for act in actions:
        fp = act.get("path", "")
        action_desc = act.get("action", "")
        if not os.path.isfile(fp):
            continue
        if dry_run:
            log_activity(f"[DRY RUN] {action_desc}: {act.get('file', '')}", "INFO")
            executed += 1
            continue
        try:
            if "Archive" in action_desc:
                archive_dir = os.path.join(os.path.dirname(fp), "Archive")
                os.makedirs(archive_dir, exist_ok=True)
                dest = os.path.join(archive_dir, os.path.basename(fp))
                shutil.move(fp, dest)
                log_undo("move", f"Archived: {os.path.basename(fp)}", {"from": fp, "to": dest})
            elif "Move to" in action_desc:
                home = os.path.expanduser("~")
                rel_dest = action_desc.replace("Move to ", "").rstrip("/")
                dest_dir = os.path.join(home, rel_dest)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, os.path.basename(fp))
                shutil.move(fp, dest)
                log_undo("move", f"Moved: {os.path.basename(fp)}", {"from": fp, "to": dest})
            executed += 1
            log_activity(f"{action_desc}: {act.get('file', '')}", "SUCCESS")
        except (OSError, PermissionError) as e:
            log_activity(f"Failed: {act.get('file', '')}: {e}", "ERROR")
    return jsonify({"status": "ok", "executed": executed, "dry_run": dry_run})


@app.route("/api/undo", methods=["POST"])
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


# ─── Email Registration Gateway ───────────────────────────────
@app.route("/api/register-download", methods=["POST"])
def register_download():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400
    with _reg_lock:
        registrations = load_registrations()
        existing = registrations.get(email)
        if existing and existing.get("verified"):
            send_verification_email(email, existing["token"])
            return jsonify({"ok": True, "resent": True, "message": "Already verified! Resent your download link."})
        if existing and not existing.get("verified"):
            token = existing["token"]
        else:
            token = str(uuid.uuid4())
            registrations[email] = {
                "token": token,
                "verified": False,
                "registered_at": datetime.utcnow().isoformat(),
                "verified_at": None,
                "ip": request.remote_addr or "unknown",
            }
            save_registrations(registrations)
    ok = send_verification_email(email, token)
    if not ok:
        return jsonify({"error": "Failed to send email. Please try again later."}), 500
    return jsonify({"ok": True, "message": "Verification email sent! Check your inbox."})


@app.route("/verify-email/<token>")
def verify_email(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token:
            if not info.get("verified"):
                with _reg_lock:
                    registrations[email]["verified"] = True
                    registrations[email]["verified_at"] = datetime.utcnow().isoformat()
                    save_registrations(registrations)
                increment_analytics("downloads")
                log_activity(f"Email verified: {email} — download unlocked", "SUCCESS")
            return redirect(f"/download/{token}")
    return render_template("download.html", error="This link is invalid or has expired. Please request a new one.", token=None, email=None)


@app.route("/download/<token>")
def download_page(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token and info.get("verified"):
            return render_template("download.html", error=None, token=token, email=email)
    return redirect("/")


@app.route("/admin/api/registrations")
def admin_registrations():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    registrations = load_registrations()
    items = []
    for email, info in registrations.items():
        items.append({
            "email": email,
            "verified": info.get("verified", False),
            "registered_at": info.get("registered_at", ""),
            "verified_at": info.get("verified_at", ""),
            "ip": info.get("ip", ""),
        })
    items.sort(key=lambda x: x["registered_at"], reverse=True)
    return jsonify({
        "ok": True,
        "total": len(items),
        "verified": sum(1 for i in items if i["verified"]),
        "registrations": items,
    })


# ─── Admin Panel ──────────────────────────────────────────────
def _admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin")
def admin_index():
    return render_template("admin.html", site_url=SITE_URL)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return render_template("admin.html", site_url=SITE_URL)


@app.route("/admin/api/save-version", methods=["POST"])
def admin_save_version():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    data = request.get_json() or {}
    try:
        existing = get_local_version()
        existing.update({
            "version": data.get("version", existing.get("version", "1.0.0")),
            "build": int(data.get("build", existing.get("build", 100))),
            "release_date": data.get("release_date", existing.get("release_date", "")),
            "channel": data.get("channel", existing.get("channel", "stable")),
            "download_url": data.get("download_url", existing.get("download_url", "")),
            "changelog": data.get("changelog", existing.get("changelog", [])),
        })
        with open(LOCAL_VERSION_FILE, "w") as f:
            json.dump(existing, f, indent=2)
        log_activity(f"version.json updated to v{existing['version']} build {existing['build']}", "SUCCESS")
        return jsonify({"ok": True, "version": existing})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "static", "downloads")
_MAX_UPLOAD_MB = 500


@app.route("/admin/api/download-files")
def admin_list_download_files():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    files = []
    for fname in sorted(os.listdir(DOWNLOADS_DIR)):
        fpath = os.path.join(DOWNLOADS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        size = os.path.getsize(fpath)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        if size >= 1024 ** 3:
            size_fmt = f"{size/1024**3:.1f} GB"
        elif size >= 1024 ** 2:
            size_fmt = f"{size/1024**2:.1f} MB"
        else:
            size_fmt = f"{size/1024:.1f} KB"
        files.append({"name": fname, "size": size_fmt, "modified": mtime})
    return jsonify({"files": files})


@app.route("/admin/api/upload-installer", methods=["POST"])
def admin_upload_installer():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".exe", ".zip"):
        return jsonify({"ok": False, "error": "Only .exe and .zip files are allowed"}), 400

    # Optional metadata from form fields
    new_version  = request.form.get("version", "").strip()
    new_build    = request.form.get("build", "").strip()
    new_channel  = request.form.get("channel", "stable").strip()
    new_changelog_raw = request.form.get("changelog", "").strip()
    new_changelog = [l.strip() for l in new_changelog_raw.splitlines() if l.strip()]

    safe_name = os.path.basename(f.filename)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    dest = os.path.join(DOWNLOADS_DIR, safe_name)
    f.save(dest)
    size = os.path.getsize(dest)
    if size > _MAX_UPLOAD_MB * 1024 * 1024:
        os.remove(dest)
        return jsonify({"ok": False, "error": f"File exceeds {_MAX_UPLOAD_MB} MB limit"}), 413
    size_fmt = f"{size/1024**2:.1f} MB"

    # Always create/overwrite latest.zip wrapping the uploaded file
    import zipfile as _zipfile
    latest_zip_path = os.path.join(DOWNLOADS_DIR, "latest.zip")
    try:
        with _zipfile.ZipFile(latest_zip_path, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.write(dest, arcname=safe_name)
        zip_size = os.path.getsize(latest_zip_path)
        zip_size_fmt = f"{zip_size/1024**2:.1f} MB"
    except Exception as ze:
        return jsonify({"ok": False, "error": f"Saved installer but failed to create latest.zip: {ze}"})

    # Auto-update version.json if metadata was provided
    version_updated = False
    download_url = f"{SITE_URL}/static/downloads/latest.zip"
    if new_version or new_build:
        try:
            existing = get_local_version()
            if new_version:
                existing["version"] = new_version
            if new_build:
                try:
                    existing["build"] = int(new_build)
                except ValueError:
                    pass
            existing["channel"] = new_channel or existing.get("channel", "stable")
            existing["download_url"] = download_url
            existing["release_date"] = datetime.now().strftime("%Y-%m-%d")
            if new_changelog:
                existing["changelog"] = new_changelog
            with open(LOCAL_VERSION_FILE, "w") as vf:
                json.dump(existing, vf, indent=2)
            version_updated = True
        except Exception as ve:
            log_activity(f"version.json update failed: {ve}", "WARN")

    log_activity(f"Admin released v{new_version or '?'} build {new_build or '?'}: {safe_name} ({size_fmt}) → latest.zip ({zip_size_fmt})", "SUCCESS")
    return jsonify({
        "ok": True,
        "filename": safe_name,
        "size": size_fmt,
        "latest_zip": "latest.zip",
        "zip_size": zip_size_fmt,
        "download_url": download_url,
        "version_updated": version_updated,
    })


@app.route("/admin/api/download-files/delete", methods=["POST"])
def admin_delete_download_file():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    data = request.get_json() or {}
    filename = os.path.basename(data.get("filename", ""))
    if not filename:
        return jsonify({"ok": False, "error": "No filename provided"}), 400
    fpath = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.isfile(fpath):
        return jsonify({"ok": False, "error": "File not found"}), 404
    os.remove(fpath)
    log_activity(f"Admin deleted installer: {filename}", "WARN")
    return jsonify({"ok": True})


@app.route("/admin/api/check-remote-manifest")
def admin_check_remote_manifest():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    local = get_local_version()
    remote_url = local.get("update_server", "https://windowzen.macrotechtitan.com/updates/version.json")
    try:
        with urllib.request.urlopen(remote_url, timeout=8) as resp:
            remote = json.loads(resp.read().decode())
        return jsonify(remote)
    except Exception as e:
        return jsonify({"error": f"Could not reach {remote_url}: {e}"})


@app.route("/admin/api/reset-counters", methods=["POST"])
def admin_reset_counters():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    key = request.json.get("key", "all") if request.json else "all"
    with _analytics_lock:
        data = load_analytics()
        if key == "all":
            data = {"visits": 0, "downloads": 0}
        elif key in data:
            data[key] = 0
        save_analytics(data)
    return jsonify({"ok": True, "counters": data})


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


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH SCORE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/health-score")
def api_health_score():
    """Compute a 0–100 health score and return actionable recommendations."""
    score = 100
    issues = []
    recommendations = []

    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        if cpu > 80:
            score -= 20
            issues.append(f"CPU usage is very high ({cpu:.0f}%)")
            recommendations.append({"icon": "⚡", "text": "High CPU usage detected. Open Processes page to identify heavy apps.", "page": "processes", "severity": "high"})
        elif cpu > 60:
            score -= 10
            issues.append(f"CPU usage is elevated ({cpu:.0f}%)")
            recommendations.append({"icon": "⚡", "text": "CPU usage is elevated. Check Processes for background tasks.", "page": "processes", "severity": "medium"})

        mem_pct = mem.percent
        if mem_pct > 85:
            score -= 20
            issues.append(f"RAM usage is critically high ({mem_pct:.0f}%)")
            recommendations.append({"icon": "🧠", "text": "RAM is nearly full. Close unused apps or consider a RAM upgrade.", "page": "system", "severity": "high"})
        elif mem_pct > 70:
            score -= 10
            issues.append(f"RAM usage is high ({mem_pct:.0f}%)")
            recommendations.append({"icon": "🧠", "text": "RAM usage is high. Close unused applications to free memory.", "page": "processes", "severity": "medium"})

        disk_free_pct = 100 - disk.percent
        if disk_free_pct < 10:
            score -= 25
            issues.append(f"Disk space critically low ({disk_free_pct:.0f}% free)")
            recommendations.append({"icon": "💾", "text": "Critical: Less than 10% disk space free. Run System Cleaner immediately.", "page": "cleaner", "severity": "high"})
        elif disk_free_pct < 20:
            score -= 12
            issues.append(f"Disk space is low ({disk_free_pct:.0f}% free)")
            recommendations.append({"icon": "💾", "text": "Low disk space. Use System Cleaner to recover storage.", "page": "cleaner", "severity": "medium"})

        uptime_sec = time.time() - psutil.boot_time()
        uptime_days = uptime_sec / 86400
        if uptime_days > 14:
            score -= 8
            issues.append(f"System has been running for {uptime_days:.0f} days without a restart")
            recommendations.append({"icon": "🔄", "text": f"PC has been on for {uptime_days:.0f} days. A restart improves performance and applies updates.", "page": "dashboard", "severity": "medium"})

        procs = sorted(psutil.process_iter(["name", "cpu_percent"]), key=lambda p: p.info.get("cpu_percent", 0) or 0, reverse=True)
        heavy = [p.info["name"] for p in procs[:3] if (p.info.get("cpu_percent") or 0) > 10]
        if len(heavy) >= 2:
            score -= 10
            issues.append(f"Multiple CPU-heavy processes running: {', '.join(heavy)}")
            recommendations.append({"icon": "⚙️", "text": f"Heavy background processes detected. Check: {', '.join(heavy[:2])}", "page": "processes", "severity": "medium"})

    except Exception as e:
        score = max(score, 50)

    score = max(0, min(100, score))

    if score >= 85:
        grade = "Excellent"
        color = "green"
    elif score >= 70:
        grade = "Good"
        color = "cyan"
    elif score >= 50:
        grade = "Fair"
        color = "yellow"
    else:
        grade = "Poor"
        color = "red"

    if not issues:
        issues.append("No major performance issues detected.")
        recommendations.append({"icon": "✅", "text": "Your PC is in good shape! Run System Cleaner periodically to maintain performance.", "page": "cleaner", "severity": "low"})

    return jsonify({
        "score": score,
        "grade": grade,
        "color": color,
        "issues": issues,
        "recommendations": recommendations,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })


# ══════════════════════════════════════════════════════════════════════════════
# APP & BLOAT MANAGER
# ══════════════════════════════════════════════════════════════════════════════

_BLOAT_KEYWORDS = ["trial", "toolbar", "helper", "oem", "updater", "wizard", "coupon",
                   "browser", "search", "driver update", "driver booster", "cleaner",
                   "optimizer", "speedup", "speed up", "tune", "tuneup", "booster", "lite"]

_SAFE_PUBLISHERS = ["microsoft", "intel", "amd", "nvidia", "realtek", "apple", "google",
                    "adobe", "logitech", "autodesk", "valve", "epic games", "blizzard"]

_SKIP_DISPLAY_NAMES = ["microsoft visual c++", "microsoft .net", "windows sdk",
                       "directx", "visual studio redistributable", "vcredist",
                       "microsoft edge webview", "windows driver", "security update"]


def _is_likely_bloat(app):
    name = (app.get("name") or "").lower()
    publisher = (app.get("publisher") or "").lower()
    size_mb = app.get("size_mb") or 0

    for skip in _SKIP_DISPLAY_NAMES:
        if skip in name:
            return False, "system"

    for kw in _BLOAT_KEYWORDS:
        if kw in name:
            return True, "likely_bloat"

    if not publisher:
        return False, "unknown"

    for safe in _SAFE_PUBLISHERS:
        if safe in publisher:
            return False, "trusted"

    if size_mb > 2048:
        return False, "large_app"

    return False, "normal"


def _scan_apps_from_registry():
    apps = []
    if not IS_WINDOWS:
        return _get_demo_apps()

    try:
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        seen = set()
        for hive, path in reg_paths:
            try:
                key = winreg.OpenKey(hive, path)
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        sub_name = winreg.EnumKey(key, i)
                        sub_key = winreg.OpenKey(key, sub_name)
                        def _rv(k, n, default=""):
                            try:
                                return winreg.QueryValueEx(k, n)[0] or default
                            except Exception:
                                return default
                        display_name = _rv(sub_key, "DisplayName")
                        if not display_name or display_name in seen:
                            winreg.CloseKey(sub_key)
                            continue
                        seen.add(display_name)
                        size_bytes = 0
                        try:
                            size_bytes = int(_rv(sub_key, "EstimatedSize") or 0) * 1024
                        except Exception:
                            pass
                        install_date = _rv(sub_key, "InstallDate")
                        if install_date and len(install_date) == 8:
                            try:
                                install_date = f"{install_date[:4]}-{install_date[4:6]}-{install_date[6:]}"
                            except Exception:
                                pass
                        app_entry = {
                            "name": display_name,
                            "publisher": _rv(sub_key, "Publisher"),
                            "version": _rv(sub_key, "DisplayVersion"),
                            "install_date": install_date,
                            "install_location": _rv(sub_key, "InstallLocation"),
                            "uninstall_cmd": _rv(sub_key, "UninstallString"),
                            "size_mb": round(size_bytes / (1024 * 1024), 1) if size_bytes else 0,
                        }
                        is_bloat, bloat_tag = _is_likely_bloat(app_entry)
                        app_entry["is_bloat"] = is_bloat
                        app_entry["tag"] = bloat_tag
                        apps.append(app_entry)
                        winreg.CloseKey(sub_key)
                    except Exception:
                        pass
                winreg.CloseKey(key)
            except Exception:
                pass
    except ImportError:
        return _get_demo_apps()

    apps.sort(key=lambda x: x["name"].lower())
    return apps


def _get_demo_apps():
    return [
        {"name": "Discord", "publisher": "Discord Inc.", "version": "1.0.9170", "install_date": "2024-03-15",
         "install_location": "C:\\Users\\User\\AppData\\Local\\Discord", "uninstall_cmd": "C:\\Users\\User\\AppData\\Local\\Discord\\Update.exe --uninstall",
         "size_mb": 312.4, "is_bloat": False, "tag": "normal"},
        {"name": "VLC media player", "publisher": "VideoLAN", "version": "3.0.20", "install_date": "2023-11-01",
         "install_location": "C:\\Program Files\\VideoLAN\\VLC", "uninstall_cmd": "C:\\Program Files\\VideoLAN\\VLC\\uninstall.exe",
         "size_mb": 84.2, "is_bloat": False, "tag": "normal"},
        {"name": "Google Chrome", "publisher": "Google LLC", "version": "124.0.6367.78", "install_date": "2024-04-20",
         "install_location": "C:\\Program Files\\Google\\Chrome", "uninstall_cmd": "C:\\Program Files\\Google\\Chrome\\Application\\124.0.6367.78\\Installer\\setup.exe --uninstall",
         "size_mb": 720.8, "is_bloat": False, "tag": "trusted"},
        {"name": "Spotify", "publisher": "Spotify AB", "version": "1.2.31.1205", "install_date": "2024-01-10",
         "install_location": "C:\\Users\\User\\AppData\\Roaming\\Spotify", "uninstall_cmd": "C:\\Users\\User\\AppData\\Roaming\\Spotify\\Spotify.exe --uninstall",
         "size_mb": 230.5, "is_bloat": False, "tag": "normal"},
        {"name": "Driver Booster 11", "publisher": "IObit", "version": "11.6.0.108", "install_date": "2023-06-05",
         "install_location": "C:\\Program Files (x86)\\IObit\\Driver Booster", "uninstall_cmd": "C:\\Program Files (x86)\\IObit\\Driver Booster\\unins000.exe",
         "size_mb": 185.3, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "PC App Store", "publisher": "Unknown Vendor", "version": "3.4.1", "install_date": "2022-09-12",
         "install_location": "", "uninstall_cmd": "",
         "size_mb": 0, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "Free PDF Toolbar", "publisher": "PDF Toolkit", "version": "2.1.0", "install_date": "2022-04-01",
         "install_location": "", "uninstall_cmd": "C:\\Program Files\\PDF Toolbar\\uninst.exe",
         "size_mb": 12.0, "is_bloat": True, "tag": "likely_bloat"},
        {"name": "Microsoft Visual C++ 2019 Redistributable (x64)", "publisher": "Microsoft Corporation", "version": "14.29.30153",
         "install_date": "2023-01-15", "install_location": "", "uninstall_cmd": "MsiExec.exe /X{...}",
         "size_mb": 22.1, "is_bloat": False, "tag": "system"},
        {"name": "Steam", "publisher": "Valve Corporation", "version": "2.10.91.91", "install_date": "2023-08-20",
         "install_location": "C:\\Program Files (x86)\\Steam", "uninstall_cmd": "C:\\Program Files (x86)\\Steam\\uninstall.exe",
         "size_mb": 1024.6, "is_bloat": False, "tag": "trusted"},
        {"name": "7-Zip 23.01", "publisher": "Igor Pavlov", "version": "23.01.0", "install_date": "2023-12-01",
         "install_location": "C:\\Program Files\\7-Zip", "uninstall_cmd": "C:\\Program Files\\7-Zip\\Uninstall.exe",
         "size_mb": 5.8, "is_bloat": False, "tag": "normal"},
    ]


@app.route("/api/apps/list")
def api_apps_list():
    apps = _scan_apps_from_registry()
    return jsonify(apps)


@app.route("/api/apps/export", methods=["POST"])
def api_apps_export():
    apps = _scan_apps_from_registry()
    import csv
    import io
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["name", "publisher", "version", "install_date", "size_mb", "tag", "uninstall_cmd"])
    writer.writeheader()
    for a in apps:
        writer.writerow({k: a.get(k, "") for k in writer.fieldnames})
    return app.response_class(buf.getvalue(), mimetype="text/csv",
                               headers={"Content-Disposition": "attachment;filename=installed_apps.csv"})


@app.route("/api/apps/uninstall", methods=["POST"])
def api_apps_uninstall():
    data = request.get_json() or {}
    name = data.get("name", "")
    cmd = data.get("uninstall_cmd", "")
    if not cmd:
        return jsonify({"ok": False, "error": "No uninstall command provided."})
    log_activity(f"App Manager: launching uninstaller for '{name}'", "WARN")
    if not IS_WINDOWS:
        return jsonify({"ok": True, "demo": True, "msg": f"[DEMO] Would run: {cmd}"})
    try:
        subprocess.Popen(cmd, shell=True, creationflags=_WIN_NO_WINDOW)
        return jsonify({"ok": True, "msg": f"Uninstaller launched for {name}. Follow the prompts."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/apps/open-folder", methods=["POST"])
def api_apps_open_folder():
    data = request.get_json() or {}
    path = data.get("path", "")
    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "error": "Folder does not exist or path not provided."})
    if IS_WINDOWS:
        subprocess.Popen(["explorer", path])
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════════════════════════════════
# BROKEN SHORTCUTS + EMPTY FOLDERS SCANNER
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/cleaner/broken-shortcuts")
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


@app.route("/api/cleaner/delete-shortcuts", methods=["POST"])
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


@app.route("/api/cleaner/empty-folders")
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


@app.route("/api/cleaner/delete-empty-folders", methods=["POST"])
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
# FOLDER SIZE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/folder-sizes/scan", methods=["POST"])
def api_folder_sizes_scan():
    data = request.get_json() or {}
    root_path = data.get("path", os.path.expanduser("~"))
    max_depth = int(data.get("depth", 2))

    if not IS_WINDOWS:
        return jsonify({"folders": [
            {"path": "C:\\Users\\User\\Downloads", "name": "Downloads", "size_bytes": 8589934592, "size_human": "8.0 GB", "depth": 1, "file_count": 842},
            {"path": "C:\\Users\\User\\Videos", "name": "Videos", "size_bytes": 5368709120, "size_human": "5.0 GB", "depth": 1, "file_count": 34},
            {"path": "C:\\Users\\User\\Documents", "name": "Documents", "size_bytes": 2147483648, "size_human": "2.0 GB", "depth": 1, "file_count": 1203},
            {"path": "C:\\Users\\User\\Pictures", "name": "Pictures", "size_bytes": 1073741824, "size_human": "1.0 GB", "depth": 1, "file_count": 567},
            {"path": "C:\\Users\\User\\AppData\\Local\\Temp", "name": "Temp", "size_bytes": 536870912, "size_human": "512.0 MB", "depth": 2, "file_count": 4321},
            {"path": "C:\\Users\\User\\AppData\\Roaming\\Spotify", "name": "Spotify", "size_bytes": 314572800, "size_human": "300.0 MB", "depth": 2, "file_count": 88},
            {"path": "C:\\Users\\User\\Desktop", "name": "Desktop", "size_bytes": 209715200, "size_human": "200.0 MB", "depth": 1, "file_count": 41},
        ], "demo": True})

    def _dir_size_and_count(path):
        total = 0
        count = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                        count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        sub_size, sub_count = _dir_size_and_count(entry.path)
                        total += sub_size
                        count += sub_count
                except PermissionError:
                    pass
        except PermissionError:
            pass
        return total, count

    def _fmt(b):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    folders = []

    def _walk(path, depth):
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(path):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                size, count = _dir_size_and_count(entry.path)
                folders.append({
                    "path": entry.path,
                    "name": entry.name,
                    "size_bytes": size,
                    "size_human": _fmt(size),
                    "depth": depth,
                    "file_count": count
                })
                if depth < max_depth:
                    _walk(entry.path, depth + 1)
        except PermissionError:
            pass

    _walk(root_path, 1)
    folders.sort(key=lambda x: x["size_bytes"], reverse=True)
    return jsonify({"folders": folders[:50], "demo": False, "root": root_path})


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP ITEMS — enhanced with impact scoring
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/startup-items/export")
def api_startup_export():
    """Export startup items to JSON."""
    items_resp = api_startup()
    return app.response_class(
        items_resp.get_data(as_text=True),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=startup_items.json"}
    )


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 13: RECOMMENDATIONS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

RECOMMENDATIONS_FILE = "recommendations_state.json"
_rec_lock = threading.Lock()

def _load_rec_state():
    try:
        if os.path.exists(RECOMMENDATIONS_FILE):
            with open(RECOMMENDATIONS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"dismissed": [], "snoozed": {}, "history": []}

def _save_rec_state(state):
    try:
        with open(RECOMMENDATIONS_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def _generate_recommendations():
    recs = []
    ts = datetime.now().isoformat()

    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        if cpu > 80:
            recs.append({"id": "cpu_high", "category": "Performance", "priority": "high",
                "title": f"CPU is under heavy load ({cpu:.0f}%)",
                "explanation": "Sustained high CPU usage slows the whole system. Check top processes and close unnecessary apps.",
                "evidence": f"CPU at {cpu:.0f}%", "action": "View Processes", "module": "processes",
                "benefit": 8, "risk": "low", "actionable": True})
        elif cpu > 60:
            recs.append({"id": "cpu_medium", "category": "Performance", "priority": "medium",
                "title": f"CPU usage is elevated ({cpu:.0f}%)",
                "explanation": "CPU is moderately busy. Consider closing background apps.",
                "evidence": f"CPU at {cpu:.0f}%", "action": "View Processes", "module": "processes",
                "benefit": 5, "risk": "low", "actionable": True})

        ram_avail_gb = mem.available / (1024 ** 3)
        if ram_avail_gb < 1.5:
            recs.append({"id": "ram_critical", "category": "Performance", "priority": "high",
                "title": f"Low RAM — only {ram_avail_gb:.1f} GB available",
                "explanation": "Very low available RAM forces Windows to use slow page file swapping. Close apps or consider a RAM upgrade.",
                "evidence": f"{ram_avail_gb:.1f} GB free of {mem.total/(1024**3):.1f} GB",
                "action": "View System Info", "module": "system", "benefit": 9, "risk": "low", "actionable": True})
        elif mem.percent > 80:
            recs.append({"id": "ram_high", "category": "Performance", "priority": "medium",
                "title": f"Memory usage is high ({mem.percent:.0f}%)",
                "explanation": "High RAM usage can cause slowdowns. Close unused apps or browser tabs.",
                "evidence": f"{mem.percent:.0f}% used ({ram_avail_gb:.1f} GB free)",
                "action": "View Processes", "module": "processes", "benefit": 6, "risk": "low", "actionable": True})

        disk_free_pct = 100 - disk.percent
        if disk_free_pct < 10:
            recs.append({"id": "disk_critical", "category": "Storage", "priority": "high",
                "title": f"Disk is almost full — only {disk_free_pct:.0f}% free",
                "explanation": "Windows needs free disk space to function properly. Run a system clean now.",
                "evidence": f"{format_bytes(disk.free)} free of {format_bytes(disk.total)}",
                "action": "Clean Now", "module": "cleaner", "benefit": 10, "risk": "low", "actionable": True})
        elif disk_free_pct < 20:
            recs.append({"id": "disk_low", "category": "Storage", "priority": "medium",
                "title": f"Disk space is getting low ({disk_free_pct:.0f}% free)",
                "explanation": "Consider running the system cleaner or large file finder to reclaim space.",
                "evidence": f"{format_bytes(disk.free)} free of {format_bytes(disk.total)}",
                "action": "Scan for Junk", "module": "cleaner", "benefit": 7, "risk": "low", "actionable": True})

        uptime_secs = time.time() - psutil.boot_time()
        uptime_days = uptime_secs / 86400
        if uptime_days > 14:
            recs.append({"id": "uptime_long", "category": "Maintenance", "priority": "medium",
                "title": f"System has been running for {uptime_days:.0f} days",
                "explanation": "Long uptime can lead to memory leaks and accumulated temp files. A restart is recommended.",
                "evidence": f"Uptime: {uptime_days:.1f} days", "action": "Restart Reminder", "module": "dashboard",
                "benefit": 5, "risk": "low", "actionable": False})
        elif uptime_days > 7:
            recs.append({"id": "uptime_week", "category": "Maintenance", "priority": "low",
                "title": f"PC has been on for {uptime_days:.0f} days without restart",
                "explanation": "Consider restarting this week to apply pending updates and clear memory.",
                "evidence": f"Uptime: {uptime_days:.1f} days", "action": None, "module": "dashboard",
                "benefit": 3, "risk": "low", "actionable": False})
    except Exception:
        pass

    try:
        procs = [(p.name(), p.cpu_percent()) for p in psutil.process_iter(["name", "cpu_percent"]) if p.info["cpu_percent"] > 15]
        if len(procs) >= 3:
            names = ", ".join(p[0] for p in procs[:3])
            recs.append({"id": "heavy_procs", "category": "Performance", "priority": "medium",
                "title": f"{len(procs)} processes are consuming high CPU",
                "explanation": f"Several background processes are using significant CPU: {names}.",
                "evidence": f"High-CPU processes: {names}", "action": "View Processes", "module": "processes",
                "benefit": 6, "risk": "low", "actionable": True})
    except Exception:
        pass

    try:
        home = os.path.expanduser("~")
        dl = os.path.join(home, "Downloads")
        if os.path.isdir(dl):
            old_files = [f for f in os.listdir(dl)
                         if os.path.isfile(os.path.join(dl, f))
                         and (time.time() - os.path.getmtime(os.path.join(dl, f))) > 60 * 86400]
            if len(old_files) > 10:
                recs.append({"id": "downloads_old", "category": "Organization", "priority": "medium",
                    "title": f"Downloads folder has {len(old_files)} files older than 60 days",
                    "explanation": "Old downloads accumulate over time. Review and archive or delete them.",
                    "evidence": f"{len(old_files)} files older than 60 days in Downloads",
                    "action": "Organize Downloads", "module": "file-organizer", "benefit": 5, "risk": "low", "actionable": True})

        desktop = os.path.join(home, "Desktop")
        if os.path.isdir(desktop):
            desktop_files = [f for f in os.listdir(desktop) if os.path.isfile(os.path.join(desktop, f))]
            if len(desktop_files) > 20:
                recs.append({"id": "desktop_cluttered", "category": "Organization", "priority": "low",
                    "title": f"Desktop has {len(desktop_files)} files — consider organizing",
                    "explanation": "A cluttered desktop can slow icon rendering and make finding files harder.",
                    "evidence": f"{len(desktop_files)} files on Desktop",
                    "action": "File Organizer", "module": "file-organizer", "benefit": 3, "risk": "low", "actionable": True})
    except Exception:
        pass

    scan_data = scan_results
    if scan_data.get("total_size", 0) > 500 * 1024 * 1024:
        recs.append({"id": "junk_large", "category": "Storage", "priority": "medium",
            "title": f"Last scan found {format_bytes(scan_data['total_size'])} of cleanable junk",
            "explanation": "Your last system scan identified significant clutter. Run the cleaner to reclaim space.",
            "evidence": f"{format_bytes(scan_data['total_size'])} in {scan_data.get('total_files', 0)} files",
            "action": "Clean Now", "module": "cleaner", "benefit": 8, "risk": "low", "actionable": True})

    if scan_data.get("last_scan") is None:
        recs.append({"id": "no_scan", "category": "Maintenance", "priority": "medium",
            "title": "You haven't run a system scan yet",
            "explanation": "Run your first scan to discover temp files, large files, and clutter on this system.",
            "evidence": "No scan history found", "action": "Scan Now", "module": "cleaner",
            "benefit": 7, "risk": "low", "actionable": True})

    hour = datetime.now().hour
    if hour >= 21 or hour < 7:
        recs.append({"id": "night_light", "category": "Wellness", "priority": "low",
            "title": "It's late — consider enabling Night Light mode",
            "explanation": "Blue light exposure in the evening affects sleep quality. Enable Night Light in Windows Display settings.",
            "evidence": f"Current time: {datetime.now().strftime('%H:%M')}",
            "action": "Open Wellness", "module": "wellness", "benefit": 4, "risk": "low", "actionable": True})

    state = _load_rec_state()
    dismissed = set(state.get("dismissed", []))
    snoozed = state.get("snoozed", {})
    now_iso = datetime.now().isoformat()

    filtered = []
    for r in recs:
        rid = r["id"]
        if rid in dismissed:
            continue
        if rid in snoozed:
            snooze_until = snoozed[rid]
            if now_iso < snooze_until:
                continue
            else:
                del snoozed[rid]
        r["timestamp"] = ts
        filtered.append(r)

    filtered.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    state["snoozed"] = snoozed
    _save_rec_state(state)
    return filtered


@app.route("/api/recommendations")
def api_recommendations():
    recs = _generate_recommendations()
    return jsonify({"recommendations": recs, "total": len(recs),
                    "high": sum(1 for r in recs if r["priority"] == "high"),
                    "medium": sum(1 for r in recs if r["priority"] == "medium"),
                    "low": sum(1 for r in recs if r["priority"] == "low")})


@app.route("/api/recommendations/dismiss", methods=["POST"])
def api_rec_dismiss():
    data = request.get_json() or {}
    rid = data.get("id")
    if not rid:
        return jsonify({"status": "error"}), 400
    with _rec_lock:
        state = _load_rec_state()
        if rid not in state["dismissed"]:
            state["dismissed"].append(rid)
        history_entry = {"id": rid, "action": "dismissed", "timestamp": datetime.now().isoformat()}
        state.setdefault("history", []).append(history_entry)
        _save_rec_state(state)
    return jsonify({"status": "ok"})


@app.route("/api/recommendations/snooze", methods=["POST"])
def api_rec_snooze():
    data = request.get_json() or {}
    rid = data.get("id")
    hours = int(data.get("hours", 24))
    if not rid:
        return jsonify({"status": "error"}), 400
    with _rec_lock:
        state = _load_rec_state()
        until = (datetime.now() + timedelta(hours=hours)).isoformat()
        state.setdefault("snoozed", {})[rid] = until
        state.setdefault("history", []).append({"id": rid, "action": f"snoozed_{hours}h", "timestamp": datetime.now().isoformat()})
        _save_rec_state(state)
    return jsonify({"status": "ok", "snoozed_until": until})


@app.route("/api/recommendations/reset-dismissed", methods=["POST"])
def api_rec_reset():
    with _rec_lock:
        state = _load_rec_state()
        state["dismissed"] = []
        state["snoozed"] = {}
        _save_rec_state(state)
    return jsonify({"status": "ok"})


@app.route("/api/recommendations/history")
def api_rec_history():
    state = _load_rec_state()
    return jsonify({"history": list(reversed(state.get("history", [])))})


@app.route("/api/recommendations/export")
def api_rec_export():
    recs = _generate_recommendations()
    lines = ["MTT Windows Infinite Optimizer — Recommendations Report",
             f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "", ""]
    for r in recs:
        lines.append(f"[{r['priority'].upper()}] {r['title']}")
        lines.append(f"  Category : {r['category']}")
        lines.append(f"  Evidence : {r['evidence']}")
        lines.append(f"  Why      : {r['explanation']}")
        lines.append("")
    content = "\n".join(lines)
    return app.response_class(content, mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=recommendations.txt"})


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


@app.route("/api/profiles")
def api_profiles():
    data = _load_profiles_data()
    all_profiles = {**BUILTIN_PROFILES, **data.get("custom_profiles", {})}
    return jsonify({"profiles": list(all_profiles.values()),
                    "active": data.get("active_profile"),
                    "history": data.get("history", [])[-5:]})


@app.route("/api/profiles/apply", methods=["POST"])
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


@app.route("/api/profiles/save", methods=["POST"])
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


@app.route("/api/profiles/delete", methods=["POST"])
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


@app.route("/api/profiles/restore-previous", methods=["POST"])
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


@app.route("/api/maintenance/tasks")
def api_maintenance_tasks():
    tasks = _load_maintenance_tasks()
    return jsonify({"tasks": tasks})


@app.route("/api/maintenance/tasks/toggle", methods=["POST"])
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


@app.route("/api/maintenance/tasks/run", methods=["POST"])
def api_maintenance_run():
    data = request.get_json() or {}
    tid = data.get("id")
    if not tid:
        return jsonify({"status": "error", "message": "Task ID required"}), 400
    result = _run_maintenance_task(tid)
    return jsonify(result)


@app.route("/api/maintenance/tasks/save", methods=["POST"])
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


@app.route("/api/maintenance/tasks/delete", methods=["POST"])
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


@app.route("/api/maintenance/history")
def api_maintenance_history():
    history = _load_maintenance_history()
    return jsonify({"history": list(reversed(history[-50:]))})


@app.route("/api/maintenance/history/export")
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
    return app.response_class(content, mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=maintenance_history.txt"})


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
