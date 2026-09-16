"""Unified log of destructive operations, downloadable as .txt or .json.

Every destructive feature — Deep Clean, duplicate removal, large-file
deletion, zero-length removal — records what it did here, in one shape, so
the UI can show a single summary panel afterwards and hand the user a file.

This module ONLY records. It never deletes, never decides what may be
deleted, and is never consulted by ``core.safety``: a caller that stopped
logging would still delete exactly the same things. Logging failures are
swallowed for the same reason — a broken log must not break a cleanup.

Shape of one operation::

    {
      "id": "20260915-181234-000001",
      "operation": "deep_clean",          # stable key, used by the UI
      "label": "Deep Clean",
      "started_at": "2026-09-15 18:12:34",
      "completed_at": "2026-09-15 18:13:02",
      "status": "running|completed|blocked|failed",
      "restore_point": {"created": bool, "message": str},
      "sections": [                        # one per Deep Clean target, or
        {                                  # one per finder run
          "key": "windows_update",
          "label": "Windows Update cache",
          "count": 1000, "bytes": 3221225472,
          "permanent": False,
          "note": "",
          "items": [{"path": ..., "bytes": ..., "action": "recycled"}],
          "items_truncated": 0,
          "skipped": [{"path": ..., "reason": ...}],
          "errors":  [{"path": ..., "error":  ...}],
        }
      ],
      "totals": {"count": 1000, "bytes": 3221225472, "bytes_fmt": "3.0 GB"},
      "message": "Reclaimed 3.0 GB.",
    }

Only paths, byte counts and the app's own reasons are recorded — never file
contents and never credentials.
"""
import functools
import threading
from datetime import datetime

from core.util import format_bytes

# Operations kept in memory. Like activity_log and undo_log in core.state,
# this buffer is per-run: it is not written to disk, so an installed copy
# never accumulates a file of the user's paths.
MAX_OPERATIONS = 25

# Per section. A Deep Clean of a temp folder can remove tens of thousands of
# files; the totals stay exact but the per-item list is capped so neither the
# buffer nor a downloaded log grows without bound.
MAX_ITEMS_PER_SECTION = 2000

# Human labels for the operation keys the UI and the download use.
OPERATION_LABELS = {
    "deep_clean": "Deep Clean",
    "duplicates": "Duplicate removal",
    "large_files": "Large-file deletion",
    "zero_length": "Zero-length file removal",
}

_lock = threading.Lock()
_operations = []      # oldest first
_counter = 0


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _never_raises(default=None):
    """Recording must never be able to break a cleanup that is under way.

    Every function a destructive path calls is wrapped in this: a bug here
    costs a log entry, not a half-finished deletion. The read side is not
    wrapped — an endpoint may fail loudly.
    """
    def decorate(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                return default() if callable(default) else default
        return inner
    return decorate


@_never_raises()
def start(operation, label=None):
    """Open a log entry for an operation that is about to run."""
    global _counter
    with _lock:
        _counter += 1
        entry = {
            "id": f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_counter:06d}",
            "operation": operation,
            "label": label or OPERATION_LABELS.get(operation, operation),
            "started_at": _now(),
            "completed_at": None,
            "status": "running",
            "restore_point": None,
            "sections": [],
            "totals": {"count": 0, "bytes": 0, "bytes_fmt": "0 B"},
            "message": "",
        }
        _operations.append(entry)
        while len(_operations) > MAX_OPERATIONS:
            _operations.pop(0)
    return entry


@_never_raises()
def set_restore_point(entry, restore_point):
    """Record the guard_batch restore-point outcome for this operation."""
    if not entry or not isinstance(restore_point, dict):
        return
    with _lock:
        entry["restore_point"] = {
            "created": bool(restore_point.get("created")),
            "message": restore_point.get("message", ""),
        }


@_never_raises()
def add_section(entry, label, count=0, bytes_freed=0, items=None, skipped=None,
                errors=None, permanent=False, note="", key=""):
    """Append one unit of work (a Deep Clean target, or a finder's batch)."""
    if not entry:
        return None
    items = list(items or [])
    truncated = max(0, len(items) - MAX_ITEMS_PER_SECTION)
    section = {
        "key": key,
        "label": label,
        "count": int(count or 0),
        "bytes": int(bytes_freed or 0),
        "bytes_fmt": format_bytes(int(bytes_freed or 0)),
        "permanent": bool(permanent),
        "note": note or "",
        "items": items[:MAX_ITEMS_PER_SECTION],
        "items_truncated": truncated,
        "skipped": list(skipped or []),
        "errors": list(errors or []),
    }
    with _lock:
        entry["sections"].append(section)
        entry["totals"]["count"] += section["count"]
        entry["totals"]["bytes"] += section["bytes"]
        entry["totals"]["bytes_fmt"] = format_bytes(entry["totals"]["bytes"])
    return section


@_never_raises(default=list)
def make_items(paths, sizes=None, action="recycled"):
    """Build per-item rows from the paths a deleter reported it removed.

    ``sizes`` maps path -> bytes measured BEFORE the delete; anything missing
    is recorded as 0 rather than guessed.
    """
    sizes = sizes or {}
    return [{"path": p, "bytes": int(sizes.get(p, 0) or 0), "action": action}
            for p in (paths or [])]


@_never_raises()
def finish(entry, status="completed", message=""):
    """Close the entry. ``status`` is completed, blocked or failed."""
    if not entry:
        return None
    with _lock:
        entry["status"] = status
        entry["message"] = message or entry.get("message", "")
        entry["completed_at"] = _now()
    return entry


@_never_raises()
def fail_running(operation, message=""):
    """Mark the newest still-running entry for ``operation`` as failed.

    For work that runs in a background thread: the caller that catches the
    exception is not the one holding the entry.
    """
    with _lock:
        for entry in reversed(_operations):
            if entry["operation"] == operation and entry["status"] == "running":
                entry["status"] = "failed"
                entry["message"] = message
                entry["completed_at"] = _now()
                return entry
    return None


def recent(limit=10, include_items=False):
    """Newest-first copies of the last operations.

    Item lists are omitted by default: the summary panel and the history
    list only need counts, and a polled endpoint should not ship thousands
    of paths every time.
    """
    with _lock:
        rows = list(reversed(_operations))[:max(1, int(limit or 10))]
        return [_copy(op, include_items) for op in rows]


def latest(include_items=True):
    with _lock:
        if not _operations:
            return None
        return _copy(_operations[-1], include_items)


def _copy(entry, include_items):
    """Deep-enough copy: callers (and jsonify) never touch the live entry."""
    out = dict(entry)
    out["totals"] = dict(entry["totals"])
    out["restore_point"] = dict(entry["restore_point"]) if entry.get("restore_point") else None
    sections = []
    for s in entry["sections"]:
        sec = dict(s)
        sec["skipped"] = [dict(x) for x in s["skipped"]]
        sec["errors"] = [dict(x) for x in s["errors"]]
        if include_items:
            sec["items"] = [dict(x) for x in s["items"]]
        else:
            sec.pop("items", None)
        sec["item_count"] = len(s["items"])
        sections.append(sec)
    out["sections"] = sections
    return out


# ─── Rendering ─────────────────────────────────────────────────
def _restore_point_line(entry):
    rp = entry.get("restore_point")
    if not rp:
        return "not requested"
    if rp.get("created"):
        return "created before the batch"
    return f"NOT created — {rp.get('message', '')}".rstrip(" —")


def to_text(entries):
    """Human-readable .txt rendering of one or more operations."""
    if isinstance(entries, dict):
        entries = [entries]
    lines = [
        "MTT Windows Infinite Optimizer — activity log",
        f"Generated: {_now()}",
        f"Operations: {len(entries)}",
    ]
    for entry in entries:
        totals = entry.get("totals", {})
        lines += [
            "",
            "=" * 72,
            f"{entry.get('label', '')}  [{entry.get('operation', '')}]",
            "=" * 72,
            f"Started:       {entry.get('started_at', '')}",
            f"Completed:     {entry.get('completed_at') or '—'}",
            f"Status:        {entry.get('status', '')}",
            f"Restore point: {_restore_point_line(entry)}",
            f"Totals:        {totals.get('count', 0)} item(s), "
            f"{totals.get('bytes_fmt', '0 B')} reclaimed",
        ]
        if entry.get("message"):
            lines.append(f"Note:          {entry['message']}")

        for s in entry.get("sections", []):
            lines += [
                "",
                f"-- {s.get('label', '')} — {s.get('count', 0)} item(s), "
                f"{s.get('bytes_fmt', '0 B')}"
                + (" (PERMANENT — not recycled)" if s.get("permanent") else ""),
            ]
            if s.get("note"):
                lines.append(f"   {s['note']}")
            for item in s.get("items", []):
                lines.append(f"   [{item.get('action', '')}] "
                             f"{format_bytes(item.get('bytes', 0)):>10}  "
                             f"{item.get('path', '')}")
            if s.get("items_truncated"):
                lines.append(f"   … and {s['items_truncated']} more item(s) "
                             f"not listed (totals above are complete)")
            if s.get("skipped"):
                lines.append(f"   Skipped ({len(s['skipped'])}):")
                for b in s["skipped"]:
                    lines.append(f"     {b.get('path', '')} — {b.get('reason', '')}")
            if s.get("errors"):
                lines.append(f"   Errors ({len(s['errors'])}):")
                for e in s["errors"]:
                    lines.append(f"     {e.get('path', '')} — {e.get('error', '')}")
    return "\n".join(lines) + "\n"


def filename(entries, extension):
    """Suggested download filename for an attachment."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if isinstance(entries, dict):
        return f"mtt-activity-log-{entries.get('operation', 'operation')}-{stamp}.{extension}"
    return f"mtt-activity-log-{stamp}.{extension}"
