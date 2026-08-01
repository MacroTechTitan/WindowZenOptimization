"""Large File Finder — report only.

Scans USER-SELECTED roots (never a whole drive by default), surfaces files
over a configurable threshold, categorises them by extension, and flags
superseded installers. This module never deletes; routes/largefiles.py owns
the separate, per-file deletion action.
"""
import os
import re
import threading
from datetime import datetime

from core.state import IS_WINDOWS
from core.util import log_activity, format_bytes
from core.safety import is_excluded_path, is_cloud_sync_path

DEFAULT_THRESHOLD_MB = 500
MAX_RESULTS = 500

# ─── Categories ────────────────────────────────────────────────
CATEGORIES = {
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".mpg", ".mpeg", ".ts", ".m2ts", ".prproj", ".veg"},
    "installer_archive": {".exe", ".msi", ".msix", ".appx", ".zip", ".rar", ".7z",
                          ".tar", ".gz", ".bz2", ".xz", ".cab", ".pkg", ".deb", ".rpm"},
    "disk_image": {".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".vdi", ".dmg",
                   ".wim", ".esd", ".qcow2"},
    "model_file": {".gguf", ".ggml", ".safetensors", ".ckpt", ".pt", ".pth", ".bin",
                   ".onnx", ".h5", ".pb", ".tflite", ".mlmodel", ".npz", ".msgpack"},
}


def categorize(filename):
    ext = os.path.splitext(filename)[1].lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return "other"


def suggested_roots():
    """Default suggestions only — the user picks what actually gets scanned."""
    home = os.path.expanduser("~")
    candidates = [
        ("Downloads", os.path.join(home, "Downloads")),
        ("Desktop", os.path.join(home, "Desktop")),
        ("Videos", os.path.join(home, "Videos")),
        ("Documents", os.path.join(home, "Documents")),
        ("User home", home),
    ]
    out = []
    for label, path in candidates:
        if not os.path.isdir(path):
            continue
        synced, _ = is_cloud_sync_path(path)
        out.append({
            "label": label,
            "path": path,
            "default_on": label in ("Downloads", "Desktop"),
            "cloud_synced": synced,
        })
    return out


# ─── Superseded-installer heuristic ────────────────────────────
_VERSION_RE = re.compile(r"[._-]?v?(\d+(?:[._]\d+){1,3})")
_INSTALLER_EXTS = {".exe", ".msi", ".msix", ".appx"}


def _version_tuple(text):
    m = _VERSION_RE.search(text)
    if not m:
        return None
    parts = re.split(r"[._]", m.group(1))
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def _product_key(filename):
    """Strip version/date/build noise so two builds of one product collide."""
    stem = os.path.splitext(filename)[0].lower()
    stem = _VERSION_RE.sub(" ", stem)
    stem = re.sub(r"\b(x64|x86|win64|win32|amd64|arm64|setup|installer|"
                  r"full|offline|online|latest|final|release)\b", " ", stem)
    stem = re.sub(r"[^a-z]+", " ", stem)
    return " ".join(stem.split())


def flag_old_installers(files):
    """Mark installers that have a newer same-product file alongside them.

    Heuristic and advisory only — nothing is auto-selected for deletion.
    """
    groups = {}
    for f in files:
        if os.path.splitext(f["name"])[1].lower() not in _INSTALLER_EXTS:
            continue
        version = _version_tuple(f["name"])
        if version is None:
            continue
        key = _product_key(f["name"])
        if not key:
            continue
        groups.setdefault((key, os.path.dirname(f["path"]).lower()), []).append((version, f))

    flagged = 0
    for (key, _folder), members in groups.items():
        if len(members) < 2:
            continue
        newest = max(v for v, _ in members)
        for version, f in members:
            if version < newest:
                f["old_installer"] = True
                f["superseded_by"] = ".".join(str(n) for n in newest)
                flagged += 1
    return flagged


# ─── Scan ──────────────────────────────────────────────────────
largefiles_results = {
    "status": "idle",
    "files": [],
    "roots": [],
    "threshold_mb": DEFAULT_THRESHOLD_MB,
    "total_bytes": 0,
    "by_category": {},
    "old_installers": 0,
    "skipped_roots": [],
    "last_scan": None,
    "truncated": False,
}

_lock = threading.Lock()


def scan_large_files(roots, threshold_mb=DEFAULT_THRESHOLD_MB):
    """Report phase. Deletes nothing.

    Only the roots handed in are walked; excluded system roots are dropped.
    """
    threshold = max(1, int(threshold_mb)) * 1024 * 1024
    accepted, skipped = [], []
    for r in roots or []:
        if not r:
            continue
        excluded, reason = is_excluded_path(r)
        if excluded:
            skipped.append({"path": r, "reason": reason})
            log_activity(f"Large File Finder: skipping protected root {r}", "WARN")
            continue
        if not os.path.isdir(r):
            skipped.append({"path": r, "reason": "not a directory"})
            continue
        accepted.append(r)

    log_activity(f"Large File Finder: scanning {len(accepted)} root(s) "
                 f"for files over {threshold_mb} MB", "TASK")

    found = []
    seen = set()
    for root in accepted:
        for dirpath, dirnames, filenames in os.walk(root):
            # Do not descend into protected or cloud-synced subtrees.
            keep = []
            for d in dirnames:
                sub = os.path.join(dirpath, d)
                excluded, _ = is_excluded_path(sub)
                if excluded or d.lower() in ("$recycle.bin", "system volume information"):
                    continue
                keep.append(d)
            dirnames[:] = keep

            for fname in filenames:
                fp = os.path.join(dirpath, fname)
                key = os.path.normcase(fp)
                if key in seen:
                    continue
                try:
                    st = os.stat(fp)
                except (OSError, PermissionError, ValueError):
                    continue
                if not os.path.isfile(fp) or st.st_size < threshold:
                    continue
                seen.add(key)
                synced, cloud_root = is_cloud_sync_path(fp)
                found.append({
                    "path": fp,
                    "name": fname,
                    "size": st.st_size,
                    "size_fmt": format_bytes(st.st_size),
                    "category": categorize(fname),
                    "folder": dirpath,
                    "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "cloud_synced": synced,
                    "cloud_root": cloud_root if synced else "",
                    "old_installer": False,
                    "superseded_by": "",
                })

    found.sort(key=lambda f: f["size"], reverse=True)
    old_count = flag_old_installers(found)

    by_category = {}
    for f in found:
        slot = by_category.setdefault(f["category"], {"count": 0, "bytes": 0})
        slot["count"] += 1
        slot["bytes"] += f["size"]
    for slot in by_category.values():
        slot["bytes_fmt"] = format_bytes(slot["bytes"])

    total = sum(f["size"] for f in found)
    truncated = len(found) > MAX_RESULTS

    with _lock:
        largefiles_results.update({
            "status": "complete",
            "files": found[:MAX_RESULTS],
            "roots": accepted,
            "threshold_mb": threshold_mb,
            "total_bytes": total,
            "total_fmt": format_bytes(total),
            "by_category": by_category,
            "old_installers": old_count,
            "skipped_roots": skipped,
            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "truncated": truncated,
            "shown": min(len(found), MAX_RESULTS),
            "found": len(found),
            "platform_supported": IS_WINDOWS,
        })

    if truncated:
        log_activity(f"Large File Finder: {len(found)} matches, showing the "
                     f"largest {MAX_RESULTS}", "WARN")
    log_activity(f"Large File Finder: {len(found)} file(s) over {threshold_mb} MB, "
                 f"{format_bytes(total)} total, {old_count} superseded installer(s)",
                 "SUCCESS")
    return dict(largefiles_results)
