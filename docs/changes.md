# Changes

This file lists notable changes in AudioMason2, grouped by issue.


## Issue TBD

- 2026-02-09T00:00:00+01:00 Added new file I/O root `config` for configuration-owned filesystem data.
- 2026-02-09T00:00:00+01:00 Added configuration key: `file_io.roots.config_dir` (legacy fallback: `config_dir`).
- 2026-02-09T00:00:00+01:00 Updated specification version and change log per documentation gate requirements.




## Issue 994

- 2026-02-10T00:00:00+01:00 Resolver documentation: define configuration schema registry and deterministic key listing for admin tooling.
- 2026-02-10T00:00:00+01:00 Resolver documentation: allow unknown keys for compatibility (Variant B), surfaced as unknown/advanced with no type validation.
- 2026-02-10T00:00:00+01:00 Specification: add minimal type validation baseline for known keys.


## Issue 474

- 2026-02-10T09:43:25+01:00 ConfigService: add unset_value(key_path) to remove a user config key and prune empty parent mappings.
- 2026-02-10T09:43:25+01:00 ConfigService: validate logging.level on set_value with the same allowed values and normalization baseline as resolver.
- 2026-02-10T09:43:25+01:00 Documentation: update specification and change log for ConfigService unset support.




## Issue 831

- 2026-02-10T00:00:00+01:00 CLI: remove diagnostic print in web start; emit debug details only at DEBUG verbosity.
- 2026-02-10T00:00:00+01:00 Orchestrator: strict validation of `logging.level`; invalid values raise ConfigError (no silent fallback).
- 2026-02-09T00:00:00+01:00 Logging contract debt: orchestrator rejects invalid logging.level (no silent fallback).
- 2026-02-09T00:00:00+01:00 Logging contract debt: CLI/UI runtime diagnostics do not use print(); all diagnostics go through core logger.
- 2026-02-09T00:00:00+01:00 Logging contract debt: file_io archives do not use stdlib logging; use core logger.
- 2026-02-09T00:00:00+01:00 Updated specification version and change log per documentation gate requirements.

## Issue 343

- 2026-02-09T19:48:26+01:00 Phase 3: Plugins and daemon route runtime diagnostics through core logging (no print()).
- 2026-02-09T19:48:26+01:00 Phase 3: Job-context routing is guaranteed by the core log sink binding; standalone daemon remains usable.
- 2026-02-09T19:48:26+01:00 Updated specification version and change log per documentation gate requirements.


## Issue 340

- 2026-02-09T00:00:00+01:00 Phase 1: Core logging supports an optional global log sink.
- 2026-02-09T00:00:00+01:00 Phase 1: Orchestrator binds the log sink to JobService.append_log_line(job_id, line) for the lifetime of a running job.
- 2026-02-09T00:00:00+01:00 Phase 1: WizardEngine and EventBus route runtime diagnostics through core logging so they appear in job logs when a job is running.
- 2026-02-09T00:00:00+01:00 Updated specification version and change log per documentation gate requirements.

## Issue 344

- 2026-02-09T20:00:00+01:00 Issue 344: Fix unit test isolation by clearing pre-imported 'plugins' modules from sys.modules.
- 2026-02-09T10:49:39+01:00 Issue 344: Fix builtin plugin loading so 'plugins.*' imports work without PYTHONPATH by ensuring repo root is on sys.path when plugins/ is a package.
- 2026-02-09T10:49:39+01:00 Issue 344: Updated specification version and change log per documentation gate requirements.

## Issue 020

- 2026-02-09T02:03:50+01:00 Fixed mypy failure in file_io plugin cleanup by avoiding Optional Path capture inside async thread lambda.
- 2026-02-09T02:03:50+01:00 Updated specification version and change log per documentation gate requirements.

## Issue 554

- 2026-02-09T00:00:11+01:00 Added new file I/O root `wizards` for wizard-owned filesystem data.
- 2026-02-09T00:00:11+01:00 Added configuration key: `file_io.roots.wizards_dir` (legacy fallback: `wizards_dir`).
- 2026-02-09T00:00:11+01:00 Added specification versioning (start at 1.0.0; bump patch version on each change).
- 2026-02-09T00:00:11+01:00 Added mandatory change log rules: every patch must update `docs/changes.md` and each change entry must start with a patch creation timestamp.
- 2026-02-09T00:00:11+01:00 Added pytest coverage for the `wizards` root jail behavior.

## Issue 202

- 2026-02-09T01:09:46+01:00 WizardService now stores wizard definitions under the file_io `wizards` root in `definitions/<name>.yaml`.
- 2026-02-09T01:09:46+01:00 WizardEngine is async-only; removed nested asyncio.run during async plugin calls.
- 2026-02-09T01:09:46+01:00 Orchestrator and CLI now resolve wizard definitions via WizardService (file_io) instead of direct filesystem reads.
- 2026-02-09T01:09:46+01:00 Added test coverage for wizard execution via WizardService-backed storage.

## Issue 266

- 2026-02-09T00:00:00+01:00 Web `/api/stage` now always returns `dir` to keep unit tests stable independent of debug mode.

## Issue 400

- 2026-02-09T00:00:00+01:00 Resolver now provides resolve_logging_level() for `logging.level`.
- 2026-02-09T00:00:00+01:00 Strict validation and explicit default `normal`.
- 2026-02-09T00:00:00+01:00 Specification updated for canonical `logging.level` contract.

## Issue 402

- 2026-02-09T20:43:47+01:00 Resolver: Added immutable LoggingPolicy resolved in one place from canonical logging.level.
- 2026-02-09T20:43:47+01:00 Resolver: LoggingPolicy derives emission flags deterministically (quiet/normal/verbose/debug).
- 2026-02-09T20:43:47+01:00 Documentation: Updated specification to describe LoggingPolicy and alias rules.
