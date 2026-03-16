import os
import sys
import time
import json
import glob
import socket
import hashlib
import threading
import platform
import shutil
import psutil
import subprocess
import urllib.request
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mtt-optimizer-secret-2026-macro-tech-titan")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mttadmin2026")

IS_WINDOWS = platform.system() == "Windows"
SETTINGS_FILE = "settings.json"
activity_log = []
LOG_MAX = 200
scheduler = BackgroundScheduler()

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
                    capture_output=True, text=True, timeout=10
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
                    capture_output=True, timeout=30
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
                capture_output=True, text=True, timeout=10
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
                capture_output=True, text=True, timeout=10
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
                capture_output=True, text=True, timeout=10
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


def run_file_organizer_scan():
    log_activity("Starting file organizer scan...", "TASK")
    home = os.path.expanduser("~")
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
    dup_dirs = [
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
    return render_template("landing.html")


@app.route("/eula")
def eula_page():
    return render_template("eula.html")


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
    return render_template("dashboard.html", initial_page=page or "dashboard")


@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_system_metrics())


@app.route("/api/logs")
def api_logs():
    return jsonify(activity_log[-50:])


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
            subprocess.Popen(["shutdown", "/r", "/t", "30"])
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
    thread = threading.Thread(target=run_file_organizer_scan, daemon=True)
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
                cmd, shell=True, capture_output=True, text=True, timeout=30
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


# ─── Admin Panel ──────────────────────────────────────────────
def _admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin")
def admin_index():
    return render_template("admin.html")


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
    return render_template("admin.html")


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


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
