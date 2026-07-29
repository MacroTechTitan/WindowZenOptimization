import os
import sys
import time
import json
import glob
import uuid
import socket
import hashlib
import threading
import platform
import shutil
import tempfile
import psutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.state import (
    activity_log, LOG_MAX, IS_WINDOWS, _WIN_NO_WINDOW, SITE_URL, scheduler,
    scan_results, cleaning_status, activity_data, registry_data,
    file_organizer_results, security_data, deep_analysis_data,
    undo_log, UNDO_LOG_MAX, large_files_results, organize_preview_results,
    NETWORK_FIX_STEPS, _net_fix_lock, network_fix_state,
)
from core.util import log_activity, log_undo, format_bytes, get_dir_size, get_windows_username, get_local_version
from core.config import (
    settings, save_settings, load_analytics, save_analytics, increment_analytics,
)
from core.registrations import load_registrations, save_registrations, _reg_lock
from core.email import send_verification_email, add_to_sendgrid_list
from scanners.system import get_system_metrics, update_wellness
from scanners.registry import scan_registry, fix_registry
from scanners.security import run_security_scan
from scanners.deep import run_deep_analysis
from scanners.files import run_file_organizer_scan
from scanners.apps import (
    _scan_apps_from_registry, _build_uninstall_invocation, _registry_has_display_name,
)
from cleaners.targets import get_active_targets
from cleaners.runner import run_system_scan, run_system_clean, setup_scheduler

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "mtt-optimizer-secret-2026-macro-tech-titan")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "mttadmin2026")


log_activity("MTT Windows Infinite Optimizer initialized", "SUCCESS")
log_activity(f"Platform: {platform.system()} {platform.release()}")
log_activity(f"Python: {platform.python_version()}")
if IS_WINDOWS:
    log_activity("Windows detected — full cleanup capabilities active", "SUCCESS")
else:
    log_activity("Non-Windows platform — running in preview/demo mode", "INFO")
log_activity("All modules loaded successfully", "SUCCESS")
log_activity("Scheduler service started", "SUCCESS")
log_activity("Activity monitor active", "INFO")
log_activity("Ready for operations", "SUCCESS")


# ─── Blueprint registration ───────────────────────────────────
from routes.pages import bp as pages_bp
app.register_blueprint(pages_bp)

from routes.metrics import bp as metrics_bp
app.register_blueprint(metrics_bp)

from routes.apps import bp as apps_bp
app.register_blueprint(apps_bp)

from routes.clean import bp as clean_bp
app.register_blueprint(clean_bp)

from routes.registry import bp as registry_bp
app.register_blueprint(registry_bp)

from routes.security import bp as security_bp
app.register_blueprint(security_bp)

from routes.deep import bp as deep_bp
app.register_blueprint(deep_bp)

from routes.files import bp as files_bp
app.register_blueprint(files_bp)


# ─── Email Registration Gateway ───────────────────────────────
@app.route("/api/register-download", methods=["POST"])
def register_download():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return jsonify({"error": "Please enter a valid email address."}), 400
    with _reg_lock:
        registrations = load_registrations()
        existing = registrations.get(email)
        if existing and existing.get("verified"):
            send_verification_email(email, existing["token"])
            return jsonify({"ok": True, "resent": True, "message": "Already verified! Resent your download link."})
        if existing and not existing.get("verified"):
            token = existing["token"]
            registrations[email]["registered_at"] = datetime.utcnow().isoformat()
            save_registrations(registrations)
        else:
            token = str(uuid.uuid4())
            registrations[email] = {
                "token": token,
                "verified": False,
                "registered_at": datetime.utcnow().isoformat(),
                "verified_at": None,
                "ip": request.remote_addr or "unknown",
            }
            save_registrations(registrations)
    ok = send_verification_email(email, token)
    if not ok:
        return jsonify({"error": "Failed to send email. Please try again later."}), 500
    add_to_sendgrid_list(email)
    return jsonify({"ok": True, "message": "Verification email sent! Check your inbox."})


TOKEN_EXPIRY_DAYS = 7

@app.route("/verify-email/<token>")
def verify_email(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token:
            if not info.get("verified"):
                try:
                    registered_at = datetime.fromisoformat(info.get("registered_at", ""))
                    if datetime.utcnow() - registered_at > timedelta(days=TOKEN_EXPIRY_DAYS):
                        return render_template("download.html", error="This link has expired (links are valid for 7 days). Please request a new one.", token=None, email=None)
                except Exception:
                    pass
                with _reg_lock:
                    registrations[email]["verified"] = True
                    registrations[email]["verified_at"] = datetime.utcnow().isoformat()
                    save_registrations(registrations)
                increment_analytics("downloads")
                log_activity(f"Email verified: {email} — download unlocked", "SUCCESS")
            return redirect(f"/download/{token}")
    return render_template("download.html", error="This link is invalid or has expired. Please request a new one.", token=None, email=None)


@app.route("/download/<token>")
def download_page(token):
    registrations = load_registrations()
    for email, info in registrations.items():
        if info.get("token") == token and info.get("verified"):
            return render_template("download.html", error=None, token=token, email=email)
    return redirect("/")


@app.route("/admin/api/registrations")
def admin_registrations():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    registrations = load_registrations()
    items = []
    for email, info in registrations.items():
        items.append({
            "email": email,
            "verified": info.get("verified", False),
            "registered_at": info.get("registered_at", ""),
            "verified_at": info.get("verified_at", ""),
            "ip": info.get("ip", ""),
        })
    items.sort(key=lambda x: x["registered_at"], reverse=True)
    return jsonify({
        "ok": True,
        "total": len(items),
        "verified": sum(1 for i in items if i["verified"]),
        "registrations": items,
    })


# ─── Admin Panel ──────────────────────────────────────────────
def _admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin")
def admin_index():
    return render_template("admin.html", site_url=SITE_URL)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json() or {}
    if data.get("password") == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return render_template("admin.html", site_url=SITE_URL)


@app.route("/admin/api/save-version", methods=["POST"])
def admin_save_version():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    data = request.get_json() or {}
    try:
        existing = get_local_version()
        existing.update({
            "version": data.get("version", existing.get("version", "1.0.0")),
            "build": int(data.get("build", existing.get("build", 100))),
            "release_date": data.get("release_date", existing.get("release_date", "")),
            "channel": data.get("channel", existing.get("channel", "stable")),
            "download_url": data.get("download_url", existing.get("download_url", "")),
            "changelog": data.get("changelog", existing.get("changelog", [])),
        })
        with open(LOCAL_VERSION_FILE, "w") as f:
            json.dump(existing, f, indent=2)
        log_activity(f"version.json updated to v{existing['version']} build {existing['build']}", "SUCCESS")
        return jsonify({"ok": True, "version": existing})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "static", "downloads")
_MAX_UPLOAD_MB = 500


@app.route("/admin/api/download-files")
def admin_list_download_files():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    files = []
    for fname in sorted(os.listdir(DOWNLOADS_DIR)):
        fpath = os.path.join(DOWNLOADS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        size = os.path.getsize(fpath)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        if size >= 1024 ** 3:
            size_fmt = f"{size/1024**3:.1f} GB"
        elif size >= 1024 ** 2:
            size_fmt = f"{size/1024**2:.1f} MB"
        else:
            size_fmt = f"{size/1024:.1f} KB"
        files.append({"name": fname, "size": size_fmt, "modified": mtime})
    return jsonify({"files": files})


@app.route("/admin/api/upload-installer", methods=["POST"])
def admin_upload_installer():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".exe", ".zip"):
        return jsonify({"ok": False, "error": "Only .exe and .zip files are allowed"}), 400

    # Optional metadata from form fields
    new_version  = request.form.get("version", "").strip()
    new_build    = request.form.get("build", "").strip()
    new_channel  = request.form.get("channel", "stable").strip()
    new_changelog_raw = request.form.get("changelog", "").strip()
    new_changelog = [l.strip() for l in new_changelog_raw.splitlines() if l.strip()]

    safe_name = os.path.basename(f.filename)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    dest = os.path.join(DOWNLOADS_DIR, safe_name)
    f.save(dest)
    size = os.path.getsize(dest)
    if size > _MAX_UPLOAD_MB * 1024 * 1024:
        os.remove(dest)
        return jsonify({"ok": False, "error": f"File exceeds {_MAX_UPLOAD_MB} MB limit"}), 413
    size_fmt = f"{size/1024**2:.1f} MB"

    # Always create/overwrite latest.zip wrapping the uploaded file
    import zipfile as _zipfile
    latest_zip_path = os.path.join(DOWNLOADS_DIR, "latest.zip")
    try:
        with _zipfile.ZipFile(latest_zip_path, "w", _zipfile.ZIP_DEFLATED) as zf:
            zf.write(dest, arcname=safe_name)
        zip_size = os.path.getsize(latest_zip_path)
        zip_size_fmt = f"{zip_size/1024**2:.1f} MB"
    except Exception as ze:
        return jsonify({"ok": False, "error": f"Saved installer but failed to create latest.zip: {ze}"})

    # Auto-update version.json if metadata was provided
    version_updated = False
    download_url = f"{SITE_URL}/static/downloads/latest.zip"
    if new_version or new_build:
        try:
            existing = get_local_version()
            if new_version:
                existing["version"] = new_version
            if new_build:
                try:
                    existing["build"] = int(new_build)
                except ValueError:
                    pass
            existing["channel"] = new_channel or existing.get("channel", "stable")
            existing["download_url"] = download_url
            existing["release_date"] = datetime.now().strftime("%Y-%m-%d")
            if new_changelog:
                existing["changelog"] = new_changelog
            with open(LOCAL_VERSION_FILE, "w") as vf:
                json.dump(existing, vf, indent=2)
            version_updated = True
        except Exception as ve:
            log_activity(f"version.json update failed: {ve}", "WARN")

    log_activity(f"Admin released v{new_version or '?'} build {new_build or '?'}: {safe_name} ({size_fmt}) → latest.zip ({zip_size_fmt})", "SUCCESS")
    return jsonify({
        "ok": True,
        "filename": safe_name,
        "size": size_fmt,
        "latest_zip": "latest.zip",
        "zip_size": zip_size_fmt,
        "download_url": download_url,
        "version_updated": version_updated,
    })


@app.route("/admin/api/download-files/delete", methods=["POST"])
def admin_delete_download_file():
    if not _admin_required():
        return jsonify({"ok": False, "error": "Not authenticated"}), 401
    data = request.get_json() or {}
    filename = os.path.basename(data.get("filename", ""))
    if not filename:
        return jsonify({"ok": False, "error": "No filename provided"}), 400
    fpath = os.path.join(DOWNLOADS_DIR, filename)
    if not os.path.isfile(fpath):
        return jsonify({"ok": False, "error": "File not found"}), 404
    os.remove(fpath)
    log_activity(f"Admin deleted installer: {filename}", "WARN")
    return jsonify({"ok": True})


@app.route("/admin/api/check-remote-manifest")
def admin_check_remote_manifest():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    local = get_local_version()
    remote_url = local.get("update_server", "https://windowzen.macrotechtitan.com/updates/version.json")
    try:
        with urllib.request.urlopen(remote_url, timeout=8) as resp:
            remote = json.loads(resp.read().decode())
        return jsonify(remote)
    except Exception as e:
        return jsonify({"error": f"Could not reach {remote_url}: {e}"})


@app.route("/admin/api/reset-counters", methods=["POST"])
def admin_reset_counters():
    if not _admin_required():
        return jsonify({"error": "Not authenticated"}), 401
    key = request.json.get("key", "all") if request.json else "all"
    with _analytics_lock:
        data = load_analytics()
        if key == "all":
            data = {"visits": 0, "downloads": 0}
        elif key in data:
            data[key] = 0
        save_analytics(data)
    return jsonify({"ok": True, "counters": data})


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
