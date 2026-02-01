# One-shot Audit Report (audit_report.py)

This command runs the full audit flow end-to-end and prints a human-readable report
to the terminal.

It is intended for non-programmers: you run ONE command and get:
- evidence collection output
- evaluation output
- a delta summary (improvements / regressions / blockers / unknowns)

## What it runs

1) `python3 audit/run_runtime_evidence.py --repo <REPO_ROOT>`
2) `pytest` (generates JUnit evidence per repo config)
3) `python3 audit/evaluate_audit.py --profile <PROFILE>`
4) `python3 audit/summarize_audit.py --profile <PROFILE>`

## Default profile (no flags required)

By default you can run:

```
python3 audit/audit_report.py
```

The profile is taken from `audit/audit_report_config.yaml`:

```yaml
default_profile: C3_ALL_v5
```

You can override the profile for a single run:

```
python3 audit/audit_report.py --profile C3_ALL_v5
```

## Config file

By default the report reads:

- `audit/audit_report_config.yaml`

You can override the config path (relative to repo root):

```
python3 audit/audit_report.py --config audit/audit_report_config.yaml
```

## Git automation (default ON)

By default, this pipeline publishes artifacts:
- runtime evidence tool publishes its evidence outputs
- evaluator creates and publishes an audit result
- summarizer creates and publishes a summary

To disable git publish everywhere:

```
python3 audit/audit_report.py --no-git
```

Commit but do not push:

```
python3 audit/audit_report.py --git-no-push
```

Skip commit hooks (git commit --no-verify) for evaluator and summarizer:

```
python3 audit/audit_report.py --git-no-verify
```

## Enforcing git publish

By default, if git publish is skipped (e.g. detached HEAD / rebase), the report
fails with a non-zero exit code.

If you want to allow skip (not recommended for certification):

```
python3 audit/audit_report.py --allow-git-skip
```

## Output

This tool prints a structured report to stdout and exits:
- 0 on success
- 2 on failure


Evidence publishing

- The one-shot report publishes the JUnit evidence file (`audit/results/pytest_junit.xml`) so the repository remains clean after the run.
