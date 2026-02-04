# BadGuys Specification

Status: normative

This document is the authoritative specification for the BadGuys suite shipped in this repository.
BadGuys exists to systematically break the AM Patch Runner and verify that it FAILs correctly.

## 1. Scope and goals

BadGuys is NOT a happy-path test runner. The primary goals are:
- exercise failure branches of the runner
- verify that failures are deterministic and human-actionable
- verify isolation: each test must not leak state to another test

Non-goals:
- replacing pytest for AM2
- benchmarking performance

## 2. Terminology

- repo_root: the Git repository root (parent directory of "badguys/").
- suite run: one invocation of "python3 badguys/badguys.py ...".
- test: one file in "badguys/tests/" with name "test_*.py".
- plan: an ordered list of steps returned by a test.
- commit test: a test declaring makes_commit=true.

## 3. Entry point (CLI)

### 3.1 Wrapper

"badguys/badguys.py" is a thin wrapper that ensures repo_root is on sys.path and then calls
"badguys.run_suite.main(argv)".

### 3.2 Canonical invocation

From repo_root:
- python3 badguys/badguys.py

### 3.3 CLI options

BadGuys supports these options (see badguys/run_suite.py):
- --config PATH
  - repo-relative path to a TOML config file
  - default: badguys/config.toml

- --commit-limit N
  - overrides suite.commit_limit from config

- --runner-verbosity {debug,verbose,normal,quiet}
  - overrides suite.runner_verbosity from config
  - passed through to the runner command as: --verbosity=<mode>

- console verbosity short flags (mutually exclusive):
  - -q => quiet
  - -n => normal
  - -v => verbose
  - -d => debug

- --log-verbosity {debug,verbose,normal,quiet}
  - controls what is written to central and per-test logs

- --include NAME (repeatable)
  - include filter on test names

- --exclude NAME (repeatable)
  - exclude filter on test names

- --list-tests
  - print discovered test names (after filtering and guard rules) and exit

Exit codes:
- 0 on overall SUCCESS
- 1 on overall FAIL

## 4. Configuration (TOML)

Default config path: badguys/config.toml

### 4.1 [suite]

- issue_id (string)
  - default issue id used by tests

- runner_cmd (array of strings)
  - argv for invoking the AM Patch Runner
  - default: ["python3", "scripts/am_patch.py"]

- runner_verbosity (string)
  - one of: debug, verbose, normal, quiet
  - appended to runner_cmd as: --verbosity=<mode>

- console_verbosity (string)
  - one of: debug, verbose, normal, quiet
  - may be overridden by -q/-n/-v/-d

- log_verbosity (string)
  - one of: debug, verbose, normal, quiet

- patches_dir (string)
  - repo-relative directory used by tests to store patch artifacts

- logs_dir (string)
  - repo-relative directory for per-test logs
  - NOTE: the engine clears this directory at start of run

- central_log_pattern (string)
  - repo-relative path pattern (format string)
  - supports {run_id}

- commit_limit (int)
  - maximum number of selected tests with makes_commit=true

### 4.2 [lock]

- path (string)
  - lock file path (repo-relative by default)

- ttl_seconds (int)
  - lock stale threshold used by on_conflict=steal

- on_conflict (string)
  - fail: second run fails when lock exists
  - steal: second run steals lock only if stale by ttl_seconds

### 4.3 [guard]

- require_guard_test (bool)
  - if true, the suite enforces that guard_test_name is present

- guard_test_name (string)
  - name of the guard test

- abort_on_guard_fail (bool)
  - if true, a failing guard stops the run immediately

### 4.4 [filters]

- include (array of strings)
  - default include list

- exclude (array of strings)
  - default exclude list

CLI include/exclude are appended to config lists.

## 5. Discovery and selection

Discovery is implemented in badguys/tests/__init__.py.

Rules:
1) Tests are files in badguys/tests/ matched by glob: test_*.py
2) Files are processed in lexicographic order by filename.
3) Each file must define a dict TEST with keys:
   - name (string)
   - run (callable)
   - optional: makes_commit (bool)
   - optional: is_guard (bool)
4) Contract: TEST["name"] MUST equal the filename stem (basename without .py).
5) Include filter is applied first (if non-empty).
6) Exclude filter is applied second.
7) If require_guard_test=true:
   - guard_test_name must be present after filtering, otherwise FAIL with:
     "FAIL: guard test not found: <name>"
   - guard test is moved to index 0

## 6. Test contract

### 6.1 Structure

- One test == one file "badguys/tests/test_*.py".
- TEST["name"] == filename stem.
- A test must implement run(ctx) and return one of:
  - Plan (preferred), or
  - [] (empty list) for pure no-op tests (legacy compatibility)

### 6.2 Plan and steps

Plan and step types are defined in badguys/_util.py:
- Plan(steps=[...], cleanup_paths=[...])

Supported step types:
- CmdStep(argv=[...], cwd=..., expect_rc=...)
- FuncStep(name=..., fn=callable)
- ExpectPathExists(path=Path)

The engine executes steps in order.

### 6.3 Cleanup

Two cleanup layers exist:
1) Engine cleanup between tests (hard isolation):
   - patches/workspaces/issue_<issue_id>/
   - patches/logs/*
   - patches/successful/issue_<issue_id>*
   - patches/unsuccessful/issue_<issue_id>*

2) Per-plan cleanup_paths:
   - each path is deleted after the test plan finishes

Tests must not rely on artifacts from any previous test.

### 6.4 Forbidden patterns

- Nested invocation of "badguys/badguys.py" from inside a test run.
  Reason: the suite holds a global lock during the run.

## 7. Locking

BadGuys uses a process lock to prevent concurrent runs:
- acquire_lock is called before logs/init and before running any test.
- release_lock is called in a finally block.

Lock file content (text):
- pid=<int>
- started=<unix-epoch-seconds>

Behavior:
- on_conflict=fail: FAIL if lock exists
- on_conflict=steal: steal only if the lock is stale by ttl_seconds

## 8. Logging and verbosity

BadGuys produces:
- one central log file at: central_log_pattern.format(run_id=...)
- per-test logs at: logs_dir/<test_name>.log

Console verbosity (console_verbosity):
- quiet: no progress output (and heartbeat disabled)
- normal/verbose/debug: prints per-test result lines and may print verbose output

Log verbosity (log_verbosity):
- quiet: minimal central log
- normal/verbose/debug: includes additional information

Runner verbosity:
- passed through to AM Patch Runner as --verbosity=<mode>

Heartbeat:
- enabled only if console_verbosity in {normal, verbose, debug}
- emitted to stderr every ~5 seconds while a command step runs

## 9. Commit tests and commit_limit

A test is a commit test if TEST["makes_commit"] == True.

Before running tests, BadGuys checks:
- if number of selected commit tests > commit_limit => FAIL before executing tests
- the FAIL includes a list of selected commit tests and a fix hint

## 10. Rerun-latest (-l) contract (runner-facing)

BadGuys includes tests that exercise the runner's "-l" behavior by creating an "unsuccessful" patch bundle
and then invoking the runner with -l to apply the latest patch.

## 11. Error reporting and DX

When a failure happens, the suite must:
- return non-zero exit code
- emit a FAIL reason that includes what happened and how to fix

## 12. Extension rules

- Every new significant runner feature MUST have at least one BadGuys test.
- Every bug fix MUST add a regression BadGuys test.
- If a behavior cannot be tested, the design is considered incomplete.
