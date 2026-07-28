"""Monitoring endpoints: counters, update check, live metrics, logs,
health score, wellness/activity, and the recommendations engine."""
import os
import json
import time
import threading
from datetime import datetime, timedelta

import psutil
from flask import Blueprint, jsonify, request, current_app

from core.state import activity_log, activity_data, scan_results
from core.util import log_activity, format_bytes, get_local_version
from core.config import settings, load_analytics, increment_analytics
from scanners.system import get_system_metrics, update_wellness

bp = Blueprint("metrics", __name__)


@bp.route("/api/counters")
def get_counters():
    return jsonify(load_analytics())


@bp.route("/api/counters/download", methods=["POST"])
def count_download():
    data = increment_analytics("downloads")
    return jsonify({"ok": True, "downloads": data["downloads"]})


# ── Update system ────────────────────────────────────────────────
# The app never modifies itself. It only checks GitHub Releases and points the
# user at the release page; the NSIS installer handles upgrade-in-place.
GITHUB_RELEASES_API = "https://api.github.com/repos/MacroTechTitan/WindowZenOptimization/releases/latest"


def _ver_tuple(v):
    parts = []
    for x in str(v).lstrip("vV").split("."):
        try:
            parts.append(int(x))
        except Exception:
            parts.append(0)
    return tuple(parts)


@bp.route("/api/updates/check")
def api_updates_check():
    """Check GitHub Releases for a newer version. The app never self-updates."""
    import urllib.request
    local = get_local_version()
    local_version = str(local.get("version", "1.0.0"))

    try:
        req = urllib.request.Request(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "WindowZenOptimizer"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            release = json.loads(resp.read().decode())
    except Exception as e:
        return jsonify({
            "update_available": False,
            "latest": local_version,
            "current": local_version,
            "url": "",
            "error": f"Could not reach the update server: {e}",
        })

    tag = str(release.get("tag_name", "")).lstrip("vV")
    html_url = release.get("html_url", "")
    update_available = bool(tag) and _ver_tuple(tag) > _ver_tuple(local_version)

    return jsonify({
        "update_available": update_available,
        "latest": tag or local_version,
        "current": local_version,
        "url": html_url,
    })


@bp.route("/api/metrics")
def api_metrics():
    return jsonify(get_system_metrics())


@bp.route("/api/logs")
def api_logs():
    return jsonify(activity_log[-50:])


@bp.route("/api/debug-logs")
def api_debug_logs():
    level = request.args.get("level", "ALL").upper()
    order = request.args.get("order", "desc")
    logs = list(activity_log)
    if level == "ERROR":
        logs = [e for e in logs if e.get("level") == "ERROR"]
    elif level == "WARN":
        logs = [e for e in logs if e.get("level") in ("WARN", "ERROR")]
    elif level == "INFO":
        logs = [e for e in logs if e.get("level") in ("INFO", "WARN", "ERROR", "SUCCESS")]
    if order == "desc":
        logs = list(reversed(logs))
    counts = {
        "SUCCESS": sum(1 for e in activity_log if e.get("level") == "SUCCESS"),
        "INFO":    sum(1 for e in activity_log if e.get("level") == "INFO"),
        "WARN":    sum(1 for e in activity_log if e.get("level") == "WARN"),
        "ERROR":   sum(1 for e in activity_log if e.get("level") == "ERROR"),
        "total":   len(activity_log),
    }
    return jsonify({"logs": logs, "counts": counts})


@bp.route("/api/debug-logs/clear", methods=["POST"])
def api_debug_logs_clear():
    activity_log.clear()
    log_activity("Debug log cleared by user", "INFO")
    return jsonify({"ok": True})


@bp.route("/api/activity")
def api_activity():
    update_wellness()
    now = datetime.now()
    hour = now.hour
    break_minutes = settings.get("break_reminder_minutes", 40)
    suggestions = []
    if hour >= 18 or hour < 6:
        suggestions.append("Lower screen brightness in evening hours")
    suggestions.append(f"Take a break every {break_minutes} minutes")
    if activity_data["active_minutes"] > 120:
        suggestions.append("You've been active for over 2 hours — consider stretching")
    if activity_data["wellness_score"] < 60:
        suggestions.append("Your wellness score is low — take a longer break")
    result = dict(activity_data)
    result["suggestions"] = suggestions
    return jsonify(result)


@bp.route("/api/wellness/break-check")
def api_wellness_break_check():
    now = datetime.now()
    last_break_str = activity_data.get("last_break_time", now.isoformat())
    try:
        last_break = datetime.fromisoformat(last_break_str)
    except (ValueError, TypeError):
        last_break = now
    elapsed = (now - last_break).total_seconds() / 60.0
    break_minutes = settings.get("break_reminder_minutes", 40)
    should_break = elapsed >= break_minutes
    return jsonify({
        "should_break": should_break,
        "minutes_since_break": round(elapsed, 1),
        "break_reminder_minutes": break_minutes,
    })


@bp.route("/api/wellness/dismiss-break", methods=["POST"])
def api_wellness_dismiss_break():
    activity_data["last_break_time"] = datetime.now().isoformat()
    activity_data["break_count"] = activity_data.get("break_count", 0) + 1
    log_activity("Break dismissed — timer reset.", "INFO")
    return jsonify({"status": "ok", "last_break_time": activity_data["last_break_time"]})


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH SCORE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@bp.route("/api/health-score")
def api_health_score():
    """Compute a 0–100 health score and return actionable recommendations."""
    score = 100
    issues = []
    recommendations = []

    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        if cpu > 80:
            score -= 20
            issues.append(f"CPU usage is very high ({cpu:.0f}%)")
            recommendations.append({"icon": "⚡", "text": "High CPU usage detected. Open Processes page to identify heavy apps.", "page": "processes", "severity": "high"})
        elif cpu > 60:
            score -= 10
            issues.append(f"CPU usage is elevated ({cpu:.0f}%)")
            recommendations.append({"icon": "⚡", "text": "CPU usage is elevated. Check Processes for background tasks.", "page": "processes", "severity": "medium"})

        mem_pct = mem.percent
        if mem_pct > 85:
            score -= 20
            issues.append(f"RAM usage is critically high ({mem_pct:.0f}%)")
            recommendations.append({"icon": "🧠", "text": "RAM is nearly full. Close unused apps or consider a RAM upgrade.", "page": "system", "severity": "high"})
        elif mem_pct > 70:
            score -= 10
            issues.append(f"RAM usage is high ({mem_pct:.0f}%)")
            recommendations.append({"icon": "🧠", "text": "RAM usage is high. Close unused applications to free memory.", "page": "processes", "severity": "medium"})

        disk_free_pct = 100 - disk.percent
        if disk_free_pct < 10:
            score -= 25
            issues.append(f"Disk space critically low ({disk_free_pct:.0f}% free)")
            recommendations.append({"icon": "💾", "text": "Critical: Less than 10% disk space free. Run System Cleaner immediately.", "page": "cleaner", "severity": "high"})
        elif disk_free_pct < 20:
            score -= 12
            issues.append(f"Disk space is low ({disk_free_pct:.0f}% free)")
            recommendations.append({"icon": "💾", "text": "Low disk space. Use System Cleaner to recover storage.", "page": "cleaner", "severity": "medium"})

        uptime_sec = time.time() - psutil.boot_time()
        uptime_days = uptime_sec / 86400
        if uptime_days > 14:
            score -= 8
            issues.append(f"System has been running for {uptime_days:.0f} days without a restart")
            recommendations.append({"icon": "🔄", "text": f"PC has been on for {uptime_days:.0f} days. A restart improves performance and applies updates.", "page": "dashboard", "severity": "medium"})

        procs = sorted(psutil.process_iter(["name", "cpu_percent"]), key=lambda p: p.info.get("cpu_percent", 0) or 0, reverse=True)
        heavy = [p.info["name"] for p in procs[:3] if (p.info.get("cpu_percent") or 0) > 10]
        if len(heavy) >= 2:
            score -= 10
            issues.append(f"Multiple CPU-heavy processes running: {', '.join(heavy)}")
            recommendations.append({"icon": "⚙️", "text": f"Heavy background processes detected. Check: {', '.join(heavy[:2])}", "page": "processes", "severity": "medium"})

    except Exception as e:
        score = max(score, 50)

    score = max(0, min(100, score))

    if score >= 85:
        grade = "Excellent"
        color = "green"
    elif score >= 70:
        grade = "Good"
        color = "cyan"
    elif score >= 50:
        grade = "Fair"
        color = "yellow"
    else:
        grade = "Poor"
        color = "red"

    if not issues:
        issues.append("No major performance issues detected.")
        recommendations.append({"icon": "✅", "text": "Your PC is in good shape! Run System Cleaner periodically to maintain performance.", "page": "cleaner", "severity": "low"})

    return jsonify({
        "score": score,
        "grade": grade,
        "color": color,
        "issues": issues,
        "recommendations": recommendations,
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 13: RECOMMENDATIONS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

RECOMMENDATIONS_FILE = "recommendations_state.json"
_rec_lock = threading.Lock()

def _load_rec_state():
    try:
        if os.path.exists(RECOMMENDATIONS_FILE):
            with open(RECOMMENDATIONS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"dismissed": [], "snoozed": {}, "history": []}

def _save_rec_state(state):
    try:
        with open(RECOMMENDATIONS_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

def _generate_recommendations():
    recs = []
    ts = datetime.now().isoformat()

    try:
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        if cpu > 80:
            recs.append({"id": "cpu_high", "category": "Performance", "priority": "high",
                "title": f"CPU is under heavy load ({cpu:.0f}%)",
                "explanation": "Sustained high CPU usage slows the whole system. Check top processes and close unnecessary apps.",
                "evidence": f"CPU at {cpu:.0f}%", "action": "View Processes", "module": "processes",
                "benefit": 8, "risk": "low", "actionable": True})
        elif cpu > 60:
            recs.append({"id": "cpu_medium", "category": "Performance", "priority": "medium",
                "title": f"CPU usage is elevated ({cpu:.0f}%)",
                "explanation": "CPU is moderately busy. Consider closing background apps.",
                "evidence": f"CPU at {cpu:.0f}%", "action": "View Processes", "module": "processes",
                "benefit": 5, "risk": "low", "actionable": True})

        ram_avail_gb = mem.available / (1024 ** 3)
        if ram_avail_gb < 1.5:
            recs.append({"id": "ram_critical", "category": "Performance", "priority": "high",
                "title": f"Low RAM — only {ram_avail_gb:.1f} GB available",
                "explanation": "Very low available RAM forces Windows to use slow page file swapping. Close apps or consider a RAM upgrade.",
                "evidence": f"{ram_avail_gb:.1f} GB free of {mem.total/(1024**3):.1f} GB",
                "action": "View System Info", "module": "system", "benefit": 9, "risk": "low", "actionable": True})
        elif mem.percent > 80:
            recs.append({"id": "ram_high", "category": "Performance", "priority": "medium",
                "title": f"Memory usage is high ({mem.percent:.0f}%)",
                "explanation": "High RAM usage can cause slowdowns. Close unused apps or browser tabs.",
                "evidence": f"{mem.percent:.0f}% used ({ram_avail_gb:.1f} GB free)",
                "action": "View Processes", "module": "processes", "benefit": 6, "risk": "low", "actionable": True})

        disk_free_pct = 100 - disk.percent
        if disk_free_pct < 10:
            recs.append({"id": "disk_critical", "category": "Storage", "priority": "high",
                "title": f"Disk is almost full — only {disk_free_pct:.0f}% free",
                "explanation": "Windows needs free disk space to function properly. Run a system clean now.",
                "evidence": f"{format_bytes(disk.free)} free of {format_bytes(disk.total)}",
                "action": "Clean Now", "module": "cleaner", "benefit": 10, "risk": "low", "actionable": True})
        elif disk_free_pct < 20:
            recs.append({"id": "disk_low", "category": "Storage", "priority": "medium",
                "title": f"Disk space is getting low ({disk_free_pct:.0f}% free)",
                "explanation": "Consider running the system cleaner or large file finder to reclaim space.",
                "evidence": f"{format_bytes(disk.free)} free of {format_bytes(disk.total)}",
                "action": "Scan for Junk", "module": "cleaner", "benefit": 7, "risk": "low", "actionable": True})

        uptime_secs = time.time() - psutil.boot_time()
        uptime_days = uptime_secs / 86400
        if uptime_days > 14:
            recs.append({"id": "uptime_long", "category": "Maintenance", "priority": "medium",
                "title": f"System has been running for {uptime_days:.0f} days",
                "explanation": "Long uptime can lead to memory leaks and accumulated temp files. A restart is recommended.",
                "evidence": f"Uptime: {uptime_days:.1f} days", "action": "Restart Reminder", "module": "dashboard",
                "benefit": 5, "risk": "low", "actionable": False})
        elif uptime_days > 7:
            recs.append({"id": "uptime_week", "category": "Maintenance", "priority": "low",
                "title": f"PC has been on for {uptime_days:.0f} days without restart",
                "explanation": "Consider restarting this week to apply pending updates and clear memory.",
                "evidence": f"Uptime: {uptime_days:.1f} days", "action": None, "module": "dashboard",
                "benefit": 3, "risk": "low", "actionable": False})
    except Exception:
        pass

    try:
        procs = [(p.name(), p.cpu_percent()) for p in psutil.process_iter(["name", "cpu_percent"]) if p.info["cpu_percent"] > 15]
        if len(procs) >= 3:
            names = ", ".join(p[0] for p in procs[:3])
            recs.append({"id": "heavy_procs", "category": "Performance", "priority": "medium",
                "title": f"{len(procs)} processes are consuming high CPU",
                "explanation": f"Several background processes are using significant CPU: {names}.",
                "evidence": f"High-CPU processes: {names}", "action": "View Processes", "module": "processes",
                "benefit": 6, "risk": "low", "actionable": True})
    except Exception:
        pass

    try:
        home = os.path.expanduser("~")
        dl = os.path.join(home, "Downloads")
        if os.path.isdir(dl):
            old_files = [f for f in os.listdir(dl)
                         if os.path.isfile(os.path.join(dl, f))
                         and (time.time() - os.path.getmtime(os.path.join(dl, f))) > 60 * 86400]
            if len(old_files) > 10:
                recs.append({"id": "downloads_old", "category": "Organization", "priority": "medium",
                    "title": f"Downloads folder has {len(old_files)} files older than 60 days",
                    "explanation": "Old downloads accumulate over time. Review and archive or delete them.",
                    "evidence": f"{len(old_files)} files older than 60 days in Downloads",
                    "action": "Organize Downloads", "module": "file-organizer", "benefit": 5, "risk": "low", "actionable": True})

        desktop = os.path.join(home, "Desktop")
        if os.path.isdir(desktop):
            desktop_files = [f for f in os.listdir(desktop) if os.path.isfile(os.path.join(desktop, f))]
            if len(desktop_files) > 20:
                recs.append({"id": "desktop_cluttered", "category": "Organization", "priority": "low",
                    "title": f"Desktop has {len(desktop_files)} files — consider organizing",
                    "explanation": "A cluttered desktop can slow icon rendering and make finding files harder.",
                    "evidence": f"{len(desktop_files)} files on Desktop",
                    "action": "File Organizer", "module": "file-organizer", "benefit": 3, "risk": "low", "actionable": True})
    except Exception:
        pass

    scan_data = scan_results
    if scan_data.get("total_size", 0) > 500 * 1024 * 1024:
        recs.append({"id": "junk_large", "category": "Storage", "priority": "medium",
            "title": f"Last scan found {format_bytes(scan_data['total_size'])} of cleanable junk",
            "explanation": "Your last system scan identified significant clutter. Run the cleaner to reclaim space.",
            "evidence": f"{format_bytes(scan_data['total_size'])} in {scan_data.get('total_files', 0)} files",
            "action": "Clean Now", "module": "cleaner", "benefit": 8, "risk": "low", "actionable": True})

    if scan_data.get("last_scan") is None:
        recs.append({"id": "no_scan", "category": "Maintenance", "priority": "medium",
            "title": "You haven't run a system scan yet",
            "explanation": "Run your first scan to discover temp files, large files, and clutter on this system.",
            "evidence": "No scan history found", "action": "Scan Now", "module": "cleaner",
            "benefit": 7, "risk": "low", "actionable": True})

    hour = datetime.now().hour
    if hour >= 21 or hour < 7:
        recs.append({"id": "night_light", "category": "Wellness", "priority": "low",
            "title": "It's late — consider enabling Night Light mode",
            "explanation": "Blue light exposure in the evening affects sleep quality. Enable Night Light in Windows Display settings.",
            "evidence": f"Current time: {datetime.now().strftime('%H:%M')}",
            "action": "Open Wellness", "module": "wellness", "benefit": 4, "risk": "low", "actionable": True})

    state = _load_rec_state()
    dismissed = set(state.get("dismissed", []))
    snoozed = state.get("snoozed", {})
    now_iso = datetime.now().isoformat()

    filtered = []
    for r in recs:
        rid = r["id"]
        if rid in dismissed:
            continue
        if rid in snoozed:
            snooze_until = snoozed[rid]
            if now_iso < snooze_until:
                continue
            else:
                del snoozed[rid]
        r["timestamp"] = ts
        filtered.append(r)

    filtered.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    state["snoozed"] = snoozed
    _save_rec_state(state)
    return filtered


@bp.route("/api/recommendations")
def api_recommendations():
    recs = _generate_recommendations()
    return jsonify({"recommendations": recs, "total": len(recs),
                    "high": sum(1 for r in recs if r["priority"] == "high"),
                    "medium": sum(1 for r in recs if r["priority"] == "medium"),
                    "low": sum(1 for r in recs if r["priority"] == "low")})


@bp.route("/api/recommendations/dismiss", methods=["POST"])
def api_rec_dismiss():
    data = request.get_json() or {}
    rid = data.get("id")
    if not rid:
        return jsonify({"status": "error"}), 400
    with _rec_lock:
        state = _load_rec_state()
        if rid not in state["dismissed"]:
            state["dismissed"].append(rid)
        history_entry = {"id": rid, "action": "dismissed", "timestamp": datetime.now().isoformat()}
        state.setdefault("history", []).append(history_entry)
        _save_rec_state(state)
    return jsonify({"status": "ok"})


@bp.route("/api/recommendations/snooze", methods=["POST"])
def api_rec_snooze():
    data = request.get_json() or {}
    rid = data.get("id")
    hours = int(data.get("hours", 24))
    if not rid:
        return jsonify({"status": "error"}), 400
    with _rec_lock:
        state = _load_rec_state()
        until = (datetime.now() + timedelta(hours=hours)).isoformat()
        state.setdefault("snoozed", {})[rid] = until
        state.setdefault("history", []).append({"id": rid, "action": f"snoozed_{hours}h", "timestamp": datetime.now().isoformat()})
        _save_rec_state(state)
    return jsonify({"status": "ok", "snoozed_until": until})


@bp.route("/api/recommendations/reset-dismissed", methods=["POST"])
def api_rec_reset():
    with _rec_lock:
        state = _load_rec_state()
        state["dismissed"] = []
        state["snoozed"] = {}
        _save_rec_state(state)
    return jsonify({"status": "ok"})


@bp.route("/api/recommendations/history")
def api_rec_history():
    state = _load_rec_state()
    return jsonify({"history": list(reversed(state.get("history", [])))})


@bp.route("/api/recommendations/export")
def api_rec_export():
    recs = _generate_recommendations()
    lines = ["MTT Windows Infinite Optimizer — Recommendations Report",
             f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "", ""]
    for r in recs:
        lines.append(f"[{r['priority'].upper()}] {r['title']}")
        lines.append(f"  Category : {r['category']}")
        lines.append(f"  Evidence : {r['evidence']}")
        lines.append(f"  Why      : {r['explanation']}")
        lines.append("")
    content = "\n".join(lines)
    return current_app.response_class(content, mimetype="text/plain",
        headers={"Content-Disposition": "attachment;filename=recommendations.txt"})
