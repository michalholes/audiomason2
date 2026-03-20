2026-03-19T10:37:00Z

- import UI now exposes the current v3 step projection through a read-only GET /import/ui/session/{session_id}/step/{step_id} route delegated to engine.get_step_definition
- import web prompt-select regression coverage now uses the real route boundary for runtime display items instead of a direct engine-only projection source
- the import web patch gate now loads the shared browser global declarations through the web wizard asset so the TypeScript gate sees the window globals used across the browser bundles
