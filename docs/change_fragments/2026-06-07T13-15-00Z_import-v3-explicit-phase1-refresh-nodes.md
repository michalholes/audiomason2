Replaced default v3 no-op refresh checkpoints (`phase1_runtime_defaults`, `author_loop_check`,
`title_loop_check`, `cover_loop_check`) with explicit `call.invoke@1` authority calls to
`import.phase1_refresh` and deterministic writes back to `$.state.vars.phase1`.
