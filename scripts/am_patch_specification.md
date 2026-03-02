# AM Patch Runner - Functional Specification v4 (UPDATED)

This document reflects the **current, implemented behavior** of the AM
Patch Runner after introduction of: - `-w` / `--finalize-workspace` -
blessed gate outputs - workspace cleanup semantics parity

This document is **authoritative** for current runner behavior.

------------------------------------------------------------------------

## 0. Core Principles (NonNegotiable)

### 0.1 Universal controllability

Every runner behavior is controllable via: - CLI flags **or** -
`--override KEY=VALUE` overrides, with precedence: **CLI \> config \>
defaults**.

#

### Phase 2: hardcoded settings must be configurable

The runner must not hardcode operational paths, filenames, workspace
layout, or scope exemptions. Every such setting must be configurable
via:

1)  config file key (am_patch.toml), and
2)  CLI override (either a dedicated flag or --override KEY=VALUE).

The config file path itself is CLI-only and must not be a config key.

The following keys are normative (defaults shown):

-   patch_dir_name = "patches"
-   patch_layout_logs_dir = "logs"
-   patch_layout_json_dir = "logs_json"
-   patch_layout_workspaces_dir = "workspaces"
-   patch_layout_successful_dir = "successful"
-   patch_layout_unsuccessful_dir = "unsuccessful"
-   lockfile_name = "am_patch.lock"
-   current_log_symlink_name = "am_patch.log"
-   current_log_symlink_enabled = true
-   log_level = "verbose" (allowed:
    quiet\|normal\|warning\|verbose\|debug)
-   log_ts_format = "%Y%m%d\_%H%M%S"
-   log_template_issue = "am_patch_issue\_{issue}\_{ts}.log"
-   log_template_finalize = "am_patch_finalize\_{ts}.log"
-   json_out = false (when true, write debug-complete NDJSON event log)
-   failure_zip_name = "patched.zip"
-   failure_zip_template = "" (when set: render filename using {issue} and optional
    {ts}/{nonce}/{log}/{attempt})
-   failure_zip_cleanup_glob_template = "patched_issue{issue}_*.zip"
-   failure_zip_keep_per_issue = 1
-   failure_zip_delete_on_success_commit = true
-   failure_zip_log_dir = "logs"
-   failure_zip_patch_dir = "patches"

Note: Zip artifacts written by the runner (failure zip and the success
archive zip) are written atomically (tmp file + replace + fsync) to avoid
partial reads.

-   workspace_issue_dir_template = "issue\_{issue}"
-   workspace_repo_dir_name = "repo"
-   workspace_meta_filename = "meta.json"
-   workspace_history_logs_dir = "logs"
-   workspace_history_oldlogs_dir = "oldlogs"
-   workspace_history_patches_dir = "patches"
-   workspace_history_oldpatches_dir = "oldpatches"
-   blessed_gate_outputs = \["audit/results/pytest_junit.xml"\]
-   gates_skip_biome = true
-   gate_biome_extensions = [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"]
-   gate_biome_command = ["npm", "run", "lint", "--"]
-   gates_skip_typescript = true
-   gate_typescript_extensions = [".ts", ".tsx", ".mts", ".cts"]
-   gate_typescript_command = ["tsc", "--noEmit", "--pretty", "false"]
-   scope_ignore_prefixes = \[".am_patch/", ".pytest_cache/",
    ".mypy_cache/", ".ruff_cache/", "**pycache**/"\]
-   scope_ignore_suffixes = \[".pyc"\]
-   scope_ignore_contains = \["/**pycache**/"\]
-   venv_bootstrap_mode = "auto" (allowed: auto\|always\|never)
-   venv_bootstrap_python = ".venv/bin/python"
-   rollback_workspace_on_fail = "none-applied" (allowed:
    none-applied\|always\|never)

Log filtering policy: - log_level is a config key (same allowed values
as verbosity: quiet\|normal\|warning\|verbose\|debug). - Meaning:
filters what is written to the file log, using the same semantics table
as verbosity. - Default: verbose.

These keys affect concrete behavior: - filesystem locations (patch dir
layout and workspace layout), - log naming and the optional current-log
symlink, - the name and internal structure of the failure diagnostics
zip, - which changed paths are ignored for scope enforcement and
promotion hygiene, - early venv interpreter bootstrap behavior.

## 0.2 Determinism over convenience

The runner never guesses, never implicitly expands scope, and never
mutates state without explicit authorization.

------------------------------------------------------------------------

## 1. Version Visibility

The runner prints its version: - on every invocation - in `--help`

Example:

    am_patch RUNNER_VERSION=4.3.10

Version discipline: - Any change that alters runner behavior MUST bump
`RUNNER_VERSION`. - Any change that alters runner behavior MUST update
this specification under `scripts/`.

------------------------------------------------------------------------

## 1.1 Verbosity and status output

Runner supports 5 verbosity modes for screen output (and the same level
names for the file log filter).

Levels are inherited: each higher mode includes everything from the
lower mode.

-   quiet:
    -   START
    -   RESULT
    -   On FAIL: full stdout + stderr of the failed step(s)
-   normal:
    -   quiet + legacy concise flow format:
        -   RUN
        -   LOG
        -   DO
        -   STATUS (elapsed format)
        -   OK / FAIL
        -   RESULT
        -   FILES
        -   COMMIT
        -   PUSH
    -   On FAIL: full stdout + stderr of the failed step(s)
-   warning:
    -   normal + warnings (if any)
    -   On FAIL: full stdout + stderr
-   verbose:
    -   warning + diagnostic sections (config, workspace meta, gate
        summaries, patch summary, etc.)
        -   Unified patch application progress (UNIFIED_PATCH ...) is part of the patch summary and appears only in verbose+ unless it represents a failure.
    -   On FAIL: full stdout + stderr
-   debug:
    -   verbose + full internal command metadata (RUN cmd=..., cwd=...,
        returncode=...)
    -   verbose + full diagnostic dumps
    -   On FAIL: full stdout + stderr

Verbosity inheritance (contract): - Verbosity modes are cumulative. Each
higher mode MUST include all guaranteed outputs of the next lower mode,
and MAY add additional detail.

CLI: - `-q`/`-v`/`-n`/`-d` /
`--verbosity {debug,verbose,normal,warning,quiet}` (default:
`verbose`) - `--log-level {debug,verbose,normal,warning,quiet}`
(default: `verbose`)

`--verbosity` controls screen output. `--log-level` controls what is
written into the file log.

Both use the same semantics table (severity+channel filtering):

-   `quiet`: allow only summary=True (START/RESULT). All other messages
    are denied.
-   `normal`: allow CORE(INFO/WARNING/ERROR). Deny DETAIL and DEBUG.
-   `warning`: normal + allow DETAIL(WARNING). Deny DETAIL(INFO/ERROR)
    and DEBUG.
-   `verbose`: warning + allow DETAIL(INFO). Deny DEBUG.
-   `debug`: allow everything.

Full error detail bypass (non-filterable):

- By default, full stdout/stderr of a failed step MUST be emitted with a bypass flag so it
  is visible even in quiet.
- Exception (autofix/autoformat failure dump): for Ruff/Biome autoformat/autofix steps,
  failed-step stdout/stderr MUST NOT bypass filtering. It MUST be emitted as
  DETAIL+WARNING so it is visible only at warning/verbose/debug.

Monolith gate failures (normative):

- If Monolith gate fails, the runner MUST emit the concrete failure reasons
  (the FAIL violation lines) as full error detail so they are visible even in
  `--verbosity quiet` and `--log-level quiet`.
- The one-line failure summary (e.g. `MONOLITH: FAIL`) is not sufficient on its own.

Status indicator: - TTY: single-line overwrite on stderr:
`STATUS: <STAGE>  ELAPSED: <mm:ss>` - non-TTY: periodic heartbeat on
stderr (1s interval): `HEARTBEAT: <STAGE> elapsed=<mm:ss>` - Before
printing any normal stdout line (e.g., `DO:`, `OK:`, `FAIL:`, `RUN:`,
`LOG:`), the runner MUST first terminate any active TTY status line with
a newline, so output never concatenates onto the status line. - enabled
in `normal`, `warning`, `verbose`, `debug`

Final summary (always printed at the end): - SUCCESS: -
`RESULT: SUCCESS` - `FILES:` block (only when `PUSH: OK`), formatted
strictly:

    FILES:

    A path1
    M path2
    D path3

-   `COMMIT: <sha>` or `(none)`
-   `PUSH: OK|FAIL` (when commit/push is enabled) NOTE: 'PUSH: UNKNOWN'
    is forbidden; if it appears, it indicates a runner defect.
-   `LOG: <path>`
-   FAIL:
    -   `RESULT: FAIL`
    -   `STAGE: <stage-id>[, <stage-id>...]`
    -   When multiple failures occur in a single run, STAGE MUST be a
        single line with a comma-separated list of all known failing
        stages (deterministic order).
    -   `REASON: <one line>`
    -   `LOG: <path>`

Quiet sinks: - If `--verbosity quiet`, the console prints only START +
RESULT (plus error detail on FAIL). - If `--log-level quiet`, the log
file contains only START + RESULT (plus error detail on FAIL).

Priority rule (normative): - If patch application fails (e.g.,
`git apply` fails in unified patch mode), the final FAIL summary MUST
report `STAGE: PATCH_APPLY`. - Any later problems discovered in
subsequent steps (e.g., scope enforcement) MAY be logged as secondary
failures but MUST NOT override the primary PATCH_APPLY failure.

## 2. Modes of Operation

### 2.1 Workspace mode (default)

-   Requires `ISSUE_ID` positional argument.
-   Patch execution and gates run in a workspace.
-   Promotion to live occurs only after successful validation.

### 2.2 Finalize mode (`-f`)

-   Operates directly on the live repository.
-   No workspace is created or used.
-   Commit message is provided via `-f`.

### 2.3 Finalizeworkspace mode (`--finalize-workspace ISSUE_ID`)

-   Operates on an **existing workspace**.
-   No patch script is executed.
-   Commit message is read from
    `patches/workspaces/issue_<ID>/meta.json`.
-   Execution order:
    1.  Gates in workspace
    2.  Promotion workspace live
    3.  Gates in live
    4.  Commit + push

### 2.4 Test mode (`--test-mode`)

-   Workspace-only mode intended for runner testing (e.g. badguys).
-   Patch execution and gates run in the workspace as usual.
-   After workspace gates and the live-repo guard check (after gates),
    the runner performs a hard STOP:
    -   no promotion to live,
    -   no live gates,
    -   no commit/push,
    -   no patch archives,
    -   no failure-zip artifacts.
-   Workspace directory is deleted on exit (SUCCESS or FAILURE).

Workspace cleanup: - In test mode, the workspace is deleted on exit
ALWAYS (SUCCESS or FAILURE). - `--keep-workspace` is ignored in test
mode. - `delete_workspace_on_success` does not apply in test mode.

------------------------------------------------------------------------

## 3. Configuration System

### 3.1 Config file

-   Path: `scripts/am_patch/am_patch.toml`
-   Loaded on every run.
-   Source of each effective value is logged.

### 3.2 CLI (normative)

### 3.2.1 Help contract

The runner provides two help views:

-   `--help` (`-h`) prints short help (common workflow options only).
-   `--help-all` (`-H`) prints full help (workflow-grouped reference).

Rules:

-   Options shown in short help may have both short and long forms.
-   Options not in short help are long-only (no short aliases).
-   Full help shows options in long form; for short-help options, the
    short alias is shown in parentheses.
 -   Short help does not show defaults.

Help-all completeness: all supported options that affect behavior, including gate control flags
such as `--skip-biome`, `--skip-typescript`, `--gate-biome-extensions`,
`--gate-typescript-extensions`, `--gate-biome-command`, and `--gate-typescript-command`,
MUST appear in `--help-all` output.

### 3.2.2 Config introspection

-   `--show-config` (`-c`) prints the effective policy/config and exits.
    It prints the same effective output normally logged at the start of
    a run.

### 3.2.3 Promotion toggle (commit/push)

-   `--disable-promotion` sets `commit_and_push=false`.

Effects: - Patch mode: gates run, but the runner does not commit or
push. - `--finalize-live`: gates run, but the runner does not commit or
push. - `-w` / `--finalize-workspace`: workspace promotion still occurs
and gates run in both workspace and live repo, but the runner does not
commit or push. In this case, the workspace is preserved to avoid losing
the easiest re-run path while the live repo has uncommitted changes.

This toggle affects only commit/push behavior. It does not change patch
execution, gates, or workspace promotion semantics.

### 3.2.4 Overrides symmetry

Every behavior has a config key and is overridable via CLI, primarily
via:

-   `--override KEY=VALUE` (repeatable)

------------------------------------------------------------------------

## 4. Patch Contract (Scope)

### 4.1 Mandatory FILES declaration

Patch scripts must declare intended paths via `FILES = [...]`.

### 4.2 Scope enforcement

Default: - Touching undeclared files FAIL - Declaring but not touching
FAIL - Noop patch FAIL

All are overrideable.

When reusing an issue workspace across multiple runs, the runner
maintains a per-issue cumulative allowlist ("allowed union") of paths
that were previously legalized for this ISSUE_ID.

Scope enforcement MUST allow touched paths that are either: - declared
by the current patch (FILES), or - present in the per-issue allowed
union, or - blessed gate outputs.

This ensures repeated patching within the same ISSUE_ID does not require
`-a` solely due to prior legalized changes in the reused workspace.

### 4.3 Blessed gate outputs

Some files are explicitly allowlisted as **gateproduced audit
artifacts**.

Current allowlist: - `audit/results/pytest_junit.xml`

Properties: - Do **not** trigger scope violations - Do **not** require
`-a` - Are automatically promotable and committable when changed

This mechanism is **separate from** `-a`.

------------------------------------------------------------------------

## 5. `-a` (Allow outside files)

`-a` is a **strong override** intended for large refactors.

Semantics: - Legalizes touching undeclared files - Expands promotion
scope accordingly - Should be used deliberately and sparingly

`-a` is **not required** for blessed gate outputs.

------------------------------------------------------------------------

## 6. Gates

### 6.1 Execution

-   Gates run after the patch is applied (unified or script).
-   If patch apply fails, gates may still run only when explicitly
    enabled by policy:
    -   apply_failure_partial_gates_policy = "never|always|repair_only"
    -   apply_failure_zero_gates_policy = "never|always|repair_only"
-   repair_only means: run gates after PATCH_APPLY failure only when
    workspace_attempt >= 2 (workspace_attempt is the workspace meta.json
    attempt counter exposed as ws.attempt).
-   Defaults:
    -   apply_failure_partial_gates_policy = "repair_only"
    -   apply_failure_zero_gates_policy = "never"
-   These keys follow 0.1 precedence: CLI > config > defaults.
-   When gates run after patch apply failure, the run remains FAIL with
    PATCH_APPLY as the primary reason.
-   Default gate order is:
    1)  COMPILE (python bytecode compilation)
    2)  JS syntax (only when JS files are touched)
    3)  Biome (only when configured and matching files are touched)
    4)  TypeScript (only when configured and matching files are touched)
    5)  Ruff
    6)  Pytest
    7)  Mypy
    8)  Monolith (anti-monolith AST gate)
    9)  Docs (documentation obligation)
-   Individual gates may be configured on/off.

### 6.1.1 COMPILE gate

-   Purpose: fail fast on syntax errors after patch application.
-   Implementation: runs `python -m compileall -q` in the workspace repo
    root.
    -   Targets: `compile_targets` (default: `["."]`).
    -   Exclude: `compile_exclude` (default: `[]`) is compiled into a
        `compileall -x <regex>` directory filter.
-   Config:
    -   `compile_check = true|false` (default: true)
    -   `compile_targets = ["...", ...]` (default: `["."]`)
    -   `compile_exclude = ["...", ...]` (default: `[]`)
-   CLI override:
    -   `--no-compile-check` disables this gate for the run.
    -   `--override compile_targets=...` and
        `--override compile_exclude=...` follow the same list format as
        `ruff_targets`.
-   Failure behavior is identical to other gates: the run fails with
    `GATE:COMPILE`, a failure zip is produced, and the success archive
    zip is not.

### 6.1.2 JS syntax gate

-   Purpose: fail fast on JavaScript syntax errors when a patch touches JS files.
-   Trigger: the gate is evaluated only when at least one changed path ends with an extension
    listed in `gate_js_extensions` (case-insensitive suffix match).
-   If not triggered, the gate is SKIPPED and MUST NOT execute any external tool.
-   Touched JS paths that do not exist as files after patch application are ignored (e.g.,
    deletions). If all touched JS paths are non-existent, the gate is SKIPPED and MUST NOT
    execute any external tool.
-   Implementation: runs an external command for each touched JS file:
    -   Default command argv: `["node", "--check"]`
    -   Invocation: `<argv...> <file>`
    -   Files are processed in deterministic lexicographic order.
-   Controls (precedence: CLI > config > defaults):
    -   `gates_skip_js = true|false` (default: false)
    -   `gate_js_extensions = [".js", ...]` (default: `[".js"]`)
    -   `gate_js_command = list[str] | str` (default: `["node", "--check"]`)
        -   If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv including the tool.
-   CLI:
    -   `--skip-js` (equivalent to `--override gates_skip_js=true`)

### 6.1.3 Biome gate

-   Purpose: run Biome lint/format checks when a patch touches supported files.
-   Trigger: the gate is evaluated only when at least one changed path ends with an extension
    listed in `gate_biome_extensions` (case-insensitive suffix match).
-   If not triggered, the gate is SKIPPED and MUST NOT execute any external tool.
-   Changed paths that do not exist as files after patch application are ignored (e.g.,
    deletions). If all matched paths are non-existent, the gate is SKIPPED and MUST NOT
    execute any external tool.
-   Variant B execution semantics (file-scoped):
    -   Runner builds a deterministic lexicographically sorted list of matched changed files.
    -   When biome_format=true: Runner executes: `GATE: BIOME_FORMAT (write)` exactly once:
        `<format_argv...> <changed_file_1> <changed_file_2> ...`
    -   When biome_autofix=false: Runner executes the gate exactly once:
        `<argv...> <changed_file_1> <changed_file_2> ...`
    -   When biome_autofix=true:
        -   Runner executes: `GATE: BIOME (check)` exactly once:
            `<argv...> <changed_file_1> <changed_file_2> ...`
        -   If (check) fails: Runner executes: `GATE: BIOME_AUTOFIX (apply)` exactly once:
            `<fix_argv...> <changed_file_1> <changed_file_2> ...`
        -   Runner executes: `GATE: BIOME (final)` exactly once:
            `<argv...> <changed_file_1> <changed_file_2> ...`
        -   Gate result is determined only by (final).
-   Controls (precedence: CLI > config > defaults):
    -   `gates_skip_biome = true|false` (default: true)
    -   `gate_biome_extensions = [".js", ...]`
        (default: `[".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"]`)
    -   `gate_biome_command = list[str] | str`
        (default: `["npm", "run", "lint:files", "--"]`)
        -   If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv including the tool.
    -   `biome_format = true|false` (default: true)
    -   `gate_biome_format_command = list[str] | str`
        (default: `["npm", "exec", "--", "biome", "format", "--write"]`)
        -   If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv including the tool.
    -   `biome_format_legalize_outside = true|false` (default: true)
        -   When true, files modified by BIOME_FORMAT (write) outside the changed paths set
            are legalized only if their extension matches gate_biome_extensions.
        -   Runner MUST emit: `legalized_biome_format_files=[...]` (sorted, repo-relative).
    -   `biome_autofix = true|false` (default: true)
    -   `gate_biome_fix_command = list[str] | str`
        (default: `["npm", "run", "lint:files:fix", "--"]`)
        -   If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv including the tool.
    -   `biome_autofix_legalize_outside = true|false` (default: true)
        -   When true, files modified by BIOME_AUTOFIX (apply) outside the changed paths set
            are legalized only if their extension matches gate_biome_extensions.
        -   Runner MUST emit: `legalized_biome_autofix_files=[...]` (sorted, repo-relative).
-   CLI (explicit flags; no `--override` required for these options):
    -   `--skip-biome` (equivalent to setting `gates_skip_biome=true`)
    -   `--gate-biome-extensions CSV_OR_REPEATABLE` sets `gate_biome_extensions`
    -   `--gate-biome-command STR` sets `gate_biome_command`
    -   `--biome-format` sets `biome_format=true`
    -   `--no-biome-format` sets `biome_format=false`
    -   `--biome-format-legalize-outside` sets `biome_format_legalize_outside=true`
    -   `--no-biome-format-legalize-outside` sets `biome_format_legalize_outside=false`
    -   `--gate-biome-format-command STR` sets `gate_biome_format_command`
    -   `--biome-autofix` sets `biome_autofix=true`
    -   `--no-biome-autofix` sets `biome_autofix=false`
    -   `--biome-autofix-legalize-outside` sets `biome_autofix_legalize_outside=true`
    -   `--no-biome-autofix-legalize-outside` sets `biome_autofix_legalize_outside=false`
    -   `--gate-biome-fix-command STR` sets `gate_biome_fix_command`

### 6.1.4 TypeScript gate

-   Purpose: run TypeScript typechecking when a patch touches TypeScript files.
-   Trigger: the gate is evaluated only when at least one changed path ends with an extension
    listed in `gate_typescript_extensions` (case-insensitive suffix match).
-   If not triggered, the gate is SKIPPED and MUST NOT execute any external tool.
-   Changed paths that do not exist as files after patch application are ignored (e.g.,
    deletions). If all matched paths are non-existent, the gate is SKIPPED and MUST NOT
    execute any external tool.
-   Variant B execution semantics (file-scoped):
    -   Runner builds a deterministic lexicographically sorted list of matched changed files.
    -   Runner executes the gate exactly once:
        `<argv...> <changed_file_1> <changed_file_2> ...`
-   Controls (precedence: CLI > config > defaults):
    -   `gates_skip_typescript = true|false` (default: true)
    -   `gate_typescript_extensions = [".ts", ...]`
        (default: `[".ts", ".tsx", ".mts", ".cts"]`)
    -   `gate_typescript_command = list[str] | str`
        (default: `["tsc", "--noEmit", "--pretty", "false"]`)
        -   If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv including the tool.
-   CLI (explicit flags; no `--override` required for these options):
    -   `--skip-typescript` (equivalent to setting `gates_skip_typescript=true`)
    -   `--gate-typescript-extensions CSV_OR_REPEATABLE` sets `gate_typescript_extensions`
    -   `--gate-typescript-command STR` sets `gate_typescript_command`

### Python gates - auto mode

This section defines file-scoped triggering semantics for Ruff, Mypy, and Pytest when the
corresponding mode policy key is set to "auto". Types, defaults, and allowed values are
defined in scripts/am_patch_policy_glossary.md.

Policy keys:
- gate_ruff_mode in {auto, always}
- gate_mypy_mode in {auto, always}
- gate_pytest_mode in {auto, always}
- gate_pytest_js_prefixes: list[str] (default [])

Mode semantics:
- always: the gate executes whenever it is not skipped by existing skip_* mechanisms.
- auto: the gate executes only when its trigger matches. If not triggered, the gate MUST be
  skipped and MUST emit the exact log line shown below.

Auto mode triggers (decision-only; deterministic):

- Ruff (gate_ruff_mode=auto) triggers if any changed path is:
  - pyproject.toml, or
  - a .py file under any directory prefix listed in ruff_targets.
  If not triggered: `gate_ruff=SKIP (no_matching_files)`

- Mypy (gate_mypy_mode=auto) triggers if any changed path is:
  - pyproject.toml, or
  - a .py file under any directory prefix listed in mypy_targets.
  If not triggered: `gate_mypy=SKIP (no_matching_files)`

- Pytest (gate_pytest_mode=auto) triggers if any changed path is:
  - pyproject.toml or pytest.ini, or
  - a .py file under any directory prefix listed in pytest_targets, or
  - a .py file under src/ or plugins/ or scripts/, or
  - a .js/.mjs/.cjs file under any directory prefix listed in gate_pytest_js_prefixes.
  If not triggered: `gate_pytest=SKIP (no_matching_files)`

Notes:
- In auto mode, trigger evaluation uses the changed paths set for the run (after scope ignore
  filtering), and does not require the files to exist after patch application (deletions may
  still trigger).
- gate_pytest_js_prefixes uses directory-prefix matching: a prefix matches "prefix" exactly
  or any path starting with "prefix/".

### Dedicated CLI flags + precedence

Precedence is fixed: CLI flags > config file (am_patch.toml) > defaults.

Dedicated UX flags are provided so users do not need to use `--override KEY=VALUE` for the
most common mode switches. The flags map to policy keys as follows:

- `--ruff-mode {auto,always}` -> gate_ruff_mode
- `--mypy-mode {auto,always}` -> gate_mypy_mode
- `--pytest-mode {auto,always}` -> gate_pytest_mode
- `--pytest-js-prefixes CSV` -> gate_pytest_js_prefixes

`--pytest-js-prefixes` semantics:
- CSV is a comma-separated list of directory prefixes (example:
  `scripts/patchhub/static,plugins/import/ui/web/assets`).
- Matching uses the same directory-prefix rule as above: "prefix" or "prefix/...".
- Default is an empty list.

These flags MUST override any config file values for the mapped keys.

### 6.1.5 BADGUYS gate (runner-only)

-   Purpose: protect the runner itself by running the badguys suite when
    the runner is modified.
-   Default command argv: `["badguys/badguys.py", "-q"]`
-   Execution: the runner invokes: `python -u <argv...>` (no shell).
-   Success criteria: exit code == 0
-   Controls (precedence: CLI \> config \> defaults):
    -   `gate_badguys_runner = "auto" | "on" | "off"` (default:
        `"auto"`)
        -   `auto`: run only when the current run touches runner files:
            -   `scripts/am_patch.py`
            -   `scripts/am_patch/**`
            -   `scripts/am_patch*.md` (runner docs)
        -   `on`: always run
        -   `off`: never run
    -   `gate_badguys_command = list[str] | str` (default:
        `["badguys/badguys.py", "-q"]`)
        -   If a string is used (cfg or CLI), it is parsed using
            shell-like splitting (shlex).
        -   The value must be non-empty and is treated as argv without
            the python prefix.
    -   `gate_badguys_cwd = "auto" | "workspace" | "clone" | "live"`
        (default: `"auto"`)
        -   `workspace`: run in the current workspace repo (tests the
            patched runner).
        -   `clone`: if invoked from live repo, clone live repo into an
            isolated workspace dir and run there.
        -   `live`: run in live repo root (debug; may conflict with
            runner lock when nested am_patch is spawned).
        -   `auto`: if invoked from a workspace repo, use it; otherwise
            use clone to avoid lock conflicts.
    -   CLI:
        -   `--gate-badguys-runner {auto,on,off}`
        -   `--gate-badguys-command "badguys/badguys.py -q"`
        -   `--gate-badguys-cwd {auto,workspace,clone,live}`

Execution points: - workspace mode: after workspace gates, and again
after promotion (before commit/push) if the runner was touched -
finalize-workspace: after workspace gates and after live gates -
finalize: after live gates

### 6.2 Enforcement

-   Without `-g`: any failing gate stops progression.
-   With `-g`: failures are logged but execution continues.

This behavior is **uniform** across: - workspace gates - live gates -
finalizeworkspace

------------------------------------------------------------------------

### 6.1.6 Docs gate (documentation obligation)

-   Purpose: enforce that documentation is updated when watched code
    areas change.
-   Trigger: the gate is evaluated only if at least one changed path
    matches `gate_docs_include` and does not match `gate_docs_exclude`
    (directory-prefix match with boundary).
-   If triggered, the gate requires that all files listed in
    `gate_docs_required_files` are also present in the changed paths set
    for this run.
-   Controls (precedence: CLI \> config \> defaults):
    -   `gates_skip_docs = true|false` (default: false)
    -   `gate_docs_include = ["src", "plugins"]` (default)
    -   `gate_docs_exclude = ["badguys", "patches"]` (default)
    -   `gate_docs_required_files = ["docs/changes.md", "docs/specification.md"]`

        (default)
-   CLI (optional convenience flags; equivalent overrides are also
    supported):
    -   `--skip-docs`
    -   `--docs-include CSV`
    -   `--docs-exclude CSV`
-   Failure behavior: treated the same as other gates (subject to
    `-g/--allow-gates-fail`).


### 6.1.7 Monolith gate (anti-monolith)

-   Purpose: detect monolith growth and enforce ownership boundaries using read-only AST analysis.
-   Scan set (policy: gate_monolith_scan_scope, gate_monolith_extensions):
    -   patch: analyze only touched existing files whose suffix is in gate_monolith_extensions.
    -   workspace: deterministic scan under ownership roots listed in gate_monolith_areas_prefixes,
        filtering by suffix.
-   JS support: .js uses deterministic heuristics (no external parsers) for exports and internal relative imports.
-   Baseline model (no git): compare new text (cwd/relpath) vs old text (repo_root/relpath).
-   Metrics (old vs new): LOC (non-empty lines), EXPORTS (public export surface; for .js counted via export/module.exports/exports.<name> heuristics), INTERNAL_IMPORTS (distinct internal modules), optional FANIN/FANOUT graph deltas.
-   Parse errors: violation MONO.PARSE; severity controlled by gate_monolith_on_parse_error.
-   Rule IDs (stable API): MONO.PARSE, MONO.GROWTH, MONO.NEWFILE, MONO.HUB, MONO.CORE, MONO.CROSSAREA, MONO.CATCHALL.
-   Mode semantics (policy: gate_monolith_mode):
    -   strict: any violation => FAIL
    -   warn_only: only MONO.CORE, MONO.CATCHALL, and MONO.PARSE (when gate_monolith_on_parse_error=fail) => FAIL; others => WARN
    -   report_only: never FAIL; all violations are reported and final state is WARN

Controls (precedence: CLI > config > defaults):

-   gates_skip_monolith = true|false (default: false)
-   gate_monolith_enabled = true|false (default: true)
-   gate_monolith_mode = strict|warn_only|report_only (default: strict)
-   gate_monolith_scan_scope = patch|workspace (default: patch)
-   gate_monolith_extensions = [".py", ".js", ...] (default: [".py", ".js"])
-   gate_monolith_compute_fanin = true|false (default: true)
-   gate_monolith_on_parse_error = fail|warn (default: fail)
-   gate_monolith_areas_prefixes = list[str] (ownership root prefixes; first match wins)
-   gate_monolith_areas_names = list[str] (logical ownership area names)
-   gate_monolith_areas_dynamic = list[str] (empty string means None; otherwise template string)
-   Thresholds and lists: gate_monolith_* (all are policy keys; see am_patch.toml defaults).

Monolith areas invariants:

-   The three lists MUST have the same length N.
-   For each index i:
    -   gate_monolith_areas_prefixes[i] MUST be non-empty after trim.
    -   gate_monolith_areas_names[i] MUST be non-empty after trim.
    -   gate_monolith_areas_dynamic[i] trimmed:
        -   "" means no dynamic template (None)
        -   otherwise is a template string (example: "plugins.<name>")

Legacy key (no backward compatibility):

-   gate_monolith_areas is no longer supported.
-   If gate_monolith_areas is present in configuration, the runner MUST fail with CONFIG/INVALID.

CLI:

-   --skip-monolith (equivalent to --override gates_skip_monolith=true)

Skip log contract:

-   If skipped by user: gate_monolith=SKIP (skipped_by_user)
-   If disabled by policy: gate_monolith=SKIP (disabled_by_policy)

#### Verbose statistics (DETAIL+INFO)

When the Monolith gate runs and emits the diagnostic section banner `GATE: MONOLITH`,
it MUST also emit the following stable `key=value` statistics lines via the DETAIL
channel (DETAIL+INFO). These lines MUST be emitted for all outcomes (PASS/WARN/FAIL)
but MUST NOT appear when the screen/log level filters out DETAIL (e.g. normal).

Keys and types:

-   gate_monolith_files_scanned=int
-   gate_monolith_files_new=int
-   gate_monolith_parse_errors_new=int
-   gate_monolith_parse_errors_old=int
-   gate_monolith_loc_total_old=int
-   gate_monolith_loc_total_new=int
-   gate_monolith_loc_total_delta=int
-   gate_monolith_imports_total_old=int
-   gate_monolith_imports_total_new=int
-   gate_monolith_imports_total_delta=int
-   gate_monolith_exports_total_old=int
-   gate_monolith_exports_total_new=int
-   gate_monolith_exports_total_delta=int
-   gate_monolith_fanin_delta_max=int|n/a
-   gate_monolith_fanout_delta_max=int|n/a

Fan delta semantics:

-   The value is the maximum positive delta observed across scanned files,
    computed as (new - old).
-   If gate_monolith_compute_fanin=false, both fan delta keys MUST be emitted
    with the literal value `n/a`.
## 7. Promotion Rules

### 7.1 Workspace live

Promotion set includes: - Declared & touched files - Blessed gate
outputs - (plus any additional files when `-a` is active)

Promotion hygiene excludes deterministic junk (e.g. runner caches),
independent of scope logic.

### 7.2 Live-changed resolution

If promotion detects that the live repo changed since `base_sha` for one
or more files in the promotion set, the runner applies an explicit
resolution policy.

Controls (precedence: CLI \> config \> defaults): - CLI (full help only,
long form): - `--overwrite-live` : overwrite live with the workspace
version for the conflicting files. - `--overwrite-workspace` : keep the
live version and skip promoting the conflicting files. -
`--allow-live-changed` : legacy alias for `--overwrite-live`. - Config /
overrides: -
`live_changed_resolution = "fail" | "overwrite_live" | "overwrite_workspace"`

Default behavior: - `live_changed_resolution = "fail"` and
`fail_if_live_files_changed = true` =\> promotion FAILS with
`LIVE_CHANGED`.

This behavior applies to workspace promotion and `-w` /
`--finalize-workspace`.

### 7.3 Failure zip archive hygiene

When building the failure zip, the runner excludes repository internals
and tool/runtime caches from the archived
`changed/touched subset (no full workspace)` tree:

-   `.git/`
-   `venv/`, `.venv/`
-   `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
-   `__pycache__/`
-   `*.pyc`

This is independent of scope logic and does not affect patch execution,
gates, or promotion semantics.

Failure zip naming and retention:

-   Legacy mode (default): when `failure_zip_template` is empty, the
    runner writes `failure_zip_name` (default: `patched.zip`).
-
Placeholders: {issue}, {ts}, {nonce}, {log}, {attempt}.
- {attempt} is the per-issue workspace attempt counter (1,2,3...).
- In -w / --finalize-workspace, the runner bumps the workspace attempt counter at the
  start of the run, so {attempt} increments across repeated finalize attempts.
- For retention safety with lexicographic sorting, prefer padding via format spec,
  e.g. {attempt:04d}.

Template mode: when `failure_zip_template` is set, the runner renders the filename
using `{issue}` and may also use `{ts}`, `{nonce}`, `{log}`, `{attempt}`.
-   Before writing a new failure zip, the runner applies per-issue
    retention using `failure_zip_cleanup_glob_template` and
    `failure_zip_keep_per_issue` (default: keep 1).
-   After writing a failure zip, the runner applies the same per-issue
    retention again, ensuring the newest zip is always included in the
    retained set.
-   After a successful commit, the runner removes failure zips for that
    issue when `failure_zip_delete_on_success_commit` is true.

Workspace failure subset (general): - In workspace mode, the failure zip
MUST include the deterministic union of: - the per-issue cumulative
`allowed_union` set, - the workspace `changed_paths` snapshot
immediately after the patch attempt (before gates), - patch targets
(declared/touched targets in unified mode; touched delta in script
mode).

Finalize-workspace failure subset: - In `-w` / `--finalize-workspace`,
the failure zip MUST include the workspace changed/touched subset even
if the run fails during workspace gates, promotion, or live gates. - The
subset is the deterministic union of: - workspace `changed_paths`
snapshot before workspace gates, - workspace `changed_paths` snapshot
after workspace gates (to capture gate-induced edits such as
formatting), - the `files_to_promote` list computed from the promotable
workspace change set.

## 1.2 Workspace rollback after failure

Workspace rollback after a failed run is controlled by
`rollback_workspace_on_fail`.

CLI: - `--rollback-workspace-on-fail {none-applied,always,never}`

Config: - `rollback_workspace_on_fail = "none-applied"|"always"|"never"`

Semantics on failure (`RESULT: FAIL`): - `none-applied`: rollback
workspace only if 0 patches were applied successfully
(`applied_ok == 0`) - `always`: rollback workspace on any failure
(including partial apply) - `never`: never rollback workspace
automatically

The runner MUST log a single summary line stating whether rollback was
executed or skipped, including the selected mode and `applied_ok`.

------------------------------------------------------------------------

## 7.4 Success archive (git-archive zip)

On SUCCESS (in `workspace`, `--finalize-live`, and `-w` /
`--finalize-workspace` modes; excluding `--test-mode`), the runner
creates a clean git-archive success zip as a clean `git archive HEAD`
snapshot of the final live repository state.

Naming:
- The output filename is controlled by `success_archive_name`
  (default `{repo}-{branch}.zip`, e.g. `audiomason2-main.zip`).
- Supported placeholders for success_archive_name:
  - {repo}: repository name
  - {branch}: current branch (or "detached")
  - {issue}: issue id from CLI (fallback: "noissue")
  - {ts}: HEAD committer time in UTC (YYYYMMDD_%H%M%S), not runtime time
- Example:
  - "{repo}-{branch}-issue{issue}-{ts}.zip"

Destination directory:
- The output directory is controlled by `success_archive_dir`:
  - "patch_dir": write to `patches/` (default)
  - "successful_dir": write to `patches/successful/`

Deterministic retention (optional):
- Retention is enabled only when:
  - `success_archive_keep_count > 0`, AND
  - `success_archive_cleanup_glob_template` is non-empty.
- The runner MUST enforce deterministic retention after writing the new
  success archive:
  1. List candidates using `success_archive_cleanup_glob_template`
     (glob) in the selected destination directory.
  2. Sort candidates lexicographically by filename (not by mtime).
  3. Never delete the newly created success archive.
  4. Delete from the start of the sorted list until
     `count <= success_archive_keep_count`.
- Use of filesystem timestamps (mtime) is forbidden.

CLI flags (dedicated; precedence CLI > config > defaults):
- --success-archive-dir {patch_dir,successful_dir}
- --success-archive-cleanup-glob TEMPLATE
- --success-archive-keep-count N

The runner writes both the failure zip and the success archive zip
atomically (tmp file + replace + fsync) so they are safe to read
immediately after the run. It contains only git-tracked files (as if
fetched from the remote) and does not include logs, workspaces, caches,
or patch inputs.

------------------------------------------------------------------------

## 7.5 Issue diff bundle (artifacts)

On SUCCESS (in `workspace`, `--finalize-live`, and `-w` / `--finalize-workspace` modes;
excluding `--test-mode`), the runner creates an issue diff bundle zip under
`patches/artifacts/`.

Naming: `issue_<issue>_diff.zip` (suffix `_v2`, `_v3`, ... on collision);
`issue_FINALIZE_<ts>_diff.zip` when ISSUE_ID is not provided (finalize pseudo-issue).

Contents (normative):
- `manifest.txt` (issue id, base sha, files list, diff entries list,
  logs list, snapshot entries list)
- `diff/` (per-file unified diffs: `diff/<repo_rel_path>.patch`)
- `files/` (full file snapshots: `files/<repo_rel_path>`; MUST be byte-exact content of the file
  as present in the working tree at bundle creation time)
- `logs/` (the relevant run log(s))

Required inputs: `base_sha` MUST be set before posthook runs and MUST NOT be missing on SUCCESS.
`files_to_promote` MUST be the deterministic file set used for promotion/commit.

Base SHA by mode: `workspace` and `-w` / `--finalize-workspace`:
`base_sha = workspace_base_sha`. `--finalize-live`: `base_sha = head_sha` at finalize start.

Runner MUST log `issue_diff_base_sha` and `issue_diff_paths_count` before writing the diff bundle.

## 8. Git Behavior

### 8.1 Commit

-   Commit failure stops runner.
-   Repository remains dirty.
-   Staging rules:
    -   In `--finalize-live` (aka `-f`) mode, the runner stages the
        entire live working tree before commit.
    -   In `workspace` and `-w` / `--finalize-workspace` modes, the
        runner commits only the paths it has promoted (those paths are
        staged explicitly during promotion). Any unrelated dirty changes
        in the live working tree remain uncommitted and continue to
        appear as dirty after the run.

### 8.2 Push

-   Push failure may be allowed by policy.
-   Commit remains local.

### 8.3 No autonomous rebase

Pull/rebase only when explicitly enabled.

------------------------------------------------------------------------

## 9. Workspace Rules

-   Workspaces may be reused.
-   Dirty workspaces are allowed.
-   Workspace deletion occurs only on SUCCESS and only if enabled.

------------------------------------------------------------------------

## 10. Logging Contract

A single primary log includes: - runner version - effective
configuration with sources - declared FILES - gate execution results -
promotion plan - commit SHA (if any)

------------------------------------------------------------------------

## 11. Success Definition

Runner SUCCESS guarantees: - at least one real change (unless explicitly
allowed) - no unintended scope violations - gates passed or were
explicitly overridden - promotion and commit behavior followed policy

------------------------------------------------------------------------

## 12. Authority

This document defines correctness. If implementation diverges, the
implementation is wrong.

## 13. Post-success Audit Step

After a run reaches SUCCESS **with commit+push completed successfully**,
the runner executes an additional **AUDIT** step:

-   Command executed:

        python3 -u audit/audit_report.py

-   Working directory: live repository root.

-   Purpose: display the current audit status reflecting the just-pushed
    changes.

-   Scope:

    -   In `workspace` mode and `-w` / `--finalize-workspace`, it runs
        **after** workspace deletion (when enabled).
    -   In `--finalize-live`, there is no workspace; it runs after
        `SUCCESS`.
    -   It never reads or mutates the workspace.

Failure semantics: - If the audit command exits non-zero, the run FAILS
with stage `AUDIT`. - No rollback is performed (code is already
committed and pushed).

### Console color output

The runner may emit ANSI colors on stdout for the tokens: - OK, FAIL in
normal progress lines - SUCCESS, FAIL in the final RESULT summary - OK,
FAIL in PUSH summary - FILE lines in the final FILES block (when
printed) may be colored yellow (ANSI palette index 11) when color is
enabled.

Implementation note: - Use ANSI 256-color yellow (palette 11):
\\x1b\[38;5;11m. Exact RGB is not guaranteed; this is widely supported
when 256-color is available.

Controls: - Policy/config key: console_color (auto\|always\|never,
default auto) - CLI: --color {auto,always,never} and --no-color (alias
for never) - Env: NO_COLOR forces never

Precedence: NO_COLOR \> CLI \> config \> default.

------------------------------------------------------------------------

## Appendix A. Implemented CLI Surface and Policy Coverage

Tento dodatok enumeruje poloky, ktor existuj v implementcii
(`scripts/am_patch/cli.py`, `scripts/am_patch/config.py`), ale neboli
explicitne pomenovan v hlavnch astiach tejto pecifikcie v ase auditu.

### A.1 CLI flags poloky chbajce v texte pecifikcie

### artifacts/logging

-   `--current-log-symlink` changes names/locations of logs and
    artifacts
-   `--current-log-symlink-name` changes names/locations of logs and
    artifacts
-   `--failure-zip-log-dir` changes names/locations of logs and
    artifacts
-   `--failure-zip-name` changes names/locations of logs and artifacts
-   `--failure-zip-patch-dir` changes names/locations of logs and
    artifacts
-   `--log-template-finalize` changes names/locations of logs and
    artifacts
-   `--log-template-issue` changes names/locations of logs and artifacts
-   `--no-current-log-symlink` changes names/locations of logs and
    artifacts

### core-behavior

-   `--allow-undeclared-paths` changes patching outcome/safety or gate
    logic
-   `--allow-untouched-files` changes patching outcome/safety or gate
    logic
-   `--enforce-allowed-files` changes patching outcome/safety or gate
    logic
-   `--gates-on-partial-apply` changes patching outcome/safety or gate
    logic
-   `--gates-on-zero-apply` changes patching outcome/safety or gate
    logic
-   `--gates-order` changes patching outcome/safety or gate logic
-   `--live-repo-guard` changes patching outcome/safety or gate logic
-   `--live-repo-guard-scope` changes patching outcome/safety or gate
    logic
-   `--no-rollback-on-commit-push-failure` changes patching
    outcome/safety or gate logic
-   `--no-rollback-workspace-on-fail` changes patching outcome/safety or
    gate logic

### misc

-   `--blessed-gate-output` auxiliary switch
-   `--patch-dir-name` auxiliary switch
-   `--patch-layout-logs-dir` auxiliary switch
-   `--patch-layout-successful-dir` auxiliary switch
-   `--patch-layout-unsuccessful-dir` auxiliary switch
-   `--patch-layout-workspaces-dir` auxiliary switch
-   `--post-success-audit` auxiliary switch
-   `--pytest-use-venv` auxiliary switch
-   `--require-push-success` auxiliary switch
-   `--rerun-latest` auxiliary switch
-   `--ruff-autofix-legalize-outside` auxiliary switch
-   `--ruff-format` auxiliary switch
-   `--scope-ignore-contains` auxiliary switch
-   `--scope-ignore-prefix` auxiliary switch
-   `--scope-ignore-suffix` auxiliary switch
-   `--soft-reset-workspace` auxiliary switch
-   `--success-archive-name` auxiliary switch
-   `--venv-bootstrap-mode` auxiliary switch
-   `--venv-bootstrap-python` auxiliary switch
-   `--version` auxiliary switch
-   `--workspace-history-logs-dir` auxiliary switch
-   `--workspace-history-oldlogs-dir` auxiliary switch
-   `--workspace-history-oldpatches-dir` auxiliary switch
-   `--workspace-history-patches-dir` auxiliary switch
-   `--workspace-issue-dir-template` auxiliary switch
-   `--workspace-meta-filename` auxiliary switch
-   `--workspace-repo-dir-name` auxiliary switch

### sandbox

-   `--patch-jail` changes isolation and security boundaries
-   `--patch-jail-unshare-net` changes isolation and security boundaries

### A.2 Policy ke poloky chbajce v texte pecifikcie

This appendix is resolved by the authoritative policy glossary:
- scripts/am_patch_policy_glossary.md

### gates

-   `gates_allow_fail` changes which gates run and in what order
-   `gates_order` changes which gates run and in what order
-   `gates_skip_mypy` changes which gates run and in what order
-   `gates_skip_pytest` changes which gates run and in what order
-   `gates_skip_ruff` changes which gates run and in what order
-   `mypy_targets` changes which gates run and in what order
-   `pytest_targets` changes which gates run and in what order
-   `pytest_use_venv` changes which gates run and in what order
-   `run_all_tests` changes which gates run and in what order

### git-safety

-   `allow_non_main` men bezpenostn predpoklady (branch/up-to-date)
-   `enforce_main_branch` men bezpenostn predpoklady (branch/up-to-date)
-   `require_up_to_date` men bezpenostn predpoklady (branch/up-to-date)
-   `skip_up_to_date` men bezpenostn predpoklady (branch/up-to-date)

### misc

-   `audit_rubric_guard` doplnkov policy k
-   `default_branch` doplnkov policy k
-   `live_repo_guard` doplnkov policy k
-   `live_repo_guard_scope` doplnkov policy k
-   `repo_root` doplnkov policy k
-   `ruff_autofix` doplnkov policy k
-   `ruff_autofix_legalize_outside` doplnkov policy k
-   `ruff_format` doplnkov policy k

### patch-format

-   `ascii_only_patch` changes patch application mode
-   `unified_patch` changes patch application mode
-   `unified_patch_continue` changes patch application mode
-   `unified_patch_strip` changes patch application mode
-   `unified_patch_touch_on_fail` changes patch application mode

### sandbox

-   `patch_jail` men izolciu behu
-   `patch_jail_unshare_net` men izolciu behu

### scope/promotion

-   `allow_declared_untouched` changes scope/rollback/promotion rules
-   `allow_no_op` changes scope/rollback/promotion rules
-   `allow_outside_files` changes scope/rollback/promotion rules
-   `allow_push_fail` changes scope/rollback/promotion rules
-   `declared_untouched_fail` changes scope/rollback/promotion rules
-   `enforce_allowed_files` changes scope/rollback/promotion rules
-   `no_op_fail` changes scope/rollback/promotion rules
-   `no_rollback` changes scope/rollback/promotion rules

### workflow

-   `post_success_audit` changes runner workflow
-   `soft_reset_workspace` changes runner workflow
-   `test_mode` changes runner workflow
-   `test_mode_isolate_patch_dir` changes runner workflow
-   `update_workspace` changes runner workflow

## NDJSON event log

When json_out is enabled, the runner writes a debug-complete NDJSON (JSONL) event log.
This is an additional render of the same log emission events (it does not replace diagnostics).

Location:
- The NDJSON file is written under patch_layout_json_dir (under patch_dir).
- The NDJSON filename is deterministic and is NOT derived from the regular log filename.
- Workspace/issue runs: am_patch_issue_<ISSUE>.jsonl
- Finalize (including finalize-workspace): am_patch_finalize.jsonl

Behavior:
- The NDJSON file is current-only and is truncated at the start of each run.
- The NDJSON sink is debug-complete: it records every Logger.emit(...) call (no filtering by verbosity/log_level).
- Full error detail (failed step stdout/stderr) must be included.
- By default it must bypass filtering.
- Exception: for Ruff/Biome autoformat/autofix steps, the failed-step dump must be
  emitted without bypass, using DETAIL+WARNING.
- The JSON sink is best-effort; failures to write NDJSON must not change runner behavior.

Format:
- One JSON object per line (NDJSON).
- Event types: hello, log, result.
- log events include: seq, ts_mono_ms, stage, kind, sev, ch, summary, bypass, msg.
- Failed step detail may include stdout and stderr fields.

## IPC socket

The runner exposes an optional Unix domain socket control plane.

Protocol:
- protocol id: am_patch_ipc/1
- transport: Unix domain socket (AF_UNIX stream)
- framing: newline-delimited JSON (NDJSON)

Message envelopes (mandatory):

Client -> runner command:
- {"type":"cmd","cmd":"<command>","cmd_id":"<string>","args":{...}}

Runner -> client reply:
- {"type":"reply","cmd_id":"<string>","ok":true,"data":{...}}
- {"type":"reply","cmd_id":"<string>","ok":false,"error":{"code":"<ERR_CODE>","message":"<text>"}}

Event stream (runner -> client):
- NDJSON events identical to the runner NDJSON event model (hello/log/result)
- control events: {"type":"control","event":"<name>", ...}

Default location:
- ipc_socket_enabled = true
- ipc_socket_mode = patch_dir
- ipc_socket_name_template = am_patch_ipc_{issue}_{pid}.sock
- In patch_dir mode, the socket path is <patch_dir>/<rendered name>.

Configuration keys (Policy):
- ipc_socket_enabled: bool
- ipc_socket_mode: patch_dir|base_dir|system_runtime
- ipc_socket_path: explicit path override (highest priority)
- ipc_socket_name_template: filename template (no path separators)
- ipc_socket_base_dir: used when mode=base_dir
- ipc_socket_system_runtime_dir: optional override when mode=system_runtime

CLI overrides:
- --ipc-socket PATH
- --no-ipc-socket
- --ipc-socket-mode MODE
- --ipc-socket-base-dir DIR
- --ipc-socket-name-template TEMPLATE

Commands (cmd field):
- ping
- get_state
- cancel
- stop_after_step (args: {"step":"<STEP>"})
- pause_after_step (args: {"step":"<STEP>"})
- resume
- set_verbosity (args: {"verbosity":"<level>","log_level":"<level>"})

Semantics:
- cancel requests termination at the next safe boundary.
- stop_after_step terminates when the named step completes.
- pause_after_step pauses the main thread when the named step completes; resume continues.
- resume returns INVALID_STATE if the runner is not paused.
- Priority at a boundary: cancel > stop_after_step > pause_after_step.

The safe boundary definition is the emission of an OK/FAIL step token ("OK: <STEP>" or "FAIL: <STEP>").

Socket file lifecycle:
- The runner MUST attempt to remove the IPC socket file on process exit, best-effort.
  (Success or failure.)
- The runner MAY delay socket removal after exit, controlled by:
  - ipc_socket_cleanup_delay_success_s (exit code 0)
  - ipc_socket_cleanup_delay_failure_s (exit code non-0 and exceptions)
- Exceptions are treated as failure for cleanup delay.

Startup behavior when socket path exists:
- Controlled by ipc_socket_on_startup_exists:
  - fail (default): fail-fast with SOCKET_EXISTS
  - wait_then_fail: wait ipc_socket_on_startup_wait_s seconds, then fail if still exists
  - unlink_if_stale: connect-test; unlink only if connect fails; otherwise fail with SOCKET_EXISTS
- The runner MUST NOT unlink an existing socket without an explicit stale-detection step
  (except unlink_if_stale after a failed connect-test).

Constant socket names:
- ipc_socket_name_template MAY be a constant string (example: am_patch.sock).
- Consequence: single-instance socket in the selected scope; parallel runs conflict unless
  the name differs.

------------------------------------------------------------------------

## PatchHub Config Editor Contract

PatchHub may edit the runner configuration file:
- scripts/am_patch/am_patch.toml

The normative meaning of Policy keys is defined by the runner-owned glossary file:
- scripts/am_patch_policy_glossary.md
Schema export "help" strings MUST be consistent with that glossary.

The runner provides an authoritative schema export describing the Policy surface and
PatchHub-safe editing rules.

Schema export:
- Module: scripts/am_patch/config_schema.py
- Function: get_policy_schema() -> dict
- Schema version field: schema_version (string)
- The implementation constant SCHEMA_VERSION MUST be bumped when the schema shape changes.

Editing engine:
- Module: scripts/am_patch/config_edit.py
- validate_patchhub_update(values: dict, schema: dict) -> dict
  - Reject unknown keys.
  - Reject read-only keys.
  - Enforce schema types and enum allow-lists.
- apply_update_to_config_text(original_text: str, values: dict, schema: dict) -> str
  - Preserve comments and ordering.
  - Only modify RHS of canonical key assignments.
  - Insert missing keys into the schema-declared TOML section.
  - After edit, validate using the existing build_policy pathway.
- validate_config_text_roundtrip(text: str) -> None
  - Parse TOML, flatten sections, build Policy.
  - Raise RunnerError on failure.

------------------------------------------------------------------------
