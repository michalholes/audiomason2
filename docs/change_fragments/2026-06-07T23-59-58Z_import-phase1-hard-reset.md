2026-06-07T23:59:58Z hard reset removes custom PHASE 1 primitive ids and helper projection files.

- Removed runtime registration and dispatch for `phase1.*` primitives.
- Replaced v3 `phase1_refresh_pipeline` library nodes with baseline primitives only.
- Removed create-path PHASE 1 helper preseed call and switched to lightweight in-state seed.
- Removed planner fallback recompute from projection helpers; planner now requires persisted session authority.
