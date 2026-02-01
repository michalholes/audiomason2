# Audit Evaluator (evaluate_audit.py)

This document describes the audit evaluator tool:

- `audit/evaluate_audit.py`

The evaluator consumes already-generated evidence artifacts (pytest JUnit and runtime evidence)
and produces a single audit result file plus a certification verdict.

It does NOT execute tests or runtime commands.

## Inputs

Required:
- `audit/audit_rubric.yaml`

Optional:
- `audit/results/pytest_junit.xml`
- `audit/results/runtime_evidence*.yaml` (one or many)

Notes:
- Runtime evidence files are read in lexical filename order.
- For a given `requirement_id`, the evaluator selects the latest-seen run:
  later file wins; within a file, later run index wins.

## Output

The evaluator writes a new YAML file under `audit/results/` and never overwrites an existing file.

Default output name (when `--out` is not used):

- `audit/results/audit_<PROFILE>_<TIMESTAMP>_<INPUTS_FINGERPRINT>.yaml`

Where:
- `<TIMESTAMP>` is derived from inputs (NOT from current time):
  max of `pytest_junit.xml` testsuite timestamp and all runtime evidence `meta.generated_at`.
- `<INPUTS_FINGERPRINT>` is a stable hash of rubric + evidence files.

The output YAML is stable:
- `audit_result_schema: 1`
- YAML keys are written with stable ordering.
- Requirements are sorted by `requirement_id`.

## Certification

The evaluator computes two layers:

1) Technical results
- For each requirement in the rubric:
  status is one of: `PASS`, `PARTIAL`, `DEBT`, `UNKNOWN`
- Each requirement includes evidence pointers and a short reason.

2) Certification verdict
- Applies the selected profile, e.g. `C3_ALL_v5`
- Produces `PASS` or `FAIL` with reasons

### Future-domain policy

This tool supports an additional policy for domains not explicitly mentioned in profile rules.

- Default: `--future-domain-policy v1`

`v1` means:
- every domain found in the rubric MUST have `UNKNOWN==0` and `DEBT==0`
- this prevents new domains from being silently ignored

`informational` means:
- domains not covered by profile rules are still reported, but do not block the verdict

## Evidence pointers

Each requirement result contains a list of evidence pointers.

Examples:

Runtime pointer:
- `kind: runtime`
- `keys` include `requirement_id`, `evidence_file`, `run_index`, and command/returncode

Pytest pointer:
- `kind: pytest` or `pytest_fail`
- `keys` include `domain`, `nodeid`, `classname`, `name`, and `file` (when present)

## Git publication (default ON)

By default, the evaluator will:
- create the audit result file,
- commit it,
- push it.

This is enabled by default to make audit results self-publishing.

Important behavior:
- The evaluator commits ONLY the file(s) it created.
- It uses an alternative git index (via `the primary git index`) so it does not interfere with:
  - an existing dirty working tree
  - an existing staged index in your session

If git publish cannot run (detached HEAD, merge/rebase in progress, no repo, etc.),
the evaluator still writes the audit YAML, and records publication status in the report.

## CLI options

From repo root:

- `--repo PATH`
  Repository root (default: `.`)

- `--rubric PATH`
  Rubric YAML path (default: `audit/audit_rubric.yaml`)

- `--results-dir PATH`
  Results directory (default: `audit/results`)

- `--profile NAME`
  Certification profile name from rubric (default: `C3_ALL_v5`)

- `--future-domain-policy {v1,informational}`
  Policy for domains not explicitly covered by profile rules (default: `v1`)

- `--out PATH`
  Explicit output YAML path. Must not already exist.

- `--no-git`
  Disable git commit/push automation (default: enabled)

- `--git-no-push`
  Commit but do not push (default: push)

- `--git-remote NAME`
  Remote name for push (default: `origin`)

- `--git-branch NAME`
  Branch name for push (default: current branch)

- `--git-no-verify`
  Pass `--no-verify` to `git commit`

## Typical examples

Run evaluator with defaults (writes result, commits, pushes):
```bash
python3 audit/evaluate_audit.py --profile C3_ALL_v5
```

Run evaluator without git automation:
```bash
python3 audit/evaluate_audit.py --profile C3_ALL_v5 --no-git
```

Run evaluator with commit only:
```bash
python3 audit/evaluate_audit.py --profile C3_ALL_v5 --git-no-push
```

Run evaluator with explicit output path:
```bash
python3 audit/evaluate_audit.py --profile C3_ALL_v5 --out audit/results/audit_manual.yaml
```

Relax future-domain policy (domains not in profile rules become informational):
```bash
python3 audit/evaluate_audit.py --profile C3_ALL_v5 --future-domain-policy informational
```


Git publishing

- Artifacts are published by staging only the artifact paths and committing with `git commit --only -- <paths>`.
- This keeps the primary index coherent and avoids confusing staged/untracked states.
