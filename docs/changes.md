# Changes

This file lists notable changes in AudioMason2, grouped by issue.

## Issue 554

- 2026-02-09T00:00:11+01:00 Added new file I/O root `wizards` for wizard-owned filesystem data.
- 2026-02-09T00:00:11+01:00 Added configuration key: `file_io.roots.wizards_dir` (legacy fallback: `wizards_dir`).
- 2026-02-09T00:00:11+01:00 Added specification versioning (start at 1.0.0; bump patch version on each change).
- 2026-02-09T00:00:11+01:00 Added mandatory change log rules: every patch must update `docs/changes.md` and each change entry must start with a patch creation timestamp.
- 2026-02-09T00:00:11+01:00 Added pytest coverage for the `wizards` root jail behavior.
