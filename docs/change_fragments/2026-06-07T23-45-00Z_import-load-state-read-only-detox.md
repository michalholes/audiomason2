2026-06-07T23:45:00Z SB-04 detoxes hidden PHASE 1 recompute in load_state.

- Removed hidden `vars.phase1` recompute from `ImportWizardEngine._load_state(...)`.
- Removed `_load_state(...)` persistence side effect so load remains read-only.
- Kept state normalization for `conflicts.policy` based on `answers.conflict_policy.mode`.
- Preserved all other load-path validation and shape normalization behavior.
