#!/usr/bin/env bash
# Serve the Flask app on localhost for a visual check WITHOUT starting the
# background scheduler (app.py's __main__ starts it, and settings.json can
# schedule an automatic clean). Usage: bash scripts/serve-preview.sh [port]
set -euo pipefail

PORT="${1:-5055}"
echo "Serving preview (scheduler NOT started) on http://127.0.0.1:$PORT"
exec python -c "from app import app; app.run(host='127.0.0.1', port=$PORT, debug=False, use_reloader=False)"
