"""Generic helpers shared across the app: logging, byte formatting,
directory sizing, and environment lookups."""
import os
from datetime import datetime

from core.state import activity_log, LOG_MAX


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
