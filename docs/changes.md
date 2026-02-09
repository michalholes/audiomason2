# Changes

This file lists notable changes in AudioMason2, grouped by issue.

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
