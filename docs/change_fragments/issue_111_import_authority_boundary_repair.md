Issue 111 repairs the import plugin to remove absolute-path authority from session/runtime state, route cover and metadata behavior through import-owned boundary adapters, replace direct effective-model artifact reads with storage-bound access, and eliminate runtime/editor second-truth dependence on legacy catalog and flow artifacts while preserving existing import behavior.

Repair v2: gate-fix follow-up aligned the cover seam, metadata seam, diagnostics drift test, and monolith split without restoring removed authority paths.

Repair v6: split cover-path compatibility helpers out of file/materialization glue, narrowed cover boundary coupling, and fixed validator lint/import-order compliance on diagnostics tests.
- repair v7: tighten RootName typing in cover boundary to satisfy mypy overlay gate.
