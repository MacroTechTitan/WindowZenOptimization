"""Security scan endpoint: POST starts a background scan, GET returns results."""
import threading

from flask import Blueprint, jsonify, request

from core.state import security_data
from scanners.security import run_security_scan

bp = Blueprint("security", __name__)


@bp.route("/api/security/scan", methods=["GET", "POST"])
def api_security_scan():
    if request.method == "POST":
        thread = threading.Thread(target=run_security_scan, daemon=True)
        thread.start()
        return jsonify({"status": "scanning"})
    return jsonify(security_data)
