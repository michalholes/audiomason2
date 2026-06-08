2026-06-07T23:59:57Z import v3 now uses list-first PHASE 1 authority and real generic IO/data primitives.

- Implemented resolver-friendly `io.list@1`, `io.stat@1`, and `io.read_meta@1` against FileService.
- Implemented deterministic `data.group_by@1` with `key_expr` and optional `value_expr`.
- Rewired v3 PHASE 1 refresh/default libraries to derive selection and relation state from `vars.phase1.authors[]` and `vars.phase1.books[]`.
- Reduced create-time PHASE 1 seeding to list-first source identity and selection seed data only.
- Updated authority consumers (`prompt_select_ui_projection.py`, `plan.py`, `job_requests.py`) to consume the new list-first shape without legacy shape fallbacks.
