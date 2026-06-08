2026-06-07T23:58:00Z SB-04 detoxes import resume path to stay read-only.

- Updated `plugins/import/engine_session_create.py` in
  `resume_session_from_context(...)` to remove hidden PHASE 1 projection recompute.
- Removed the v3 legacy sync hook call (`sync_v3_legacy_state(...)`) from resume.
- Removed resume-path persistence (`engine.persist_state(...)`); resume now loads,
  validates, emits diagnostics, ensures minimum state fields, and applies in-memory
  fingerprint correction only when needed.
