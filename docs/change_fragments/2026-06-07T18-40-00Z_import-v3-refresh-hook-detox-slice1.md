# import v3 submit-path refresh hook detox (sb-04 slice 1)

- Added NEW v3 refresh-workflow detection in submit handling by requiring
  `phase1_runtime_defaults`, `author_loop_check`, `title_loop_check`, and
  `cover_loop_check` to be `call.invoke` nodes with
  `inputs.operation_id = import.phase1_refresh`.
- For detected NEW workflows, submit now keeps prompt payload validation and
  interpreter submit execution, but skips legacy hidden refresh hooks and the
  extra second `run_automatic_steps(...)` pass.
- Legacy compatibility remains unchanged: if explicit refresh nodes are absent,
  engine-side loop sync hooks, phase1 authority refresh, and second auto-pass
  still run exactly as before.
