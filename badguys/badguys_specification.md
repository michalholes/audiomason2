# BadGuys Specification

Status: normative

Specification Version: 0.3.3

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
- prescribing a full matrix of every runner combination

### 1.1 AMP-facing coverage contract

BadGuys coverage for the AM Patch Runner is capability-based, not exhaustive.

Capability groups (normative):
- G1: discovery, filters, guard enforcement, and suite locking
- G2: patch intake, execution scope, and runner test-mode isolation
- G3: runner gate families and skip controls, including dont-touch, compile, js,
  biome, typescript, ruff, pytest, mypy, docs, and monolith
- G4: workspace, archive, rerun, and promotion semantics
- G5: IPC, NDJSON, heartbeat, handshake, and cancel control flow

Coverage rules (normative):
- BadGuys MUST maintain at least one normative test path for each capability group.
- A capability group MAY be covered by multiple tests; a single test MAY cover
  multiple groups.
- BadGuys MUST NOT claim full runner coverage merely from a passing partial or
  historical matrix.
- New runner-facing capability added to scripts/am_patch.py or its normative
  specification MUST be assigned to one of the capability groups in this
  document before related coverage is claimed.
- Capability-based coverage does not require enumerating every flag
  combination or every policy permutation.

## 2. Terminology

- repo_root: the Git repository root (parent directory of "badguys/").
- suite run: one invocation of "python3 badguys/badguys.py ...".
- test: one file in "badguys/tests/" with the ".bdg" extension.
- plan: an ordered list of steps returned by a test.
- commit test: a test declaring makes_commit=true.
- config: a TOML file providing BadGuys configuration.
- capability group: one normative runner-facing coverage area defined in
  section 1.1.
- observability primitive: a step capability whose only purpose is to expose
  deterministic data to central evaluation.

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
  - the selected config file MUST be the single source of truth for all configuration-driven
    behavior, including [suite], [runner], [lock], [guard], [filters], [subjects], [recipes],
    and [evaluation]

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

- --per-run-logs-post-run {delete_all,keep_all,delete_successful}
  - overrides [suite].per_run_logs_post_run from config for this run
  - controls what happens to per-test artifacts in logs_dir after the suite run completes

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

For all scalar settings (runner_verbosity, console_verbosity, log_verbosity, per_run_logs_post_run, commit_limit):
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
Behavior-changing configuration for BadGuys is centralized in this one TOML file.
Known behavior-changing top-level tables are: [suite], [runner], [lock], [guard], [filters],
[subjects], [recipes], and [evaluation].

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
  - repo-relative directory for per-test artifacts
  - default if missing: "patches/badguys_logs"
  - NOTE (normative): the engine MUST delete this directory at the start of each suite run, then recreate it

- per_run_logs_post_run (string)
  - one of: delete_all, keep_all, delete_successful
  - default if missing: "keep_all"
  - controls what happens to per-test artifacts in logs_dir after the suite run completes
  - delete_all: delete logs_dir entirely
  - keep_all: keep all per-test artifacts
  - delete_successful: delete per-test artifact directories for tests that PASSED;
    keep artifacts for failed or unexecuted tests

- copy_runner_log (bool)
  - default if missing: false
  - if true, and if the runner IPC result includes log_path, BadGuys MAY copy that artifact into
    the per-test artifacts directory
  - if false, BadGuys MUST NOT copy log_path (runner logs are human-readable)

- write_subprocess_stdio (bool)
  - default if missing: false
  - if true, BadGuys MAY write captured subprocess stdout/stderr into per-test artifacts
  - if false, BadGuys MUST NOT write subprocess stdout/stderr into per-test artifacts

- central_log_pattern (string)
  - repo-relative path pattern (format string)
  - supports {run_id}
  - default if missing: "patches/badguys_{run_id}.log"

- commit_limit (int)
  - maximum number of selected tests with makes_commit=true
  - default if missing: 1


### 4.2 [runner]

- full_runner_tests (array of strings)
  - list of test_ids that are allowed to invoke the AM Patch Runner without --test-mode
  - default if missing: []
  - each entry MUST be an existing discovered test_id; otherwise the suite MUST FAIL before execution
  - duplicates MUST be rejected (suite MUST FAIL before execution)

### 4.3 [lock]

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

### 4.4 [guard]

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

### 4.5 [subjects]

[subjects] defines logical test subjects and their repo-relative target paths.

- structure:
  - [subjects.tests.<test_id>.<subject_id>]
  - required key: relpath (string, repo-relative path)

Rules (normative):
- subject_id is a logical identifier used by `.bdg` payloads and recipe tables
- relpath MUST be repo-relative
- relpath entries MUST be read from the effective config selected by --config PATH
- if a referenced subject is missing, the suite MUST FAIL deterministically before execution

### 4.6 [recipes]

[recipes] defines how `.bdg` payloads are materialized and how steps are executed.

- structure:
  - [recipes.tests.<test_id>.assets.<asset_id>]
  - [recipes.tests.<test_id>.assets.<asset_id>.entries.<entry_id>]
  - [recipes.tests.<test_id>.steps.<step_index>]

Rules (normative):
- asset and step recipes MUST be read from the effective config selected by --config PATH
- recipe data is the single source of truth for filesystem paths, command-line arguments, and
  step-level execution overrides
- if a required asset recipe, entry recipe, or step recipe is missing, the suite MUST FAIL
  deterministically before execution
- if `.bdg` repeats behavior controlled by [recipes], the suite MUST FAIL deterministically
- [recipes] and [evaluation] are distinct: [recipes] controls materialization/execution;
  [evaluation] controls PASS/FAIL expectations

## 5. Environment variables

BadGuys MUST support this environment variable:

- AM_PATCH_BADGUYS_RUNNER_PYTHON
  - If set, and if runner_cmd[0] appears to be a Python executable selector
    (e.g., "python", "python3", "/usr/bin/python3", or a path ending in "/python" or "/python3"),
    then BadGuys MUST replace runner_cmd[0] with the value of AM_PATCH_BADGUYS_RUNNER_PYTHON.
  - Purpose: allow the runner to control the interpreter used for nested runner invocations
    when running inside environments where the default "python3" may not be valid.

## 6. Discovery and selection

Discovery is implemented in badguys/discovery.py.

Rules (normative):
1) Tests are files in badguys/tests/ matched by glob: *.bdg
2) Files MUST be processed in lexicographic order by filename.
3) Each test file MUST be a TOML document. The test id is the filename stem
   (basename without the .bdg extension).
4) The TOML document MAY contain a [meta] table. Supported keys:
   - makes_commit (bool, default false)
   - is_guard (bool, default false)
5) The effective include filter is applied first (if non-empty).
6) The effective exclude filter is applied second.
7) If include and exclude are both non-empty and overlap, the suite MUST FAIL with:
   "FAIL: include/exclude conflict: <comma-separated names>"
8) If guard.require_guard_test=true:
   - if guard.guard_test_name is present in the effective exclude set, the suite MUST FAIL with:
     "FAIL: guard test excluded but required: <name>"
   - if the guard test is not present after filtering but exists in the full discovered set, the
     suite MUST inject the guard test back into the selected list.
   - if the guard test does not exist in the full discovered set, the suite MUST FAIL with:
     "FAIL: guard test not found: <name>"
   - the guard test MUST be moved to index 0 (run first)

## 7. Test contract

### 7.1 Structure

- One test == one file "badguys/tests/*.bdg".
- The test id is the filename stem (basename without .bdg).
- A .bdg file MUST be valid TOML and MUST contain at least one [[step]].

The .bdg schema is defined by badguys/bdg_loader.py (normative):

- [meta] (optional table)
  - makes_commit (bool, default false)
  - is_guard (bool, default false)

- [[asset]] (optional array of tables)
  - id (string, required, unique within the file)
  - kind (string, required)
  - content (string, optional)
  - [[asset.entry]] (optional array of tables)
    - name (string, required)
    - content (string, required)

- [[step]] (required array of tables)
  - op (string, required)
  - additional keys are op-specific parameters

#### 7.1.1 Token substitution in strings (normative)

BadGuys MUST support token substitution in all string fields originating from a `.bdg` file,
including:
- `[[asset]].content`
- `[[asset.entry]].content`
- any string parameter values inside `[[step]]` tables (including lists of strings)

Tokens are written as `${name}` and MUST be replaced before an operation executes.

Supported tokens (normative):
- `${issue_id}`: replaced with the effective `suite.issue_id` string.
- `${now_stamp}`: replaced with a per-test stamp computed once at test start,
  using local time format `YYYYMMDD_HHMMSS`.

Consistency rule (normative):
- Within a single test execution, every `${now_stamp}` expansion MUST yield the same value.

Safety rule (normative):
- Central evaluation rules MUST NOT depend on the exact `${now_stamp}` value.
  `${now_stamp}` exists only to make prepared artifacts unique.

### 7.2 Execution model

- Discovery produces TestDef objects whose run(ctx) returns a BdgTest.
- The engine MUST execute the listed BdgStep objects in order.

### 7.3 Runner result determination (normative)

When a step executes the AM Patch Runner (scripts/am_patch.py), BadGuys MUST determine the
runner outcome primarily from the IPC socket event stream.

Primary rule:
- If an IPC event with type="result" is obtained, BadGuys MUST use:
  - ok (boolean) as the authoritative PASS/FAIL signal, and
  - return_code as the authoritative runner return code.

Fallback rule:
- If no IPC type="result" event is obtained, BadGuys MUST fall back to the subprocess exit code.

BadGuys MUST NOT use stdout/stderr parsing as the authoritative decision source for PASS/FAIL.

IPC stream persistence rule:
- For every step that invokes scripts/am_patch.py, BadGuys MUST capture the complete IPC event
  stream (NDJSON, one JSON object per line) and write it into the per-test artifacts directory as:
  logs_dir/<test_id>/runner.ipc.step<step_index>.jsonl
- The stream file MUST contain the exact NDJSON lines received from the socket (no filtering and
  no reformatting).

Runner value_text rule:
- For every runner-invoking step, BadGuys MUST compute a deterministic value_text string by
  concatenating the 'msg' field from every IPC event with type="log" in receive order, separated
  by a single '\n'. This value_text MUST be used as the step's evaluation 'value'.

Runner artifact copy rule:
- If the IPC result includes json_path, BadGuys MUST copy it into logs_dir/<test_id>/ as:
  runner.result.json
- If the IPC result includes log_path:
  - if suite.copy_runner_log=true, BadGuys MAY copy it into logs_dir/<test_id>/ as:
    runner.log.txt
  - otherwise, BadGuys MUST NOT copy it.
- The copy operation for json_path and log_path MUST occur eagerly when the valid IPC
  type="result" event is received, not after the runner subprocess exits.
- After eager copy succeeds, BadGuys MUST treat the copied artifact in logs_dir/<test_id>/ as
  authoritative and MUST NOT require the original source path to remain present after runner exit.

#### 7.3.1 Required AMP-facing observability primitives (normative)

To satisfy the capability groups in section 1.1 without moving expectations
into `.bdg` files, BadGuys MUST provide the following observability primitives,
whether implemented as step operations, executor hooks, or equivalent centrally
controlled mechanisms:

- text file read
  - MUST read a deterministic UTF-8 text artifact from either:
    - a repo-relative path, or
    - a path relative to the current test artifacts directory
  - intended use: runner result JSON, generated manifests, or copied artifacts

- zip entry listing
  - MUST return the sorted entry names from a zip artifact addressed by
    repo-relative path or test-artifact-relative path
  - intended use: archive hygiene and bundle layout assertions

- git status inspection
  - MUST support at least two scopes: repo_root and runner workspace
  - MUST return deterministic porcelain-style paths for the selected scope
  - intended use: workspace, promotion, and finalize semantics

- IPC command send
  - MUST send a newline-delimited JSON command to the runner IPC socket used by
    the current step
  - reply and control events observed after the command MUST remain available
    to central evaluation via the persisted IPC stream

These primitives are observability-only. They MUST NOT move filesystem paths,
command lines, or PASS/FAIL expectations out of [recipes] and [evaluation].


### 7.4 Runner test mode (normative)

When a step executes the AM Patch Runner, BadGuys MUST control runner mode centrally.

Default rule:
- For every step that invokes scripts/am_patch.py, BadGuys MUST inject the flag --test-mode
  into the runner argv (including informational invocations such as -h, --help-all, or --show-config).

Full runner allowlist rule:
- If the current test_id is listed in config table [runner].full_runner_tests, BadGuys MUST NOT inject
  --test-mode for that test.

Single source of truth rule:
- A test definition MUST NOT attempt to control runner mode directly via extra_args.
- If extra_args contains --test-mode for any runner invocation, the suite MUST FAIL before execution
  with a deterministic error message identifying the test_id.

### 7.5 Cleanup and isolation (normative)

BadGuys provides two cleanup layers:

1) Engine cleanup between tests (hard isolation):
   - patches/workspaces/issue_<issue_id>/
   - patches/logs/issue_<issue_id>*
   - patches/successful/issue_<issue_id>*
   - patches/unsuccessful/issue_<issue_id>*
   - patches/patched_issue<issue_id>_*.zip
   - patches/issue_<issue_id>__bdg__test_*

2) Per-plan cleanup_paths:
   - each path in cleanup_paths MUST be deleted after the test plan finishes (pass or fail)

Tests MUST NOT rely on artifacts from any previous test.

#### 7.5.1 Subject-scoped workspace preparation (normative)

BadGuys MAY provide engine-level workspace preparation steps that operate on declared
subjects before runner execution.

DELETE_SUBJECT semantics (normative):
- A step with `op = "DELETE_SUBJECT"` MUST resolve its target exclusively from:
  - `recipes.tests.<test_id>.steps.<step_index>.subject`, and
  - `subjects.tests.<test_id>.<subject_id>.relpath`
- The `.bdg` step for `DELETE_SUBJECT` MUST NOT embed filesystem path parameters.
- The step recipe for `DELETE_SUBJECT` MUST allow exactly one key: `subject`.
- If the referenced subject is missing, the suite MUST FAIL deterministically.
- If the resolved path does not exist, the operation MUST succeed with `rc=0`.
- If the resolved path is a regular file or a symlink, the operation MUST delete it and
  succeed with `rc=0`.
- If the resolved path is a directory, the operation MUST FAIL deterministically.
- `DELETE_SUBJECT` MUST NOT target any path that is not declared in `[subjects]`.

### 7.6 Forbidden patterns

- A test MUST NOT invoke "python3 badguys/badguys.py" (directly or indirectly).
  Reason: the suite holds a global lock during the run; nesting would deadlock or violate isolation.

## 8. Logging, verbosity, and heartbeat

### 8.1 Log outputs

BadGuys MUST produce:
- one central run log file at: central_log_pattern.format(run_id=...)
  - format: NDJSON (one JSON object per line)
  - first line MUST be a single JSON object with at least: {"type":"badguys_run","run_id":"..."}
- per-test artifacts at: logs_dir/<test_id>/ (directory)
  - each test directory MUST contain a file: badguys.test.jsonl (NDJSON)
  - for each runner-invoking step, the directory MUST contain the corresponding
    runner.ipc.step<step_index>.jsonl file (see 7.3)

The per-test artifacts root directory (logs_dir) MUST be cleared at the start of each suite run.
The central log path MUST be created (parents created as needed).


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

#### Summary line (normative)

- console_verbosity=quiet:
  - MUST print exactly one final summary line:
    - "BadGuys summary: OK" or "BadGuys summary: FAIL"
  - MUST NOT include passed/failed counts

- console_verbosity in {normal, verbose, debug}:
  - MUST print a final summary line that includes counts:
    - "BadGuys summary: OK passed=<N> failed=<M>" or
    - "BadGuys summary: FAIL passed=<N> failed=<M>"
  - passed MUST equal the number of executed tests that PASSED
  - failed MUST equal the number of executed tests that FAILED
  - tests that did not execute (e.g. interrupted run) MUST NOT be counted as failed

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


## BdG tests

BadGuys tests are defined by files under `badguys/tests/` with the `.bdg` extension.

A `.bdg` file is TOML and contains:

- `[meta]` with optional `makes_commit` (bool) and `is_guard` (bool)
- `[[asset]]` entries with `id`, `kind`, and embedded content
- `[[asset.entry]]` entries with logical entry ids and embedded content
- `[[step]]` entries with `op` and parameters.

Logical subject-to-path mapping and execution/materialization recipe MUST live in
`badguys/config.toml` under [subjects] and [recipes].

`.bdg` MUST NOT contain filesystem paths, command lines, expectations, or step-level execution
overrides that are controlled by [recipes].

## Central evaluation

All PASS/FAIL rules are defined centrally in `badguys/config.toml` under `[evaluation]` and keyed by `(test_id, step_index)`.

If `evaluation.strict_coverage=true`, missing rules for a step is a deterministic FAIL.


Supported evaluation rule keys (normative):
- rc_eq (int), rc_ne (int)
- stdout_contains (string|list[string]), stdout_not_contains (string|list[string]),
  stdout_regex (string|list[string])
- stderr_contains (string|list[string]), stderr_not_contains (string|list[string]),
  stderr_regex (string|list[string])
- value_eq (any), value_contains (string|list[string]), value_not_contains (string|list[string]),
  value_regex (string|list[string])
- list_eq (list[string]), list_contains (string|list[string]),
  list_not_contains (string|list[string])
- equals_step_index (int)

Runner evaluation constraint (normative):
- For any step that invokes scripts/am_patch.py, evaluation rules MUST NOT use any stdout_* or
  stderr_* keys. The runner subprocess stdio is non-authoritative and may be empty.
- For any step that invokes scripts/am_patch.py, the evaluation 'value' MUST be the runner
  value_text defined in section 7.3.
