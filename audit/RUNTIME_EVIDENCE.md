
# Runtime evidence tooling

This folder contains the canonical audit rubric and tooling to generate runtime evidence.

## Canonical rubric file

Use this file name only (it is expected to stay stable across upgrades):

- audit/audit_rubric.yaml

Older or versioned rubric files may exist for history, but the canonical input for tooling and tests is the file above.

## Runtime evidence runner

The runtime evidence runner executes commands declared in the rubric (under requirements[].runtime_evidence.commands)
and stores a single YAML report under audit/results/.

Typical usage:

```bash
cd /home/pi/audiomason2
python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml
```

With an explicit output file:

```bash
python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml --out audit/results/runtime_evidence_manual.yaml
```

Timeout control (per command):

```bash
python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml --timeout 60
```

Notes:
- This tool does NOT commit or push results. Commit the generated YAML file manually if desired.
- The runner is designed to tolerate a dirty working tree (it only reads and writes the output file).

## Rubric runtime_evidence schema (summary)

Each requirement can define a runtime_evidence block:

- required: true|false
- commands: list of command strings (executed in repo root)
- acceptance_checks: list of checks applied to the captured result (returncode, stdout parsing, required fields, etc.)

Example snippet:

```yaml
runtime_evidence:
  required: true
  commands:
    - python -m audiomason audit --list-domains --format yaml
  acceptance_checks:
    - kind: returncode
      equals: 0
```

## Output report schema (summary)

The generated YAML report contains:
- meta: environment info and the rubric path
- runs: one entry per executed command, including returncode, stdout/stderr, duration, and acceptance results

This report is intended to be consumed by the ALL audit tooling.
