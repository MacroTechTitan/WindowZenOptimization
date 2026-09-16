#!/usr/bin/env bash
# Build a scratch page that renders the REAL App.activitySummaryHtml against
# a real /api/activity-log/recent payload, for a visual check of the summary
# panel. The payload is inlined because a file:// page may not fetch().
# Usage: bash scripts/render-summary-harness.sh <port>
set -euo pipefail

PORT="${1:?usage: render-summary-harness.sh <port>}"
OUT=".scratch/summary-harness.html"
mkdir -p .scratch

echo "Building $OUT against http://127.0.0.1:$PORT"
curl -sf "http://127.0.0.1:$PORT/api/activity-log/recent?limit=1" -o .scratch/latest-op.json

python - "$PORT" "$OUT" <<'PY'
import json, sys

port, out = sys.argv[1], sys.argv[2]
payload = json.load(open(".scratch/latest-op.json"))
op = json.dumps(payload["operations"][0])
# Inlined, not linked: a file:// page cannot reliably pull either from the
# dev server, and the point is to render the REAL app.js function.
css = open("static/css/style.css", encoding="utf-8").read()
js = open("static/js/app.js", encoding="utf-8").read()
open(out, "w", encoding="utf-8").write(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>{css}</style>
<style>body {{ background:#0a0f1e; padding:16px; }}</style>
</head><body>
<div id="panel"></div>
<script>{js}</script>
<script>
  document.getElementById('panel').innerHTML = App.activitySummaryHtml({op});
</script>
</body></html>
""")
print(f"wrote {out}")
PY
