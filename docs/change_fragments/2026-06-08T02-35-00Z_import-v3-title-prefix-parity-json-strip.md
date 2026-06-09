2026-06-08T02:35:00Z restored title normalization parity in v3 JSON flow by stripping author prefixes from normalized book titles.

- Added JSON-only title prefix stripping nodes in PHASE 1 refresh/default pipelines to remove `<author> - ` and `<author>/` prefixes after normalization.
- Kept implementation fully declarative in `default_wizard_v3_source.json` with deterministic conditions and `data.set` writes via `$.op.outputs.value`.
- Updated prompt defaults to consume metadata authority values so `effective_title_item` suggests title-only values instead of author-prefixed labels.
