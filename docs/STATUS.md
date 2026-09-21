# WindowZen — Project Status (resume document)

Last updated: 2026-09-14. Read this first when picking the project back up
after a pause.

## Done

- **v1.1.0 published and live.** GitHub release with a signed installer:
  https://github.com/MacroTechTitan/WindowZenOptimization/releases/tag/v1.1.0
  - Asset: `MTT_InfiniteOptimizer_Setup_v1.1.0.exe`
  - Signed by **Macro Tech Titan Inc.** (SSL.com), RFC 3161 timestamped,
    verified with `signtool verify /pa`. Cert expires 2027-08-21; the
    timestamp keeps existing signatures valid past that date.
  - Both the inner app exe and the installer are signed.
  - The `v1.1.0` tag points at `0447043`. The three commits after it (the
    signing docs and the `build_installer.bat` signing steps) change no app
    code, so the tagged source matches the shipped binary.
- **Automated two-stage signing** is wired into `build_installer.bat`. It
  reads the `MTT_SIGN_USER` / `MTT_SIGN_PASS` / `MTT_SIGN_TOTP` env vars and
  skips signing (unsigned build) if any is unset. The recipe and credential
  gotchas are in `docs/SIGNING.md`.
- **Sprints 1-3 complete** (details in `docs/SPRINT1.md` … `docs/SPRINT3_UX.md`):
  - Uninstall fixed
  - Monolith split into `core` / `scanners` / `cleaners` / `routes`
  - Self-update removed
  - Features: deep clean, large files, duplicates, zero-length finder,
    AI storage report, internet optimizer
  - Safety layer (Recycle Bin + restore point) verified live

## To resume (in order)

1. **Wire the landing-page download button** to the v1.1.0 release asset
   URL, behind the email-capture gate. The release exists, but nothing
   drives traffic to it yet.
2. **Clean-VM test:** run the installer on a machine WITHOUT the dev setup
   (no Python) to confirm it works for real users. This has never been done;
   so far it has only been tested on the dev machine.
3. **Then start paid-tier work** (see below).

## Monetization model (decided)

- **Free tier:** all scan/clean/find features + the AI storage **report**.
  The report is the marketing hook: it shows the problem but doesn't fix it.
- **Paid:** $39 one-time perpetual + $19/yr feed. Paid features are
  automation + intelligence + curated feed:
  - Model-cache policy engine (prunes what the free report shows)
  - Memory-pressure daemon
  - Bloat-intelligence feed (recurring-revenue anchor)
  - Performance profiles with revert
  - Scheduling
  - Multi-machine license
- **Structure (Structure A):** PUBLIC repo = free tool; PRIVATE repo = Pro
  modules compiled into the signed release. **This module boundary is NOT
  built yet.** It is the first real paid-tier task.

## Phase 2 backlog

See `docs/BACKLOG_PHASE2.md`: cybersecurity module (v1.1 headline),
folder-level dedup, startup/task manager, etc.

## Known cleanup items

- **Stale self-update references in `templates/admin.html`.** It still
  points at the removed self-hosted update system
  (`windowzen.macrotechtitan.com/updates`, 11 occurrences: the update
  instructions panel, the download-URL placeholder, and the endpoint status
  list). It should point at GitHub Releases or be removed.
- ~~Branding assets not wired into the build~~ **Resolved: branding IS now
  wired in.** Assets live in `static/branding/` (`mtt-app.ico`,
  `mtt-installer.ico`, favicons, logos, splash) and ship via the static
  add-data. `build_installer.bat` passes `--icon static\branding\mtt-app.ico`
  to PyInstaller; `installer.nsi` sets `MUI_ICON` / `MUI_UNICON` to
  `mtt-installer.ico` and uses `mtt-app.ico` for the Start Menu and desktop
  shortcuts. The pages use the `static/branding` favicons.

## First-party promo banner

- The top brand strip rotates first-party MTT promos from
  `static/branding/promos.json` (served by `GET /api/promos`) every 8s, with
  a fade. It can be dismissed for the session, and links open in the system
  browser via `POST /api/promos/open`, which only accepts URLs from
  promos.json. Spec: `docs/BANNER_SPEC.md`.
- Pro gate: `App.isPro()` in `static/js/app.js` returns `false` until
  licensing exists. Pro users will see the plain brand line instead.
