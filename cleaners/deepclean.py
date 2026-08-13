"""Deep Clean apply phase.

The restore-point gate covers the whole run: guard_batch is called once
before any target is touched, and the run is refused unless it succeeds or
the user explicitly confirmed proceeding without one.

File-removing targets (modes "contents", "files", "patterns", "tree") are
gated by core.safety:
  * every item passes check_deletable (Windows core / Program Files /
    Package Cache / cloud-sync roots are refused),
  * removal goes through send_to_recycle_bin, which uses SHFileOperationW
    with FOF_ALLOWUNDO so the delete is undoable, and refuses the batch
    outright rather than silently permanent-deleting when it would overflow
    the bin — unless the caller passed allow_permanent, which the UI has to
    surface to the user per action,
  * before/after paths and bytes are written to the activity log.

Two modes do NOT delete files and so are not gated that way:
  * "recycle_bin" runs Clear-RecycleBin. Emptying the bin is permanent by
    definition — there is nowhere further to recycle to. It only ever runs
    when the user ticks that specific target.
  * "dism" shells out to DISM /StartComponentCleanup. It is a subprocess
    that manages the component store itself; this module deletes nothing
    for it and cannot make it undoable.

The apply phase only ever runs for targets the user explicitly selected in
the UI after seeing the report.
"""
import os
import glob
import subprocess
import threading
from datetime import datetime

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.deepclean import DEEPCLEAN_TARGETS, recycle_bin_size

_lock = threading.Lock()

deepclean_state = {
    "status": "idle",          # idle | running | complete | blocked
    "current": "",
    "progress": 0,
    "results": [],
    "bytes_freed": 0,
    "started_at": None,
    "completed_at": None,
    "restore_point": None,
    "message": "",
}


def _service(action, name):
    """net stop/start a Windows service. Returns (ok, output)."""
    if not IS_WINDOWS:
        return True, f"[preview] would {action} {name}"
    try:
        proc = subprocess.run(["net", action, name], capture_output=True, text=True,
                              timeout=120, creationflags=_WIN_NO_WINDOW)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode == 0, out
    except Exception as e:
        return False, str(e)


def _collect_paths(key, target):
    """Concrete filesystem entries this target would remove."""
    mode = target.get("mode", "contents")
    try:
        roots = target["paths_fn"]()
    except Exception:
        roots = []

    if mode == "files":
        return [p for p in roots if os.path.isfile(p)]

    if mode == "patterns":
        out = []
        for base in roots:
            if not os.path.isdir(base):
                continue
            for pattern in target.get("file_patterns", []):
                out.extend(m for m in glob.glob(os.path.join(base, "**", pattern),
                                                recursive=True) if os.path.isfile(m))
        return out

    if mode == "tree":
        return [p for p in roots if os.path.exists(p)]

    # "contents" — remove what is inside the directory, keep the directory.
    out = []
    for base in roots:
        if not os.path.isdir(base):
            continue
        try:
            out.extend(os.path.join(base, name) for name in os.listdir(base))
        except (OSError, PermissionError):
            pass
    return out


def _bytes_of(paths):
    total = 0
    for p in paths:
        try:
            if os.path.isfile(p):
                total += os.path.getsize(p)
            elif os.path.isdir(p):
                for dirpath, _, filenames in os.walk(p):
                    for f in filenames:
                        try:
                            total += os.path.getsize(os.path.join(dirpath, f))
                        except (OSError, PermissionError):
                            pass
        except (OSError, PermissionError):
            pass
    return total


def _empty_recycle_bin():
    """Explicit, user-selected, and permanent by definition."""
    count, size = recycle_bin_size()
    if not IS_WINDOWS:
        return {"bytes": 0, "count": 0, "note": "Preview mode — Recycle Bin not emptied."}
    log_activity(f"Emptying Recycle Bin — {count} item(s), {format_bytes(size)} "
                 f"(permanent, user-selected)", "WARN")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Clear-RecycleBin -Force -ErrorAction Stop"],
                       capture_output=True, text=True, timeout=300,
                       creationflags=_WIN_NO_WINDOW)
        log_activity(f"Recycle Bin emptied — {format_bytes(size)} reclaimed", "SUCCESS")
        return {"bytes": size, "count": count, "note": "Recycle Bin emptied."}
    except Exception as e:
        log_activity(f"Could not empty Recycle Bin: {e}", "ERROR")
        return {"bytes": 0, "count": 0, "note": f"Failed: {e}"}


def _run_dism_cleanup():
    """DISM StartComponentCleanup — a subprocess, not a file delete."""
    entry = {"bytes": 0, "count": 0, "note": "", "output": ""}
    if not IS_WINDOWS:
        entry["note"] = "Preview mode — DISM not run."
        return entry
    log_activity("Running DISM /Online /Cleanup-Image /StartComponentCleanup "
                 "(this can take 10-30 minutes)", "TASK")
    try:
        proc = subprocess.run(
            ["dism.exe", "/Online", "/Cleanup-Image", "/StartComponentCleanup"],
            capture_output=True, text=True, timeout=3600,
            creationflags=_WIN_NO_WINDOW)
        entry["output"] = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
        if proc.returncode == 0:
            entry["note"] = "DISM component cleanup completed."
            log_activity("DISM component store cleanup completed", "SUCCESS")
        else:
            entry["note"] = f"DISM exited with code {proc.returncode}. Administrator required."
            log_activity(f"DISM cleanup exit code {proc.returncode}", "WARN")
    except subprocess.TimeoutExpired:
        entry["note"] = "DISM timed out after 60 minutes."
        log_activity("DISM cleanup timed out", "ERROR")
    except Exception as e:
        entry["note"] = f"DISM failed: {e}"
        log_activity(f"DISM cleanup failed: {e}", "ERROR")
    return entry


def apply_deepclean(keys, proceed_without_restore_point=False, allow_permanent=False):
    """Run the apply phase for the explicitly selected target keys.

    Returns the final deepclean_state dict.
    """
    with _lock:
        if deepclean_state["status"] == "running":
            return dict(deepclean_state)
        deepclean_state.update({
            "status": "running", "current": "", "progress": 0, "results": [],
            "bytes_freed": 0, "message": "",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": None, "restore_point": None,
        })

    selected = [k for k in (keys or []) if k in DEEPCLEAN_TARGETS]
    # Report-only targets can never be applied, whatever the client sends.
    refused = [k for k in selected if DEEPCLEAN_TARGETS[k].get("report_only")]
    for k in refused:
        log_activity(f"Deep Clean: '{k}' is report-only and was not cleaned", "INFO")
    selected = [k for k in selected if not DEEPCLEAN_TARGETS[k].get("report_only")]

    if not selected:
        with _lock:
            deepclean_state.update({
                "status": "complete", "message": "No cleanable targets were selected.",
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        return dict(deepclean_state)

    log_activity(f"Deep Clean apply requested for: {', '.join(selected)}", "TASK")

    # ── Restore point gate (once, before the whole batch) ──────
    ok, payload = guard_batch(
        selected, proceed_without_restore_point,
        description="MTT Optimizer — before Deep Clean")
    if not ok:
        with _lock:
            deepclean_state.update({
                "status": "blocked",
                "message": payload["message"],
                "restore_point": payload["restore_point"],
                "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        log_activity("Deep Clean BLOCKED — no restore point and no explicit "
                     "confirmation to proceed without one", "WARN")
        return dict(deepclean_state)

    with _lock:
        deepclean_state["restore_point"] = payload["restore_point"]

    results = []
    total_freed = 0
    stopped_services = []

    for i, key in enumerate(selected):
        target = DEEPCLEAN_TARGETS[key]
        with _lock:
            deepclean_state["current"] = target["label"]
            deepclean_state["progress"] = int(i / len(selected) * 100)

        entry = {"key": key, "label": target["label"], "bytes": 0, "count": 0,
                 "blocked": [], "errors": [], "note": ""}
        mode = target.get("mode", "contents")

        if mode == "recycle_bin":
            r = _empty_recycle_bin()
            entry.update(bytes=r["bytes"], count=r["count"], note=r["note"])
            results.append(entry)
            total_freed += r["bytes"]
            continue

        if mode == "dism":
            r = _run_dism_cleanup()
            entry.update(note=r["note"], output=r.get("output", ""))
            results.append(entry)
            continue

        # Stop dependent services first (Windows Update cache).
        services = target.get("services", [])
        for svc in services:
            ok_stop, out = _service("stop", svc)
            log_activity(f"Deep Clean: stopping {svc} — "
                         f"{'ok' if ok_stop else 'failed'}", "INFO" if ok_stop else "WARN")
            if ok_stop:
                stopped_services.append(svc)

        paths = _collect_paths(key, target)
        # Belt-and-braces: re-check every single path at apply time.
        safe_paths = []
        for p in paths:
            allowed, reason = check_deletable(p)
            if allowed:
                safe_paths.append(p)
            else:
                entry["blocked"].append({"path": p, "reason": reason})

        planned_bytes = _bytes_of(safe_paths)
        log_activity(f"Deep Clean: {target['label']} — {len(safe_paths)} item(s), "
                     f"{format_bytes(planned_bytes)} before", "INFO")

        r = send_to_recycle_bin(safe_paths, allow_permanent=allow_permanent,
                                total_bytes=planned_bytes)
        entry["bytes"] = r["bytes"] if r["recycled"] else 0
        entry["count"] = len(r["recycled"])
        entry["blocked"].extend(r["blocked"])
        entry["errors"] = r["errors"]
        entry["permanent"] = r["permanent"]
        if r["message"]:
            entry["note"] = r["message"]

        remaining = _bytes_of([p for p in safe_paths if os.path.exists(p)])
        log_activity(f"Deep Clean: {target['label']} — after: {format_bytes(remaining)} "
                     f"remaining, {format_bytes(entry['bytes'])} reclaimed", "SUCCESS")
        if entry["count"]:
            log_undo("recycle", f"Deep Clean: {target['label']}",
                     {"target": key, "count": entry["count"], "bytes": entry["bytes"],
                      "recoverable": not r["permanent"]})

        total_freed += entry["bytes"]
        results.append(entry)

        # Restart anything we stopped for this target.
        for svc in services:
            ok_start, out = _service("start", svc)
            log_activity(f"Deep Clean: restarting {svc} — "
                         f"{'ok' if ok_start else 'failed'}", "INFO" if ok_start else "WARN")
            if svc in stopped_services:
                stopped_services.remove(svc)

    # Safety net: never leave a service we stopped in a stopped state.
    for svc in list(stopped_services):
        _service("start", svc)
        log_activity(f"Deep Clean: restarted {svc} during cleanup", "INFO")

    with _lock:
        deepclean_state.update({
            "status": "complete", "current": "", "progress": 100,
            "results": results, "bytes_freed": total_freed,
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": f"Reclaimed {format_bytes(total_freed)}.",
        })
    log_activity(f"Deep Clean complete — {format_bytes(total_freed)} reclaimed", "SUCCESS")
    return dict(deepclean_state)
