from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import RunnerError


@dataclass
class Policy:
    _src: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        from dataclasses import fields

        for f in fields(self):
            if f.name == "_src":
                continue
            self._src.setdefault(f.name, "default")

    repo_root: str | None = None
    patch_dir: str | None = None
    default_branch: str = "main"

    require_up_to_date: bool = True
    enforce_main_branch: bool = True

    update_workspace: bool = False
    soft_reset_workspace: bool = False
    test_mode: bool = False
    delete_workspace_on_success: bool = True

    ascii_only_patch: bool = True
    no_op_fail: bool = True
    allow_no_op: bool = False
    enforce_allowed_files: bool = True

    run_all_tests: bool = True
    ruff_autofix: bool = True
    ruff_autofix_legalize_outside: bool = True

    # NEW: ruff format before ruff check (default ON)
    ruff_format: bool = True

    gates_allow_fail: bool = False
    gates_skip_ruff: bool = False
    gates_skip_pytest: bool = False
    gates_skip_mypy: bool = False
    gates_order: list[str] = field(default_factory=lambda: ["ruff", "pytest", "mypy"])

    ruff_targets: list[str] = field(default_factory=lambda: ["src", "tests"])
    pytest_targets: list[str] = field(default_factory=lambda: ["tests"])
    mypy_targets: list[str] = field(default_factory=lambda: ["src"])

    # NEW: run pytest using live repo .venv python (default ON)
    pytest_use_venv: bool = True

    fail_if_live_files_changed: bool = True
    live_changed_resolution: str = "fail"  # fail|overwrite_live|overwrite_workspace

    commit_and_push: bool = True

    # Post-success audit report (default ON)
    post_success_audit: bool = True

    # Existing: promotion rollback on commit/push failure (legacy)
    no_rollback: bool = False

    # NEW: rollback workspace to pre-patch checkpoint on PATCH failure only (default ON)
    rollback_workspace_on_fail: bool = True

    # NEW: live repo guard (default ON)
    live_repo_guard: bool = True

    # NEW: live repo guard scope (default: 'patch')
    # - 'patch': guard before/after patching+scope enforcement only
    # - 'patch_and_gates': additionally guard after gates
    live_repo_guard_scope: str = "patch"

    # NEW: audit rubric guard (default ON)
    # If true, preflight verifies that audit/audit_rubric.yaml contains required
    # runtime evidence commands
    # for all domains listed in src/audiomason/audit/registry.py.
    audit_rubric_guard: bool = True

    # NEW: patch execution jail (bubblewrap) (default ON)
    patch_jail: bool = True
    patch_jail_unshare_net: bool = True

    skip_up_to_date: bool = False
    allow_non_main: bool = False
    allow_push_fail: bool = True
    declared_untouched_fail: bool = True
    allow_declared_untouched: bool = False
    allow_outside_files: bool = False


def _as_bool(d: dict[str, Any], k: str, default: bool) -> bool:
    return bool(d.get(k, default))


def _as_str(d: dict[str, Any], k: str, default: str | None) -> str | None:
    v = d.get(k, default)
    return None if v is None else str(v)


def _as_list_str(d: dict[str, Any], k: str, default: list[str]) -> list[str]:
    v = d.get(k, None)
    if v is None:
        return list(default)
    if isinstance(v, list):
        out: list[str] = []
        for x in v:
            if isinstance(x, str):
                s = x.strip()
                if s and s not in out:
                    out.append(s)
        return out or list(default)
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else list(default)
    return list(default)


def _parse_override_kv(s: str) -> tuple[str, object]:
    if "=" not in s:
        raise ValueError("override must be KEY=VALUE")
    k, v = s.split("=", 1)
    k = k.strip()
    v = v.strip()
    if v.lower() in ("true", "false"):
        return k, (v.lower() == "true")
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return k, []
        return k, [x.strip().strip("'\"") for x in inner.split(",")]
    if "," in v:
        return k, [x.strip().strip("'\"") for x in v.split(",")]
    if re.fullmatch(r"-?\d+", v):
        return k, int(v)
    return k, v


def _flatten_sections(cfg: dict[str, object]) -> dict[str, object]:
    if not isinstance(cfg, dict):
        return {}
    out: dict[str, object] = dict(cfg)
    for section in (
        "git",
        "paths",
        "workspace",
        "patch",
        "scope",
        "gates",
        "promotion",
        "security",
        "logging",
        "audit",
    ):
        sec = cfg.get(section)
        if isinstance(sec, dict):
            for k, v in sec.items():
                if isinstance(k, str):
                    out.setdefault(k, v)

    # Compatibility/alias keys for common TOML naming.
    if "order" in out and "gates_order" not in out:
        out["gates_order"] = out["order"]
    if "enforce_files_only" in out and "enforce_allowed_files" not in out:
        out["enforce_allowed_files"] = out["enforce_files_only"]
    if "rollback_on_failure" in out and "no_rollback" not in out:
        # rollback_on_failure=true => no_rollback=false
        out["no_rollback"] = not bool(out["rollback_on_failure"])
    if "delete_on_success" in out and "delete_workspace_on_success" not in out:
        out["delete_workspace_on_success"] = out["delete_on_success"]
    if "fetch_always" in out:
        # ignore; fetch behavior is currently unconditional
        pass
    if "enforce_files_only" in out:
        pass

    return out


def load_config(path: Path) -> tuple[dict[str, Any], bool]:
    if not path.exists():
        return {}, False
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return _flatten_sections(data), True


def _mark_cfg(p: Policy, cfg: dict[str, Any], key: str) -> None:
    if key in cfg:
        p._src[key] = "config"


def build_policy(defaults: Policy, cfg: dict[str, Any]) -> Policy:
    _fields = getattr(Policy, "__dataclass_fields__", {})
    _kwargs = {
        k: v
        for k, v in defaults.__dict__.items()
        if k in _fields and getattr(_fields[k], "init", True)
    }
    p = Policy(**_kwargs)

    p.repo_root = _as_str(cfg, "repo_root", p.repo_root)
    _mark_cfg(p, cfg, "repo_root")
    p.patch_dir = _as_str(cfg, "patch_dir", p.patch_dir)
    _mark_cfg(p, cfg, "patch_dir")
    p.default_branch = str(cfg.get("default_branch", p.default_branch))
    _mark_cfg(p, cfg, "default_branch")

    p.require_up_to_date = _as_bool(cfg, "require_up_to_date", p.require_up_to_date)
    _mark_cfg(p, cfg, "require_up_to_date")
    p.enforce_main_branch = _as_bool(cfg, "enforce_main_branch", p.enforce_main_branch)
    _mark_cfg(p, cfg, "enforce_main_branch")

    p.update_workspace = _as_bool(cfg, "update_workspace", p.update_workspace)
    _mark_cfg(p, cfg, "update_workspace")
    p.soft_reset_workspace = _as_bool(cfg, "soft_reset_workspace", p.soft_reset_workspace)
    _mark_cfg(p, cfg, "soft_reset_workspace")
    p.delete_workspace_on_success = _as_bool(
        cfg, "delete_workspace_on_success", p.delete_workspace_on_success
    )
    _mark_cfg(p, cfg, "delete_workspace_on_success")
    p.test_mode = _as_bool(cfg, "test_mode", p.test_mode)
    _mark_cfg(p, cfg, "test_mode")

    p.ascii_only_patch = _as_bool(cfg, "ascii_only_patch", p.ascii_only_patch)
    _mark_cfg(p, cfg, "ascii_only_patch")
    p.no_op_fail = _as_bool(cfg, "no_op_fail", p.no_op_fail)
    _mark_cfg(p, cfg, "no_op_fail")
    p.allow_no_op = _as_bool(cfg, "allow_no_op", p.allow_no_op)
    _mark_cfg(p, cfg, "allow_no_op")
    p.enforce_allowed_files = _as_bool(cfg, "enforce_allowed_files", p.enforce_allowed_files)
    _mark_cfg(p, cfg, "enforce_allowed_files")

    p.run_all_tests = _as_bool(cfg, "run_all_tests", p.run_all_tests)
    _mark_cfg(p, cfg, "run_all_tests")
    p.ruff_autofix = _as_bool(cfg, "ruff_autofix", p.ruff_autofix)
    _mark_cfg(p, cfg, "ruff_autofix")
    p.ruff_autofix_legalize_outside = _as_bool(
        cfg, "ruff_autofix_legalize_outside", p.ruff_autofix_legalize_outside
    )
    _mark_cfg(p, cfg, "ruff_autofix_legalize_outside")
    p.ruff_format = _as_bool(cfg, "ruff_format", p.ruff_format)
    _mark_cfg(p, cfg, "ruff_format")

    p.gates_allow_fail = _as_bool(cfg, "gates_allow_fail", p.gates_allow_fail)
    _mark_cfg(p, cfg, "gates_allow_fail")
    p.gates_skip_ruff = _as_bool(cfg, "gates_skip_ruff", p.gates_skip_ruff)
    _mark_cfg(p, cfg, "gates_skip_ruff")
    p.gates_skip_pytest = _as_bool(cfg, "gates_skip_pytest", p.gates_skip_pytest)
    _mark_cfg(p, cfg, "gates_skip_pytest")
    p.gates_skip_mypy = _as_bool(cfg, "gates_skip_mypy", p.gates_skip_mypy)
    _mark_cfg(p, cfg, "gates_skip_mypy")

    p.gates_order = _as_list_str(cfg, "gates_order", p.gates_order)
    _mark_cfg(p, cfg, "gates_order")

    p.ruff_targets = _as_list_str(cfg, "ruff_targets", p.ruff_targets)
    _mark_cfg(p, cfg, "ruff_targets")
    p.pytest_targets = _as_list_str(cfg, "pytest_targets", p.pytest_targets)
    _mark_cfg(p, cfg, "pytest_targets")
    p.mypy_targets = _as_list_str(cfg, "mypy_targets", p.mypy_targets)
    _mark_cfg(p, cfg, "mypy_targets")

    p.pytest_use_venv = _as_bool(cfg, "pytest_use_venv", p.pytest_use_venv)
    _mark_cfg(p, cfg, "pytest_use_venv")

    p.fail_if_live_files_changed = _as_bool(
        cfg, "fail_if_live_files_changed", p.fail_if_live_files_changed
    )
    _mark_cfg(p, cfg, "fail_if_live_files_changed")

    p.live_changed_resolution = str(cfg.get("live_changed_resolution", p.live_changed_resolution))
    _mark_cfg(p, cfg, "live_changed_resolution")
    if p.live_changed_resolution not in ("fail", "overwrite_live", "overwrite_workspace"):
        raise RunnerError(
            "CONFIG",
            "INVALID_LIVE_CHANGED_RESOLUTION",
            (
                f"invalid live_changed_resolution={p.live_changed_resolution!r}; "
                "allowed: fail|overwrite_live|overwrite_workspace"
            ),
        )
    p.commit_and_push = _as_bool(cfg, "commit_and_push", p.commit_and_push)
    _mark_cfg(p, cfg, "commit_and_push")

    p.post_success_audit = _as_bool(cfg, "post_success_audit", p.post_success_audit)
    _mark_cfg(p, cfg, "post_success_audit")

    p.no_rollback = _as_bool(cfg, "no_rollback", p.no_rollback)
    _mark_cfg(p, cfg, "no_rollback")

    p.rollback_workspace_on_fail = _as_bool(
        cfg, "rollback_workspace_on_fail", p.rollback_workspace_on_fail
    )
    _mark_cfg(p, cfg, "rollback_workspace_on_fail")
    p.live_repo_guard = _as_bool(cfg, "live_repo_guard", p.live_repo_guard)
    _mark_cfg(p, cfg, "live_repo_guard")
    p.live_repo_guard_scope = str(cfg.get("live_repo_guard_scope", p.live_repo_guard_scope))
    _mark_cfg(p, cfg, "live_repo_guard_scope")
    p.patch_jail = _as_bool(cfg, "patch_jail", p.patch_jail)
    _mark_cfg(p, cfg, "patch_jail")
    p.patch_jail_unshare_net = _as_bool(cfg, "patch_jail_unshare_net", p.patch_jail_unshare_net)
    _mark_cfg(p, cfg, "patch_jail_unshare_net")

    p.skip_up_to_date = _as_bool(cfg, "skip_up_to_date", p.skip_up_to_date)
    _mark_cfg(p, cfg, "skip_up_to_date")
    p.allow_non_main = _as_bool(cfg, "allow_non_main", p.allow_non_main)
    _mark_cfg(p, cfg, "allow_non_main")

    p.allow_push_fail = _as_bool(cfg, "allow_push_fail", p.allow_push_fail)
    _mark_cfg(p, cfg, "allow_push_fail")

    p.allow_outside_files = _as_bool(cfg, "allow_outside_files", p.allow_outside_files)
    _mark_cfg(p, cfg, "allow_outside_files")
    p.declared_untouched_fail = _as_bool(cfg, "declared_untouched_fail", p.declared_untouched_fail)
    _mark_cfg(p, cfg, "declared_untouched_fail")
    p.allow_declared_untouched = _as_bool(
        cfg, "allow_declared_untouched", p.allow_declared_untouched
    )
    _mark_cfg(p, cfg, "allow_declared_untouched")

    p.audit_rubric_guard = _as_bool(cfg, "audit_rubric_guard", p.audit_rubric_guard)
    _mark_cfg(p, cfg, "audit_rubric_guard")

    if p.live_repo_guard_scope not in ("patch", "patch_and_gates"):
        raise RunnerError(
            "CONFIG", "INVALID", f"invalid live_repo_guard_scope={p.live_repo_guard_scope!r}"
        )

    return p


def apply_cli_overrides(p: Policy, mapping: dict[str, object | None]) -> None:
    for k, v in mapping.items():
        if v is None:
            continue
        if not hasattr(p, k):
            continue
        setattr(p, k, v)
        p._src[k] = "cli"

    # Parse KEY=VALUE overrides (highest priority)
    ovs = mapping.get("overrides")
    if not ovs:
        return
    if isinstance(ovs, str):
        ovs = [ovs]
    if not isinstance(ovs, list):
        return
    for item in ovs:
        if not item:
            continue
        k, v = _parse_override_kv(str(item))
        if hasattr(p, k):
            setattr(p, k, v)
            p._src[k] = "cli"


def policy_for_log(p: Policy) -> str:
    # Stable key order for audit logs.
    keys = sorted([k for k in p.__dict__.keys() if k != "_src"])
    lines: list[str] = []
    for k in keys:
        v = getattr(p, k)
        src = p._src.get(k, "unknown")
        lines.append(f"{k}={v!r} (src={src})")
    return "\n".join(lines)
