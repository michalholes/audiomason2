2026-06-07T23:15:00Z SB-04 removes hidden submit hooks for all v3 sessions.

- Simplified `plugins/import/engine_step_submit.py` v3 submit handling to keep
  only interpreter-authoritative `submit_current_step(...)` plus legacy
  read-only compatibility sync (`sync_v3_legacy_state(...)`).
- Removed capability-gated fallback branch (`if not has_explicit_refresh_nodes`)
  so hidden loop sync hooks are never used in active v3 submit flow.
- Removed hidden-hook helpers and legacy extra auto-pass execution
  (`run_automatic_steps(...)` re-run and phase1 authority refresh hooks).
