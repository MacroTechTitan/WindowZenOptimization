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

from routes.registration import bp as registration_bp
app.register_blueprint(registration_bp)

from routes.admin import bp as admin_bp
app.register_blueprint(admin_bp)


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
