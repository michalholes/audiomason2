2026-06-08T00:15:00Z moved PHASE 1 runtime defaults out of session-create seed into explicit DSL authority.

- Reduced create-time PHASE 1 seed in `engine_session_create.py` to selection and catalog authority essentials.
- Added explicit `phase1_runtime_defaults_pipeline` library in v3 default JSON to set metadata/cover/policy defaults in DSL authority.
- Kept loading behavior fail-fast for authored v3 artifacts (no compatibility fallback migration path).
