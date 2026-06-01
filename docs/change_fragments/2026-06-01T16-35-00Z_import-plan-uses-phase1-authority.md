# import plan uses phase1 authority

- Fixed `engine.compute_plan()` to pass current PHASE 1 session authority (`state.vars.phase1`) into planner computation.
- This prevents recomputation fallback from dropping archive-derived selections when discovery only exposes the bundle file.
- As a result, `select_books` submissions that include bundle-internal books no longer fail with `PlanSelectionError: invalid selected_book_ids`.
