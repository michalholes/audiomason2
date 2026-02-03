# badguys tests

This folder contains patch scripts used by `badguys/run_suite.py`.

Conventions:

- Patch scripts must be deterministic.
- Patch scripts should only touch files under `badguys/tmp/` (unless a test
  explicitly targets a different path/policy).
- Patch scripts are copied to `patches/badguys_suite/` during execution (for kind=patch).
- Scripts used for preflight rejection tests (kind=reject) are executed in-place.

Subfolders:

- noop/
  No-op behavior and `-n/--allow-no-op`.

- untouched/
  Declared-but-untouched behavior and `-t/--allow-untouched-files`.

- undeclared/
  Touching paths outside declared FILES and `-a/--allow-undeclared-paths`.

- preflight/
  Preflight validations such as patch path must be under `patches/`.

- git/
  Git preflight behavior (main branch enforcement, allow non-main).

- workspace/
  Stateful workspace behavior (dirty tree + soft reset).

- rerun_latest/
  Deterministic setup for `-l/--rerun-latest`.

## Finalize sandbox

Finalize paths are exercised via `badguys/tools/finalize_sandbox.py`.
It creates a local bare origin + local clone under `/tmp/badguys_finalize_sandbox/` so
commits and pushes can be tested without touching GitHub.
