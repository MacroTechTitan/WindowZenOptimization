#!/usr/bin/env bash
# Serve the app with a few synthetic activity-log entries already recorded,
# so the summary panel and the history list can be checked visually without
# deleting anything. Seeding writes to the in-memory log ONLY.
# Usage: bash scripts/serve-preview-seeded.sh [port]
set -euo pipefail

PORT="${1:-5060}"
echo "Serving seeded preview (scheduler NOT started) on http://127.0.0.1:$PORT"

python - "$PORT" <<'PY'
import sys
from app import app
from core import activity_log

op = activity_log.start("deep_clean")
activity_log.set_restore_point(op, {"created": True, "message": "System Restore point created."})
activity_log.add_section(
    op, "Windows Update cache", key="windows_update", count=1284,
    bytes_freed=3_221_225_472,
    items=[{"path": rf"C:\Windows\SoftwareDistribution\Download\file{i}.esd",
            "bytes": 2_500_000, "action": "recycled"} for i in range(1284)],
    skipped=[{"path": r"C:\Windows\System32\config", "reason": "Blocked — protected system location"}])
activity_log.add_section(
    op, "Memory dumps", key="memory_dumps", count=2, bytes_freed=16_000_000_000,
    items=[{"path": r"C:\Windows\MEMORY.DMP", "bytes": 16_000_000_000, "action": "permanent"}],
    permanent=True,
    note="Deleted permanently — the Recycle Bin cannot usefully hold these.")
activity_log.finish(op, message="Reclaimed 17.9 GB.")

op2 = activity_log.start("duplicates")
activity_log.set_restore_point(op2, {"created": False, "message": "System Protection is off for this drive."})
activity_log.add_section(
    op2, "Duplicate copies", count=3, bytes_freed=48_000_000,
    items=[{"path": rf"C:\Users\me\Pictures\holiday ({i}).jpg", "bytes": 16_000_000,
            "action": "recycled"} for i in range(3)])
activity_log.finish(op2, message="Removed 3 duplicate copy(ies) — 45.8 MB reclaimed.")

app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, use_reloader=False)
PY
