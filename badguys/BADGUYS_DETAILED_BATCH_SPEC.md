# BADGUYS DETAILED BATCH SPECIFICATION

This document provides a **detailed, per-batch specification** for implementing the BadGuys test suite
so that it fully enforces the AudioMason2 runner specification.

This is a **design-level specification**, not implementation.
It defines *what each test must do and prove*, not *how it is coded*.

---

## BATCH 1 - CORE SAFETY & CONTRACT BASICS (A + B + C + D)

### Purpose
Prevent the most expensive and dangerous classes of runner bugs:
silent side effects, incorrect patch application, broken scope enforcement, and gate misbehavior.

### Preconditions
- BadGuys infrastructure is functional.
- Tests run in isolated workspaces.
- Helpers live outside `badguys/tests/`.

---

### A1. test_040_test_mode_hard_stop_no_archives
Intent:
Verify that `--test-mode` performs a hard STOP after workspace gates.

Setup:
- Patch modifies a file under `docs/` only.
- Patch is valid and would otherwise succeed.

Action:
- Run runner with `--test-mode`.

Required evidence:
- Exit code == 0.
- Workspace directory does not exist after run.
- No `patched.zip`.
- No success archive.
- Log contains no commit/push markers.

---

### A2. test_041_test_mode_cleanup_on_fail
Intent:
Verify workspace cleanup in test-mode even when the run FAILs.

Setup:
- Patch introduces a Python syntax error in a compile-target path.

Action:
- Run runner with `--test-mode`.

Required evidence:
- Exit code != 0.
- Failure stage indicates COMPILE.
- Workspace directory does not exist.
- No archives created.

---

### B1. test_050_unified_patch_zip_recursive_detection
Intent:
Ensure zip unified-patch autodetection is recursive.

Setup:
- Zip contains `subdir/x.patch`.

Action:
- Run runner with zip patch.

Required evidence:
- Patch applied successfully.
- Log indicates unified patch discovery.

---

### B2. test_051_unified_patch_order_lexicographic
Intent:
Ensure deterministic lexicographic patch application order.

Setup:
- Zip contains two patches modifying the same doc file.
- Final content differs based on order.

Action:
- Run runner.

Required evidence:
- Final file content matches lexicographic order.

---

### B3. test_052_unified_patch_ignores_py_when_patch_present
Intent:
Ensure `.py` patch scripts are ignored when `*.patch` exists.

Setup:
- Zip contains one `.patch` and one `.py` with conflicting intent.

Action:
- Run runner.

Required evidence:
- Only `.patch` effect is present.
- `.py` effect is absent.

---

### C1. test_060_scope_touching_undeclared_fails
Intent:
Enforce scope: touching undeclared files must FAIL.

Setup:
- Patch declares FILES for one doc.
- Patch modifies an additional doc.

Action:
- Run runner.

Required evidence:
- FAIL with scope violation reason.

---

### C2. test_061_scope_declared_but_not_touched_fails
Intent:
Enforce scope: declared-but-not-touched must FAIL.

Setup:
- Patch declares FILES but makes no effective change.

Action:
- Run runner.

Required evidence:
- FAIL with declared-not-touched reason.

---

### C3. test_062_scope_noop_patch_fails
Intent:
Enforce scope: noop patch must FAIL.

Setup:
- Valid unified diff with no effective change.

Action:
- Run runner.

Required evidence:
- FAIL with noop reason.

---

### C4. test_063_blessed_gate_output_allowed_without_a
Intent:
Blessed outputs must not trigger scope failure.

Setup:
- Change produces or modifies `audit/results/pytest_junit.xml`.

Action:
- Run runner without `-a`.

Required evidence:
- Scope does not FAIL.
- No requirement for `-a`.

---

### C5. test_064_a_allows_undeclared
Intent:
Verify `-a` override semantics.

Setup:
- Same as C1.

Action:
- Run runner with `-a`.

Required evidence:
- Scope passes.
- Undeclared file included in promotion set.

---

### D1. test_070_gate_order_is_compile_ruff_pytest_mypy
Intent:
Verify gate execution order.

Setup:
- Patch introduces Python syntax error.

Action:
- Run runner without `-g`.

Required evidence:
- FAIL at COMPILE.
- Ruff/Pytest/Mypy not executed.

---

### D2. test_071_compile_exclude_respected
Intent:
Verify `compile_exclude` behavior.

Setup:
- Syntax error in excluded path.
- Override `compile_exclude` provided.

Action:
- Run runner.

Required evidence:
- COMPILE passes.
- Subsequent gates execute.

---

### D3. test_072_g_continues_after_gate_fail
Intent:
Verify `-g` continues after gate failure.

Setup:
- Patch causes Ruff failure only.

Action:
- Run runner with `-g`.

Required evidence:
- Ruff FAIL logged.
- Later gates executed.

---

## BATCH 2 - PROMOTION & GIT SEMANTICS (E + F)

### Purpose
Guarantee correctness when interacting with the live repository and git.

---

### E1. test_080_live_changed_default_fails
Intent:
Default policy must FAIL on live-changed conflict.

Setup:
- Workspace modifies file X.
- Live repo independently modifies X.

Action:
- Run runner.

Required evidence:
- FAIL with LIVE_CHANGED.

---

### E2. test_081_overwrite_live
Intent:
Verify overwrite-live behavior.

Setup:
- Same as E1.

Action:
- Run runner with `--overwrite-live`.

Required evidence:
- SUCCESS.
- Live file equals workspace version.

---

### E3. test_082_overwrite_workspace
Intent:
Verify overwrite-workspace behavior.

Setup:
- Same as E1.

Action:
- Run runner with `--overwrite-workspace`.

Required evidence:
- Conflicting file skipped.
- Live unchanged.

---

### F1. test_090_finalize_live_stages_entire_tree
Intent:
Verify `-f` stages entire live tree.

Setup:
- Unrelated dirty change exists in live repo.
- Patch modifies a different file.

Action:
- Run runner with `-f`.

Required evidence:
- Commit includes unrelated change.

---

### F2. test_091_workspace_commits_only_promoted
Intent:
Verify workspace commits only promoted files.

Setup:
- Unrelated dirty change exists in live repo.

Action:
- Run workspace mode runner.

Required evidence:
- Commit excludes unrelated change.
- Dirty change remains.

---

## BATCH 3 - ARCHIVES & HYGIENE (G)

### G1. test_100_patched_zip_hygiene
Intent:
Ensure patched.zip cleanliness.

Setup:
- Force FAIL to generate patched.zip.

Required evidence:
- patched.zip contains no forbidden paths.

---

### G2. test_101_success_archive_created_on_success_non_test_mode
Intent:
Ensure success archive creation.

Setup:
- Successful run outside test-mode.

Required evidence:
- Success archive exists.
- Only git-tracked files included.

---

## BATCH 4 - BADGUYS GATE (H)

### H1. test_110_badguys_gate_auto_triggers_only_on_runner_touch
Intent:
Ensure auto gate triggers only on runner changes.

Setup:
- Two patches: one touching runner, one not.

Required evidence:
- BadGuys runs only for runner-touch case.

---

### H2. test_111_badguys_gate_command_string_is_shlex_split
Intent:
Ensure shlex parsing of command string.

Setup:
- Command specified as string with args.

Required evidence:
- Args are honored.

---

### H3. test_112_badguys_gate_cwd_auto_clone_vs_workspace
Intent:
Ensure correct CWD selection.

Required evidence:
- Auto selects workspace or clone correctly.

---

### H4. test_113_badguys_execution_points_per_mode
Intent:
Ensure correct execution points.

Required evidence:
- BadGuys runs exactly where specified per mode.

---

## BATCH 5 - LOGGING & VERBOSITY (I)

### I1. test_120_final_summary_success_format_and_files_block_only_on_push_ok
Intent:
Ensure summary format correctness.

Required evidence:
- FILES block appears only when PUSH OK.

---

### I2. test_121_verbosity_quiet_no_status_indicator
Intent:
Ensure quiet mode silence.

Required evidence:
- No heartbeat or status output.
- Only final summary.

---

## BATCH 6 - POST-SUCCESS AUDIT (J)

### J1. test_130_audit_runs_after_success_with_push
Intent:
Ensure audit step behavior.

Required evidence:
- Audit runs only after push.
- Audit failure changes stage to AUDIT.
- No rollback occurs.

---

## END OF SPECIFICATION
