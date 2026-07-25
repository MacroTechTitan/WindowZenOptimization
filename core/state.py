"""Shared mutable state and constants — single source of truth.

Every module that touches these globals imports them from here so that all
in-place mutations are visible everywhere. No module rebinds these names
(there are no `global x = ...` reassignments anywhere in the codebase), so
importing the names directly is safe.
"""
import os
import platform
import subprocess
import threading
from datetime import datetime

# Repo root: parent of the core/ package. Used to anchor __file__-based paths
# so they resolve to the same absolute location they did when defined in the
# top-level app.py (which lived at the repo root).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Platform constants ────────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
_WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0

# ─── Activity log buffer ───────────────────────────────────────
activity_log = []
LOG_MAX = 200

# ─── Scan / clean / wellness / registry / security state ───────
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

# ─── Undo log ──────────────────────────────────────────────────
undo_log = []
UNDO_LOG_MAX = 100

# ─── Large files ───────────────────────────────────────────────
large_files_results = {
    "files": [],
    "total_size": 0,
    "threshold_mb": 100,
    "last_scan": None,
    "status": "idle",
}

# ─── Organize preview ──────────────────────────────────────────
organize_preview_results = {
    "actions": [],
    "last_preview": None,
}

# ─── Network fix ───────────────────────────────────────────────
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
