# Audit Summarizer (summarize_audit.py)

This tool compares the latest two audit result files produced by `audit/evaluate_audit.py`
for a given certification profile and produces a delta report.

It produces:
- A machine-readable YAML artifact in `audit/results/` (delta summary).
- A long human-readable Markdown report in `audit/summary.md` (always overwritten).
- A SHORT CLI report printed to stdout (default), suitable for frequent/automatic runs.

The summarizer does NOT run tests or runtime commands.

## Inputs

- `audit/results/audit_<PROFILE>_*.yaml` (audit results; must have `audit_result_schema: 1`)

The summarizer ignores:
- `runtime_evidence*.yaml`
- `audit_summary_*.yaml`
- Any YAML that is not `audit_result_schema: 1`

## Outputs

1) Delta YAML (unique filename):
- `audit/results/audit_summary_<PROFILE>_<timestamp>_<current_fp>_vs_<prev_fp>.yaml`

If the default output filename already exists, the tool appends `__N` to make it unique.

2) Long human report (fixed filename, overwritten each run):
- `audit/summary.md`

## Git publish (default ON)

By default the tool commits and pushes ONLY the files written by the summarizer:
- the delta YAML in `audit/results/`
- `audit/summary.md`

Disable git automation:
- `--no-git`

Commit but do not push:
- `--git-no-push`

Choose remote / branch:
- `--git-remote origin`
- `--git-branch main`

Skip commit hooks:
- `--git-no-verify`

## CLI options

- `--profile <NAME>` (required)
- `--results-dir <DIR>` (default: `audit/results`)
- `--no-git`
- `--git-no-push`
- `--git-remote <REMOTE>`
- `--git-branch <BRANCH>`
- `--git-no-verify`
- `--quiet` (suppress normal stdout output; errors still print)
- `--print-files` (print output file paths before the short report)

## Typical examples

Summarize and publish:
```
python3 audit/summarize_audit.py --profile C3_ALL_v5
```

Summarize without git:
```
python3 audit/summarize_audit.py --profile C3_ALL_v5 --no-git
```

Summarize, commit but do not push:
```
python3 audit/summarize_audit.py --profile C3_ALL_v5 --git-no-push
```

Quiet mode (useful for scripts):
```
python3 audit/summarize_audit.py --profile C3_ALL_v5 --quiet
```

Print file paths (useful when debugging tooling):
```
python3 audit/summarize_audit.py --profile C3_ALL_v5 --print-files
```

## Short CLI output format (default)

The summarizer prints ONLY these sections (in this order):

- Improvements + regressions (delta lists)
- Counts (PASS/PARTIAL/DEBT/UNKNOWN with deltas)
- A single recommended next action (based on UNKNOWN diagnosis) + examples

The long Markdown report is stored in `audit/summary.md`.

