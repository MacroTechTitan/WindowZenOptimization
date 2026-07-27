"""Static pages and the SPA dashboard shell."""
from flask import Blueprint, render_template, jsonify, request, session, redirect

from core.config import increment_analytics
from core.util import get_local_version

bp = Blueprint("pages", __name__)


@bp.route("/")
def landing():
    if session.get('desktop_mode'):
        return redirect('/app')
    increment_analytics("visits")
    return render_template("landing.html")


@bp.route("/eula")
def eula_page():
    return render_template("eula.html")


@bp.route("/loading")
def loading_page():
    """Desktop splash screen — served by Flask so there is only one navigation."""
    session['desktop_mode'] = True
    return render_template("splash_loading.html")


@bp.route("/updates/version.json")
def serve_version_json():
    """Self-hosted update manifest — mirrors what's in version.json"""
    data = get_local_version()
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@bp.route("/app")
@bp.route("/app/<page>")
def dashboard(page=None):
    desktop_mode = request.args.get("mode") == "desktop" or bool(session.get('desktop_mode'))
    if desktop_mode:
        session['desktop_mode'] = True
    return render_template("dashboard.html", initial_page=page or "dashboard", desktop_mode=desktop_mode)
