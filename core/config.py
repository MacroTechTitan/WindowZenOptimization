"""Settings and analytics persistence."""
import os
import json
import threading

SETTINGS_FILE = "settings.json"
ANALYTICS_FILE = "analytics.json"
_analytics_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "auto_clean_enabled": True,
    "auto_clean_time": "17:00",
    "clean_temp_files": True,
    "clean_user_temp": True,
    "clean_browser_cache": True,
    "clean_recycle_bin": False,
    "clean_thumbnails": True,
    "clean_downloaded_program_files": True,
    "clean_directx_shader_cache": True,
    "clean_error_reports": True,
    "clean_delivery_optimization": True,
    "clean_defender_temp": True,
    "clean_windows_update": False,
    "clean_windows_old": False,
    "clean_old_logs": True,
    "activity_tracking": True,
    "break_reminder_minutes": 40,
    "dark_mode": True,
}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                merged = {**DEFAULT_SETTINGS, **saved}
                return merged
        except (json.JSONDecodeError, IOError):
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings():
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
    except IOError:
        pass


settings = load_settings()


# ─── Analytics helpers ─────────────────────────────────────────
def load_analytics():
    if os.path.exists(ANALYTICS_FILE):
        try:
            with open(ANALYTICS_FILE, "r") as f:
                data = json.load(f)
                data.setdefault("visits", 0)
                data.setdefault("downloads", 0)
                return data
        except Exception:
            pass
    return {"visits": 0, "downloads": 0}


def save_analytics(data):
    try:
        with open(ANALYTICS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def increment_analytics(key):
    with _analytics_lock:
        data = load_analytics()
        data[key] = data.get(key, 0) + 1
        save_analytics(data)
        return data
