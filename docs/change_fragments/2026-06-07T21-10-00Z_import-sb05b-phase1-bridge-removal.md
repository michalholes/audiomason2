2026-06-07T21:10:00Z - Removed the import PHASE 1 bridge authority and completed the primitive-based refresh migration.

- Removed import bridge authority `import.phase1_refresh` from runtime wiring.
- Replaced v3 refresh call sites with explicit `flow.invoke` library pipeline using
  registry-declared `phase1.*` primitives for source, metadata, cover, policy, and
  compose projection steps.
- Deleted PHASE 1 helper bridge files and moved projection authority under
  `plugins/import/primitives/` modules.
- Removed import plugin callable manifest pointer and deleted
  `plugins/import/wizard_callable_manifest.json` because no import plugin wizard
  callable operations remain.
