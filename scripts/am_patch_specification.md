# AM Patch Runner - Functional Specification v4 (UPDATED)



This document reflects the **current, implemented behavior** of the AM Patch Runner
after introduction of:
- `-w` / `--finalize-workspace`
- blessed gate outputs
- workspace cleanup semantics parity

This document is **authoritative** for current runner behavior.

---

## 0. Core Principles (NonNegotiable)

### 0.1 Universal controllability
Every runner behavior is controllable via:
- CLI flags **or**
- `--override KEY=VALUE` overrides,
with precedence: **CLI > config > defaults**.

#
### Phase 2: hardcoded settings must be configurable

The runner must not hardcode operational paths, filenames, workspace layout, or scope exemptions.
Every such setting must be configurable via:

1) config file key (am_patch.toml), and
2) CLI override (either a dedicated flag or --override KEY=VALUE).

The config file path itself is CLI-only and must not be a config key.

The following keys are normative (defaults shown):

- patch_dir_name = "patches"
- patch_layout_logs_dir = "logs"
- patch_layout_workspaces_dir = "workspaces"
- patch_layout_successful_dir = "successful"
- patch_layout_unsuccessful_dir = "unsuccessful"
- lockfile_name = "am_patch.lock"
- current_log_symlink_name = "am_patch.log"
- current_log_symlink_enabled = true
- log_ts_format = "%Y%m%d_%H%M%S"
- log_template_issue = "am_patch_issue_{issue}_{ts}.log"
- log_template_finalize = "am_patch_finalize_{ts}.log"
- failure_zip_name = "patched.zip"
- failure_zip_log_dir = "logs"
- failure_zip_patch_dir = "patches"
- workspace_issue_dir_template = "issue_{issue}"
- workspace_repo_dir_name = "repo"
- workspace_meta_filename = "meta.json"
- workspace_history_logs_dir = "logs"
- workspace_history_oldlogs_dir = "oldlogs"
- workspace_history_patches_dir = "patches"
- workspace_history_oldpatches_dir = "oldpatches"
- blessed_gate_outputs = ["audit/results/pytest_junit.xml"]
- scope_ignore_prefixes = [".am_patch/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "__pycache__/"]
- scope_ignore_suffixes = [".pyc"]
- scope_ignore_contains = ["/__pycache__/"]
- venv_bootstrap_mode = "auto"  (allowed: auto|always|never)
- venv_bootstrap_python = ".venv/bin/python"
- rollback_workspace_on_fail = "none-applied"  (allowed: none-applied|always|never)

These keys affect concrete behavior:
- filesystem locations (patch dir layout and workspace layout),
- log naming and the optional current-log symlink,
- the name and internal structure of the failure diagnostics zip,
- which changed paths are ignored for scope enforcement and promotion hygiene,
- early venv interpreter bootstrap behavior.

## 0.2 Determinism over convenience
The runner never guesses, never implicitly expands scope, and never mutates state
without explicit authorization.

---

## 1. Version Visibility

The runner prints its version:
- on every invocation
- in `--help`

Example:
```
am_patch RUNNER_VERSION=4.2.24
```

---


## 1.1 Verbosity and status output

Runner supports 4 verbosity modes for screen output:

- debug: maximum screen output + status bar
- verbose: current (legacy) behavior + status bar
- normal: only DO/OK/FAIL lines for executed steps + status bar
- quiet: no progress output and no status bar; only final summary

Verbosity inheritance (contract):
- Verbosity modes are cumulative. Each higher mode MUST include all guaranteed outputs of the next lower mode,
  and MAY add additional detail.

CLI:
- `-q`/`-v`/`-n`/`-d` / `--verbosity {debug,verbose,normal,quiet}` (default: `verbose`)

Status indicator:
- TTY: single-line overwrite on stderr: `STATUS: <STAGE>  ELAPSED: <mm:ss>`
- non-TTY: periodic heartbeat on stderr: `HEARTBEAT: <STAGE> elapsed=<mm:ss>`
- disabled in `quiet`

Final summary (always printed at the end):
- SUCCESS:
  - `RESULT: SUCCESS`
  - `FILES:` block (only when `PUSH: OK`), formatted strictly:

    FILES:

    A path1
    M path2
    D path3

  - `COMMIT: <sha>` or `(none)`
  - `PUSH: OK|FAIL|UNKNOWN` (when commit/push is enabled)
  - `LOG: <path>`
- FAIL:
  - `RESULT: FAIL`
  - `STAGE: <stage-id>[, <stage-id>...]`
  - When multiple failures occur in a single run, STAGE MUST be a single line
    with a comma-separated list of all known failing stages (deterministic order).
  - `REASON: <one line>`
  - `LOG: <path>`

Priority rule (normative):
- If patch application fails (e.g., `git apply` fails in unified patch mode), the final FAIL summary MUST report `STAGE: PATCH_APPLY`.
- Any later problems discovered in subsequent steps (e.g., scope enforcement) MAY be logged as secondary failures but MUST NOT override the primary PATCH_APPLY failure.


## 2. Modes of Operation

### 2.1 Workspace mode (default)
- Requires `ISSUE_ID` positional argument.
- Patch execution and gates run in a workspace.
- Promotion to live occurs only after successful validation.

### 2.2 Finalize mode (`-f`)
- Operates directly on the live repository.
- No workspace is created or used.
- Commit message is provided via `-f`.

### 2.3 Finalizeworkspace mode (`--finalize-workspace ISSUE_ID`)
- Operates on an **existing workspace**.
- No patch script is executed.
- Commit message is read from `patches/workspaces/issue_<ID>/meta.json`.
- Execution order:
  1. Gates in workspace
  2. Promotion workspace  live
  3. Gates in live
  4. Commit + push

### 2.4 Test mode (`--test-mode`)
- Workspace-only mode intended for runner testing (e.g. badguys).
- Patch execution and gates run in the workspace as usual.
- After workspace gates and the live-repo guard check (after gates), the runner performs a hard STOP:
  - no promotion to live,
  - no live gates,
  - no commit/push,
  - no patch archives,
  - no patched.zip artifacts.
- Workspace directory is deleted on exit (SUCCESS or FAILURE).

Workspace cleanup:
- In test mode, the workspace is deleted on exit ALWAYS (SUCCESS or FAILURE).
- `-k` is ignored in test mode.
- `delete_workspace_on_success` does not apply in test mode.

---

## 3. Configuration System

### 3.1 Config file
- Path: `scripts/am_patch/am_patch.toml`
- Loaded on every run.
- Source of each effective value is logged.

### 3.2 CLI (normative)

### 3.2.1 Help contract

The runner provides two help views:

- `--help` (`-h`) prints short help (common workflow options only).
- `--help-all` (`-H`) prints full help (workflow-grouped reference).

Rules:

- Options shown in short help may have both short and long forms.
- Options not in short help are long-only (no short aliases).
- Full help shows options in long form; for short-help options, the short alias is shown in parentheses.
- Short help does not show defaults.

### 3.2.2 Config introspection

- `--show-config` (`-c`) prints the effective policy/config and exits.
  It prints the same effective output normally logged at the start of a run.

### 3.2.3 Promotion toggle (commit/push)

- `--disable-promotion` sets `commit_and_push=false`.

Effects:
- Patch mode: gates run, but the runner does not commit or push.
- `--finalize-live`: gates run, but the runner does not commit or push.
- `-w` / `--finalize-workspace`: workspace promotion still occurs and gates run in both workspace and live repo, but the runner does not commit or push. In this case, the workspace is preserved to avoid losing the easiest re-run path while the live repo has uncommitted changes.

This toggle affects only commit/push behavior. It does not change patch execution, gates, or workspace promotion semantics.


### 3.2.4 Overrides symmetry

Every behavior has a config key and is overridable via CLI, primarily via:

- `--override KEY=VALUE` (repeatable)


---

## 4. Patch Contract (Scope)

### 4.1 Mandatory FILES declaration
Patch scripts must declare intended paths via `FILES = [...]`.

### 4.2 Scope enforcement
Default:
- Touching undeclared files  FAIL
- Declaring but not touching  FAIL
- Noop patch  FAIL

All are overrideable.

When reusing an issue workspace across multiple runs, the runner maintains a per-issue cumulative
allowlist ("allowed union") of paths that were previously legalized for this ISSUE_ID.

Scope enforcement MUST allow touched paths that are either:
- declared by the current patch (FILES), or
- present in the per-issue allowed union, or
- blessed gate outputs.

This ensures repeated patching within the same ISSUE_ID does not require `-a` solely due to
prior legalized changes in the reused workspace.

### 4.3 Blessed gate outputs
Some files are explicitly allowlisted as **gateproduced audit artifacts**.

Current allowlist:
- `audit/results/pytest_junit.xml`

Properties:
- Do **not** trigger scope violations
- Do **not** require `-a`
- Are automatically promotable and committable when changed

This mechanism is **separate from** `-a`.

---

## 5. `-a` (Allow outside files)

`-a` is a **strong override** intended for large refactors.

Semantics:
- Legalizes touching undeclared files
- Expands promotion scope accordingly
- Should be used deliberately and sparingly

`-a` is **not required** for blessed gate outputs.

---

## 6. Gates

### 6.1 Execution
- Gates run after the patch is applied (unified or script).
- If patch apply fails, gates may still run only when explicitly enabled by policy:
  - gates_on_partial_apply: run gates after partial apply failure (some files applied).
  - gates_on_zero_apply: run gates after zero apply failure (nothing applied).
- When gates run after patch apply failure, the run remains FAIL with PATCH_APPLY as the primary reason.
- Default gate order is:
  1) COMPILE (python bytecode compilation)
  2) Ruff
  3) Pytest
  4) Mypy
  5) Docs (documentation obligation)
- Individual gates may be configured on/off.


### 6.1.1 COMPILE gate
- Purpose: fail fast on syntax errors after patch application.
- Implementation: runs `python -m compileall -q` in the workspace repo root.
  - Targets: `compile_targets` (default: `["."]`).
  - Exclude: `compile_exclude` (default: `[]`) is compiled into a `compileall -x <regex>` directory filter.
- Config:
  - `compile_check = true|false` (default: true)
  - `compile_targets = ["...", ...]` (default: `["."]`)
  - `compile_exclude = ["...", ...]` (default: `[]`)
- CLI override:
  - `--no-compile-check` disables this gate for the run.
  - `--override compile_targets=...` and `--override compile_exclude=...` follow the same list format as `ruff_targets`.
- Failure behavior is identical to other gates: the run fails with `GATE:COMPILE`, `patched.zip` is produced, and `patched_success.zip` is not.

### 6.1.2 BADGUYS gate (runner-only)
- Purpose: protect the runner itself by running the badguys suite when the runner is modified.
- Default command argv: `["badguys/badguys.py", "-q"]`
- Execution: the runner invokes: `python -u <argv...>` (no shell).
- Success criteria: exit code == 0
- Controls (precedence: CLI > config > defaults):
  - `gate_badguys_runner = "auto" | "on" | "off"` (default: `"auto"`)
    - `auto`: run only when the current run touches runner files:
      - `scripts/am_patch.py`
      - `scripts/am_patch/**`
      - `scripts/am_patch*.md` (runner docs)
    - `on`: always run
    - `off`: never run
  - `gate_badguys_command = list[str] | str` (default: `["badguys/badguys.py", "-q"]`)
    - If a string is used (cfg or CLI), it is parsed using shell-like splitting (shlex).
    - The value must be non-empty and is treated as argv without the python prefix.
  - `gate_badguys_cwd = "auto" | "workspace" | "clone" | "live"` (default: `"auto"`)
    - `workspace`: run in the current workspace repo (tests the patched runner).
    - `clone`: if invoked from live repo, clone live repo into an isolated workspace dir and run there.
    - `live`: run in live repo root (debug; may conflict with runner lock when nested am_patch is spawned).
    - `auto`: if invoked from a workspace repo, use it; otherwise use clone to avoid lock conflicts.
  - CLI:
    - `--gate-badguys-runner {auto,on,off}`
    - `--gate-badguys-command "badguys/badguys.py -q"`
    - `--gate-badguys-cwd {auto,workspace,clone,live}`

Execution points:
- workspace mode: after workspace gates, and again after promotion (before commit/push) if the runner was touched
- finalize-workspace: after workspace gates and after live gates
- finalize: after live gates

### 6.2 Enforcement
- Without `-g`: any failing gate stops progression.
- With `-g`: failures are logged but execution continues.

This behavior is **uniform** across:
- workspace gates
- live gates
- finalizeworkspace

---


### 6.1.3 Docs gate (documentation obligation)
- Purpose: enforce that documentation is updated when watched code areas change.
- Trigger: the gate is evaluated only if at least one changed path matches `gate_docs_include`
  and does not match `gate_docs_exclude` (directory-prefix match with boundary).
- If triggered, the gate requires that all files listed in `gate_docs_required_files` are also
  present in the changed paths set for this run.
- Controls (precedence: CLI > config > defaults):
  - `gates_skip_docs = true|false` (default: false)
  - `gate_docs_include = ["src", "plugins"]` (default)
  - `gate_docs_exclude = ["badguys", "patches"]` (default)
  - `gate_docs_required_files = ["docs/changes.md", "docs/specification.md"]` (default)
- CLI (optional convenience flags; equivalent overrides are also supported):
  - `--skip-docs`
  - `--docs-include CSV`
  - `--docs-exclude CSV`
- Failure behavior: treated the same as other gates (subject to `-g/--allow-gates-fail`).

## 7. Promotion Rules

### 7.1 Workspace  live
Promotion set includes:
- Declared & touched files
- Blessed gate outputs
- (plus any additional files when `-a` is active)

Promotion hygiene excludes deterministic junk
(e.g. runner caches), independent of scope logic.

### 7.2 Live-changed resolution

If promotion detects that the live repo changed since `base_sha` for one or more files in the promotion set,
the runner applies an explicit resolution policy.

Controls (precedence: CLI > config > defaults):
- CLI (full help only, long form):
  - `--overwrite-live` : overwrite live with the workspace version for the conflicting files.
  - `--overwrite-workspace` : keep the live version and skip promoting the conflicting files.
  - `--allow-live-changed` : legacy alias for `--overwrite-live`.
- Config / overrides:
  - `live_changed_resolution = "fail" | "overwrite_live" | "overwrite_workspace"`

Default behavior:
- `live_changed_resolution = "fail"` and `fail_if_live_files_changed = true` => promotion FAILS with `LIVE_CHANGED`.

This behavior applies to workspace promotion and `-w` / `--finalize-workspace`.

### 7.3 Archive hygiene (`patched.zip`)

When building `patched.zip`, the runner excludes repository internals and tool/runtime caches from the archived `changed/touched subset (no full workspace)` tree:

- `.git/`
- `venv/`, `.venv/`
- `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `__pycache__/`
- `*.pyc`

This is independent of scope logic and does not affect patch execution, gates, or promotion semantics.


## 1.2 Workspace rollback after failure

Workspace rollback after a failed run is controlled by `rollback_workspace_on_fail`.

CLI:
- `--rollback-workspace-on-fail {none-applied,always,never}`

Config:
- `rollback_workspace_on_fail = "none-applied"|"always"|"never"`

Semantics on failure (`RESULT: FAIL`):
- `none-applied`: rollback workspace only if 0 patches were applied successfully (`applied_ok == 0`)
- `always`: rollback workspace on any failure (including partial apply)
- `never`: never rollback workspace automatically

The runner MUST log a single summary line stating whether rollback was executed or skipped, including
the selected mode and `applied_ok`.

---

## 7.4 Success archive (git-archive zip)

On SUCCESS (in `workspace`, `--finalize-live`, and `-w` / `--finalize-workspace` modes; excluding `--test-mode`),
the runner creates a clean git-archive success zip named by `success_archive_name` (default `{repo}-{branch}.zip`, e.g. `audiomason2-main.zip`) as a clean `git archive HEAD` snapshot of the final live repository state.
It contains only git-tracked files (as if fetched from the remote) and does not include logs, workspaces, caches, or patch inputs.

Unified patch mode (`--unified-patch`):
- Auto-detection rules (no `-u` required):
  - If PATCH_PATH ends with `.patch`: unified mode is used.
  - If PATCH_PATH ends with `.zip`: the runner scans the entire zip **recursively**.
    - If it finds **one or more** `*.patch` entries anywhere in the zip, unified mode is used.
    - All discovered `*.patch` entries are extracted and applied **in deterministic order** (lexicographic by zip-internal relative path).
    - If the zip also contains `*.py`, those are **ignored** when at least one `*.patch` entry exists.
    - If the zip contains **no** `*.patch` entries, the runner may fall back to script patch handling (see Patch script mode).
- `--unified-patch` forces unified mode and validates that PATCH_PATH is `.patch` or a `.zip` containing at least one `*.patch` entry.

- Gate pipeline note: after patches are applied, the runner may run additional gates (see Gates).
- The primary log records the discovered patch list and the apply result for each patch.

---

## 8. Git Behavior

### 8.1 Commit
- Commit failure stops runner.
- Repository remains dirty.
- Staging rules:
  - In `--finalize-live` (aka `-f`) mode, the runner stages the entire live working tree before commit.
  - In `workspace` and `-w` / `--finalize-workspace` modes, the runner commits only the paths it has promoted
    (those paths are staged explicitly during promotion). Any unrelated dirty changes in the live
    working tree remain uncommitted and continue to appear as dirty after the run.

### 8.2 Push
- Push failure may be allowed by policy.
- Commit remains local.

### 8.3 No autonomous rebase
Pull/rebase only when explicitly enabled.

---

## 9. Workspace Rules

- Workspaces may be reused.
- Dirty workspaces are allowed.
- Workspace deletion occurs only on SUCCESS and only if enabled.

---

## 10. Logging Contract

A single primary log includes:
- runner version
- effective configuration with sources
- declared FILES
- gate execution results
- promotion plan
- commit SHA (if any)

---

## 11. Success Definition

Runner SUCCESS guarantees:
- at least one real change (unless explicitly allowed)
- no unintended scope violations
- gates passed or were explicitly overridden
- promotion and commit behavior followed policy

---

## 12. Authority

This document defines correctness.
If implementation diverges, the implementation is wrong.

## 13. Post-success Audit Step

After a run reaches SUCCESS **with commit+push completed successfully**, the runner executes
an additional **AUDIT** step:

- Command executed:
  ```
  python3 -u audit/audit_report.py
  ```
- Working directory: live repository root.
- Purpose: display the current audit status reflecting the just-pushed changes.
- Scope:
  - In `workspace` mode and `-w` / `--finalize-workspace`, it runs **after** workspace deletion (when enabled).
  - In `--finalize-live`, there is no workspace; it runs after `SUCCESS`.
  - It never reads or mutates the workspace.

Failure semantics:
- If the audit command exits non-zero, the run FAILS with stage `AUDIT`.
- No rollback is performed (code is already committed and pushed).

### Console color output

The runner may emit ANSI colors on stdout for the tokens:
- OK, FAIL in normal progress lines
- SUCCESS, FAIL in the final RESULT summary
- OK, FAIL in PUSH summary
- FILE lines in the final FILES block (when printed) may be colored yellow (ANSI palette index 11) when color is enabled.

Implementation note:
- Use ANSI 256-color yellow (palette 11): \\x1b[38;5;11m. Exact RGB is not guaranteed; this is widely supported when 256-color is available.

Controls:
- Policy/config key: console_color (auto|always|never, default auto)
- CLI: --color {auto,always,never} and --no-color (alias for never)
- Env: NO_COLOR forces never

Precedence: NO_COLOR > CLI > config > default.