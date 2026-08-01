"""Duplicate File Finder — FILE level only, report only.

Three-pass strategy, deliberately cheap-first so we never full-hash the
whole scan set:

  pass 1  group by exact byte size          (stat only, no reads)
  pass 2  partial hash: first + last 64 KB  (two seeks per candidate)
  pass 3  full SHA-256, ONLY for files that collided in pass 2

Folder-level duplicate detection is explicitly out of scope this sprint
(see docs/BACKLOG_PHASE2.md) and is not implemented here.

This module never deletes. routes/duplicates.py owns the separate,
user-selected removal action.
"""
import os
import hashlib
import threading
from datetime import datetime

from core.state import IS_WINDOWS
from core.util import log_activity, format_bytes
from core.safety import is_excluded_path, is_cloud_sync_path

CHUNK = 64 * 1024          # partial-hash window, head and tail
READ_BLOCK = 1024 * 1024   # full-hash read block
MIN_SIZE = 1024            # ignore trivially small files
MAX_GROUPS = 300


def _partial_hash(path, size):
    """SHA-256 of the first and last 64 KB (whole file when smaller)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        if size <= CHUNK * 2:
            h.update(f.read())
        else:
            h.update(f.read(CHUNK))
            f.seek(-CHUNK, os.SEEK_END)
            h.update(f.read(CHUNK))
    return h.hexdigest()


def _full_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(READ_BLOCK), b""):
            h.update(block)
    return h.hexdigest()


duplicates_results = {
    "status": "idle",
    "groups": [],
    "roots": [],
    "group_count": 0,
    "reclaimable_bytes": 0,
    "reclaimable_fmt": "0 B",
    "files_hashed": 0,
    "skipped_roots": [],
    "last_scan": None,
    "truncated": False,
}

_lock = threading.Lock()


def _collect_candidates(roots):
    """pass 0 — walk the selected roots, honouring exclusions."""
    by_size = {}
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
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
                try:
                    st = os.stat(fp)
                except (OSError, PermissionError, ValueError):
                    continue
                if not os.path.isfile(fp) or st.st_size < MIN_SIZE:
                    continue
                by_size.setdefault(st.st_size, []).append((fp, st))
    return by_size


def scan_duplicates(roots, min_size=MIN_SIZE):
    """Report phase. Deletes nothing and never auto-selects a copy."""
    accepted, skipped = [], []
    for r in roots or []:
        if not r:
            continue
        excluded, reason = is_excluded_path(r)
        if excluded:
            skipped.append({"path": r, "reason": reason})
            log_activity(f"Duplicate Finder: skipping protected root {r}", "WARN")
            continue
        if not os.path.isdir(r):
            skipped.append({"path": r, "reason": "not a directory"})
            continue
        accepted.append(r)

    log_activity(f"Duplicate Finder: scanning {len(accepted)} root(s) — "
                 f"pass 1 of 3 (group by size)", "TASK")

    # ── pass 1: size ───────────────────────────────────────────
    by_size = _collect_candidates(accepted)
    size_groups = {s: v for s, v in by_size.items()
                   if len(v) > 1 and s >= max(min_size, MIN_SIZE)}
    pass1_files = sum(len(v) for v in size_groups.values())
    log_activity(f"Duplicate Finder: pass 1 — {pass1_files} file(s) share a size "
                 f"with at least one other, across {len(size_groups)} size group(s)", "INFO")

    # ── pass 2: partial hash (head + tail 64 KB) ───────────────
    partial_groups = {}
    hashed = 0
    for size, entries in size_groups.items():
        buckets = {}
        for fp, st in entries:
            try:
                ph = _partial_hash(fp, size)
                hashed += 1
            except (OSError, PermissionError):
                continue
            buckets.setdefault(ph, []).append((fp, st))
        for ph, members in buckets.items():
            if len(members) > 1:
                partial_groups[(size, ph)] = members
    pass2_files = sum(len(v) for v in partial_groups.values())
    log_activity(f"Duplicate Finder: pass 2 — {pass2_files} file(s) collided on "
                 f"partial hash; only these get a full SHA-256", "INFO")

    # ── pass 3: full SHA-256, only on partial-hash collisions ──
    full_groups = {}
    for (size, _ph), members in partial_groups.items():
        buckets = {}
        for fp, st in members:
            try:
                fh = _full_hash(fp)
                hashed += 1
            except (OSError, PermissionError):
                continue
            buckets.setdefault(fh, []).append((fp, st))
        for fh, confirmed in buckets.items():
            if len(confirmed) > 1:
                full_groups[fh] = (size, confirmed)

    # ── build the report ───────────────────────────────────────
    groups = []
    reclaimable = 0
    for digest, (size, members) in full_groups.items():
        members.sort(key=lambda m: m[1].st_mtime)   # oldest first, purely for display
        copies = []
        for fp, st in members:
            synced, cloud_root = is_cloud_sync_path(fp)
            allowed_excluded, _ = is_excluded_path(fp)
            copies.append({
                "path": fp,
                "name": os.path.basename(fp),
                "folder": os.path.dirname(fp),
                "size": size,
                "size_fmt": format_bytes(size),
                "modified": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "cloud_synced": synced,
                "cloud_root": cloud_root if synced else "",
                "protected": allowed_excluded,
                # NOTE: no "selected" / "keep" field by design — the user
                # chooses which copies to remove. Nothing is auto-selected.
            })
        wasted = size * (len(members) - 1)
        reclaimable += wasted
        groups.append({
            "hash": digest[:16],
            "size": size,
            "size_fmt": format_bytes(size),
            "count": len(members),
            "wasted": wasted,
            "wasted_fmt": format_bytes(wasted),
            "copies": copies,
        })

    groups.sort(key=lambda g: g["wasted"], reverse=True)
    truncated = len(groups) > MAX_GROUPS

    with _lock:
        duplicates_results.update({
            "status": "complete",
            "groups": groups[:MAX_GROUPS],
            "roots": accepted,
            "group_count": len(groups),
            "shown": min(len(groups), MAX_GROUPS),
            "reclaimable_bytes": reclaimable,
            "reclaimable_fmt": format_bytes(reclaimable),
            "files_hashed": hashed,
            "skipped_roots": skipped,
            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "truncated": truncated,
            "platform_supported": IS_WINDOWS,
            "passes": {
                "pass1_size_candidates": pass1_files,
                "pass2_partial_collisions": pass2_files,
                "pass3_confirmed_files": sum(g["count"] for g in groups),
            },
        })

    log_activity(f"Duplicate Finder: {len(groups)} duplicate group(s), "
                 f"{format_bytes(reclaimable)} reclaimable "
                 f"({hashed} hash operations)", "SUCCESS")
    return dict(duplicates_results)
