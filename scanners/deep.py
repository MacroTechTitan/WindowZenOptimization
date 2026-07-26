"""Deep system analysis: file-type census, installed software, event logs."""
import os
import time
import subprocess
from datetime import datetime

from core.state import IS_WINDOWS, deep_analysis_data
from core.util import log_activity


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

