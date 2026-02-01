# Runtime evidence tooling

This repo provides deterministic, machine-readable runtime evidence for the audit system.

## Protocols

Domain selftests and plugin commands MUST emit valid JSON or YAML to stdout with stable schema:

- schema_version: am2.audit.v1
- tool: audiomason
- domain: <DOMAIN>
- subject: <SUBJECT>
- status: pass|debt|fail|...
- checks: [...]

Domain registry discovery MUST emit:

- schema_version: am2.audit.registry.v1
- tool: audiomason
- domains: [...]

## Deterministic CLI commands

Registry discovery:

```bash
python -m audiomason audit --list-domains --format yaml
python -m audiomason audit --list-domains --format json
```

Domain selftests:

```bash
python -m audiomason metadata --selftest --format yaml
python -m audiomason tags --selftest --format yaml
python -m audiomason audio --selftest --format yaml
python -m audiomason covers --selftest --format yaml
python -m audiomason utils --selftest --format yaml
```

Plugins (AST-only, no execution):

```bash
python -m audiomason plugins --list --format yaml
python -m audiomason plugins --validate --format yaml
```

## Runtime evidence runner

Discover mode (runs only deterministic audit commands):

```bash
python3 audit/run_runtime_evidence.py --repo . --discover
```

Rubric mode (runs commands referenced in audit/audit_rubric.yaml):

```bash
python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml
```

Optional targeted git automation (commits only the generated output file; does not run 'git add .'):

```bash
python3 audit/run_runtime_evidence.py --repo . --discover --git-commit --git-message "audit: runtime evidence (discover)"
python3 audit/run_runtime_evidence.py --repo . --discover --git-commit --git-push --git-message "audit: runtime evidence (discover)"
```

## Typical validation snippets

Validate registry schema:

```bash
python -m audiomason audit --list-domains --format yaml | python - <<'PY'
import sys,yaml
d=yaml.safe_load(sys.stdin)
assert d["schema_version"]=="am2.audit.registry.v1"
assert d["tool"]=="audiomason"
assert isinstance(d["domains"], list) and d["domains"]
print("OK registry domains=", len(d["domains"]))
PY
```

Validate one selftest schema:

```bash
python -m audiomason metadata --selftest --format yaml | python - <<'PY'
import sys,yaml
d=yaml.safe_load(sys.stdin)
assert d["schema_version"]=="am2.audit.v1"
assert d["tool"]=="audiomason"
assert d["domain"]=="METADATA"
assert isinstance(d["checks"], list) and d["checks"]
print("OK", d["domain"], d["subject"], d["status"], "checks=", len(d["checks"]))
PY
```
