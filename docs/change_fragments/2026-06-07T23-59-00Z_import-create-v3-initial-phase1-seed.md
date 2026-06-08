2026-06-07T23:59:00Z Stabilize v3 create by seeding initial PHASE 1 authority.

- In the create-session path, pre-seed `state.vars.phase1` from discovery and
  current state before `initialize_state(...)` when PHASE 1 authority applies.
- Keep detox behavior in create: no post-initialize PHASE 1 recompute and no
  `sync_v3_legacy_state` call.
- Fixes the `missing vars.phase1` regression before the `select_authors` prompt
  for newly created v3 sessions.
