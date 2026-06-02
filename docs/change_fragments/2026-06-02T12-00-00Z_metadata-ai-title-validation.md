2026-06-02T12:00:00Z
Added a new metadata_ai plugin that provides an AI-backed author/title-check
callable for Import Phase 1 and merged its optional author/title suggestions
into import metadata validation while preserving baseline validation behavior on
AI failure. Provider,
model, endpoint, and authentication key are taken from host config.yaml.
