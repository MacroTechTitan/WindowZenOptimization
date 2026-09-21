"""First-party MTT product banner: promo list and open-in-system-browser.

Promos are read from static/branding/promos.json so they can be edited
without code changes. No third-party ad networks, no tracking.
"""
import json
import os
import webbrowser

from flask import Blueprint, jsonify, request, current_app

from core.util import log_activity

bp = Blueprint("promos", __name__)

# The existing brand-strip link, always allowed alongside the promo URLs.
BRAND_URL = "https://macrotechtitan.com"


def _load_promos():
    path = os.path.join(current_app.static_folder, "branding", "promos.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        log_activity(f"Could not read promos.json: {e}", "WARN")
        return []
    promos = []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        text, url = str(p.get("text", "")).strip(), str(p.get("url", "")).strip()
        if text and url.startswith(("https://", "http://")):
            promos.append({"text": text, "url": url})
    return promos


@bp.route("/api/promos")
def api_promos():
    return jsonify({"promos": _load_promos()})


@bp.route("/api/promos/open", methods=["POST"])
def api_promos_open():
    """Open a banner link in the system browser, not the app webview.
    Only URLs from promos.json (or the brand link) are accepted."""
    url = str((request.get_json(silent=True) or {}).get("url", ""))
    allowed = {p["url"] for p in _load_promos()} | {BRAND_URL}
    if url not in allowed:
        return jsonify({"status": "error", "message": "URL is not a known promo link"}), 400
    try:
        opened = webbrowser.open(url, new=2)
    except webbrowser.Error as e:
        opened = False
        log_activity(f"Could not open promo link {url}: {e}", "WARN")
    if not opened:
        return jsonify({"status": "error", "message": "No system browser available"}), 500
    return jsonify({"status": "ok"})
