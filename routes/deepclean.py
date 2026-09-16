"""Deep Clean endpoints — two-phase: report first, apply second.

/api/deepclean/scan never deletes. /api/deepclean/apply only touches the
target keys the client explicitly sends after seeing the report.
"""
import threading
from datetime import datetime

from flask import Blueprint, jsonify, request

from core import activity_log
from core.state import IS_WINDOWS
from core.util import log_activity, format_bytes
from core.safety import cloud_sync_roots, excluded_roots
from scanners.deepclean import DEEPCLEAN_TARGETS, scan_deepclean
from cleaners.deepclean import apply_deepclean, deepclean_state

bp = Blueprint("deepclean", __name__)

_report = {"status": "idle", "targets": [], "total_bytes": 0, "last_scan": None}
_scan_lock = threading.Lock()


@bp.route("/api/deepclean/targets")
def api_deepclean_targets():
    """Static target catalogue — name, risk label, and default on/off."""
    targets = [{
        "key": key,
        "label": t["label"],
        "description": t["description"],
        "risk": t["risk"],
        "default_on": t["default_on"],
        "report_only": t.get("report_only", False),
    } for key, t in DEEPCLEAN_TARGETS.items()]
    return jsonify({
        "targets": targets,
        "safety": {
            "recycle_bin": "Removals go to the Recycle Bin, not a permanent delete.",
            "restore_point": "A System Restore point is created before the batch.",
            "excluded_roots": excluded_roots(),
            "cloud_sync_roots": cloud_sync_roots(),
        },
    })


def _run_scan(keys, include_dism):
    try:
        result = scan_deepclean(keys, include_dism=include_dism)
        with _scan_lock:
            _report.update(result)
    except Exception as e:
        with _scan_lock:
            _report.update({"status": "error", "message": str(e)})
        log_activity(f"Deep Clean scan failed: {e}", "ERROR")


@bp.route("/api/deepclean/scan", methods=["POST"])
def api_deepclean_scan():
    """Phase 1 — report only. Changes nothing on disk."""
    data = request.get_json(silent=True) or {}
    keys = data.get("targets")
    include_dism = bool(data.get("include_dism", False))
    with _scan_lock:
        if _report.get("status") == "scanning":
            return jsonify({"status": "already_running"})
        _report.update({"status": "scanning", "targets": [], "total_bytes": 0})
    threading.Thread(target=_run_scan, args=(keys, include_dism), daemon=True).start()
    return jsonify({"status": "scanning", "include_dism": include_dism})


@bp.route("/api/deepclean/report")
def api_deepclean_report():
    with _scan_lock:
        payload = dict(_report)
    payload["total_fmt"] = format_bytes(payload.get("total_bytes", 0))
    payload["platform_supported"] = IS_WINDOWS
    return jsonify(payload)


def _run_apply(keys, without_rp, allow_permanent):
    try:
        apply_deepclean(keys, proceed_without_restore_point=without_rp,
                        allow_permanent=allow_permanent)
    except Exception as e:
        deepclean_state.update({"status": "complete", "message": f"Failed: {e}"})
        activity_log.fail_running("deep_clean", f"Deep Clean failed: {e}")
        log_activity(f"Deep Clean apply failed: {e}", "ERROR")


@bp.route("/api/deepclean/apply", methods=["POST"])
def api_deepclean_apply():
    """Phase 2 — the separate, explicit second user action.

    Requires {"confirm": true} plus the target keys chosen in the report.
    """
    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({
            "status": "error",
            "message": ("Confirmation required. Run the scan first, review the report, "
                        "then re-send with confirm=true and the targets to clean."),
        }), 400

    keys = data.get("targets") or []
    if not keys:
        return jsonify({"status": "error",
                        "message": "No targets selected."}), 400

    if deepclean_state.get("status") == "running":
        return jsonify({"status": "already_running"})

    threading.Thread(
        target=_run_apply,
        args=(keys, bool(data.get("proceed_without_restore_point", False)),
              bool(data.get("allow_permanent", False))),
        daemon=True).start()
    log_activity(f"Deep Clean apply started for {len(keys)} target(s)", "TASK")
    return jsonify({"status": "started", "targets": keys})


@bp.route("/api/deepclean/status")
def api_deepclean_status():
    payload = dict(deepclean_state)
    payload["bytes_freed_fmt"] = format_bytes(payload.get("bytes_freed", 0))
    return jsonify(payload)
