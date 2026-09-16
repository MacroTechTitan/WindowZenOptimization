#!/usr/bin/env bash
# Show routes added (+) or removed (-) between two dump-routes.sh outputs.
# Usage: bash scripts/diff-routes.sh <before-name> <after-name>
set -euo pipefail

BEFORE=".scratch/${1:?usage: diff-routes.sh <before> <after>}.txt"
AFTER=".scratch/${2:?usage: diff-routes.sh <before> <after>}.txt"

echo "url_map delta: $BEFORE -> $AFTER"
echo "before: $(wc -l < "$BEFORE") routes, after: $(wc -l < "$AFTER") routes"
# diff exits 1 when the files differ, which is the expected case here, so the
# exit status is deliberately not used to decide anything.
DELTA="$(diff "$BEFORE" "$AFTER" | grep '^[<>]' | sed 's/^</-/; s/^>/+/' || true)"
if [ -z "$DELTA" ]; then
    echo "(no change)"
else
    echo "$DELTA"
fi
