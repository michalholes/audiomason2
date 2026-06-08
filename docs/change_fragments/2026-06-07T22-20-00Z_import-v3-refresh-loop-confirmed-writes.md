2026-06-07T22:20:00Z Import v3 refresh nodes now persist per-loop confirmed maps.

- Updated `plugins/import/dsl/default_wizard_v3_source.json` refresh checkpoints
  (`author_loop_check`, `title_loop_check`, `cover_loop_check`) to keep writing
  refreshed `$.state.vars.phase1`.
- Added explicit writes so each checkpoint also persists the corresponding
  confirmed loop authority map from `import.phase1_refresh` outputs:
  `author_loop_confirmed`, `title_loop_confirmed`, and `cover_loop_confirmed`.
- This removes the regression where per-item overrides could lose authority
  after refresh transitions in NEW v3 flow.
