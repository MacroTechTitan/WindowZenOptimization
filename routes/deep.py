"""Deep system analysis endpoint: POST starts the run, GET returns state."""
import threading

from flask import Blueprint, jsonify, request

from core.state import deep_analysis_data
from scanners.deep import run_deep_analysis

bp = Blueprint("deep", __name__)


@bp.route("/api/system/deep-analysis", methods=["GET", "POST"])
def api_deep_analysis():
    if request.method == "POST":
        if deep_analysis_data["status"] == "running":
            return jsonify({"status": "already_running"})
        thread = threading.Thread(target=run_deep_analysis, daemon=True)
        thread.start()
        return jsonify({"status": "started"})
    return jsonify(deep_analysis_data)
