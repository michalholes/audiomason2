# BadGuys Specification

Status: normative

This document is the authoritative specification for the BadGuys suite shipped in this repository.
BadGuys exists to systematically break the AM Patch Runner and verify that it FAILs correctly.

Normative keywords: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY are used in their standard RFC sense.

## 1. Scope and goals

BadGuys is NOT a happy-path test runner. The primary goals are:
- exercise failure branches of the runner
- verify that failures are deterministic and human-actionable
- verify isolation: each test MUST NOT leak state to another test

Non-goals:
- replacing pytest for AM2
- benchmarking performance
- prescribing the full test matrix (test coverage is intentionally variable)

## 2. Terminology

- repo_root: the Git repository root (parent directory of "badguys/").
- suite run: one invocation of "python3 badguys/badguys.py ...".
- test: one file in "badguys/tests/" with name "test_*.py".
- plan: an ordered list of steps returned by a test.
- commit test: a test declaring makes_commit=true.
- config: a TOML file providing BadGuys configuration.

## 3. Entry points and CLI

### 3.1 Wrapper entry point

"badguys/badguys.py" is a thin wrapper that:
1) ensures repo_root is on sys.path
2) delegates to "badguys.run_suite.main(argv)"

Implementations MUST preserve this behavior to keep imports deterministic.

### 3.2 Canonical invocation

From repo_root:
- python3 badguys/badguys.py [OPTIONS]

### 3.3 CLI options (normative)

BadGuys MUST support the following CLI options and semantics:

- --config PATH
  - repo-relative path to a TOML config file
  - default: "badguys/config.toml"

- --commit-limit N
  - overrides [suite].commit_limit from config for this run

- --runner-verbosity {debug,verbose,normal,quiet}
  - overrides [suite].runner_verbosity from config for this run
  - the effective runner verbosity MUST be passed to the runner command as: --verbosity=<mode>

- console verbosity short flags (mutually exclusive):
  - -q => quiet
  - -n => normal
  - -v => verbose
  - -d => debug
  These flags override [suite].console_verbosity for this run.

- --log-verbosity {debug,verbose,normal,quiet}
  - overrides [suite].log_verbosity from config for this run
  - controls what is written to the central log and per-test logs

- --include NAME (repeatable)
  - add NAME to the include filter set for this run

- --exclude NAME (repeatable)
  - add NAME to the exclude filter set for this run

- --list-tests
  - list the discovered and selected tests (after applying include/exclude and guard rules) and exit

Exit codes:
- 0 on overall SUCCESS
- 1 on overall FAIL

### 3.4 Resolution precedence (normative)

For all scalar settings (runner_verbosity, console_verbosity, log_verbosity, commit_limit):
1) CLI explicit override MUST win
2) config value is next
3) default is last

For include/exclude:
- the effective include list MUST be: config.filters.include + CLI --include (in that order)
- the effective exclude list MUST be: config.filters.exclude + CLI --exclude (in that order)

If both include and exclude are provided:
- include MUST be applied first (restrict to include set)
- exclude MUST be applied second (remove excluded names)

## 4. Configuration (TOML)

Default config path: badguys/config.toml

The config file MUST be valid TOML. Missing top-level tables MUST be treated as empty.
Unknown keys MAY exist but MUST NOT change behavior unless explicitly defined by this specification.

### 4.1 [suite]

- issue_id (string)
  - default issue id used by tests
  - default if missing: "666"

- runner_cmd (array of strings)
  - argv for invoking the AM Patch Runner
  - default if missing: ["python3", "scripts/am_patch.py"]

- runner_verbosity (string)
  - one of: debug, verbose, normal, quiet
  - default if missing: "quiet"
  - when non-empty, MUST be appended to runner_cmd as: --verbosity=<mode>

- console_verbosity (string)
  - one of: debug, verbose, normal, quiet
  - default if missing: "normal"
  - MAY be overridden by -q/-n/-v/-d

- log_verbosity (string)
  - one of: debug, verbose, normal, quiet
  - default if missing: "normal"

- patches_dir (string)
  - repo-relative directory used by tests to store patch artifacts
  - default if missing: "patches"

- logs_dir (string)
  - repo-relative directory for per-test logs
  - default if missing: "patches/badguys_logs"
  - NOTE (normative): the engine MUST delete this directory at the start of each suite run, then recreate it

- central_log_pattern (string)
  - repo-relative path pattern (format string)
  - supports {run_id}
  - default if missing: "patches/badguys_{run_id}.log"

- commit_limit (int)
  - maximum number of selected tests with makes_commit=true
  - default if missing: 1

### 4.2 [lock]

- path (string)
  - lock file path (repo-relative)
  - default if missing: "patches/badguys.lock"

- ttl_seconds (int)
  - lock stale threshold used by on_conflict=steal
  - default if missing: 3600

- on_conflict (string)
  - "fail" or "steal"
  - default if missing: "fail"
  - semantics are defined in section 9 (Locking)

### 4.3 [guard]

- require_guard_test (bool)
  - default if missing: true
  - if true, the suite MUST enforce that guard_test_name is present after filtering

- guard_test_name (string)
  - default if missing: "test_000_test_mode_smoke"
  - defines the required guard test name when require_guard_test=true

- abort_on_guard_fail (bool)
  - default if missing: true
  - if true, a failing guard MUST stop the run immediately (FAIL-fast)

### 4.4 [filters]

- include (array of strings)
  - default if missing: []
  - default include list (see precedence rules in 3.4)

- exclude (array of strings)
  - default if missing: []
  - default exclude list (see precedence rules in 3.4)

## 5. Environment variables

BadGuys MUST support this environment variable:

- AM_PATCH_BADGUYS_RUNNER_PYTHON
  - If set, and if runner_cmd[0] appears to be a Python executable selector
    (e.g., "python", "python3", "/usr/bin/python3", or a path ending in "/python" or "/python3"),
    then BadGuys MUST replace runner_cmd[0] with the value of AM_PATCH_BADGUYS_RUNNER_PYTHON.
  - Purpose: allow the runner to control the interpreter used for nested runner invocations
    when running inside environments where the default "python3" may not be valid.

## 6. Discovery and selection

Discovery is implemented in badguys/tests/__init__.py.

Rules (normative):
1) Tests are files in badguys/tests/ matched by glob: test_*.py
2) Files MUST be processed in lexicographic order by filename.
3) Each file MUST define a dict TEST with keys:
   - name (string)
   - run (callable)
   - optional: makes_commit (bool)
   - optional: is_guard (bool)
4) Contract: TEST["name"] MUST equal the filename stem (basename without .py).
5) The effective include filter is applied first (if non-empty).
6) The effective exclude filter is applied second.
7) If guard.require_guard_test=true:
   - guard.guard_test_name MUST be present after filtering, otherwise the suite MUST FAIL with:
     "FAIL: guard test not found: <name>"
   - the guard test MUST be moved to index 0 (run first)

## 7. Test contract

### 7.1 Structure

- One test == one file "badguys/tests/test_*.py".
- TEST["name"] == filename stem.
- A test MUST implement run(ctx) and return one of:
  - Plan (preferred), or
  - [] (empty list) for pure no-op tests (legacy compatibility)

### 7.2 Plan and steps

Plan and step types are defined in badguys/_util.py:
- Plan(steps=[...], cleanup_paths=[...])

Supported step types:
- CmdStep(argv=[...], cwd=..., expect_rc=...)
- FuncStep(name=..., fn=callable)
- ExpectPathExists(path=Path)

The engine MUST execute steps in order.

### 7.3 Cleanup and isolation (normative)

BadGuys provides two cleanup layers:

1) Engine cleanup between tests (hard isolation):
   - patches/workspaces/issue_<issue_id>/
   - patches/logs/*
   - patches/successful/issue_<issue_id>*
   - patches/unsuccessful/issue_<issue_id>*

2) Per-plan cleanup_paths:
   - each path in cleanup_paths MUST be deleted after the test plan finishes (pass or fail)

Tests MUST NOT rely on artifacts from any previous test.

### 7.4 Forbidden patterns

- A test MUST NOT invoke "python3 badguys/badguys.py" (directly or indirectly).
  Reason: the suite holds a global lock during the run; nesting would deadlock or violate isolation.

## 8. Logging, verbosity, and heartbeat

### 8.1 Log outputs

BadGuys MUST produce:
- one central log file at: central_log_pattern.format(run_id=...)
- per-test logs at: logs_dir/<test_name>.log

The per-test logs directory (logs_dir) MUST be cleared at the start of each suite run.
The central log path MUST be created (parents created as needed) and MUST begin with a header line:
"BadGuys run_id=<run_id>"

### 8.2 Verbosity channels

BadGuys has three distinct verbosity controls:

- runner verbosity: affects the nested AM Patch Runner invocation (passed as --verbosity=<mode>)
- console verbosity: affects what BadGuys prints to the terminal
- log verbosity: affects what BadGuys writes into logs (central + per-test)

### 8.3 Console behavior (normative)

- console_verbosity=quiet:
  - MUST suppress progress output
  - MUST disable heartbeat

- console_verbosity in {normal, verbose, debug}:
  - MUST print per-test result lines as tests complete
  - heartbeat MUST be enabled for long-running command execution (see 8.4)

### 8.4 Heartbeat (normative)

- Heartbeat MUST be emitted only when console_verbosity in {normal, verbose, debug}.
- Heartbeat MUST be written to stderr.
- Heartbeat cadence SHOULD be approximately every 5 seconds while a command step runs.
- Heartbeat content MUST indicate that the suite is still running a test step (exact wording is implementation-defined).

## 9. Locking

BadGuys MUST use a process lock to prevent concurrent runs.

Ordering (normative):
- acquire_lock MUST happen before initializing/clearing logs and before executing any tests.
- release_lock MUST happen in a finally-equivalent block so it runs even on failures/exceptions.

Lock file content (text) MUST contain:
- pid=<int>
- started=<unix-epoch-seconds>

Behavior:
- on_conflict=fail: the second run MUST FAIL if lock exists
- on_conflict=steal: the second run MAY steal the lock only if stale by ttl_seconds, otherwise MUST FAIL

## 10. Commit tests and commit_limit

A test is a commit test if TEST["makes_commit"] == True.

Before executing tests, BadGuys MUST check:
- if the number of selected commit tests > commit_limit, the suite MUST FAIL before executing any test steps

The FAIL message SHOULD include:
- how many commit tests were selected
- the configured/effective commit_limit
- the list of selected commit tests

## 11. Error reporting and determinism

When a failure happens, the suite MUST:
- return non-zero exit code
- emit a FAIL reason that is deterministic and actionable

All paths in messages SHOULD be repo-relative where feasible.

## 12. Compatibility and evolution

BadGuys MAY add new configuration keys and new CLI options in the future.
Any such additions MUST be specified in this document (including defaults and precedence) before being considered normative.

