"""Downloadable activity-log endpoints.

Read-only: these routes report what the destructive features already did.
Nothing here deletes, and nothing here can start an operation.
"""
import json

from flask import Blueprint, jsonify, request, Response

from core import activity_log

bp = Blueprint("activity_log", __name__)


@bp.route("/api/activity-log/recent")
def api_activity_log_recent():
    """The last N operations, newest first.

    Per-item paths are omitted unless ?items=1 — the summary panel and the
    history list only need counts, and this endpoint is polled.
    """
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    include_items = request.args.get("items") in ("1", "true", "yes")
    operations = activity_log.recent(limit=limit, include_items=include_items)
    return jsonify({
        "operations": operations,
        "count": len(operations),
    })


@bp.route("/api/activity-log/download")
def api_activity_log_download():
    """Download the most recent operation (or all of them) as a file.

    ?format=txt|json   txt is human-readable, json is the structured entry
    ?scope=latest|all  latest is the default
    """
    fmt = (request.args.get("format") or "txt").lower()
    if fmt not in ("txt", "json"):
        return jsonify({"status": "error",
                        "message": "format must be txt or json"}), 400

    scope = (request.args.get("scope") or "latest").lower()
    if scope == "all":
        entries = activity_log.recent(limit=activity_log.MAX_OPERATIONS,
                                      include_items=True)
    else:
        latest = activity_log.latest(include_items=True)
        entries = [latest] if latest else []

    if not entries:
        return jsonify({
            "status": "empty",
            "message": ("No destructive operation has run yet in this session, "
                        "so there is nothing to download."),
        }), 404

    if fmt == "json":
        payload = entries[0] if scope != "all" else entries
        body = json.dumps(payload, indent=2)
        mimetype = "application/json"
    else:
        body = activity_log.to_text(entries)
        mimetype = "text/plain"

    name = activity_log.filename(entries if scope == "all" else entries[0], fmt)
    return Response(body, mimetype=mimetype, headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "Cache-Control": "no-store",
    })
