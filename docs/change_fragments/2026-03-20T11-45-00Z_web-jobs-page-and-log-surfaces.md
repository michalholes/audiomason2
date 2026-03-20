2026-03-20T11:45:00Z

Added a dedicated Jobs page in the web interface, moved the generic jobs browser off the
Logs page, and limited the generic Start action to pending non-import jobs.

Extended the EventBus and LogBus stream surfaces with scoped client-side copy, save, and
flush controls while preserving live streaming behavior.
Repaired web surface registration so TypeScript gate accepts the extracted Jobs and log stream assets without introducing untyped runtime declarations.
Normalized FileService open_read context management so the repair bundle clears the strict Ruff gate without changing runtime behavior.
