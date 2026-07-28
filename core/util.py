"""Generic helpers shared across the app: logging, byte formatting,
directory sizing, environment lookups, and local version info."""
import os
import json
from datetime import datetime

from core.state import activity_log, LOG_MAX, BASE_DIR, undo_log, UNDO_LOG_MAX

LOCAL_VERSION_FILE = os.path.join(BASE_DIR, "version.json")


def log_activity(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": message, "level": level}
    activity_log.append(entry)
    if len(activity_log) > LOG_MAX:
        activity_log.pop(0)


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


def get_local_version():
    try:
        with open(LOCAL_VERSION_FILE) as f:
            return json.load(f)
    except Exception:
        return {"version": "1.0.0", "build": 100}
