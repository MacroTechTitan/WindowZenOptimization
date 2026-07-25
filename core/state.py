"""Shared mutable state and constants — single source of truth.

Every module that touches these globals imports them from here so that all
in-place mutations are visible everywhere. No module rebinds these names
(there are no `global x = ...` reassignments anywhere in the codebase), so
importing the names directly is safe.
"""
import os

# Repo root: parent of the core/ package. Used to anchor __file__-based paths
# so they resolve to the same absolute location they did when defined in the
# top-level app.py (which lived at the repo root).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Activity log buffer ───────────────────────────────────────
activity_log = []
LOG_MAX = 200
