# import phase1 authority switch with legacy fallback

- Updated import planning to read `selected_book_ids` from `state.vars.phase1.select_books.selected_ids` first, with legacy fallback to top-level `state.selected_book_ids`.
- Updated PHASE 1 source projection to read selected author/book ids from `state.vars.phase1.select_authors.selected_ids` and `state.vars.phase1.select_books.selected_ids` when valid for current discovery scope.
- Kept top-level `state.selected_author_ids` and `state.selected_book_ids` as compatibility fallback paths when authority selections are missing or invalid.
