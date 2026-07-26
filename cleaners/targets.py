"""Cleanup target definitions and per-target scan/clean logic."""
import os
import glob
import subprocess

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import get_dir_size, log_activity


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

