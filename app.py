"""Entrypoint: build the Flask app, register the route blueprints, and run.

All routes live in routes/. Shared state and helpers live in core/, the
scanners in scanners/, and the cleaner in cleaners/.
"""
import os
import platform

from flask import Flask

from core.state import IS_WINDOWS, scheduler
from core.util import log_activity
from cleaners.runner import setup_scheduler

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

from routes.deepclean import bp as deepclean_bp
app.register_blueprint(deepclean_bp)

from routes.largefiles import bp as largefiles_bp
app.register_blueprint(largefiles_bp)

from routes.duplicates import bp as duplicates_bp
app.register_blueprint(duplicates_bp)

from routes.ai_storage import bp as ai_storage_bp
app.register_blueprint(ai_storage_bp)


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
