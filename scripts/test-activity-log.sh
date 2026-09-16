#!/usr/bin/env bash
# Exercise the activity-log wiring end to end through the Flask test client.
#
# The real deleters are patched out: this must never move a file to the
# Recycle Bin or create a System Restore point on the dev machine. What is
# under test is the LOGGING around those calls, not the calls themselves.
set -euo pipefail

echo "Testing activity log wiring (deleters patched, nothing is deleted)"
mkdir -p .scratch/activity-test

python - <<'PY'
import json, os, sys

os.makedirs(".scratch/activity-test", exist_ok=True)
probe = []
for i, size in enumerate((1024, 2048, 0)):
    p = os.path.abspath(f".scratch/activity-test/probe{i}.bin")
    with open(p, "wb") as f:
        f.write(b"x" * size)
    probe.append(p)

import app as app_module
from core import activity_log
import routes.duplicates as dup
import routes.largefiles as lf
import routes.zerolength as zl
import cleaners.deepclean as dc
from scanners.duplicates import duplicates_results
from scanners.largefiles import largefiles_results
from scanners.zerolength import zerolength_results

failures = []
def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{'' if cond else ' :: ' + detail}")
    if not cond:
        failures.append(label)

# ── Patches: no restore point, no recycle bin, nothing deleted ──
def fake_guard_batch(paths, without_rp=False, description=""):
    return True, {"restore_point": {"created": True, "message": "patched", "description": description}}

def make_fake_recycle(recycled):
    def fake(paths, allow_permanent=False, total_bytes=None):
        got = [p for p in paths if p in recycled]
        return {"recycled": got, "blocked": [], "errors": [],
                "bytes": total_bytes or 0, "permanent": False,
                "capacity": 0, "message": ""}
    return fake

for mod in (dup, lf, zl, dc):
    mod.guard_batch = fake_guard_batch

client = app_module.app.test_client()

# ── 1. Duplicate removal ───────────────────────────────────────
dup.send_to_recycle_bin = make_fake_recycle({probe[0], probe[1]})
duplicates_results.clear()
duplicates_results.update({"status": "complete", "groups": [{
    "hash": "abc123", "size": 1024,
    "copies": [{"path": probe[0], "name": "probe0.bin", "size": 1024},
               {"path": probe[1], "name": "probe1.bin", "size": 2048},
               {"path": probe[2], "name": "probe2.bin", "size": 0}]}]})
r = client.post("/api/duplicates/delete", json={
    "confirm": True, "files": [probe[0], probe[1]]})
body = r.get_json()
check("duplicates delete returns ok", r.status_code == 200 and body.get("status") == "ok", str(body))
check("duplicates response carries log_id", bool(body.get("log_id")), str(body))

latest = activity_log.latest()
check("duplicates logged as its own operation", latest["operation"] == "duplicates", str(latest))
items = latest["sections"][0]["items"]
check("duplicates logged 2 items", len(items) == 2, str(items))
check("duplicates logged per-item bytes", sorted(i["bytes"] for i in items) == [1024, 2048], str(items))
check("duplicates logged action", all(i["action"] == "recycled" for i in items), str(items))
check("duplicates totals exact", latest["totals"]["count"] == 2, str(latest["totals"]))
check("duplicates restore point recorded", latest["restore_point"]["created"] is True, str(latest["restore_point"]))

# ── 2. Large files ─────────────────────────────────────────────
lf.send_to_recycle_bin = make_fake_recycle({probe[1]})
largefiles_results.clear()
largefiles_results.update({"status": "complete", "files": [
    {"path": probe[1], "size": 2048, "size_fmt": "2.0 KB"}]})
r = client.post("/api/largefiles/delete", json={"confirm": True, "files": [probe[1]]})
check("largefiles delete ok", r.get_json().get("status") == "ok", str(r.get_json()))
latest = activity_log.latest()
check("largefiles logged", latest["operation"] == "large_files", str(latest["operation"]))
check("largefiles item bytes", latest["sections"][0]["items"][0]["bytes"] == 2048, str(latest["sections"]))

# ── 3. Zero-length ─────────────────────────────────────────────
zl.send_to_recycle_bin = make_fake_recycle({probe[2]})
zerolength_results.clear()
zerolength_results.update({"status": "complete", "found": 1, "shown": 1,
                           "files": [{"path": probe[2], "name": "probe2.bin"}]})
r = client.post("/api/zerolength/delete", json={"confirm": True, "files": [probe[2]]})
check("zerolength delete ok", r.get_json().get("status") == "ok", str(r.get_json()))
latest = activity_log.latest()
check("zerolength logged", latest["operation"] == "zero_length", str(latest["operation"]))

# ── 4. Deep Clean (a synthetic target over the scratch dir) ────
scratch = os.path.abspath(".scratch/activity-test")
dc.DEEPCLEAN_TARGETS["__test_target"] = {
    "label": "Test target", "description": "scratch", "risk": "low",
    "default_on": False, "mode": "contents",
    "paths_fn": lambda: [scratch],
}
existing = [os.path.join(scratch, n) for n in os.listdir(scratch)]
dc.send_to_recycle_bin = make_fake_recycle(set(existing))
state = dc.apply_deepclean(["__test_target"])
check("deep clean completed", state["status"] == "complete", str(state.get("status")))
latest = activity_log.latest()
check("deep clean logged", latest["operation"] == "deep_clean", str(latest["operation"]))
section = latest["sections"][0]
check("deep clean logged per-item paths", len(section["items"]) == len(existing),
      f'{len(section["items"])} vs {len(existing)}')
check("deep clean per-item bytes match on-disk sizes",
      sorted(i["bytes"] for i in section["items"]) == sorted(os.path.getsize(p) for p in existing),
      str(section["items"]))
check("deep clean state has no item list (status payload stays small)",
      "items" not in state["results"][0], str(state["results"][0].keys()))

# ── 5. Endpoints ───────────────────────────────────────────────
r = client.get("/api/activity-log/recent?limit=5")
data = r.get_json()
check("recent returns 4 operations", len(data["operations"]) == 4, str(len(data["operations"])))
check("recent omits item lists by default",
      all("items" not in s for op in data["operations"] for s in op["sections"]), "items present")
check("recent keeps item counts",
      any(s.get("item_count") for op in data["operations"] for s in op["sections"]), "no item_count")

r = client.get("/api/activity-log/recent?limit=5&items=1")
check("recent?items=1 includes items",
      any(s.get("items") for op in r.get_json()["operations"] for s in op["sections"]), "no items")

r = client.get("/api/activity-log/download?format=txt")
cd = r.headers.get("Content-Disposition", "")
check("txt download is an attachment", "attachment" in cd and cd.endswith('.txt"'), cd)
text = r.get_data(as_text=True)
check("txt names the operation", "Deep Clean" in text, text[:200])
check("txt lists an item path", scratch in text, text[:400])
check("txt reports the restore point", "Restore point:" in text, text[:200])

r = client.get("/api/activity-log/download?format=json")
cd = r.headers.get("Content-Disposition", "")
check("json download is an attachment", "attachment" in cd and cd.endswith('.json"'), cd)
parsed = json.loads(r.get_data(as_text=True))
check("json is the structured entry", parsed["operation"] == "deep_clean", str(parsed)[:200])

r = client.get("/api/activity-log/download?format=json&scope=all")
check("scope=all returns every operation", len(json.loads(r.get_data(as_text=True))) == 4, "")

r = client.get("/api/activity-log/download?format=xml")
check("bad format rejected", r.status_code == 400, str(r.status_code))

# ── 6. Truncation and blocked operations ───────────────────────
op = activity_log.start("deep_clean")
big = [{"path": f"C:\\x\\{i}", "bytes": 1, "action": "recycled"}
       for i in range(activity_log.MAX_ITEMS_PER_SECTION + 500)]
activity_log.add_section(op, "Huge", count=len(big), bytes_freed=len(big), items=big)
activity_log.finish(op)
check("items capped per section", len(op["sections"][0]["items"]) == activity_log.MAX_ITEMS_PER_SECTION,
      str(len(op["sections"][0]["items"])))
check("truncation counted", op["sections"][0]["items_truncated"] == 500,
      str(op["sections"][0]["items_truncated"]))
check("totals stay exact despite truncation", op["totals"]["count"] == len(big), str(op["totals"]))

# ── 7. A broken log must not break a deletion ──────────────────
# Recording is best-effort by design: the deleters keep working even if
# every logging call blows up.
original_now = activity_log._now
def boom(*a, **kw):
    raise RuntimeError("simulated logging failure")
activity_log._now = boom
try:
    duplicates_results.update({"status": "complete", "groups": [{
        "hash": "def456", "size": 1024,
        "copies": [{"path": probe[0], "name": "probe0.bin", "size": 1024},
                   {"path": probe[1], "name": "probe1.bin", "size": 2048}]}]})
    r = client.post("/api/duplicates/delete", json={"confirm": True, "files": [probe[0]]})
    body = r.get_json()
    check("delete still succeeds when logging raises",
          r.status_code == 200 and body.get("status") == "ok", str(body))
    check("response degrades to an empty log_id", body.get("log_id") == "", str(body.get("log_id")))
finally:
    activity_log._now = original_now

check("probe files untouched (nothing was really deleted)",
      all(os.path.exists(p) for p in probe), "a probe file went missing")

print()
if failures:
    print(f"{len(failures)} FAILED: {failures}")
    sys.exit(1)
print("all checks passed")
PY
