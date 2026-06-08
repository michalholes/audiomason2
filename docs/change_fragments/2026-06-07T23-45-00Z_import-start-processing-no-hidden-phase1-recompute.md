2026-06-07T23:45:00Z SB-04 removes hidden PHASE 1 recompute from start_processing.

- Updated `plugins/import/engine_processing.py` so `start_processing_impl(...)`
  no longer reloads `discovery.json` and rebuilds `vars.phase1` before finalize.
- Removed the hidden authority refresh gate (`phase1_session_authority_applies`)
  and projection recompute call (`build_phase1_projection`).
- `start_processing` now uses only persisted session authority from
  `state.vars.phase1` when building `job_requests.json`.
