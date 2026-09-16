#!/usr/bin/env bash
# Screenshot a URL with headless Microsoft Edge into .scratch/.
# Usage: bash scripts/screenshot-page.sh <url> <output-name> [width,height]
# Env:   BUDGET_MS  virtual time the page runs before capture (default 4000)
set -euo pipefail

URL="${1:?usage: screenshot-page.sh <url> <output-name> [w,h]}"
NAME="${2:?usage: screenshot-page.sh <url> <output-name> [w,h]}"
SIZE="${3:-1280,800}"
EDGE="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
[ -x "$EDGE" ] || EDGE="/c/Program Files/Microsoft/Edge/Application/msedge.exe"
[ -x "$EDGE" ] || { echo "msedge.exe not found" >&2; exit 1; }

mkdir -p .scratch
OUT="$(cygpath -w "$PWD/.scratch/${NAME}.png")"
PROFILE="$(cygpath -w "$PWD/.scratch/edge-profile")"
echo "Screenshot $URL at $SIZE -> .scratch/${NAME}.png"
"$EDGE" --headless=new --disable-gpu --hide-scrollbars \
    --user-data-dir="$PROFILE" --window-size="$SIZE" \
    --virtual-time-budget="${BUDGET_MS:-4000}" --screenshot="$OUT" "$URL"
[ -f ".scratch/${NAME}.png" ] || { echo "no screenshot produced" >&2; exit 1; }
