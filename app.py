import os
import time
import json
import threading
import platform
import shutil
import psutil
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = Flask(__name__)
app.secret_key = os.urandom(24)

SETTINGS_FILE = "settings.json"
activity_log = []
LOG_MAX = 200
scheduler = BackgroundScheduler()

DEFAULT_SETTINGS = {
    "auto_clean_enabled": True,
    "auto_clean_time": "17:00",
    "clean_chrome_cache": True,
    "clean_temp_files": True,
    "clean_recycle_bin": False,
    "clean_logs": True,
    "activity_tracking": True,
    "break_reminder_minutes": 60,
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
scan_results = {
    "last_scan": None,
    "junk_files_count": 0,
    "junk_files_size": 0,
    "temp_files_count": 0,
    "temp_files_size": 0,
    "chrome_cache_size": 0,
    "registry_issues": 0,
    "total_cleanable": 0,
}
activity_data = {
    "session_start": datetime.now().isoformat(),
    "active_minutes": 0,
    "idle_minutes": 0,
    "break_count": 0,
    "last_activity": datetime.now().isoformat(),
    "daily_active_hours": [],
    "wellness_score": 85,
    "apps_tracked": {},
}
cleaning_status = {
    "is_running": False,
    "current_task": "",
    "progress": 0,
    "items_cleaned": 0,
    "space_freed": 0,
}


def log_activity(message, level="INFO"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": message, "level": level}
    activity_log.append(entry)
    if len(activity_log) > LOG_MAX:
        activity_log.pop(0)


def format_bytes(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def get_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time

    try:
        temps = psutil.sensors_temperatures()
        cpu_temp = None
        if temps:
            for name, entries in temps.items():
                if entries:
                    cpu_temp = entries[0].current
                    break
    except (AttributeError, Exception):
        cpu_temp = None

    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            if info["cpu_percent"] and info["cpu_percent"] > 0.1:
                processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    processes.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)

    return {
        "cpu": {
            "percent": cpu_percent,
            "cores": psutil.cpu_count(logical=False) or 1,
            "threads": psutil.cpu_count(logical=True) or 1,
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            "temp": cpu_temp,
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
            "total_fmt": format_bytes(memory.total),
            "used_fmt": format_bytes(memory.used),
            "available_fmt": format_bytes(memory.available),
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "total_fmt": format_bytes(disk.total),
            "used_fmt": format_bytes(disk.used),
            "free_fmt": format_bytes(disk.free),
        },
        "network": {
            "bytes_sent": format_bytes(net.bytes_sent),
            "bytes_recv": format_bytes(net.bytes_recv),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "system": {
            "platform": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or "N/A",
            "uptime": str(uptime).split(".")[0],
            "boot_time": boot_time.strftime("%Y-%m-%d %H:%M"),
        },
        "top_processes": processes[:10],
    }


def simulate_scan():
    import random

    log_activity("Starting system scan...", "TASK")
    time.sleep(0.5)

    scan_results["temp_files_count"] = random.randint(120, 800)
    scan_results["temp_files_size"] = random.randint(50_000_000, 500_000_000)
    log_activity(f"Found {scan_results['temp_files_count']} temporary files ({format_bytes(scan_results['temp_files_size'])})")

    scan_results["chrome_cache_size"] = random.randint(100_000_000, 2_000_000_000)
    log_activity(f"Chrome cache: {format_bytes(scan_results['chrome_cache_size'])}")

    scan_results["junk_files_count"] = random.randint(50, 300)
    scan_results["junk_files_size"] = random.randint(20_000_000, 200_000_000)
    log_activity(f"Found {scan_results['junk_files_count']} junk files ({format_bytes(scan_results['junk_files_size'])})")

    scan_results["registry_issues"] = random.randint(5, 50)
    log_activity(f"Found {scan_results['registry_issues']} registry issues")

    scan_results["total_cleanable"] = (
        scan_results["temp_files_size"]
        + scan_results["chrome_cache_size"]
        + scan_results["junk_files_size"]
    )
    scan_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_activity(f"Scan complete. Total cleanable: {format_bytes(scan_results['total_cleanable'])}", "SUCCESS")


def simulate_clean():
    import random

    cleaning_status["is_running"] = True
    cleaning_status["progress"] = 0
    cleaning_status["items_cleaned"] = 0
    cleaning_status["space_freed"] = 0
    total_items = scan_results["temp_files_count"] + scan_results["junk_files_count"] + 15

    steps = [
        ("Cleaning temporary files...", scan_results["temp_files_count"], scan_results["temp_files_size"]),
        ("Clearing Chrome cache...", 15, scan_results["chrome_cache_size"]),
        ("Removing junk files...", scan_results["junk_files_count"], scan_results["junk_files_size"]),
        ("Cleaning registry entries...", scan_results["registry_issues"], 0),
        ("Optimizing system...", 0, 0),
    ]

    for i, (task, items, size) in enumerate(steps):
        cleaning_status["current_task"] = task
        log_activity(task, "TASK")
        time.sleep(1)
        cleaning_status["items_cleaned"] += items
        cleaning_status["space_freed"] += size
        cleaning_status["progress"] = int(((i + 1) / len(steps)) * 100)

    log_activity(f"Cleaning complete! Freed {format_bytes(cleaning_status['space_freed'])}", "SUCCESS")
    cleaning_status["is_running"] = False
    cleaning_status["current_task"] = "Complete"

    scan_results["temp_files_count"] = 0
    scan_results["temp_files_size"] = 0
    scan_results["chrome_cache_size"] = 0
    scan_results["junk_files_count"] = 0
    scan_results["junk_files_size"] = 0
    scan_results["registry_issues"] = 0
    scan_results["total_cleanable"] = 0


def update_wellness():
    import random

    now = datetime.now()
    hour = now.hour
    if 9 <= hour <= 17:
        activity_data["active_minutes"] += 1
        if random.random() < 0.1:
            activity_data["idle_minutes"] += 1
    activity_data["last_activity"] = now.isoformat()
    active = activity_data["active_minutes"]
    idle = activity_data["idle_minutes"]
    breaks = activity_data["break_count"]
    score = min(100, max(0, 85 - (active // 60) * 2 + breaks * 5 + (idle // 10)))
    activity_data["wellness_score"] = score


registry_data = {
    "orphaned_keys": 0,
    "invalid_paths": 0,
    "startup_items": 0,
    "issues_found": 0,
    "last_scan": None,
    "entries": [],
}


def scan_registry():
    import random

    log_activity("Starting registry analysis...", "TASK")
    time.sleep(1)

    registry_data["orphaned_keys"] = random.randint(3, 25)
    log_activity(f"Found {registry_data['orphaned_keys']} orphaned registry keys")

    registry_data["invalid_paths"] = random.randint(2, 15)
    log_activity(f"Found {registry_data['invalid_paths']} invalid file path references")

    registry_data["startup_items"] = random.randint(5, 20)
    log_activity(f"Detected {registry_data['startup_items']} startup items")

    registry_data["issues_found"] = registry_data["orphaned_keys"] + registry_data["invalid_paths"]

    categories = ["Software\\Classes", "Software\\Microsoft\\Windows", "CurrentVersion\\Run",
                   "CurrentVersion\\Explorer", "System\\CurrentControlSet"]
    entries = []
    for i in range(min(10, registry_data["issues_found"])):
        entries.append({
            "path": f"HKLM\\{random.choice(categories)}\\Entry_{random.randint(1000,9999)}",
            "type": random.choice(["orphaned", "invalid_path", "obsolete"]),
            "risk": random.choice(["low", "medium"]),
        })
    registry_data["entries"] = entries
    registry_data["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    scan_results["registry_issues"] = registry_data["issues_found"]
    log_activity(f"Registry scan complete. {registry_data['issues_found']} issues found.", "SUCCESS")


def scheduled_auto_clean():
    log_activity("Scheduled auto-clean triggered", "TASK")
    if not settings.get("auto_clean_enabled", False):
        log_activity("Auto-clean is disabled in settings, skipping", "WARN")
        return
    simulate_scan()
    time.sleep(1)
    simulate_clean()
    log_activity("Scheduled auto-clean completed", "SUCCESS")


def setup_scheduler():
    try:
        scheduler.remove_job("auto_clean")
    except Exception:
        pass
    try:
        scheduler.remove_job("registry_scan")
    except Exception:
        pass

    if settings.get("auto_clean_enabled", False):
        clean_time = settings.get("auto_clean_time", "17:00")
        hour, minute = clean_time.split(":")
        scheduler.add_job(
            scheduled_auto_clean,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id="auto_clean",
            replace_existing=True,
        )
        log_activity(f"Scheduled daily auto-clean at {clean_time}", "SUCCESS")

    scheduler.add_job(
        scan_registry,
        CronTrigger(day_of_week="sun", hour=3, minute=0),
        id="registry_scan",
        replace_existing=True,
    )
    log_activity("Scheduled weekly registry scan (Sunday 3:00 AM)", "SUCCESS")


log_activity("System Optimizer initialized", "SUCCESS")
log_activity(f"Platform: {platform.system()} {platform.release()}")
log_activity(f"Python: {platform.python_version()}")
log_activity("All modules loaded successfully", "SUCCESS")
log_activity("Scheduler service started", "SUCCESS")
log_activity("Activity monitor active", "INFO")
log_activity("Ready for operations", "SUCCESS")


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_system_metrics())


@app.route("/api/logs")
def api_logs():
    return jsonify(activity_log[-50:])


@app.route("/api/scan", methods=["POST"])
def api_scan():
    thread = threading.Thread(target=simulate_scan)
    thread.start()
    return jsonify({"status": "scanning"})


@app.route("/api/clean", methods=["POST"])
def api_clean():
    if cleaning_status["is_running"]:
        return jsonify({"status": "already_running"})
    thread = threading.Thread(target=simulate_clean)
    thread.start()
    return jsonify({"status": "cleaning"})


@app.route("/api/scan-results")
def api_scan_results():
    return jsonify(scan_results)


@app.route("/api/clean-status")
def api_clean_status():
    return jsonify(cleaning_status)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json()
        for key, value in data.items():
            if key in settings:
                settings[key] = value
        save_settings()
        setup_scheduler()
        log_activity("Settings updated and applied", "SUCCESS")
        return jsonify({"status": "ok", "settings": settings})
    return jsonify(settings)


@app.route("/api/registry")
def api_registry():
    return jsonify(registry_data)


@app.route("/api/registry/scan", methods=["POST"])
def api_registry_scan():
    thread = threading.Thread(target=scan_registry)
    thread.start()
    return jsonify({"status": "scanning"})


@app.route("/api/scheduler")
def api_scheduler_status():
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else "N/A",
            "trigger": str(job.trigger),
        })
    return jsonify({
        "running": scheduler.running,
        "jobs": jobs,
        "settings": {
            "auto_clean_enabled": settings.get("auto_clean_enabled"),
            "auto_clean_time": settings.get("auto_clean_time"),
        },
    })


@app.route("/api/activity")
def api_activity():
    update_wellness()
    return jsonify(activity_data)


@app.route("/api/startup-items")
def api_startup():
    items = []
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            info = proc.info
            items.append({
                "name": info["name"],
                "pid": info["pid"],
                "status": info["status"],
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    items.sort(key=lambda x: x["name"])
    return jsonify(items[:30])


if __name__ == "__main__":
    scheduler.start()
    setup_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=False)
