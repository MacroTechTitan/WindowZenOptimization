#!/usr/bin/env bash
# Import the Flask app and write its sorted url_map (rule + methods) to a file.
# Usage: bash scripts/dump-routes.sh <output-name>   -> .scratch/<output-name>.txt
set -euo pipefail

NAME="${1:?usage: dump-routes.sh <output-name>}"
OUT=".scratch/${NAME}.txt"
mkdir -p .scratch

echo "Importing app and dumping url_map to $OUT"
python - "$OUT" <<'PY'
import sys
from app import app

rows = sorted(f"{r.rule} {','.join(sorted(r.methods))}" for r in app.url_map.iter_rules())
with open(sys.argv[1], "w") as f:
    f.write("\n".join(rows) + "\n")
print(f"{len(rows)} routes")
PY
