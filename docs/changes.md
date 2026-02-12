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
