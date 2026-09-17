# First-Party Product Banner (free tier only)

Rotating single-line banner promoting MTT products. Shown to free users;
wired to hide for Pro once licensing exists (defaults to shown for now).

## Config
Create static/branding/promos.json — editable without code changes:
[
  {"text": "Life Hack Protocol - Health, Wealth, Longevity", "url": "https://lifehackprotocol.com"},
  {"text": "Deal Match AI - Agentic Deal Matching", "url": "https://dealmatch.macrotechtitan.com"},
  {"text": "Maximus Content AI - Build and scale viral content with Maximus", "url": "https://maximuscontent.macrotechtitan.com"}
]

## Behavior
- Single-line banner, one entry at a time, rotates every 8 seconds with a
  soft fade. Reuse/extend the existing top brand strip rather than adding
  a competing element.
- Links open in the system browser, NOT inside the app webview.
- Dismissible with an x for the session.
- Serve promos via GET /api/promos reading static/branding/promos.json.

## Pro gate (wired now, inert until licensing)
- Gate visibility on a single isPro flag/function returning whether the
  user is Pro. For now it returns false (banner shows for everyone). When
  licensing is added later, only that function changes and the banner
  auto-hides for Pro.
- Do NOT build licensing/entitlements now — just the flag and the gate.

## Guardrails
- First-party MTT products only. No third-party ad networks, no tracking.
- Non-invasive: no popups, never blocks the user's task.
- python -c "import app" stays clean; report url_map delta.

## Also
- Update docs/STATUS.md: branding IS now wired into the build (correct the
  stale cleanup item).

Commit as its own commit.
