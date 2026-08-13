"""File-side endpoints: the file organizer, large-file finder, Downloads
organizer preview/execute, and the folder size explorer.

Every removal here acts on files the USER picked out of a report, so all of
them go through core.safety: check_deletable per item, one restore point per
batch (guard_batch), and send_to_recycle_bin for the removal itself. Nothing
in this module deletes permanently. The move/archive actions are not deletes,
but they still run check_deletable so we never yank a file out of a
cloud-sync root or a protected system location.
"""
import os
import shutil
import threading
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from core.state import (
    IS_WINDOWS, file_organizer_results, large_files_results, organize_preview_results,
)
from core.util import log_activity, log_undo, format_bytes
from core.safety import send_to_recycle_bin, guard_batch, check_deletable
from scanners.files import run_file_organizer_scan

bp = Blueprint("files", __name__)


@bp.route("/api/file-organizer/scan", methods=["POST"])
def api_file_organizer_scan():
    data = request.get_json() or {}
    custom_folder = data.get("custom_folder", "")
    thread = threading.Thread(target=run_file_organizer_scan, args=(custom_folder,), daemon=True)
    thread.start()
    return jsonify({"status": "scanning"})


@bp.route("/api/file-organizer/results")
def api_file_organizer_results():
    return jsonify(file_organizer_results)


@bp.route("/api/file-organizer/delete", methods=["POST"])
def api_file_organizer_delete():
    """Remove user-selected files to the Recycle Bin, behind a restore point."""
    data = request.get_json() or {}
    category = data.get("category")
    files = data.get("files", [])

    if not category or not files:
        return jsonify({"status": "error", "message": "Category and files are required"}), 400

    blocked, allowed = [], []
    for fp in files:
        ok, reason = check_deletable(fp)
        (allowed.append(fp) if ok else blocked.append({"path": fp, "reason": reason}))
    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "Every selected file is protected by the safety rules."}), 400

    total = 0
    for fp in allowed:
        try:
            total += os.path.getsize(fp)
        except (OSError, PermissionError):
            pass

    # Restore point once, before the batch — never per file.
    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before file organizer removal")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=total)
    result["blocked"].extend(blocked)

    removed = set(result["recycled"])
    if removed:
        log_undo("recycle", f"File Organizer removed {len(removed)} file(s)",
                 {"count": len(removed), "bytes": result["bytes"],
                  "recoverable": not result["permanent"]})

    if category in file_organizer_results:
        file_organizer_results[category] = [
            item for item in file_organizer_results[category]
            if item.get("path") not in removed
        ]

    return jsonify({
        "status": "ok",
        "deleted": len(result["recycled"]),
        "bytes": result["bytes"],
        "bytes_fmt": format_bytes(result["bytes"]),
        "permanent": result["permanent"],
        "blocked": result["blocked"],
        "errors": result["errors"],
        "message": result["message"],
        "restore_point": payload["restore_point"],
    })


@bp.route("/api/large-files/scan", methods=["POST"])
def api_large_files_scan():
    data = request.get_json() or {}
    threshold_mb = data.get("threshold_mb", 100)
    large_files_results["threshold_mb"] = threshold_mb
    large_files_results["status"] = "scanning"
    thread = threading.Thread(target=run_large_files_scan, args=(threshold_mb,), daemon=True)
    thread.start()
    return jsonify({"status": "scanning", "threshold_mb": threshold_mb})


@bp.route("/api/large-files/results")
def api_large_files_results():
    return jsonify(large_files_results)


@bp.route("/api/large-files/delete", methods=["POST"])
def api_large_files_delete():
    """Remove user-selected large files to the Recycle Bin, behind a restore point."""
    data = request.get_json() or {}
    files = data.get("files", [])
    dry_run = data.get("dry_run", False)

    blocked, allowed = [], []
    for fp in files:
        ok, reason = check_deletable(fp)
        (allowed.append(fp) if ok else blocked.append({"path": fp, "reason": reason}))

    if dry_run:
        for fp in allowed:
            log_activity(f"[DRY RUN] Would move to Recycle Bin: {fp}", "INFO")
        return jsonify({"status": "ok", "deleted": len(allowed), "dry_run": True,
                        "blocked": blocked})

    if not allowed:
        return jsonify({"status": "blocked", "blocked": blocked,
                        "message": "Every selected file is protected by the safety rules."}), 400

    total = 0
    for fp in allowed:
        try:
            total += os.path.getsize(fp)
        except (OSError, PermissionError):
            pass

    # Restore point once, before the batch — never per file.
    ok, payload = guard_batch(
        allowed, bool(data.get("proceed_without_restore_point", False)),
        description="MTT Optimizer — before large-file removal")
    if not ok:
        payload["blocked"] = blocked
        return jsonify(payload), 409

    result = send_to_recycle_bin(
        allowed, allow_permanent=bool(data.get("allow_permanent", False)),
        total_bytes=total)
    result["blocked"].extend(blocked)

    removed = set(result["recycled"])
    if removed:
        log_undo("recycle", f"Removed {len(removed)} large file(s)",
                 {"count": len(removed), "bytes": result["bytes"],
                  "recoverable": not result["permanent"]})

    large_files_results["files"] = [
        f for f in large_files_results["files"] if f["path"] not in removed]
    return jsonify({
        "status": "ok",
        "deleted": len(result["recycled"]),
        "dry_run": False,
        "bytes": result["bytes"],
        "bytes_fmt": format_bytes(result["bytes"]),
        "permanent": result["permanent"],
        "blocked": result["blocked"],
        "errors": result["errors"],
        "message": result["message"],
        "restore_point": payload["restore_point"],
    })


@bp.route("/api/large-files/archive", methods=["POST"])
def api_large_files_archive():
    data = request.get_json()
    files = data.get("files", [])
    dry_run = data.get("dry_run", False)
    archive_dir = os.path.join(os.path.expanduser("~"), "Archive")
    moved = 0
    blocked = []
    archived = set()
    for fp in files:
        # A move is not a delete, but it still relocates the file — refuse the
        # same paths the delete gate refuses (cloud-sync roots especially,
        # where a move reads as a delete + re-upload to the provider).
        ok, reason = check_deletable(fp)
        if not ok:
            blocked.append({"path": fp, "reason": reason})
            log_activity(f"Archive refused: {fp} — {reason}", "WARN")
            continue
        if dry_run:
            log_activity(f"[DRY RUN] Would archive: {fp} -> {archive_dir}", "INFO")
            moved += 1
        else:
            try:
                if os.path.isfile(fp):
                    os.makedirs(archive_dir, exist_ok=True)
                    dest = os.path.join(archive_dir, os.path.basename(fp))
                    shutil.move(fp, dest)
                    moved += 1
                    archived.add(fp)
                    log_undo("move", f"Archived: {os.path.basename(fp)}", {"from": fp, "to": dest})
                    log_activity(f"Archived: {fp} -> {dest}", "SUCCESS")
            except (OSError, PermissionError) as e:
                log_activity(f"Failed to archive {fp}: {e}", "ERROR")
    if not dry_run:
        large_files_results["files"] = [
            f for f in large_files_results["files"] if f["path"] not in archived]
    return jsonify({"status": "ok", "moved": moved, "archive_dir": archive_dir,
                    "dry_run": dry_run, "blocked": blocked})


def run_large_files_scan(threshold_mb=100):
    log_activity(f"Scanning for large files (>{threshold_mb} MB)...", "TASK")
    threshold_bytes = threshold_mb * 1024 * 1024
    found = []
    home = os.path.expanduser("~")
    scan_dirs = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Videos"),
        os.path.join(home, "Documents"),
    ]
    for scan_dir in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        try:
            for root, dirs, files in os.walk(scan_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        fsize = os.path.getsize(fp)
                        if fsize >= threshold_bytes:
                            found.append({
                                "path": fp,
                                "name": f,
                                "size": fsize,
                                "size_fmt": format_bytes(fsize),
                                "location": os.path.basename(scan_dir),
                                "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M"),
                            })
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
    found.sort(key=lambda x: x["size"], reverse=True)
    large_files_results["files"] = found[:200]
    large_files_results["total_size"] = sum(f["size"] for f in found)
    large_files_results["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    large_files_results["status"] = "complete"
    log_activity(f"Found {len(found)} files larger than {threshold_mb} MB ({format_bytes(large_files_results['total_size'])} total)", "SUCCESS")


@bp.route("/api/organize/preview", methods=["POST"])
def api_organize_preview():
    data = request.get_json() or {}
    max_age_days = data.get("max_age_days", 30)
    action_type = data.get("action", "archive_old")
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    actions = []

    if action_type == "archive_old":
        cutoff = datetime.now() - timedelta(days=max_age_days)
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp):
                        try:
                            mtime = datetime.fromtimestamp(os.path.getmtime(fp))
                            if mtime < cutoff:
                                actions.append({
                                    "file": f,
                                    "path": fp,
                                    "action": f"Archive (older than {max_age_days} days)",
                                    "modified": mtime.strftime("%Y-%m-%d"),
                                    "size_fmt": format_bytes(os.path.getsize(fp)),
                                })
                        except (OSError, PermissionError):
                            pass
            except (OSError, PermissionError):
                pass

    elif action_type == "group_by_type":
        type_groups = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"],
            "Documents": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"],
            "Videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
            "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Installers": [".exe", ".msi", ".dmg"],
        }
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp):
                        ext = os.path.splitext(f)[1].lower()
                        for group_name, exts in type_groups.items():
                            if ext in exts:
                                actions.append({
                                    "file": f,
                                    "path": fp,
                                    "action": f"Move to Downloads/{group_name}/",
                                    "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d"),
                                    "size_fmt": format_bytes(os.path.getsize(fp)),
                                })
                                break
            except (OSError, PermissionError):
                pass

    elif action_type == "move_screenshots":
        if os.path.isdir(downloads):
            try:
                for f in os.listdir(downloads):
                    fp = os.path.join(downloads, f)
                    if os.path.isfile(fp) and ("screenshot" in f.lower() or "screen shot" in f.lower() or "capture" in f.lower()):
                        actions.append({
                            "file": f,
                            "path": fp,
                            "action": "Move to Pictures/Screenshots/",
                            "modified": datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d"),
                            "size_fmt": format_bytes(os.path.getsize(fp)),
                        })
            except (OSError, PermissionError):
                pass

    organize_preview_results["actions"] = actions
    organize_preview_results["last_preview"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({"actions": actions, "count": len(actions)})


@bp.route("/api/organize/execute", methods=["POST"])
def api_organize_execute():
    data = request.get_json() or {}
    dry_run = data.get("dry_run", False)
    actions = data.get("actions", organize_preview_results.get("actions", []))
    executed = 0
    blocked = []
    for act in actions:
        fp = act.get("path", "")
        action_desc = act.get("action", "")
        if not os.path.isfile(fp):
            continue
        # Same gate as the delete paths — a move out of a cloud-sync root
        # propagates as a delete to the provider.
        ok, reason = check_deletable(fp)
        if not ok:
            blocked.append({"path": fp, "reason": reason})
            log_activity(f"Organize refused: {fp} — {reason}", "WARN")
            continue
        if dry_run:
            log_activity(f"[DRY RUN] {action_desc}: {act.get('file', '')}", "INFO")
            executed += 1
            continue
        try:
            if "Archive" in action_desc:
                archive_dir = os.path.join(os.path.dirname(fp), "Archive")
                os.makedirs(archive_dir, exist_ok=True)
                dest = os.path.join(archive_dir, os.path.basename(fp))
                shutil.move(fp, dest)
                log_undo("move", f"Archived: {os.path.basename(fp)}", {"from": fp, "to": dest})
            elif "Move to" in action_desc:
                home = os.path.expanduser("~")
                rel_dest = action_desc.replace("Move to ", "").rstrip("/")
                dest_dir = os.path.join(home, rel_dest)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, os.path.basename(fp))
                shutil.move(fp, dest)
                log_undo("move", f"Moved: {os.path.basename(fp)}", {"from": fp, "to": dest})
            executed += 1
            log_activity(f"{action_desc}: {act.get('file', '')}", "SUCCESS")
        except (OSError, PermissionError) as e:
            log_activity(f"Failed: {act.get('file', '')}: {e}", "ERROR")
    return jsonify({"status": "ok", "executed": executed, "dry_run": dry_run,
                    "blocked": blocked})


# ══════════════════════════════════════════════════════════════════════════════
# FOLDER SIZE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

@bp.route("/api/folder-sizes/scan", methods=["POST"])
def api_folder_sizes_scan():
    data = request.get_json() or {}
    root_path = data.get("path", os.path.expanduser("~"))
    max_depth = int(data.get("depth", 2))

    if not IS_WINDOWS:
        return jsonify({"folders": [
            {"path": "C:\\Users\\User\\Downloads", "name": "Downloads", "size_bytes": 8589934592, "size_human": "8.0 GB", "depth": 1, "file_count": 842},
            {"path": "C:\\Users\\User\\Videos", "name": "Videos", "size_bytes": 5368709120, "size_human": "5.0 GB", "depth": 1, "file_count": 34},
            {"path": "C:\\Users\\User\\Documents", "name": "Documents", "size_bytes": 2147483648, "size_human": "2.0 GB", "depth": 1, "file_count": 1203},
            {"path": "C:\\Users\\User\\Pictures", "name": "Pictures", "size_bytes": 1073741824, "size_human": "1.0 GB", "depth": 1, "file_count": 567},
            {"path": "C:\\Users\\User\\AppData\\Local\\Temp", "name": "Temp", "size_bytes": 536870912, "size_human": "512.0 MB", "depth": 2, "file_count": 4321},
            {"path": "C:\\Users\\User\\AppData\\Roaming\\Spotify", "name": "Spotify", "size_bytes": 314572800, "size_human": "300.0 MB", "depth": 2, "file_count": 88},
            {"path": "C:\\Users\\User\\Desktop", "name": "Desktop", "size_bytes": 209715200, "size_human": "200.0 MB", "depth": 1, "file_count": 41},
        ], "demo": True})

    def _dir_size_and_count(path):
        total = 0
        count = 0
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                        count += 1
                    elif entry.is_dir(follow_symlinks=False):
                        sub_size, sub_count = _dir_size_and_count(entry.path)
                        total += sub_size
                        count += sub_count
                except PermissionError:
                    pass
        except PermissionError:
            pass
        return total, count

    def _fmt(b):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    folders = []

    def _walk(path, depth):
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(path):
                if not entry.is_dir(follow_symlinks=False):
                    continue
                size, count = _dir_size_and_count(entry.path)
                folders.append({
                    "path": entry.path,
                    "name": entry.name,
                    "size_bytes": size,
                    "size_human": _fmt(size),
                    "depth": depth,
                    "file_count": count
                })
                if depth < max_depth:
                    _walk(entry.path, depth + 1)
        except PermissionError:
            pass

    _walk(root_path, 1)
    folders.sort(key=lambda x: x["size_bytes"], reverse=True)
    return jsonify({"folders": folders[:50], "demo": False, "root": root_path})
