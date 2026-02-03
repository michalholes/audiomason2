# badguys (am_patch contract suite)

This directory contains a contract/regression suite for the `scripts/am_patch.py` runner.
The goal is to catch behavior regressions (especially flag regressions) early.

Key properties:

- The suite is contract-based: a step may intentionally trigger a runner failure.
  The suite passes when the *expected* outcome (ok / stage / category) matches.
- Runtime issue id is fixed to 666.
- Workspaces are cleaned deterministically to avoid leftover state between runs.
- Finalize tests are executed in a sandbox (local bare origin + local clone) so
  they can safely perform real commits and pushes without touching GitHub.

## How to run

From repo root:

- Normal mode (progress only):
  - `python3 badguys/run_suite.py`

- Verbose mode (prints more in master log, still 1 line per step on stdout):
  - `python3 badguys/run_suite.py -v`

The suite writes a master log to:

- `patches/badguys_suite.log`

If the suite fails, consult the log for the step(s) that mismatched.

## Suite configuration

`badguys/suite.toml` defines:

- `[suite]`:
  - `issue_id`: must be 666
  - `runner`: runner command (argv string)
  - `patch_dst`: destination directory where patch-kind step scripts are copied
  - `master_log`: suite master log path
- `[workspace]`: default workspace cleanup policy for steps
- `[[step]]`: ordered steps

### Step kinds

- `kind = "shell"`
  Executes `cmd` via `bash -lc` in the repo root.

- `kind = "patch"`
  Loads a patch script from `badguys/<script>`, copies it to `patch_dst`, and runs:
  `runner ... ISSUE MESSAGE patch_dst/<basename>.py`

- `kind = "reject"`
  Runs the patch script in-place (outside `patch_dst`) so runner preflight can reject it.
  This is used to test the rule: patch scripts must be under `patches/`.

### Workspace cleanup

The suite deletes `patches/workspaces/issue_666` by default:

- before each step
- after each step
- and after the suite finishes

Steps may override workspace policy with:

- `workspace = { clean_before = false, clean_after = false }`

This is required for stateful tests such as "dirty workspace -> soft reset".

### Keep workspace for debugging

- `--keep-workspace`
  Keeps workspace after the suite completes.

- `--keep-workspace-on-fail`
  Keeps workspace after the suite completes only if the suite failed.

## What is tested

The suite includes:

- CLI-only smoke tests:
  - `-h`, `-H`, `-c`

- Core behavior flags:
  - `-n/--allow-no-op` (NOOP allowed at scope; promotion may still block)
  - `-t/--allow-untouched-files` (declared but untouched)
  - `-a/--allow-undeclared-paths` (touched outside FILES)
  - `-l/--rerun-latest` (re-run latest archived patch)

- Git preflight behavior:
  - enforce main branch, and allow non-main with `--allow-non-main`

- Stateful workspace behavior:
  - dirty workspace scenario and `--soft-reset-workspace`

- Finalize behavior (most important):
  - `--finalize-live` with `--disable-promotion` (must not commit/push)
  - `--finalize-live` real commit+push (in sandbox origin)
  - `--finalize-live` with `--allow-gates-fail` (commit+push even if gates fail)
  - `--finalize-workspace` smoke with `--disable-promotion` (workspace finalize flow)

## Finalize sandbox

Finalize tests are run via `badguys/tools/finalize_sandbox.py`.

The sandbox:
- creates a local bare origin repo under `/tmp/badguys_finalize_sandbox/origin.git`
- clones the current repository into `/tmp/badguys_finalize_sandbox/clone`
- runs am_patch in that clone and pushes to the local bare origin

This prevents any interaction with GitHub while still exercising the real finalize paths.

See `badguys/tools/finalize_sandbox.py` for details.

## Adding a new test

1. Add (or reuse) a patch script under `badguys/tests/<category>/...py`.
2. Add a `[[step]]` in `badguys/suite.toml`.
3. Prefer deterministic, minimal patches that touch only `badguys/tmp/...` paths.

See `badguys/tests/README.md` for conventions.

## Artifacts and cleanup

- Master log: `patches/badguys_suite.log` (cleared at start of each run).
- Patch staging: `patches/badguys_suite/` (cleared at start and end of each run).
- Workspace: `patches/workspaces/issue_666/` (cleaned per-step; see suite.toml workspace policy).

Keep artifacts for debugging:

- `python3 badguys/run_suite.py --keep-workspace`
- `python3 badguys/run_suite.py --keep-workspace-on-fail`

## Promotion behavior in the suite

All contract steps that invoke `am_patch` in the real repository are executed with
`--disable-promotion` to ensure the suite does not create commits or push changes to GitHub.

Finalize behavior is still tested, but only inside the sandbox created by
`badguys/tools/finalize_sandbox.py` (local bare origin + local clone under `/tmp/`).
