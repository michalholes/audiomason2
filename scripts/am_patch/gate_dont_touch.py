from __future__ import annotations

from .errors import RunnerError


def _norm_decision_path(p: str) -> str:
    s = str(p).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    while s.startswith("/"):
        s = s[1:]
    return s.rstrip("/")


def _norm_protected_path(p: str) -> tuple[str, bool, str]:
    raw = str(p).strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    while raw.startswith("/"):
        raw = raw[1:]

    is_dir = raw.endswith("/")
    base = raw.rstrip("/")
    display = base + "/" if is_dir else base
    return base, is_dir, display


def _dir_prefix_match(path: str, prefix: str) -> bool:
    if not prefix:
        return False
    return path == prefix or path.startswith(prefix + "/")


def run_dont_touch_gate(decision_paths: list[str], protected_paths: list[str]) -> None:
    """Fail if any changed repo-relative path matches a protected path.

    Matching rules:
    - 'foo/' => directory prefix match
    - 'foo.txt' => exact match

    This gate is deterministic and uses only decision_paths.
    """

    norm_decisions: list[str] = []
    for p in decision_paths:
        s = _norm_decision_path(p)
        if s and s not in norm_decisions:
            norm_decisions.append(s)

    norm_protected: list[tuple[str, bool, str]] = []
    for p in protected_paths:
        base, is_dir, display = _norm_protected_path(p)
        if not base:
            continue
        key = (base, is_dir, display)
        if key not in norm_protected:
            norm_protected.append(key)

    for d in norm_decisions:
        for base, is_dir, display in norm_protected:
            if is_dir:
                if _dir_prefix_match(d, base):
                    raise RunnerError(
                        "GATES",
                        "GATES",
                        (
                            "dont-touch gate blocked protected path: "
                            f"protected={display!r} decision={d!r}"
                        ),
                    )
            else:
                if d == base:
                    raise RunnerError(
                        "GATES",
                        "GATES",
                        (
                            "dont-touch gate blocked protected path: "
                            f"protected={display!r} decision={d!r}"
                        ),
                    )
