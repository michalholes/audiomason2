## 2026-02-10T21:25:00+01:00

- cli/web: in quiet mode (-q web), print exactly 2 lines (Starting..., Finished...) and silence uvicorn logging.
- web_interface: map AM verbosity to uvicorn log_level/access_log (quiet mode fully silenced).

## 2026-02-10T21:15:00+01:00

- spec: define CLI plugin command extension contract (ICLICommands, determinism, failure isolation).
- spec: bump specification version to 1.0.21.

## 2026-02-10T21:10:29+01:00

- cli: ensure web shutdown prints a single `Finished (reason: ...)` line on normal exit, error, and Ctrl+C.
- cli: remove global KeyboardInterrupt handler that printed the literal line `Interrupted.`
- spec: document web shutdown output contract and bump specification version to 1.0.22.

## 2026-02-10T21:00:00+01:00

- web UI: render effective_snapshot entries and add per-key Reset actions.
- web_interface: return ASCII-only error text for config set/unset failures.
- Documentation: update specification and change log for Issue 500.

## 2026-02-10T20:58:21+01:00

- spec: extend CLI plugin command extension with normative ICLICommands contract, determinism, and UX rules.

## 2026-02-10T09:43:25+01:00

- ConfigService: add unset_value(key_path) to remove a user config key and prune empty parent mappings.
- ConfigService: validate logging.level on set_value with the same allowed values and normalization baseline as resolver.
- Documentation: update specification and change log for ConfigService unset support.

## 2026-02-10T00:00:00+01:00

- Logging contract debt: route CLI runtime diagnostics through core logger (no print()).
- Logging contract debt: route UI rich runtime status output through core logger (no console.print()).
- Documentation: bump specification version and update change log.
- CLI: apply resolved LoggingPolicy to core logger at process startup so -d enables debug output.
- Resolver documentation: define configuration schema registry and deterministic key listing for admin tooling.
- Resolver documentation: allow unknown keys for compatibility (Variant B), surfaced as unknown/advanced with no type validation.
- Specification: add minimal type validation baseline for known keys.
- web_interface: parse effective_snapshot YAML into an object for the UI.
- web_interface: add POST /api/am/config/unset to reset a user override (inherit).
- CLI: remove diagnostic print in web start; emit debug details only at DEBUG verbosity.
- Orchestrator: strict validation of `logging.level`; invalid values raise ConfigError (no silent fallback).
- CLI now sets canonical `logging.level` instead of alias `verbosity`.
- Web UI: Added Basic configuration editor (fixed common keys) and Advanced full-surface editor.
- Web UI: Advanced supports search, grouping by prefix, and 'overrides only' filter (source == user_config).
- Web UI: Value editing attempts JSON parse and falls back to string; Reset unsets (inherit).

## 2026-02-09T20:43:47+01:00

- Resolver: Added immutable LoggingPolicy resolved in one place from canonical logging.level.
- Resolver: LoggingPolicy derives emission flags deterministically (quiet/normal/verbose/debug).
- Documentation: Updated specification to describe LoggingPolicy and alias rules.

## 2026-02-09T20:00:00+01:00

- Issue 344: Fix unit test isolation by clearing pre-imported 'plugins' modules from sys.modules.

## 2026-02-09T19:48:26+01:00

- Phase 3: Plugins and daemon route runtime diagnostics through core logging (no print()).
- Phase 3: Job-context routing is guaranteed by the core log sink binding; standalone daemon remains usable.
- Updated specification version and change log per documentation gate requirements.

## 2026-02-09T10:49:39+01:00

- Issue 344: Fix builtin plugin loading so 'plugins.*' imports work without PYTHONPATH by ensuring repo root is on sys.path when plugins/ is a package.
- Issue 344: Updated specification version and change log per documentation gate requirements.

## 2026-02-09T02:03:50+01:00

- Fixed mypy failure in file_io plugin cleanup by avoiding Optional Path capture inside async thread lambda.
- Updated specification version and change log per documentation gate requirements.

## 2026-02-09T01:09:46+01:00

- WizardService now stores wizard definitions under the file_io `wizards` root in `definitions/<name>.yaml`.
- WizardEngine is async-only; removed nested asyncio.run during async plugin calls.
- Orchestrator and CLI now resolve wizard definitions via WizardService (file_io) instead of direct filesystem reads.
- Added test coverage for wizard execution via WizardService-backed storage.

## 2026-02-09T00:00:11+01:00

- Added new file I/O root `wizards` for wizard-owned filesystem data.
- Added configuration key: `file_io.roots.wizards_dir` (legacy fallback: `wizards_dir`).
- Added specification versioning (start at 1.0.0; bump patch version on each change).
- Added mandatory change log rules: every patch must update `docs/changes.md` and each change entry must start with a patch creation timestamp.
- Added pytest coverage for the `wizards` root jail behavior.

## 2026-02-09T00:00:00+01:00

- Added new file I/O root `config` for configuration-owned filesystem data.
- Added configuration key: `file_io.roots.config_dir` (legacy fallback: `config_dir`).
- Updated specification version and change log per documentation gate requirements.
- Logging contract debt: orchestrator rejects invalid logging.level (no silent fallback).
- Logging contract debt: CLI/UI runtime diagnostics do not use print(); all diagnostics go through core logger.
- Logging contract debt: file_io archives do not use stdlib logging; use core logger.
- Phase 1: Core logging supports an optional global log sink.
- Phase 1: Orchestrator binds the log sink to JobService.append_log_line(job_id, line) for the lifetime of a running job.
- Phase 1: WizardEngine and EventBus route runtime diagnostics through core logging so they appear in job logs when a job is running.
- Web `/api/stage` now always returns `dir` to keep unit tests stable independent of debug mode.
- Resolver now provides resolve_logging_level() for `logging.level`.
- Strict validation and explicit default `normal`.
- Specification updated for canonical `logging.level` contract.
