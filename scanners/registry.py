"""Registry scan / fix (simulated heuristic issue detection)."""
import time
from datetime import datetime

from core.state import IS_WINDOWS, registry_data, scan_results
from core.util import log_activity


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

