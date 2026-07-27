"""Full-system scan/clean orchestration and the auto-clean scheduler."""
import time
from datetime import datetime

from apscheduler.triggers.cron import CronTrigger

from core.state import scan_results, cleaning_status, scheduler
from core.config import settings
from core.util import log_activity, format_bytes
from cleaners.targets import get_active_targets, scan_target, clean_target
from scanners.registry import scan_registry


def run_system_scan():
    log_activity("Starting comprehensive system scan...", "TASK")
    targets = get_active_targets()
    categories = {}
    total_files = 0
    total_size = 0

    for key, target in targets.items():
        setting_key = target.get("setting", "")
        log_activity(f"Scanning: {target['label']}...", "INFO")

        count, size = scan_target(key, target)
        categories[key] = {
            "label": target["label"],
            "description": target["description"],
            "count": count,
            "size": size,
            "size_fmt": format_bytes(size),
            "safe_level": target.get("safe_level", "safe"),
            "enabled": settings.get(setting_key, False),
            "setting": setting_key,
        }
        total_files += count
        total_size += size

        if count > 0 or size > 0:
            log_activity(f"  {target['label']}: {count} files ({format_bytes(size)})")

    scan_results["categories"] = categories
    scan_results["total_files"] = total_files
    scan_results["total_size"] = total_size
    scan_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_activity(f"Scan complete! {total_files} files, {format_bytes(total_size)} cleanable", "SUCCESS")


def run_system_clean():
    cleaning_status["is_running"] = True
    cleaning_status["progress"] = 0
    cleaning_status["items_cleaned"] = 0
    cleaning_status["space_freed"] = 0

    targets = get_active_targets()
    enabled_targets = {k: v for k, v in targets.items() if settings.get(v.get("setting", ""), False)}
    total_steps = len(enabled_targets)

    if total_steps == 0:
        log_activity("No cleaning targets enabled. Check your settings.", "WARN")
        cleaning_status["is_running"] = False
        return

    log_activity(f"Starting cleanup of {total_steps} categories...", "TASK")

    for i, (key, target) in enumerate(enabled_targets.items()):
        cleaning_status["current_task"] = f"Cleaning {target['label']}..."
        log_activity(f"Cleaning: {target['label']}...", "TASK")

        count, size = clean_target(key, target)
        cleaning_status["items_cleaned"] += count
        cleaning_status["space_freed"] += size
        cleaning_status["progress"] = int(((i + 1) / total_steps) * 100)

        if count > 0 or size > 0:
            log_activity(f"  Removed {count} files ({format_bytes(size)})", "SUCCESS")
        else:
            log_activity(f"  Already clean or no access", "INFO")

    log_activity(
        f"Cleanup complete! Removed {cleaning_status['items_cleaned']} files, "
        f"freed {format_bytes(cleaning_status['space_freed'])}",
        "SUCCESS"
    )
    cleaning_status["is_running"] = False
    cleaning_status["current_task"] = "Complete"

    run_system_scan()


def scheduled_auto_clean():
    log_activity("Scheduled auto-clean triggered", "TASK")
    if not settings.get("auto_clean_enabled", False):
        log_activity("Auto-clean is disabled in settings, skipping", "WARN")
        return
    run_system_scan()
    time.sleep(1)
    run_system_clean()
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

