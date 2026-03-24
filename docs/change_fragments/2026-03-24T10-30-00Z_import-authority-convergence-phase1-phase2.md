2026-03-24T10:30:00Z

- converge import phase1 and phase2 authority so canonical target paths and rename outputs come from persisted import session authority rather than source path or source filenames.
- add explicit skip_processed_books decision axis and per-book cover/metadata authority propagation inside plugins/import.
- tighten type-safe rename output normalization in job request assembly so mypy accepts the fallback outputs path without changing runtime behavior.
