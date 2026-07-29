"""Registry health endpoints: current state, background scan, and fix."""
import threading

from flask import Blueprint, jsonify

from core.state import registry_data
from scanners.registry import scan_registry, fix_registry

bp = Blueprint("registry", __name__)


@bp.route("/api/registry")
def api_registry():
    return jsonify(registry_data)


@bp.route("/api/registry/scan", methods=["POST"])
def api_registry_scan():
    thread = threading.Thread(target=scan_registry, daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@bp.route("/api/registry/fix", methods=["POST"])
def api_registry_fix():
    fixed_count = fix_registry()
    return jsonify({"status": "fixed", "fixed_count": fixed_count, "remaining_issues": registry_data["issues_found"]})
