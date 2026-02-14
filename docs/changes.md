## 2026-02-15T00:25:00+01:00

-   Issue 521: import: Ensure PHASE 0/2/processed_registry use a single canonical fingerprint key builder name and explicitly forbid full-file hashing for identity (stat-signature only).
-   spec: Add explicit implementation note for the shared fingerprint builder and bump specification version to 1.0.79.

## 2026-02-15T00:10:00+01:00

-   Issue 520: import_wizard API: Ensure processed_registry always returns keys: list[str] for UI compatibility, including when registry outputs are dict-shaped (defensive compatibility).
-   spec: Clarify processed_registry keys as authoritative field for UI loaders and bump specification version to 1.0.78.

## 2026-02-14T23:31:10+01:00

-   Issue 516: import_wizard API: Ensure preflight books include fingerprint and rename_preview when available (schema parity with index).
-   spec: Document preflight schema parity and bump specification version to 1.0.77.

## 2026-02-14T23:59:30+01:00

-   Issue 515: import_wizard UI: After successful Start (HTTP 200/202), auto-advance selection to the next actionable book (deterministic author/book order).
-   Issue 515: import_wizard UI: Do not auto-advance when Start is not successful (including 409 conflicts requiring user action).
-   spec: Clarify success-only auto-advance trigger and bump specification version to 1.0.76.

## 2026-02-14T23:59:00+01:00

-   Issue 514: import_wizard: Ensure PHASE 0 deep enrichment enables external lookup by default in the Web Import Wizard context (explicit flag), while remaining strictly best-effort and fail-safe.
-   import: Default external lookup to OFF outside the Web Import Wizard context.
-   spec: Clarify lookup defaults and bump specification version to 1.0.75.

## 2026-02-14T23:55:00+01:00

-   Issue 513: import: Ensure PHASE 2 import identity keys never rely on full-file hashing and remain unified with PHASE 0 preflight fingerprints and processed_registry keys (single stat-based builder).
-   spec: Clarify fingerprint key form `<algo>:<value>` and that `sha256` refers to the stat signature (not file contents); bump specification version to 1.0.74.

## 2026-02-14T23:40:00+01:00

-   Issue 512: import_wizard API: Make processed_registry response schema stable and UI-compatible by always returning keys: list[str] of processed fingerprint keys (items/count remain for compatibility).
-   spec: Document processed_registry response example and bump specification version to 1.0.73.

## 2026-02-14T21:20:00+00:00

-   Issue 511: import_wizard UI: After successful Start, auto-advance to next actionable book (deterministic author/book order), default ON with UI toggle.
-   spec: Document Import Wizard auto-advance rule and bump specification version to 1.0.72.

## 2026-02-14T21:10:57+00:00

-   Issue 510: import_wizard UI: Drive processed state strictly from fingerprint keys in processed_registry (gray-out, disable Start, Unmark).
-   Issue 510: import_wizard UI: Unmark refreshes processed state immediately.
-   spec: Clarify processed_registry UI matching (fingerprint-only) and bump specification version to 1.0.71.

## 2026-02-14T20:57:03+00:00

-   Issue 509: import_wizard: Enable best-effort external metadata lookup by default during PHASE 0 deep enrichment (fail-safe).
-   spec: Document lookup default and bump specification version to 1.0.70.

## 2026-02-14T22:00:00+01:00

-   Issue 508: import_wizard: Unify PHASE 0 and PHASE 2 identity fingerprint builder (stat-based) and remove full-file hashing from processing.

## 2026-02-14T21:30:00+01:00

-   Issue 507: import_wizard: Export book fingerprint identity key and rename_preview in the index API for the start screen.
-   spec: Document index books[] fingerprint/rename_preview fields and bump specification version to 1.0.69.

## 2026-02-14T18:10:00+01:00

-   web_interface: Add Import Wizard visual editor for PHASE 1 config (conflict policy + audio toggles) and persist per-mode defaults.
-   import: Add WizardDefaultsStore (JOBS root) to persist wizard defaults per wizard+mode and expose import_wizard defaults API endpoints.
-   spec: Document Import Wizard defaults memory and bump specification version to 1.0.68.
-   web_interface: Import Wizard processed_registry API returns keys for UI compatibility (legacy items/count retained).

## 2026-02-14T17:50:25+01:00

-   import_wizard: Add PHASE 1 Loudness/Bitrate step options with explicit confirmation and default bitrate 96 kbps.
-   import: Apply optional MP3 re-encode/loudnorm during PHASE 2 only when confirmed in PHASE 1.
-   spec: Document Issue 504 audio processing decisions and bump specification version to 1.0.66.

## 2026-02-14T17:20:00+01:00

-   import_cli: Extend interactive CLI import wizard to continue after book selection and collect PHASE 1 decisions before starting processing.
-   spec: Document CLI import wizard continuation and bump specification version to 1.0.64.
## 2026-02-14T14:52:20+01:00

-   web_interface: In debug mode, surface non-2xx HTTP responses as client-side debug records in the Logs UI, including response body (truncated) and callsite stack.
-   web_interface: In debug mode, show an immediate toast/modal for non-2xx HTTP responses so conflicts are not hidden in DevTools.
-   spec: Document debug-mode UI transparency for HTTP failures and bump specification version to 1.0.63.
## 2026-02-14T10:38:00+01:00

-   web_interface: Add debug-only "Debug JS" page that shows in-session JS errors (window.onerror + unhandledrejection) with filter/pause/clear/export.
-   web_interface: Ensure global JS error handlers never overwrite the UI.
-   spec: Document debug-only Debug JS page and bump specification version to 1.0.62.
## 2026-02-14T09:00:00+01:00

-   web_interface: Fix Import Wizard UI runtime error (fpKeyForBook undefined) by using a global fingerprint-key helper.
-   import: Enforce Issue 503 mode contract in engine (stage parallelism=2, inplace parallelism=1) regardless of caller-provided run state.
-   spec: Clarify stage parallelism is enforced and bump specification version to 1.0.65.
## 2026-02-14T00:05:00+01:00

-   import: Enforce stage vs inplace mode contract (resume + parallelism defaults).
-   import_wizard: Default conflict policy is ask, but block PHASE 2 job creation until conflicts are resolved.
-   import: Allow optional delete_source after successful staging, guarded by fingerprint identity.
-   spec: Document stage/in-place mode contract and bump specification version to 1.0.61.
## 2026-02-13T22:45:00+01:00

-   Issue 502: import_wizard: Add processed registry integration keyed by book fingerprint (algo:value).
-   Issue 502: import: Mark processed only on successful PHASE 2 completion and support unmark.
-   Issue 502: web_interface: Gray-out processed books, disable Start, and add Unmark action in Import Wizard UI.
## 2026-02-13T21:15:00+01:00

-   import_wizard: Deep enrichment now includes deterministic ID3 majority vote, APIC cover markers, stronger fingerprints, and deterministic rename preview ordering.
-   spec: Document deep enrichment requirements and bump specification version to 1.0.60.
## 2026-02-13T21:00:00+01:00

-   Issue 500: import_wizard: Add fast index endpoint for start screen (2-level scan, no deep reads) with deterministic root signature cache under file_io JOBS.
-   Issue 500: import_wizard: Add background deep enrichment runner (non-blocking) and enrichment_status endpoint.
-   Issue 500: web_interface: Update Import Wizard UI to use index + enrichment polling; keep start/import endpoints unchanged.
-   spec: Update Import Wizard UX/API contract to include index + enrichment_status.
## 2026-02-13T20:30:00+01:00

-   Issue 706: web_interface: Add LogBus SSE stream/tail endpoints and expose them in Logs UI (auto-scroll).
-   web_interface: Add Logs UI download action for the debug bundle endpoint.
-   spec: Document LogBus endpoints and Logs UI debug bundle action; bump specification version to 1.0.58.
## 2026-02-13T19:00:00+01:00

-   Issue 416: import: Support file-based book units (archives + single audio) in PHASE 2 jobs.
-   tests: Add unit coverage for import job file sources.
-   spec: Document file-based import units and bump specification version to 1.0.57.
## 2026-02-13T14:35:00+01:00

-   core.jobs: Emit operation.start/operation.end for jobs.update_state and jobs.fail with required summary fields.
-   spec: Document jobs.fail operation lifecycle events.
## 2026-02-13T14:05:00+01:00

-   file_io: Avoid duplicate file_io.resolve envelopes by not re-wrapping resolve_abs_path; add file_io.move operation (alias of rename) with start/end diagnostics and Core logger summaries.
-   spec: Document file_io.move operation and de-dup resolve envelope behavior.
## 2026-02-13T14:00:00+01:00

-   Issue 703: import: Emit contracted step-level runtime diagnostics envelopes for import wizard steps (preflight/scan/select_source/finish), including duration, safe aggregate summaries, and short tracebacks on failures.
-   spec: Document Import observability events and bump specification version to 1.0.55.
## 2026-02-13T12:30:00+01:00

-   syslog: Persist system log to logging.system_log_path under file_io STAGE root; enforce STAGE root validation and clear errors for invalid paths.
-   web_interface: Make /api/debug/bundle zip contents deterministic (stable internal paths; timestamps only in manifest.json).
-   web_interface: Add API snapshot files (status/roots/wizards/jobs) to debug bundle.
-   spec: Document syslog single source of truth and deterministic debug bundle contract; bump specification version to 1.0.54.
## 2026-02-13T12:20:00+01:00

-   core.jobs: Emit job lifecycle diagnostics events (create/get/list, state changes, failure reasons).
-   spec: Document mandatory job observability events; bump specification version to 1.0.54.
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
## 2026-02-12T18:00:00+01:00

-   file_io: Add tail_bytes (byte-level tail read) for UI
    diagnostics/system log viewers.
-   tests: Add unit coverage for tail_bytes.
-   spec: Document file_io tail_bytes operation.
## 2026-02-12T14:59:43+01:00

-   syslog: Add syslog LogBus persistence plugin (file_io CONFIG root) with CLI (status/cat/tail).
-   spec: Document syslog plugin configuration and behavior; bump specification version to 1.0.41.
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
