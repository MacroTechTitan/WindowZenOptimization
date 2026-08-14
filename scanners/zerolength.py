"""Zero-length File Finder — report only.

A zero-byte file is ambiguous in a way a large file or a duplicate is not.
It is *sometimes* a failed download or a truncated export, and just as often
it is load-bearing: a lock file, a package marker, a sentinel a program
polls for. Deleting the second kind breaks software silently.

So this scanner is deliberately more conservative than the other two. On top
of ``core.safety.is_excluded_path`` it applies a hard, per-file exclusion
list — locations, exact filenames, extensions and container directories that
are known to use empty files as structure rather than as data. Anything on
that list is never reported at all, so it cannot be selected by accident.

This module never deletes. routes/zerolength.py owns the separate,
user-selected removal action, which routes through core.safety exactly like
the duplicate and large-file finders.
"""
import os
import threading
from datetime import datetime

from core.util import log_activity
from core.safety import is_excluded_path, is_cloud_sync_path

MAX_FILES = 500


def _sysdrive():
    return os.environ.get("SystemDrive", "C:")


def _protected_roots():
    """Locations whose empty files are never the user's to delete."""
    roots = [
        os.environ.get("SystemRoot", os.path.join(_sysdrive(), "\\Windows")),
        os.environ.get("ProgramFiles", os.path.join(_sysdrive(), "\\Program Files")),
        os.environ.get("ProgramFiles(x86)", os.path.join(_sysdrive(), "\\Program Files (x86)")),
        os.environ.get("ProgramData", os.path.join(_sysdrive(), "\\ProgramData")),
    ]
    return [os.path.normcase(os.path.abspath(r)) for r in roots if r]


# Exact filenames whose whole purpose is to exist while being empty.
PROTECTED_NAMES = {
    "__init__.py", ".gitkeep", ".keep", ".placeholder", ".nomedia",
    "desktop.ini", "py.typed", ".dirstamp", ".watchmanconfig",
    ".gitmodules", ".npmignore", ".metadata_never_index",
}

# Extensions that mark a file as a lock/sentinel rather than content.
PROTECTED_EXTS = {
    ".lock", ".lck", ".pid", ".sentinel", ".stamp", ".marker", ".lockfile",
}

# Directories whose internals belong to a tool, not to the user.
PROTECTED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "site-packages",
    "__pycache__", "$recycle.bin",
}

# Path segments that mean "per-user application state".
APPDATA_SEGMENTS = {"appdata", "application data"}


def _segments(path):
    drive, tail = os.path.splitdrive(os.path.normcase(path))
    return [s for s in tail.replace("/", os.sep).split(os.sep) if s]


def exclusion_reason(path, fname):
    """Why this empty file must not be offered for deletion, or None.

    Applied per FILE, after is_excluded_path has already vetted the tree, so
    a protected name is skipped even inside a folder the user chose.
    """
    norm = os.path.normcase(os.path.abspath(path))
    for root in _protected_roots():
        if norm == root or norm.startswith(root + os.sep):
            return "inside a protected system location"

    segs = _segments(os.path.dirname(norm))
    if any(s in APPDATA_SEGMENTS for s in segs):
        return "application data"
    hit = next((s for s in segs if s in PROTECTED_DIRS), None)
    if hit:
        return f"inside {hit}"

    low = fname.lower()
    if low in PROTECTED_NAMES:
        return "structural marker file"
    if os.path.splitext(low)[1] in PROTECTED_EXTS:
        return "lock or sentinel file"
    return None


zerolength_results = {
    "status": "idle",
    "files": [],
    "roots": [],
    "found": 0,
    "shown": 0,
    "excluded": 0,
    "skipped_roots": [],
    "last_scan": None,
    "truncated": False,
}

_lock = threading.Lock()


def scan_zero_length(roots):
    """Report phase. Deletes nothing and never pre-selects a file."""
    accepted, skipped = [], []
    for r in roots or []:
        if not r:
            continue
        excluded, reason = is_excluded_path(r)
        if excluded:
            skipped.append({"path": r, "reason": reason})
            log_activity(f"Zero-length Finder: skipping protected root {r}", "WARN")
            continue
        if not os.path.isdir(r):
            skipped.append({"path": r, "reason": "not a directory"})
            continue
        accepted.append(r)

    log_activity(f"Zero-length Finder: scanning {len(accepted)} root(s)", "TASK")

    found, excluded_count = [], 0
    for root in accepted:
        for dirpath, dirnames, filenames in os.walk(root):
            keep = []
            for d in dirnames:
                if d.lower() in PROTECTED_DIRS or d.lower() == "system volume information":
                    continue
                sub = os.path.join(dirpath, d)
                is_ex, _ = is_excluded_path(sub)
                if is_ex:
                    continue
                keep.append(d)
            dirnames[:] = keep

            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                try:
                    st = os.stat(fp)
                except (OSError, PermissionError, ValueError):
                    continue
                if st.st_size != 0 or not os.path.isfile(fp):
                    continue
                if exclusion_reason(fp, fname):
                    excluded_count += 1
                    continue
                synced, cloud_root = is_cloud_sync_path(fp)
                found.append({
                    "path": fp,
                    "name": fname,
                    "folder": dirpath,
                    "size": 0,
                    "size_fmt": "0 B",
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "mtime": st.st_mtime,
                    "cloud_synced": synced,
                    "cloud_root": cloud_root if synced else "",
                })

    found.sort(key=lambda f: f["mtime"])
    shown = found[:MAX_FILES]

    with _lock:
        zerolength_results.update({
            "status": "done",
            "files": shown,
            "roots": accepted,
            "found": len(found),
            "shown": len(shown),
            "excluded": excluded_count,
            "skipped_roots": skipped,
            "truncated": len(found) > len(shown),
            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    log_activity(f"Zero-length Finder: {len(found)} empty file(s) reported, "
                 f"{excluded_count} protected placeholder(s) withheld", "INFO")
    return dict(zerolength_results)
