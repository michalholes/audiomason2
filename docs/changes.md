## 2026-02-13T12:15:00+01:00

-   Issue 701: file_io: Emit operation.start/operation.end runtime diagnostics (diagnostics.jsonl) and Core logger summaries for file operations, including resolver decisions (resolved_path), counts, delete status, and short tracebacks on failures.

## 2026-02-13T12:00:00+01:00

-   Issue 333: web_interface: Emit operational logs via Core logger (LogBus) for request and handler operations; include traceback on failures.
-   Issue 333: web_interface: fs API uses FileService open_read/open_write (no read_bytes/write_bytes).
-   Issue 333: web_interface: logs API removes redundant UTF-8 encoding argument to satisfy linting.

## 2026-02-13T00:30:00+01:00

-   web_interface: Add "/api/debug/bundle" ZIP endpoint and Import page "Download debug info" action.
-   web_interface: Keep uvicorn access logs disabled (even in debug); rely on boundary diagnostics instead.
-   import_cli: Emit explicit preflight boundary diagnostics with duration and route DIAG envelopes through debug LogBus.
-   import: Emit per-job import job boundary diagnostics (duration_ms + traceback) from the engine service.
-   tests: Add integration coverage for import CLI diagnostics stdout and syslog persistence.

## 2026-02-13T00:15:00+01:00

-   web_interface: Import wizard preflight auto-load (debounced) and improved error detail rendering.
-   web_interface: Import wizard preflight includes synthetic "<book-only>" author group when author-less books exist.
-   web_interface: Fix import_wizard/start 500 by constructing PreflightResult correctly; add import_wizard/status endpoint.
-   tests: Add unit coverage for web import wizard preflight grouping and start validation.
-   spec: Document web import wizard auto-load, book-only group, status endpoint; bump specification version to 1.0.50.

## 2026-02-13T00:00:00+01:00

-   import_cli: Fix silent exits during interactive selection and support mixed
    inbox layouts (author/book, book-only, file units).
-   import_cli: In debug verbosity, print import-related diagnostics envelopes
    to stdout.
-   tests: Add unit coverage for mixed layout import CLI selection.
-   spec: Document import CLI UX stability rules; bump specification version to
    1.0.49.

## 2026-02-12T23:53:10+01:00

-   import: Extend PHASE 0 import preflight to support mixed inbox layouts
    (author/book directories, single-level book directories, and single-file
    units for archives/audio) without modifying the inbox.
-   import: Emit explicit skipped entries (with reason) and stable book_ref per
    discovered unit.
-   tests: Add unit coverage for mixed inbox discovery.
-   spec: Document mixed inbox preflight behavior and bump specification version
    to 1.0.48.

## 2026-02-12T22:42:28+01:00

-   cli: Add AM1-like `audiomason import` command implemented as a plugin-provided CLI command (import_cli).
-   tests: Add unit coverage for import CLI command registration and argument parsing.
-   spec: Document CLI import command and bump specification version to 1.0.47.

## 2026-02-12T22:30:00+01:00

-   web_interface: Add visual wizard configuration editor (drag reorder, enable toggle, templates, defaults memory) with server-side validation.
-   web_interface: Add /api/wizards/validate safe-save endpoint and strict model validation.
-   tests: Add unit coverage for wizard validation and backward-compatible parsing.
-   spec: Document wizard visual configuration editor and bump specification version to 1.0.46.

## 2026-02-12T21:52:44+01:00

-   web_interface: Add dedicated Import Wizard UI (author -> book guided flow) backed by import plugin services.
-   web_interface: Add import_wizard API endpoints (preflight/start/run_pending).
-   spec: Document web import wizard UX and bump specification version to 1.0.45.

## 2026-02-12T19:10:00+01:00

-   import: Add PHASE 2 import processing engine with persisted Jobs and CLI-safe service API.
-   tests: Add unit coverage for import engine stage determinism, inplace semantics, retry behavior, and service entry.

## 2026-02-12T18:45:00+01:00

-   import: Add import foundation infrastructure (run state store, deterministic preflight, processed registry) under plugins/import/.
-   tests: Add unit coverage for import foundation persistence and determinism.
-   spec: Document import wizard foundation and bump specification version to 1.0.43.

## 2026-02-12T18:32:21+01:00

-   diagnostics_console: Fix diag --help/-h handling; add wait_status_repeat and --mode events|log|both.
-   tests: Add deterministic unit tests for diagnostics_console CLI.
-   spec: Bump specification version to 1.0.42; document diagnostics console modes.

## 2026-02-12T14:59:43+01:00

-   syslog: Add syslog LogBus persistence plugin (file_io CONFIG root) with CLI (status/cat/tail).
-   spec: Document syslog plugin configuration and behavior; bump specification version to 1.0.41.

## 2026-02-12T18:00:00+01:00

-   file_io: Add tail_bytes (byte-level tail read) for UI
    diagnostics/system log viewers.
-   tests: Add unit coverage for tail_bytes.
-   spec: Document file_io tail_bytes operation.

## 2026-02-12T09:43:00+01:00

-   core: Add LogBus (publish/subscribe) for log streaming, mirroring the EventBus model.
-   core: Remove file-backed system log backend; core no longer writes any log files.
-   docs: Update system log specification: persistence is performed by external LogBus subscribers using File I/O roots.
-   file_io: Add open_append (append-only upload streaming) for
    byte-level log appends.
-   tests: Add unit coverage for open_append stream and
    FileService.open_append.
-   spec: Document file_io open_append and bump specification version to
    1.0.39.

## 2026-02-12T08:30:00+01:00

-   Add config keys logging.system_log_enabled and
    logging.system_log_path for human-readable system log file routing.
-   Apply system log file configuration in CLI bootstrap (fail-safe;
    never crash on file errors).
-   Add resolver unit tests for system log keys.
-   spec: Document system log keys and bump specification version to
    1.0.38.

## 2026-02-11T20:45:00+01:00

-   plugins: Add diagnostics_console plugin providing `audiomason diag`
    (tail/status/on/off) for runtime diagnostics JSONL sink.
-   tests: Add unit coverage for diag command help registration and
    basic behavior.
-   spec: Document diagnostics console command; bump specification
    version to 1.0.37.

## 2026-02-11T20:08:27+01:00

-   Normalized runtime diagnostic events to always publish the canonical
    envelope schema.
-   Added mandatory diagnostics event set
    (jobs/contexts/boundaries/pipelines/wizards) including boundary.fail
    and duration_ms.
-   Added pytest coverage for diagnostics envelope shape and minimal
    event sequences during pipeline execution.

## 2026-02-11T18:23:13+01:00

-   core: Add EventBus.subscribe_all to support all-event subscribers.
-   core: Add runtime diagnostics envelope and JSONL sink
    (config/env/cli enablement).
-   CLI: Add --diagnostics/--no-diagnostics flags and always-register
    diagnostics sink.
-   tests: Add coverage for diagnostics sink enablement, wrapping,
    idempotency, and subscribe_all.
-   spec: Document runtime diagnostics envelope and JSONL sink; bump
    specification version to 1.0.35.

## 2026-02-11T17:41:11+01:00

-   spec: Document web wizard job payload source_path injection; bump
    specification version to 1.0.34.

## 2026-02-11T15:00:00+01:00

-   docs: Record core ruff-driven formatting fixes; enforce docs gate
    requirements.
-   spec: Bump specification version to 1.0.33.
-   web_interface: Stream and tail diagnostics/events via Core EventBus tap; emit API route boundary diagnostics; emit import action events (preflight/queue/run/pause/resume).
