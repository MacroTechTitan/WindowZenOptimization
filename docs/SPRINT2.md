# Sprint 2: Split app.py Into Modules (No Behavior Change)

## Prime directive
This is a PURE REFACTOR. Zero behavior change. Every route, response
shape, side effect, and log line must be byte-identical to before.
The app must build and every endpoint must resolve exactly as it does
now. If any step risks changing behavior, STOP and leave that piece in
place rather than guess.

## Ground rules
- Work in small commits, one logical move per commit. After EVERY
  commit, run: python -c "import app" to confirm the app still imports
  with no errors, and python -m py_compile app.py on any touched file.
- Do NOT rename any Flask route, endpoint path, function that is
  referenced by name in templates/JS, or JSON response key.
- Do NOT change any string passed to log_activity.
- Preserve import-time side effects and execution order. Some globals
  (settings, analytics, scheduler) are initialized at import; keep that
  ordering intact.
- Use a Flask Blueprint per route module. Register all blueprints in
  app.py. Blueprint url_prefix must be empty so existing paths are
  unchanged (e.g. /api/apps/uninstall stays /api/apps/uninstall).
- If two modules need the same helper, put the helper in core/ and
  import it in both. Never duplicate a function body.
- Keep a single source of truth for shared state. Module-level mutable
  globals (deep_analysis_data, file_organizer_results, settings dict,
  analytics dict, the scheduler object) move to core/state.py and are
  imported everywhere they're used. Do NOT create second copies.

## Target structure
Create this layout under the repo root:

    app.py                 (thin entrypoint: create Flask app, import
                            + register blueprints, init scheduler, run)
    core/
      __init__.py
      state.py             (shared mutable globals + constants:
                            IS_WINDOWS, _WIN_NO_WINDOW, reg path tuples,
                            deep_analysis_data, file_organizer_results,
                            module-level caches)
      config.py            (load_settings, save_settings, settings dict,
                            load_analytics, save_analytics,
                            increment_analytics)
      registrations.py     (load_registrations, save_registrations)
      email.py             (get_resend_credentials, send_verification_email,
                            add_to_sendgrid_list)
      util.py              (format_bytes, get_dir_size, log_activity,
                            get_windows_username, get_local_version)
    scanners/
      __init__.py
      system.py            (get_system_metrics, get_ram_details,
                            get_ram_upgrade_recommendations,
                            get_motherboard_info, update_wellness)
      registry.py          (scan_registry, fix_registry)
      security.py          (run_security_scan)
      deep.py              (run_deep_analysis)
      apps.py              (_scan_apps_from_registry, _is_likely_bloat,
                            _build_uninstall_invocation,
                            _registry_has_display_name, _get_demo_apps,
                            _UNINSTALL_REG_PATHS)
      files.py             (run_file_organizer_scan)
    cleaners/
      __init__.py
      targets.py           (get_active_targets, scan_target, clean_target)
      runner.py            (run_system_scan, run_system_clean,
                            scheduled_auto_clean, setup_scheduler)
    routes/
      __init__.py
      pages.py             (landing, eula_page, loading_page, dashboard,
                            serve_version_json)
      metrics.py           (api_metrics, api_logs, api_debug_logs,
                            api_debug_logs_clear, get_counters,
                            count_download, api_updates_check)
      apps.py              (api_apps_list, api_apps_export,
                            api_apps_uninstall, api_apps_verify_uninstall,
                            api_apps_open_folder)
      clean.py             (all /api routes for scan/clean/targets)
      registry.py          (all /api routes for registry scan/fix)
      security.py          (all /api routes for security scan)
      deep.py              (all /api routes for deep analysis)
      files.py             (all /api routes for file organizer)
      registration.py      (all /api routes for email signup/verify)

## Method — do this in order, committing after each numbered step
1. Create core/ package. Move util.py helpers first (log_activity,
   format_bytes, get_dir_size, get_windows_username). Update app.py to
   import them. Commit. Verify import.
2. Move core/state.py globals and constants. Every file that used the
   global now imports from core.state. Commit. Verify.
3. Move core/config.py, core/registrations.py, core/email.py. Commit
   after each. Verify after each.
4. Create scanners/ package. Move one scanner module at a time
   (system, registry, security, deep, apps, files). Commit + verify
   after EACH module, not batched.
5. Create cleaners/ package. Move targets.py then runner.py. Commit +
   verify after each.
6. Create routes/ package. Convert route groups to Blueprints one
   module at a time. After each: register the blueprint in app.py,
   delete the old route from app.py, commit, and verify the specific
   endpoints still resolve with:
   python -c "import app; print([r.rule for r in app.app.url_map.iter_rules()])"
   Confirm the moved routes appear with identical rules.
7. Final app.py should be a thin entrypoint only. Confirm total line
   count dropped substantially and no route definitions remain in it.

## Verification gate before you call this done
- python -c "import app" succeeds with no error or warning.
- The url_map rule list is identical (same set of rules) to a baseline
  you capture BEFORE starting. Capture it first:
  python -c "import app; print(sorted(r.rule+' '+','.join(sorted(r.methods)) for r in app.app.url_map.iter_rules()))"
  Save that output. After the refactor, run it again and diff. It must
  match exactly.
- Grep templates/ and static/js/ for any url_for() or fetch() paths and
  confirm each still exists in the new url_map.
- Run cmd //c build_installer.bat and confirm the exe builds.

## Also in this sprint (small, do in their own commits)
- Remove the hardcoded banner text in templates/dashboard.html line ~99
  ("This is for display purposes only...").
- Remove the stale committed binary static/downloads/MTT_InfiniteOptimizer_Setup_v1.1.0.exe
  from git tracking (git rm --cached, add to .gitignore).

## What NOT to do
- Do not add features. Do not change response formats. Do not "improve"
  logic while moving it. Do not touch the Pro/private split yet — that
  is a later decision. Move code as-is.
