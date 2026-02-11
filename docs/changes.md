## 2026-02-11T20:08:27+01:00

- Issue 557: Normalized runtime diagnostic events to always publish the canonical envelope schema.
- Issue 557: Added mandatory diagnostics event set (jobs/contexts/boundaries/pipelines/wizards) including boundary.fail and duration_ms.
- Issue 557: Added pytest coverage for diagnostics envelope shape and minimal event sequences during pipeline execution.

## 2026-02-11T18:23:13+01:00

- core: Add EventBus.subscribe_all to support all-event subscribers.
- core: Add runtime diagnostics envelope and JSONL sink (config/env/cli enablement).
- CLI: Add --diagnostics/--no-diagnostics flags and always-register diagnostics sink.
- tests: Add coverage for diagnostics sink enablement, wrapping, idempotency, and subscribe_all.
- spec: Document runtime diagnostics envelope and JSONL sink; bump specification version to 1.0.35.

## 2026-02-11T17:41:11+01:00

- spec: Document web wizard job payload source_path injection; bump specification version to 1.0.34.

## 2026-02-11T15:00:00+01:00

- docs: Record core ruff-driven formatting fixes; enforce docs gate requirements.
- spec: Bump specification version to 1.0.33.

## 2026-02-11T09:45:00+01:00

- spec: Require both human-readable logging and structured diagnostic events project-wide.
- spec: Define authoritative diagnostic emission entry points and forbid alternate diagnostic buses.
- spec: Forbid swallowing failures across call boundaries; require start and terminal states.
- spec: Bump specification version to 1.0.32.

## 2026-02-11T02:00:00+01:00

- web UI: Add "Run wizard here" dashboard card with root browsing and wizard execution.
- web API: Add `/api/roots` allowlisted roots and path traversal rejection.
- core: Wizard jobs propagate target path into ProcessingContext.source; batch wizard jobs supported.
- spec: Document root browsing and wizard target propagation; bump specification version to 1.0.31.

## 2026-02-11T01:11:05+01:00

- CLI: Allow plugins to provide the `tui` command name by removing it from core reserved command names.
- spec: Document reserved core CLI command names and bump specification version to 1.0.30.

## 2026-02-11T00:03:29+01:00

- CLI: Preserve plugin discovery source ordering (builtin -> user -> system) for CLI command stubs.
- Tests: Add unit coverage ensuring the CLI does not globally re-sort discovered plugin directories across sources.
- spec: Clarify discovery source ordering preservation and bump specification version to 1.0.29.

## 2026-02-10T23:30:00+01:00

- Plugins: Add builtin sample plugin test_all_plugin exercising multiple interfaces and ICLICommands.
- Tests: Add integration coverage for test_all_plugin discovery, interface methods, and CLI command execution.
- spec: Document test_all_plugin as the canonical reference plugin for authors and tests.

## 2026-02-10T23:00:00+01:00

- CLI: Execute plugin-provided CLI commands lazily at invocation time (sync + async handlers).
- CLI: Track session-level plugin failures and mark affected plugin commands as [unavailable] in help output.
- Tests: Add integration tests for plugin command execution, failure isolation, and lazy import behavior.

## 2026-02-10T22:40:00+01:00

- CLI: Added manifest-only stub registry for plugin-provided CLI commands.
- CLI: Help output lists plugin commands with origin; deterministic ordering and collision checks.
- Plugins: Added `cli_commands` field to plugin.yaml for ICLICommands providers.
- Tests: Added unit coverage for plugin CLI command help and collision/shadowing failures.

## 2026-02-10T22:16:04+01:00

- core: plugin discovery enumerates plugin directories in deterministic lexicographic order by directory name.
- tests: add unit test asserting deterministic discovery ordering.
- spec: document discovery sorting key and bump specification version to 1.0.25.

## 2026-02-10T21:43:20+01:00

- cli/web: default `audiomason web` no longer emits debug messages; verbose output is info-level and gated by verbosity >= verbose.
- spec: LoggingPolicy verbose no longer implies debug emission; debug mode is required for debug emission.

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

## 2026-02-11T21:22:52+01:00

- Issue 558: Diagnostics enablement now warns on invalid AUDIOMASON_DIAGNOSTICS_ENABLED values and treats them as disabled.
- Issue 558: Specification updated with enablement examples and clarified unconditional sink install.
- Issue 558: Added unit tests for CLI/ENV/config enable priority.

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
