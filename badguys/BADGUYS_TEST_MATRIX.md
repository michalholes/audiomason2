# BADGUYS TEST MATRIX (NORMATIVE)

This document defines the **complete, normative BadGuys test matrix** for the AudioMason2 patch runner.

Contract:
- Every **normative** behavior in the runner specification is protected by **at least one** BadGuys test.
- If the runner violates the specification, **at least one test in this matrix MUST fail**.
- Any runner change that modifies behavior MUST update this matrix and the corresponding test(s).

All “Spec refs” below refer to the runner functional specification.

---

## A. TEST-MODE (HARD STOP & CLEANUP)

### A1. test_040_test_mode_hard_stop_no_archives
Protects: In `--test-mode`, after workspace gates and live-repo guard check, the runner performs a hard STOP (no promotion/live gates/commit+push/archives/patched.zip).

Spec refs:
- §2.4 Test mode (`--test-mode`): hard STOP (no promotion/live gates/commit+push/patch archives/patched.zip)

Expected evidence:
- exit code = 0
- workspace removed after run
- no `patched.zip`
- no success archive

---

### A2. test_041_test_mode_cleanup_on_fail
Protects: Workspace deletion occurs on exit ALWAYS (SUCCESS or FAILURE) in test-mode.

Spec refs:
- §2.4 Test mode: workspace deleted ALWAYS (SUCCESS or FAILURE); `-k` ignored; `delete_workspace_on_success` does not apply

Expected evidence:
- exit code != 0
- failure stage reported
- workspace removed
- no archives created

---

## B. UNIFIED PATCH HANDLING

### B1. test_050_unified_patch_zip_recursive_detection
Protects: `.zip` is treated as unified patch if it contains one or more `*.patch` entries anywhere recursively.

Spec refs:
- §7.4 Success archive → Unified patch mode: auto-detection rules for `.zip` (recursive scan; unified mode when 1+ `*.patch` exists)

---

### B2. test_051_unified_patch_order_lexicographic
Protects: Multiple `*.patch` entries discovered in a zip are applied in deterministic lexicographic order by zip-internal relative path.

Spec refs:
- §7.4 Success archive → Unified patch mode: apply `*.patch` entries in deterministic order (lexicographic by zip-internal relative path)

---

### B3. test_052_unified_patch_ignores_py_when_patch_present
Protects: If a zip contains at least one `*.patch`, any `*.py` files inside the zip are ignored.

Spec refs:
- §7.4 Success archive → Unified patch mode: ignore `*.py` when at least one `*.patch` entry exists

---

## C. SCOPE / FILES CONTRACT

### C1. test_060_scope_touching_undeclared_fails
Protects: Touching undeclared files FAILs by default (scope enforcement).

Spec refs:
- §4.2 Scope enforcement: touching undeclared files FAIL (default)

---

### C2. test_061_scope_declared_but_not_touched_fails
Protects: Declaring but not touching files FAILs by default.

Spec refs:
- §4.2 Scope enforcement: declaring but not touching FAIL (default)

---

### C3. test_062_scope_noop_patch_fails
Protects: Noop patch FAILs by default.

Spec refs:
- §4.2 Scope enforcement: noop patch FAIL (default)

---

### C4. test_063_blessed_gate_output_allowed_without_a
Protects: Blessed gate outputs do not trigger scope violations and do not require `-a`.

Spec refs:
- §4.3 Blessed gate outputs: allowlist includes `audit/results/pytest_junit.xml`; do not trigger scope violations; do not require `-a`
- §5 `-a`: `-a` is not required for blessed gate outputs

---

### C5. test_064_a_allows_undeclared
Protects: `-a` is a strong override that legalizes touching undeclared files and expands promotion scope accordingly.

Spec refs:
- §5 `-a` (Allow outside files): semantics and intent
- §7.1 Promotion set includes additional files when `-a` is active

---

## D. GATES

### D1. test_070_gate_order_is_compile_ruff_pytest_mypy
Protects: Default gate order is COMPILE → Ruff → Pytest → Mypy.

Spec refs:
- §6.1 Execution: default gate order

---

### D2. test_071_compile_exclude_respected
Protects: COMPILE gate implementation and `compile_exclude` behavior via `compileall -x <regex>`, including CLI overrides.

Spec refs:
- §6.1.1 COMPILE gate: `python -m compileall -q`; targets; exclude compiled into `compileall -x <regex>`; CLI overrides

---

### D3. test_072_g_continues_after_gate_fail
Protects: `-g` causes failures to be logged but execution continues; behavior is uniform across workspace/live/finalizeworkspace.

Spec refs:
- §6.2 Enforcement: without `-g` stop; with `-g` continue; uniform across modes

---

## E. PROMOTION & LIVE CONFLICT RESOLUTION

### E1. test_080_live_changed_default_fails
Protects: Default live-changed resolution fails promotion with `LIVE_CHANGED` when live repo changed since `base_sha`.

Spec refs:
- §7.2 Live-changed resolution: default `live_changed_resolution="fail"` ⇒ FAIL with `LIVE_CHANGED` (applies to workspace promotion and `--finalize-workspace`)

---

### E2. test_081_overwrite_live
Protects: `--overwrite-live` (and legacy alias `--allow-live-changed`) overwrites live with workspace version for conflicting files.

Spec refs:
- §7.2 Live-changed resolution: `--overwrite-live` and `--allow-live-changed` alias

---

### E3. test_082_overwrite_workspace
Protects: `--overwrite-workspace` keeps live version and skips promoting conflicting files.

Spec refs:
- §7.2 Live-changed resolution: `--overwrite-workspace` and config `live_changed_resolution="overwrite_workspace"`

---

## F. GIT STAGING RULES

### F1. test_090_finalize_live_stages_entire_tree
Protects: In `--finalize-live` (`-f`) mode, the runner stages the entire live working tree before commit.

Spec refs:
- §8.1 Commit: staging rules for `--finalize-live`

---

### F2. test_091_workspace_commits_only_promoted
Protects: In `workspace` and `--finalize-workspace`, the runner commits only promoted paths; unrelated dirty changes remain uncommitted.

Spec refs:
- §8.1 Commit: staging rules for `workspace` and `--finalize-workspace`

---

## G. ARCHIVES & HYGIENE

### G1. test_100_patched_zip_hygiene
Protects: `patched.zip` excludes repo internals and runtime caches (`.git/`, venvs, caches, `__pycache__`, `*.pyc`).

Spec refs:
- §7.3 Archive hygiene (`patched.zip`)

---

### G2. test_101_success_archive_created_on_success_non_test_mode
Protects: On SUCCESS (workspace / finalize-live / finalize-workspace), excluding test-mode, the runner creates a git-archive success zip named by `success_archive_name`.

Spec refs:
- §7.4 Success archive (git-archive zip): created on SUCCESS (excluding `--test-mode`), contains only git-tracked files

---

## H. BADGUYS GATE (RUNNER SELF-PROTECTION)

### H1. test_110_badguys_gate_auto_triggers_only_on_runner_touch
Protects: `gate_badguys_runner=auto` triggers only when the run touches runner files.

Spec refs:
- §6.1.2 BADGUYS gate: `gate_badguys_runner` and auto runner-touch paths

---

### H2. test_111_badguys_gate_command_string_is_shlex_split
Protects: `gate_badguys_command` may be a string and must be parsed using shlex; value must be non-empty.

Spec refs:
- §6.1.2 BADGUYS gate: `gate_badguys_command` list[str] | str; shlex parsing; non-empty

---

### H3. test_112_badguys_gate_cwd_auto_clone_vs_workspace
Protects: `gate_badguys_cwd=auto` uses workspace if invoked from a workspace repo; otherwise uses clone to avoid lock conflicts.

Spec refs:
- §6.1.2 BADGUYS gate: `gate_badguys_cwd` and auto selection rules

---

### H4. test_113_badguys_execution_points_per_mode
Protects: BadGuys runs at the specified execution points per mode.

Spec refs:
- §6.1.2 BADGUYS gate: execution points (workspace; finalize-workspace; finalize)

---

## I. LOGGING & SUMMARY CONTRACT

### I1. test_120_final_summary_success_format_and_files_block_only_on_push_ok
Protects: Final summary format; FILES block appears only when `PUSH: OK`.

Spec refs:
- §1.1 Verbosity and status output: final summary; FILES block only when PUSH OK; strict FILES format

---

### I2. test_121_verbosity_quiet_no_status_indicator
Protects: Quiet mode prints no progress output and no status bar; only final summary.

Spec refs:
- §1.1 Verbosity and status output: quiet mode contract; status indicator disabled in quiet

---

## J. POST-SUCCESS AUDIT

### J1. test_130_audit_runs_after_success_with_push
Protects: After SUCCESS with commit+push completed successfully, the runner executes audit command; audit failure causes stage `AUDIT` without rollback.

Spec refs:
- §13 Post-success Audit Step: command, working dir, ordering rules, failure semantics

---

## CONTRACT RULE

If the runner violates the specification, **at least one test in this matrix MUST fail**.
Any change to runner behavior **requires adding or updating a test here**.
