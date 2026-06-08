2026-06-08T01:10:00Z moved v3 first-step PHASE 1 authority bootstrap to JSON DSL over raw discovery items.

- Added explicit `phase1_bootstrap` runtime step that invokes `phase1_runtime_defaults_pipeline` before first prompt rendering.
- Reworked `phase1_runtime_defaults_pipeline` to derive `authors[]` and `books[]` from `vars.phase1.discovery_items` using deterministic `data.filter/map/group_by` and refresh nodes.
- Kept Python create path transport-only for v3 (`engine_session_create.py` now seeds `discovery_items` + minimal skeleton and runs DSL bootstrap).
- Enabled nested subflow library resolution in DSL runtime (`subflow_runtime.py`) so loop-in-library subflows stay declarative and do not fall back to Python projection logic.
