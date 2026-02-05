# BADGUYS IMPLEMENTATION PLAN (BATCH SPECIFICATION)

This document defines the **complete, ordered implementation plan** for extending BadGuys
to fully enforce the AudioMason2 runner specification.

The plan is divided into **batches**.  
Each batch is independently mergeable and increases contract coverage monotonically.

Rules:
- `badguys/tests/` contains **tests only** (no helpers, no logic).
- All helpers live outside `badguys/tests/`.
- Tests are deterministic, isolated, and produce disk + log evidence.
- `docs/` and `patches/` are gate-ignored and may be used deliberately.
- No implementation is implied by this document; this is a specification.

---

## BATCH 1 — CORE SAFETY & CONTRACT BASICS (A + B + C + D)

### Scope
Foundational correctness and safety.
This batch prevents the most expensive classes of bugs.

### Covered matrix sections
- A. Test-mode (hard stop, cleanup)
- B. Unified patch handling
- C. Scope / FILES contract
- D. Gates (order, COMPILE, `-g`)

### New tests
- test_040_test_mode_hard_stop_no_archives
- test_041_test_mode_cleanup_on_fail
- test_050_unified_patch_zip_recursive_detection
- test_051_unified_patch_order_lexicographic
- test_052_unified_patch_ignores_py_when_patch_present
- test_060_scope_touching_undeclared_fails
- test_061_scope_declared_but_not_touched_fails
- test_062_scope_noop_patch_fails
- test_063_blessed_gate_output_allowed_without_a
- test_064_a_allows_undeclared
- test_070_gate_order_is_compile_ruff_pytest_mypy
- test_071_compile_exclude_respected
- test_072_g_continues_after_gate_fail

### Key design notes
- Use `docs/` for tests that must not interact with gates.
- Use real compile targets (`scripts/` / `src/`) only when a gate must be triggered.
- Scope tests must fail on scope, not on gates.
- Every test must assert:
  - runner exit code,
  - disk artifacts (existence / non-existence),
  - log evidence (stage / reason).

---

## BATCH 2 — PROMOTION & GIT SEMANTICS (E + F)

### Scope
Correctness of promotion, live conflict handling, and commit semantics.

### Covered matrix sections
- E. Promotion & live-changed resolution
- F. Git staging rules

### New tests
- test_080_live_changed_default_fails
- test_081_overwrite_live
- test_082_overwrite_workspace
- test_090_finalize_live_stages_entire_tree
- test_091_workspace_commits_only_promoted

### Key design notes
- Tests must deliberately create divergence between workspace and live.
- Git evidence is mandatory (commit content, dirty state).
- No assumptions about user working tree cleanliness.

---

## BATCH 3 — ARCHIVES, HYGIENE & ARTIFACTS (G)

### Scope
Correct creation and cleanliness of runner-produced artifacts.

### Covered matrix sections
- G. Archives & hygiene

### New tests
- test_100_patched_zip_hygiene
- test_101_success_archive_created_on_success_non_test_mode

### Key design notes
- Zip inspection must be deterministic.
- Forbidden entries must be asserted absent by pattern.
- Success archive must be git-archive based (tracked files only).

---

## BATCH 4 — BADGUYS GATE (RUNNER SELF-PROTECTION) (H)

### Scope
Ensuring the runner correctly invokes BadGuys to protect itself.

### Covered matrix sections
- H. BadGuys gate

### New tests
- test_110_badguys_gate_auto_triggers_only_on_runner_touch
- test_111_badguys_gate_command_string_is_shlex_split
- test_112_badguys_gate_cwd_auto_clone_vs_workspace
- test_113_badguys_execution_points_per_mode

### Key design notes
- Tests must distinguish runner-touch vs non-runner-touch.
- CWD behavior must be observable (lock conflicts avoided).
- Execution-point multiplicity must be asserted via logs.

---

## BATCH 5 — LOGGING & VERBOSITY CONTRACT (I)

### Scope
User-facing correctness and observability guarantees.

### Covered matrix sections
- I. Logging & summary contract

### New tests
- test_120_final_summary_success_format_and_files_block_only_on_push_ok
- test_121_verbosity_quiet_no_status_indicator

### Key design notes
- Assertions rely on exact summary markers, not fragile formatting.
- Quiet mode must be provably silent except for final summary.

---

## BATCH 6 — POST-SUCCESS AUDIT (J)

### Scope
Correct execution and failure semantics of the audit step.

### Covered matrix sections
- J. Post-success audit

### New tests
- test_130_audit_runs_after_success_with_push

### Key design notes
- Audit must run only after successful commit + push.
- Audit failure must change stage to AUDIT without rollback.

---

## GLOBAL ACCEPTANCE RULES

- Each batch must pass BadGuys fully before the next batch begins.
- Each test added must be traceable to the matrix and specification.
- No batch may weaken guarantees provided by earlier batches.
- Any future runner feature requires:
  1) matrix update,
  2) batch assignment,
  3) new test(s).

This document is **normative**.
