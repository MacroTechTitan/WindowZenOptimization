"""Custom scan-root validation, shared by every finder.

The Large File, Duplicate and Zero-length finders all let the user type an
arbitrary folder instead of picking from the suggested list (the OneDrive /
FL Studio mirror case, and testing). This module is the one gate those
custom paths go through before they become scan roots.

It only ever validates — it never scans, and it never deletes. A folder that
passes here is an ordinary root from then on, so the scanners' own
per-directory exclusion walk still applies on top.
"""
import os

from flask import Blueprint, jsonify, request

from core.util import log_activity
from core.safety import is_excluded_path, is_cloud_sync_path

bp = Blueprint("scanroots", __name__)


def _sysdrive():
    return os.environ.get("SystemDrive", "C:")


def system_roots():
    """Roots a scan may never be pointed at, whatever the user types.

    Deliberately NOT ``core.safety.excluded_roots`` — that one carves out
    ``documented_exceptions`` (C:\\Windows\\Temp and friends) because Deep
    Clean legitimately cleans them. A finder must not be aimed there at all,
    so this list has no exceptions.
    """
    roots = [
        os.environ.get("SystemRoot", os.path.join(_sysdrive(), "\\Windows")),
        os.environ.get("ProgramFiles", os.path.join(_sysdrive(), "\\Program Files")),
        os.environ.get("ProgramFiles(x86)", os.path.join(_sysdrive(), "\\Program Files (x86)")),
        os.environ.get("ProgramData", os.path.join(_sysdrive(), "\\ProgramData")),
    ]
    return [os.path.normcase(os.path.abspath(r)) for r in roots if r]


def validate_root(raw):
    """(ok, payload) for one candidate scan root."""
    path = (raw or "").strip().strip('"')
    if not path:
        return False, {"message": "Enter a folder path."}

    path = os.path.expandvars(os.path.expanduser(path))
    try:
        path = os.path.abspath(path)
    except (OSError, ValueError):
        return False, {"message": "That path could not be resolved."}

    if not os.path.exists(path):
        return False, {"message": f"{path} does not exist."}
    if not os.path.isdir(path):
        return False, {"message": f"{path} is a file, not a folder."}

    drive, tail = os.path.splitdrive(path)
    if tail in ("", os.sep, "/"):
        return False, {"message": ("Whole-drive scans are not offered — pick a "
                                   "folder inside the drive instead.")}

    norm = os.path.normcase(path)
    for root in system_roots():
        if norm == root or norm.startswith(root + os.sep):
            return False, {"message": (f"Refused — {path} is inside a protected system "
                                       f"location ({root}). Windows, Program Files and "
                                       f"ProgramData are never scanned.")}

    excluded, reason = is_excluded_path(path)
    if excluded:
        return False, {"message": f"Refused — {reason}."}

    synced, _root = is_cloud_sync_path(path)
    return True, {
        "path": path,
        "label": os.path.basename(path.rstrip(os.sep)) or path,
        "cloud_synced": synced,
        "note": ("Cloud-synced folder — it can be scanned, but deleting a synced "
                 "file would propagate to the cloud, so removals stay blocked."
                 if synced else ""),
    }


@bp.route("/api/scan-roots/validate", methods=["POST"])
def api_scan_roots_validate():
    """Validate one user-typed folder. Reports only; scans nothing."""
    data = request.get_json(silent=True) or {}
    ok, payload = validate_root(data.get("path"))
    if not ok:
        log_activity(f"Custom scan folder refused: {data.get('path')!r} — "
                     f"{payload['message']}", "WARN")
        return jsonify({"ok": False, **payload}), 400
    log_activity(f"Custom scan folder accepted: {payload['path']}", "INFO")
    return jsonify({"ok": True, **payload})
