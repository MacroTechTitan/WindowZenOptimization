"""Duplicate File Finder endpoints — file-level only.

Scan reports groups of byte-identical files. Removal is a separate action
where the USER picks which copies go; the server refuses any request that
would leave a group with no surviving copy.
"""
import os
import threading

from flask import Blueprint, jsonify, request

from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.duplicates import scan_duplicates, duplicates_results
from scanners.largefiles import suggested_roots

bp = Blueprint("duplicates", __name__)


@bp.route("/api/duplicates/roots")
def api_duplicates_roots():
    return jsonify({
        "roots": suggested_roots(),
        "note": ("Only the folders you select are scanned. Windows and Program Files "
                 "are always excluded. Folder-level duplicate detection is not part "
                 "of this release."),
        "scope": "file-level only",
    })


def _run_scan(roots):
    try:
        scan_duplicates(roots)
    except Exception as e:
        duplicates_results.update({"status": "error", "message": str(e)})
        log_activity(f"Duplicate Finder scan failed: {e}", "ERROR")


@bp.route("/api/duplicates/scan", methods=["POST"])
def api_duplicates_scan():
    """Phase 1 — report only."""
    data = request.get_json(silent=True) or {}
    roots = data.get("roots") or []
    if not roots:
        return jsonify({"status": "error",
                        "message": "Select at least one folder to scan."}), 400
    if duplicates_results.get("status") == "scanning":
        return jsonify({"status": "already_running"})
    duplicates_results.update({"status": "scanning", "groups": []})
    threading.Thread(target=_run_scan, args=(roots,), daemon=True).start()
    return jsonify({"status": "scanning", "roots": roots})


@bp.route("/api/duplicates/report")
def api_duplicates_report():
    return jsonify(dict(duplicates_results))


@bp.route("/api/duplicates/delete", methods=["POST"])
def api_duplicates_delete():
    """Phase 2 — remove the copies the user explicitly picked.

    Refuses to delete every copy in any group: at least one must survive.
    """
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": "Confirmation required — send confirm=true with the copies you chose.",
        }), 400

    files = data.get("files") or []
    if not files:
        return jsonify({"status": "error", "message": "No copies selected."}), 400

    groups = duplicates_results.get("groups", [])
    if not groups:
        return jsonify({"status": "error",
                        "message": "No current duplicate report. Run a scan first."}), 400

    selected = {os.path.normcase(p) for p in files}

    # Guard: never let a group lose all of its copies.
    would_wipe = []
    known = set()
    for g in groups:
        paths = {os.path.normcase(c["path"]) for c in g["copies"]}
        known |= paths
        chosen_here = paths & selected
        if chosen_here and len(chosen_here) == len(paths):
            would_wipe.append({
                "hash": g["hash"],
                "name": g["copies"][0]["name"],
                "count": len(paths),
            })
    if would_wipe:
        names = ", ".join(w["name"] for w in would_wipe[:5])
        return jsonify({
            "status": "error",
            "message": (f"Refused — that selection would delete every copy in "
                        f"{len(would_wipe)} group(s) ({names}). Leave at least one "
                        f"copy of each file."),
            "groups_at_risk": would_wipe,
        }), 400

    unknown = [p for p in files if os.path.normcase(p) not in known]
    if unknown:
        log_activity(f"Duplicate Finder: {len(unknown)} path(s) outside the current "
                     f"report were ignored", "WARN")
    chosen = [p for p in files if os.path.normcase(p) in known]
    if not chosen:
        return jsonify({"status": "error",
                        "message": "None of the selected copies are in the current report."}), 400

    blocked, allowed = [], []
    for p in chosen:
        ok, reason = check_deletable(p)
        (allowed.append(p) if ok else blocked.append({"path": p, "reason": reason}))
    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "Every selected copy is protected by the safety rules."}), 400

    total = 0
    for p in allowed:
        try:
            total += os.path.getsize(p)
        except (OSError, PermissionError):
            pass

    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before duplicate removal")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=total)
    result["blocked"].extend(blocked)

    if result["recycled"]:
        log_undo("recycle", f"Removed {len(result['recycled'])} duplicate copy(ies)",
                 {"count": len(result["recycled"]), "bytes": result["bytes"],
                  "recoverable": not result["permanent"]})
        removed = {os.path.normcase(p) for p in result["recycled"]}
        surviving = []
        for g in groups:
            g["copies"] = [c for c in g["copies"]
                           if os.path.normcase(c["path"]) not in removed]
            g["count"] = len(g["copies"])
            g["wasted"] = g["size"] * max(0, g["count"] - 1)
            g["wasted_fmt"] = format_bytes(g["wasted"])
            if g["count"] > 1:
                surviving.append(g)
        duplicates_results["groups"] = surviving
        duplicates_results["group_count"] = len(surviving)
        duplicates_results["reclaimable_bytes"] = sum(g["wasted"] for g in surviving)
        duplicates_results["reclaimable_fmt"] = format_bytes(
            duplicates_results["reclaimable_bytes"])

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
