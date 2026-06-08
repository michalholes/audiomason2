2026-06-07T23:58:00Z SB-04 detoxes hidden PHASE 1 recompute in create path.

- Removed `vars.phase1` seeding/recompute from `create_new_session_from_context(...)`.
- Removed create-path `sync_v3_legacy_state(...)` hook for v3 session initialization.
- Kept v3 initialization authority in `initialize_state(...)` and interpreter flow.
- Preserved artifact writes, diagnostics events, and session decision logging behavior.
