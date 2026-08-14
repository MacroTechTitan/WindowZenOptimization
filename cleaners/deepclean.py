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

Three modes do NOT delete files and so are not gated that way:
  * "recycle_bin" runs Clear-RecycleBin. Emptying the bin is permanent by
    definition — there is nowhere further to recycle to. It only ever runs
    when the user ticks that specific target.
  * "dism" shells out to DISM /StartComponentCleanup. It is a subprocess
    that manages the component store itself; this module deletes nothing
    for it and cannot make it undoable.
  * "command" runs a declared subprocess — ipconfig /flushdns, wsreset.exe.
    The tool owns whatever it clears; this module removes nothing itself.

One mode deletes permanently, and which deleter a target uses is a property
of the TARGET, not of the caller:
  * "system_permanent" (font_cache, memory_dumps) uses permanent_delete(),
    guarded by deepclean_system_roots() — an allowlist computed from the
    system_permanent rows of DEEPCLEAN_TARGETS in the scanner module, not
    from any caller-supplied dict. Anything outside it raises
    PermanentDeleteRefused. These are system files the Recycle Bin cannot
    meaningfully hold: a 16 GB MEMORY.DMP moved to C:\\$Recycle.Bin frees
    nothing, and the font cache is regenerated on the next boot.

Everything else — including every target that touches user-profile files,
such as jump_lists — keeps the send_to_recycle_bin route. Sprint 3's rule
(RECYCLE BIN, NOT PERMANENT) governs anything a user could plausibly want
back. Both paths still run behind guard_batch and per-item check_deletable.

"report_dirs" (leftover_programs) is report-only and is refused by the
apply phase outright, whatever the client sends.

The apply phase only ever runs for targets the user explicitly selected in
the UI after seeing the report.
"""
import os
import glob
import shutil
import subprocess
import threading
from datetime import datetime

from core.state import IS_WINDOWS, _WIN_NO_WINDOW
from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.deepclean import DEEPCLEAN_TARGETS, recycle_bin_size

_lock = threading.Lock()


# ─── Permanent-delete allowlist for system_permanent targets ───
class PermanentDeleteRefused(ValueError):
    """Raised when the permanent deleter is handed a path it does not own.
    Always a caller bug — never swallow it silently upstream."""


def deepclean_system_roots():
    """Every root a ``system_permanent`` target may delete inside.

    Computed from the ``system_permanent`` rows of DEEPCLEAN_TARGETS in the
    scanner module — NOT from a caller-supplied dict — which is what makes
    this a guard rather than a restatement of the caller's intent.
    """
    roots = []
    for key, target in DEEPCLEAN_TARGETS.items():
        if target.get("mode") != "system_permanent":
            continue
        try:
            paths = target["paths_fn"]()
        except Exception:
            continue
        for p in paths:
            if not p:
                continue
            try:
                roots.append(os.path.normcase(os.path.abspath(p)))
            except (OSError, ValueError):
                pass
    return roots


def is_deepclean_system_path(path, allowlist=None):
    if allowlist is None:
        allowlist = deepclean_system_roots()
    if not path:
        return False
    try:
        target = os.path.normcase(os.path.abspath(path))
    except (OSError, ValueError):
        return False
    drive, tail = os.path.splitdrive(target)
    if tail in ("", os.sep, "/"):
        return False
    for root in allowlist:
        if target == root or target.startswith(root + os.sep):
            return True
    return False


def permanent_delete(path, allowlist=None):
    """The ONLY permanent deleter in this module.

    Refuses anything outside the system_permanent allowlist. Returns
    (deleted, bytes_freed). Raises PermanentDeleteRefused for a disallowed
    path — a caller bug, so it is deliberately not folded into the OSError
    path where it would look like an ordinary per-file failure.

    User files never reach this function: they go to
    core.safety.send_to_recycle_bin, which is recoverable.
    """
    if not is_deepclean_system_path(path, allowlist):
        raise PermanentDeleteRefused(
            f"Refusing to permanently delete {path!r} — it is not inside any "
            f"declared Deep Clean system-target root. User files must go "
            f"through core.safety.send_to_recycle_bin instead.")
    if os.path.isfile(path):
        fsize = os.path.getsize(path)
        os.remove(path)
        return True, fsize
    if os.path.isdir(path):
        freed = _bytes_of([path])
        shutil.rmtree(path, ignore_errors=True)
        return True, freed
    return False, 0


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

    if mode == "system_permanent":
        # Expand a declared directory into its children so the directory
        # itself survives — Windows expects FontCache and LiveKernelReports
        # to exist, just to be empty. Declared files are taken as they are.
        out = []
        for p in roots:
            if os.path.isfile(p):
                out.append(p)
            elif os.path.isdir(p):
                try:
                    out.extend(os.path.join(p, name) for name in os.listdir(p))
                except (OSError, PermissionError):
                    pass
        return out

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


def _run_command(target):
    """A target whose work is a subprocess, not a file delete."""
    cmd = target.get("command", [])
    entry = {"bytes": 0, "count": 0, "note": "", "output": ""}
    if not cmd:
        entry["note"] = "No command defined."
        return entry
    if not IS_WINDOWS:
        entry["note"] = f"Preview mode — '{' '.join(cmd)}' not run."
        return entry
    log_activity(f"Deep Clean: running {' '.join(cmd)}", "TASK")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                              creationflags=_WIN_NO_WINDOW)
        entry["output"] = ((proc.stdout or "") + (proc.stderr or ""))[-2000:]
        if proc.returncode == 0:
            entry["note"] = f"{' '.join(cmd)} completed."
            log_activity(f"Deep Clean: {' '.join(cmd)} completed", "SUCCESS")
        else:
            entry["note"] = (f"{' '.join(cmd)} exited with code {proc.returncode}. "
                             f"Administrator may be required.")
            log_activity(f"Deep Clean: {' '.join(cmd)} exit code {proc.returncode}", "WARN")
    except subprocess.TimeoutExpired:
        entry["note"] = f"{' '.join(cmd)} timed out."
        log_activity(f"Deep Clean: {' '.join(cmd)} timed out", "ERROR")
    except Exception as e:
        entry["note"] = f"{' '.join(cmd)} failed: {e}"
        log_activity(f"Deep Clean: {' '.join(cmd)} failed: {e}", "ERROR")
    return entry


def _apply_system_permanent(key, target, entry):
    """Allowlist-guarded permanent delete for system-only targets.

    These are files the Recycle Bin cannot meaningfully hold: a 16 GB
    MEMORY.DMP moved to C:\\$Recycle.Bin frees nothing at all, and the font
    cache is regenerated by Windows on the next boot. Everything a user
    could plausibly want back still goes through send_to_recycle_bin.
    """
    allowlist = deepclean_system_roots()
    paths = _collect_paths(key, target)

    safe_paths = []
    for p in paths:
        allowed, reason = check_deletable(p)
        if not allowed:
            entry["blocked"].append({"path": p, "reason": reason})
            continue
        if not is_deepclean_system_path(p, allowlist):
            entry["blocked"].append({
                "path": p, "reason": "outside the Deep Clean system-target allowlist"})
            continue
        safe_paths.append(p)

    planned = _bytes_of(safe_paths)
    log_activity(f"Deep Clean: {target['label']} — {len(safe_paths)} item(s), "
                 f"{format_bytes(planned)} before (permanent, system target)", "WARN")

    freed = count = 0
    for p in safe_paths:
        try:
            deleted, fsize = permanent_delete(p, allowlist)
            if deleted:
                freed += fsize
                count += 1
        except PermanentDeleteRefused as e:
            # A caller bug, not a per-file error — surface it loudly.
            entry["blocked"].append({"path": p, "reason": str(e)})
            log_activity(f"Deep Clean: {e}", "ERROR")
        except (OSError, PermissionError) as e:
            entry["errors"].append({"path": p, "error": str(e)})

    entry["bytes"] = freed
    entry["count"] = count
    entry["permanent"] = True
    entry["note"] = ("Deleted permanently — the Recycle Bin cannot usefully hold "
                     "these and Windows regenerates them.")
    log_activity(f"Deep Clean: {target['label']} — {format_bytes(freed)} reclaimed "
                 f"permanently from {count} item(s)", "SUCCESS")
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

        if mode == "command":
            r = _run_command(target)
            entry.update(bytes=r["bytes"], count=r["count"], note=r["note"],
                         output=r.get("output", ""))
            results.append(entry)
            total_freed += r["bytes"]
            continue

        # Stop dependent services first (Windows Update cache, font cache).
        services = target.get("services", [])
        for svc in services:
            ok_stop, out = _service("stop", svc)
            log_activity(f"Deep Clean: stopping {svc} — "
                         f"{'ok' if ok_stop else 'failed'}", "INFO" if ok_stop else "WARN")
            if ok_stop:
                stopped_services.append(svc)

        # Which deleter a target uses is a property of the TARGET, not of the
        # caller: system-only caches are permanently deleted behind an
        # allowlist, everything a user could want back is recycled.
        if mode == "system_permanent":
            _apply_system_permanent(key, target, entry)
            if entry["count"]:
                log_undo("permanent", f"Deep Clean: {target['label']}",
                         {"target": key, "count": entry["count"],
                          "bytes": entry["bytes"], "recoverable": False})
            total_freed += entry["bytes"]
            results.append(entry)
            for svc in services:
                ok_start, _ = _service("start", svc)
                log_activity(f"Deep Clean: restarting {svc} — "
                             f"{'ok' if ok_start else 'failed'}",
                             "INFO" if ok_start else "WARN")
                if svc in stopped_services:
                    stopped_services.remove(svc)
            continue

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
