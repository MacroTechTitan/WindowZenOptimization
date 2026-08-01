"""Large File Finder endpoints.

Scan is report-only. Deletion is a separate action, per-file, user-selected,
to the Recycle Bin, behind a restore point.
"""
import os
import threading

from flask import Blueprint, jsonify, request

from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.largefiles import (
    DEFAULT_THRESHOLD_MB, CATEGORIES, suggested_roots,
    scan_large_files, largefiles_results,
)

bp = Blueprint("largefiles", __name__)


@bp.route("/api/largefiles/roots")
def api_largefiles_roots():
    """Suggested scan roots. The user chooses; nothing is scanned implicitly."""
    return jsonify({
        "roots": suggested_roots(),
        "default_threshold_mb": DEFAULT_THRESHOLD_MB,
        "categories": sorted(list(CATEGORIES.keys()) + ["other"]),
        "note": ("Only the roots you select are scanned. Whole-drive scanning is "
                 "not offered; Windows and Program Files are always excluded."),
    })


def _run_scan(roots, threshold_mb):
    try:
        scan_large_files(roots, threshold_mb)
    except Exception as e:
        largefiles_results.update({"status": "error", "message": str(e)})
        log_activity(f"Large File Finder scan failed: {e}", "ERROR")


@bp.route("/api/largefiles/scan", methods=["POST"])
def api_largefiles_scan():
    """Phase 1 — report only."""
    data = request.get_json(silent=True) or {}
    roots = data.get("roots") or []
    if not roots:
        return jsonify({
            "status": "error",
            "message": "Select at least one folder to scan. Whole-drive scans are not offered.",
        }), 400
    try:
        threshold_mb = int(data.get("threshold_mb", DEFAULT_THRESHOLD_MB))
    except (TypeError, ValueError):
        threshold_mb = DEFAULT_THRESHOLD_MB

    if largefiles_results.get("status") == "scanning":
        return jsonify({"status": "already_running"})
    largefiles_results.update({"status": "scanning", "files": []})
    threading.Thread(target=_run_scan, args=(roots, threshold_mb), daemon=True).start()
    return jsonify({"status": "scanning", "roots": roots, "threshold_mb": threshold_mb})


@bp.route("/api/largefiles/report")
def api_largefiles_report():
    return jsonify(dict(largefiles_results))


@bp.route("/api/largefiles/delete", methods=["POST"])
def api_largefiles_delete():
    """Phase 2 — explicit, per-file, user-selected removal to the Recycle Bin."""
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": "Confirmation required — send confirm=true with the files you selected.",
        }), 400

    files = data.get("files") or []
    if not files:
        return jsonify({"status": "error", "message": "No files selected."}), 400

    # Only ever act on files this scan actually reported.
    reported = {os.path.normcase(f["path"]) for f in largefiles_results.get("files", [])}
    chosen, unknown = [], []
    for p in files:
        if os.path.normcase(p) in reported:
            chosen.append(p)
        else:
            unknown.append(p)
    if unknown:
        log_activity(f"Large File Finder: {len(unknown)} path(s) not in the current "
                     f"report were ignored", "WARN")
    if not chosen:
        return jsonify({"status": "error",
                        "message": "None of the selected files are in the current report. "
                                   "Re-scan and try again."}), 400

    blocked = []
    allowed = []
    for p in chosen:
        ok, reason = check_deletable(p)
        (allowed if ok else blocked).append(p if ok else {"path": p, "reason": reason})

    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "Every selected file is protected by the safety rules."}), 400

    total = 0
    for p in allowed:
        try:
            total += os.path.getsize(p)
        except (OSError, PermissionError):
            pass

    # Restore point before the batch.
    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before large-file deletion")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=total)
    result["blocked"].extend(blocked)

    if result["recycled"]:
        log_undo("recycle", f"Large File Finder removed {len(result['recycled'])} file(s)",
                 {"count": len(result["recycled"]), "bytes": result["bytes"],
                  "recoverable": not result["permanent"]})
        removed = {os.path.normcase(p) for p in result["recycled"]}
        largefiles_results["files"] = [
            f for f in largefiles_results.get("files", [])
            if os.path.normcase(f["path"]) not in removed]
        largefiles_results["total_bytes"] = sum(
            f["size"] for f in largefiles_results["files"])
        largefiles_results["total_fmt"] = format_bytes(largefiles_results["total_bytes"])

    return jsonify({
        "status": "ok",
        "deleted": len(result["recycled"]),
        "bytes": result["bytes"],
        "bytes_fmt": format_bytes(result["bytes"]),
        "permanent": result["permanent"],
        "blocked": result["blocked"],
        "errors": result["errors"],
        "message": result["message"],
        "restore_point": payload["restore_point"],
    })
