# AM Patch Runner - Functional Specification v4 (UPDATED)

This document reflects the **current, implemented behavior** of the AM Patch Runner
after introduction of:
- `--finalize-workspace`
- blessed gate outputs
- workspace cleanup semantics parity

This document is **authoritative** for current runner behavior.

---

## 0. Core Principles (NonNegotiable)

### 0.1 Universal controllability
Every runner behavior is controllable via:
- CLI flags **or**
- `-o KEY=VALUE` overrides,
with precedence: **CLI > config > defaults**.

### 0.2 Determinism over convenience
The runner never guesses, never implicitly expands scope, and never mutates state
without explicit authorization.

---

## 1. Version Visibility

The runner prints its version:
- on every invocation
- in `--help`

Example:
```
am_patch RUNNER_VERSION=4.1.43
```

---

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
- `--finalize-workspace`: workspace promotion still occurs and gates run in both workspace and live repo, but the runner does not commit or push. In this case, the workspace is preserved to avoid losing the easiest re-run path while the live repo has uncommitted changes.

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
- All configured gates run unless explicitly skipped.

### 6.2 Enforcement
- Without `-g`: any failing gate stops progression.
- With `-g`: failures are logged but execution continues.

This behavior is **uniform** across:
- workspace gates
- live gates
- finalizeworkspace

---

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

This behavior applies to workspace promotion and `--finalize-workspace`.

### 7.3 Archive hygiene (`patched.zip`)

When building `patched.zip`, the runner excludes repository internals and tool/runtime caches from the archived `changed/touched subset (no full workspace)` tree:

- `.git/`
- `venv/`, `.venv/`
- `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`
- `__pycache__/`
- `*.pyc`

This is independent of scope logic and does not affect patch execution, gates, or promotion semantics.


## 7.4 Success archive (`patched_success.zip`)

On SUCCESS (in `workspace`, `--finalize-live`, and `--finalize-workspace` modes; excluding `--test-mode`),
the runner creates `patched_success.zip` as a clean `git archive HEAD` snapshot of the final live repository state.
It contains only git-tracked files (as if fetched from the remote) and does not include logs, workspaces, caches, or patch inputs.

Unified patch mode (`--unified-patch`):
- On FAIL, `patched.zip` may include individual failed `.patch` inputs, but never includes the original input `.zip`.
- Lists of `touched_files`, `changed_files`, and `failed_patches` are recorded in the primary log (no separate manifest files).


---

## 8. Git Behavior

### 8.1 Commit
- Commit failure stops runner.
- Repository remains dirty.

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
  - In `workspace` mode and `--finalize-workspace`, it runs **after** workspace deletion (when enabled).
  - In `--finalize-live`, there is no workspace; it runs after `SUCCESS`.
  - It never reads or mutates the workspace.

Failure semantics:
- If the audit command exits non-zero, the run FAILS with stage `AUDIT`.
- No rollback is performed (code is already committed and pushed).
