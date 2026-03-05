from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DontTouchViolation:
    protected_path: str
    decision_path: str


def _norm_rel_path(p: str) -> str:
    s = str(p).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    # Repo-relative only.
    return s


def _iter_violations(
    decision_paths: list[str],
    protected_paths: list[str],
) -> list[DontTouchViolation]:
    dec = [_norm_rel_path(p) for p in decision_paths]
    prot = [_norm_rel_path(p) for p in protected_paths]

    violations: list[DontTouchViolation] = []
    for d in dec:
        if not d:
            continue
        for p in prot:
            if not p:
                continue
            if p.endswith("/"):
                prefix = p.rstrip("/")
                if d == prefix or d.startswith(prefix + "/"):
                    violations.append(DontTouchViolation(p, d))
            else:
                if d == p:
                    violations.append(DontTouchViolation(p, d))
    return violations


def run_dont_touch_gate(
    decision_paths: list[str],
    protected_paths: list[str],
) -> tuple[bool, str | None, str | None]:
    """Return (ok, protected_path, decision_path).

    Deterministic, repo-relative only. No filesystem access.

    Matching:
    - If protected path ends with '/', it is a directory-prefix match.
    - Otherwise it is an exact file match.
    """

    violations = _iter_violations(decision_paths, protected_paths)
    if not violations:
        return True, None, None

    # Deterministic selection: sort by protected then decision.
    v = sorted(violations, key=lambda x: (x.protected_path, x.decision_path))[0]
    return False, v.protected_path, v.decision_path
