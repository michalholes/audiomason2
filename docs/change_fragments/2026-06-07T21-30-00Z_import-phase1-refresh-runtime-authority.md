2026-06-07T21:30:00Z Import v3 refresh callable now rebuilds PHASE 1 authority from runtime context.

- Updated `ImportPlugin.phase1_refresh` to compute `result.phase1` via
  `build_phase1_projection(...)` when runtime source context is available.
- Refresh now resolves discovery deterministically from `state.source` and a
  runtime file service (injected `file_service` or rehydrated
  `vars.runtime.detached_runtime`).
- If runtime discovery cannot be resolved or refresh fails, the callable
  returns a conservative fallback using existing `state.vars.phase1` without
  raising.
- The callable response still includes `phase1`, `author_loop_confirmed`,
  `title_loop_confirmed`, and `cover_loop_confirmed`.
