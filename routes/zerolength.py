"""Zero-length File Finder endpoints — report, then user-selected removal.

Same two-phase shape as the duplicate finder: a scan that only reports, and
a separate delete that acts on exactly the paths the user ticked. Nothing is
ever pre-selected, and every removal goes through core.safety —
``guard_batch`` for the restore point and ``send_to_recycle_bin`` for the
delete itself. There is no raw ``os.remove`` on this path.

An empty file recovered from the Recycle Bin is byte-identical to the one
that was deleted, which makes the Recycle Bin route a complete undo here.
"""
import os
import threading

from flask import Blueprint, jsonify, request

from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.zerolength import (scan_zero_length, zerolength_results,
                                 exclusion_reason)
from scanners.largefiles import suggested_roots

bp = Blueprint("zerolength", __name__)


@bp.route("/api/zerolength/roots")
def api_zerolength_roots():
    return jsonify({
        "roots": suggested_roots(),
        "note": ("Only the folders you select are scanned. Windows, Program Files "
                 "and ProgramData are always excluded, and known placeholder files "
                 "(__init__.py, .gitkeep, *.lock and similar) are never reported."),
        "warning": ("A zero-byte file is not always junk — lock files, package "
                    "markers and sentinels are empty by design. Review each one "
                    "before deleting."),
    })


def _run_scan(roots):
    try:
        scan_zero_length(roots)
    except Exception as e:
        zerolength_results.update({"status": "error", "message": str(e)})
        log_activity(f"Zero-length Finder scan failed: {e}", "ERROR")


@bp.route("/api/zerolength/scan", methods=["POST"])
def api_zerolength_scan():
    """Phase 1 — report only."""
    data = request.get_json(silent=True) or {}
    roots = data.get("roots") or []
    if not roots:
        return jsonify({"status": "error",
                        "message": "Select at least one folder to scan."}), 400
    if zerolength_results.get("status") == "scanning":
        return jsonify({"status": "already_running"})
    zerolength_results.update({"status": "scanning", "files": []})
    threading.Thread(target=_run_scan, args=(roots,), daemon=True).start()
    return jsonify({"status": "scanning", "roots": roots})


@bp.route("/api/zerolength/report")
def api_zerolength_report():
    return jsonify(dict(zerolength_results))


@bp.route("/api/zerolength/delete", methods=["POST"])
def api_zerolength_delete():
    """Phase 2 — remove exactly the empty files the user picked."""
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": "Confirmation required — send confirm=true with the files you chose.",
        }), 400

    files = data.get("files") or []
    if not files:
        return jsonify({"status": "error", "message": "No files selected."}), 400

    reported = zerolength_results.get("files", [])
    if not reported:
        return jsonify({"status": "error",
                        "message": "No current zero-length report. Run a scan first."}), 400

    known = {os.path.normcase(f["path"]) for f in reported}
    unknown = [p for p in files if os.path.normcase(p) not in known]
    if unknown:
        log_activity(f"Zero-length Finder: {len(unknown)} path(s) outside the current "
                     f"report were ignored", "WARN")
    chosen = [p for p in files if os.path.normcase(p) in known]
    if not chosen:
        return jsonify({"status": "error",
                        "message": "None of the selected files are in the current report."}), 400

    blocked, allowed = [], []
    for p in chosen:
        # Re-apply the placeholder guard at delete time. The report already
        # withheld these, so reaching here means the file changed underneath
        # us or the path was hand-crafted; either way it is not deletable.
        reason = exclusion_reason(p, os.path.basename(p))
        if reason:
            blocked.append({"path": p, "reason": reason})
            continue
        try:
            if os.path.getsize(p) != 0:
                blocked.append({"path": p, "reason": "no longer empty — it has been written to"})
                continue
        except (OSError, PermissionError):
            blocked.append({"path": p, "reason": "unreadable"})
            continue
        ok, why = check_deletable(p)
        (allowed.append(p) if ok else blocked.append({"path": p, "reason": why}))

    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "Every selected file is protected by the safety rules."}), 400

    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before zero-length file removal")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=0)
    result["blocked"].extend(blocked)

    if result["recycled"]:
        log_undo("recycle", f"Removed {len(result['recycled'])} zero-length file(s)",
                 {"count": len(result["recycled"]), "bytes": 0,
                  "recoverable": not result["permanent"]})
        removed = {os.path.normcase(p) for p in result["recycled"]}
        surviving = [f for f in reported if os.path.normcase(f["path"]) not in removed]
        zerolength_results["files"] = surviving
        zerolength_results["shown"] = len(surviving)
        zerolength_results["found"] = max(0, zerolength_results.get("found", 0)
                                          - len(result["recycled"]))

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
