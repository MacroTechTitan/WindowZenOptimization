"""AI Storage Report endpoints — READ ONLY.

There is deliberately no delete, prune, or manage endpoint in this
blueprint. Model-cache management is Phase 2 / Pro
(docs/BACKLOG_PHASE2.md); this sprint reports only.
"""
import threading

from flask import Blueprint, jsonify

from core.util import log_activity
from scanners.ai_storage import scan_ai_storage, ai_storage_results

bp = Blueprint("ai_storage", __name__)


def _run_scan():
    try:
        scan_ai_storage()
    except Exception as e:
        ai_storage_results.update({"status": "error", "message": str(e)})
        log_activity(f"AI Storage Report failed: {e}", "ERROR")


@bp.route("/api/ai-storage/scan", methods=["POST"])
def api_ai_storage_scan():
    """Build the report. Read-only — nothing is modified or removed."""
    if ai_storage_results.get("status") == "scanning":
        return jsonify({"status": "already_running"})
    ai_storage_results.update({"status": "scanning", "tools": []})
    threading.Thread(target=_run_scan, daemon=True).start()
    return jsonify({"status": "scanning", "read_only": True})


@bp.route("/api/ai-storage/report")
def api_ai_storage_report():
    payload = dict(ai_storage_results)
    payload["read_only"] = True
    payload["management"] = ("Reporting only in this release. Pruning old revisions "
                             "and de-duplicating model blobs is planned for a future "
                             "version.")
    return jsonify(payload)
