Timestamp: 2026-03-23T00:00:00Z

Import PHASE 2 now persists per-action rename authority in canonical job_requests.json and the plugin runner consumes that authority before cover embedding, tag writing, and publish.

The import v3 regression coverage now guards that prerequisite-driven hidden steps stay explicit in the shared graph, auto-advance without extra user submits, and do not render as CLI Step prompts.
The repair overlay now resolves PHASE 2 source scope from persisted state or plan authority and falls back to deterministic non-split rename outputs when scanned audio files are absent.
