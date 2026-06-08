2026-06-08T02:05:00Z wired AI metadata validation into v3 import flow using JSON-only orchestration.

- Added explicit `call.invoke(metadata.ai_title_validate)` nodes after each primary metadata validation step.
- Added JSON-only `flow.invoke(metadata_ai_apply_pipeline)` stages to apply AI suggestions to PHASE 1 metadata authority fields without introducing new callable operation IDs.
- Extended PHASE 1 refresh/default pipelines to seed metadata author/title defaults from selected author/book labels before validation calls.
- Preserved strict anti-drift constraints: no import-side hidden business merge helper and no new custom primitive IDs.
