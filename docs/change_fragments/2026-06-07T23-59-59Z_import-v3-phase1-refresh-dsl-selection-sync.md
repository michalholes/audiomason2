2026-06-07T23:59:59Z phase1_refresh_pipeline now performs explicit DSL-side selection synchronization.

- Replaced the passthrough `phase1_refresh_pipeline` library with explicit `data.map`/`data.filter` nodes.
- Refresh now synchronizes selected author labels, filtered/selected book ids, selected book labels, selected source paths, and cover hint arrays in JSON authority.
- Added seed fields (`author_labels_by_id`, `book_meta.author_id`, `cover.item_modes`) to support deterministic refresh expressions without hidden Python bridge logic.
