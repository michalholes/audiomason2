2026-06-07T23:59:40Z SB-05 stabilizes rerun/resume legacy selection projection.

- Added `_sync_legacy_selection_from_phase1(state)` in
  `plugins/import/engine_session_create.py`.
- The helper projects `vars.phase1.select_authors.selected_ids` and
  `vars.phase1.select_books.selected_ids` into top-level
  `selected_author_ids` and `selected_book_ids` only when values are valid
  `list[str]`.
- No hidden recompute was introduced; this is a read-only compatibility
  projection applied in create and resume paths.
