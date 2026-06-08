2026-06-08T01:25:00Z fixed v3 source selection coercion when prompt payload is numeric or list-shaped JSON.

- Updated `source.resolve_selection@1` in `plugins/import/primitives/data_v1.py` to accept deterministic selection forms beyond string expressions.
- Supported forms now include integer index, list of indices, and list of selected ids, while preserving stable discovery order.
- Removed implicit fallback to `all` for non-string payloads, which previously caused selecting one author to keep all authors/books.
