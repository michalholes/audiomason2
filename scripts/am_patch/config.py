from __future__ import annotations

import re
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import RunnerError


def default_config_path(scripts_dir: Path) -> Path:
    """Return the default config path (repo-relative, deterministic)."""
    return scripts_dir / "am_patch" / "am_patch.toml"


def resolve_config_path(cli_config: str | None, repo_root: Path, scripts_dir: Path) -> Path:
    """Resolve config path.

    - If cli_config is provided, use it (relative paths are resolved against repo_root).
    - Otherwise use the default config path under scripts/.
    """
    if cli_config:
        p = Path(cli_config)
        return p if p.is_absolute() else (repo_root / p)
    return default_config_path(scripts_dir)


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
    # When patch_dir is not explicitly set, patch_dir_name determines the default
    # directory under repo_root used for runner artifacts.
    patch_dir_name: str = "patches"

    # Layout names under patch_dir.
    patch_layout_logs_dir: str = "logs"
    patch_layout_workspaces_dir: str = "workspaces"
    patch_layout_successful_dir: str = "successful"
    patch_layout_unsuccessful_dir: str = "unsuccessful"

    # Lock and "current log" symlink names under patch_dir.
    lockfile_name: str = "am_patch.lock"
    current_log_symlink_name: str = "am_patch.log"
    current_log_symlink_enabled: bool = True

    # Log filename templates (placeholders: {issue}, {ts}) and timestamp format.
    log_ts_format: str = "%Y%m%d_%H%M%S"
    log_template_issue: str = "am_patch_issue_{issue}_{ts}.log"
    log_template_finalize: str = "am_patch_finalize_{ts}.log"

    # Failure diagnostics zip naming and internal directory structure.
    failure_zip_name: str = "patched.zip"
    failure_zip_log_dir: str = "logs"
    failure_zip_patch_dir: str = "patches"

    # Workspace on-disk layout.
    workspace_issue_dir_template: str = "issue_{issue}"
    workspace_repo_dir_name: str = "repo"
    workspace_meta_filename: str = "meta.json"

    # Per-workspace history directories.
    workspace_history_logs_dir: str = "logs"
    workspace_history_oldlogs_dir: str = "oldlogs"
    workspace_history_patches_dir: str = "patches"
    workspace_history_oldpatches_dir: str = "oldpatches"

    # Scope exemptions.
    blessed_gate_outputs: list[str] = field(
        default_factory=lambda: ["audit/results/pytest_junit.xml"]
    )
    scope_ignore_prefixes: list[str] = field(
        default_factory=lambda: [
            ".am_patch/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            "__pycache__/",
        ]
    )
    scope_ignore_suffixes: list[str] = field(default_factory=lambda: [".pyc"])
    scope_ignore_contains: list[str] = field(default_factory=lambda: ["/__pycache__/"])

    # Venv bootstrap (entrypoint re-exec) behavior.
    # - auto: re-exec only when current interpreter is outside repo/.venv
    # - always: always re-exec into venv python (unless already there)
    # - never: disable bootstrap
    venv_bootstrap_mode: str = "auto"  # auto|always|never
    venv_bootstrap_python: str = ".venv/bin/python"

    default_branch: str = "main"

    # Success archive name template for git-archive success zip.
    # Placeholders: {repo}, {branch}
    # Final filename is sanitized to a basename and forced to end with ".zip".
    success_archive_name: str = "{repo}-{branch}.zip"

    require_up_to_date: bool = True
    enforce_main_branch: bool = True

    update_workspace: bool = False
    soft_reset_workspace: bool = False
    test_mode: bool = False
    # In --test-mode, isolate runner work paths (lock/logs/workspaces/archives)
    # under patches/_test_mode/issue_<ID>_pid_<PID>/ to avoid collisions with live runs.
    # Only applies when patch_dir is not explicitly set.
    test_mode_isolate_patch_dir: bool = True
    delete_workspace_on_success: bool = True

    ascii_only_patch: bool = True

    # Screen output verbosity (default: verbose = today's behavior)
    verbosity: str = "verbose"

    # File log level (default: verbose to preserve today's detailed log output)
    log_level: str = "verbose"

    # Console output coloring for OK/FAIL tokens.
    # auto: enable colors only when stdout is a TTY
    # always: always enable
    # never: disable
    console_color: str = "auto"  # auto|always|never

    # Unified patch input (.patch / .zip)
    unified_patch: bool = False
    unified_patch_continue: bool = True
    unified_patch_strip: int | None = None  # None=infer
    unified_patch_touch_on_fail: bool = True
    no_op_fail: bool = True
    allow_no_op: bool = False
    enforce_allowed_files: bool = True

    run_all_tests: bool = True
    compile_check: bool = True
    compile_targets: list[str] = field(default_factory=lambda: ["."])
    compile_exclude: list[str] = field(default_factory=list)
    ruff_autofix: bool = True
    ruff_autofix_legalize_outside: bool = True

    # NEW: ruff format before ruff check (default ON)
    ruff_format: bool = True

    gates_allow_fail: bool = False
    gates_skip_ruff: bool = False
    gates_skip_pytest: bool = False
    gates_skip_mypy: bool = False
    gates_skip_docs: bool = False
    gates_on_partial_apply: bool = False
    gates_on_zero_apply: bool = False
    gate_docs_include: list[str] = field(default_factory=lambda: ["src", "plugins"])
    gate_docs_exclude: list[str] = field(default_factory=lambda: ["badguys", "patches"])
    gate_docs_required_files: list[str] = field(
        default_factory=lambda: ["docs/changes.md", "docs/specification.md"]
    )
    gates_order: list[str] = field(
        default_factory=lambda: ["compile", "ruff", "pytest", "mypy", "docs"]
    )

    # NEW: extra runner-only gate: badguys (default auto)
    # - auto: run only when patch touches runner files
    # - on: always run
    # - off: never run
    gate_badguys_runner: str = "auto"

    # BADGUYS gate command (argv without python prefix). Default: badguys/badguys.py -q
    gate_badguys_command: list[str] = field(default_factory=lambda: ["badguys/badguys.py", "-q"])

    # Where to run the BADGUYS gate. auto|workspace|clone|live
    gate_badguys_cwd: str = "auto"
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
    rollback_workspace_on_fail: str = "none-applied"

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


def _as_rollback_mode(d: dict[str, Any], k: str, default: str) -> str:
    v = d.get(k, default)
    if isinstance(v, bool):
        # Legacy bool config support:
        # True  -> none-applied (rollback only if 0 patches applied)
        # False -> never
        return "none-applied" if v else "never"
    if not isinstance(v, str):
        raise TypeError(f"config key {k!r} must be a string or bool, got {type(v).__name__}")
    if v not in ("none-applied", "always", "never"):
        raise ValueError(f"config key {k!r} has invalid value {v!r}")
    return v


def _as_list_str(d: dict[str, Any], k: str, default: list[str]) -> list[str]:
    v = d.get(k)
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


def _validate_basename(v: str, *, field: str) -> str:
    s = str(v).strip()
    if not s:
        raise RunnerError("CONFIG", "INVALID", f"{field} must be non-empty")
    if "/" in s or "\\" in s:
        raise RunnerError(
            "CONFIG", "INVALID", f"{field} must be a basename (no path separators): {s!r}"
        )
    return s


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


def _coerce_override_value(cur: object, raw: object) -> object:
    # Preserve type of existing policy field where possible.
    if isinstance(cur, bool):
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            s = raw.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off"):
                return False
        raise RunnerError("CONFIG", "INVALID", f"invalid boolean override: {raw!r}")

    if isinstance(cur, int):
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw.strip())
            except Exception as e:
                raise RunnerError("CONFIG", "INVALID", f"invalid integer override: {raw!r}") from e
        raise RunnerError("CONFIG", "INVALID", f"invalid integer override: {raw!r}")

    if isinstance(cur, list):
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            parts = [p for p in (x.strip() for x in raw.split(",")) if p]
            return parts
        raise RunnerError("CONFIG", "INVALID", f"invalid list override: {raw!r}")

    return raw


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
    p.patch_dir_name = str(cfg.get("patch_dir_name", p.patch_dir_name))
    _mark_cfg(p, cfg, "patch_dir_name")

    p.patch_layout_logs_dir = str(cfg.get("patch_layout_logs_dir", p.patch_layout_logs_dir))
    _mark_cfg(p, cfg, "patch_layout_logs_dir")
    p.patch_layout_workspaces_dir = str(
        cfg.get("patch_layout_workspaces_dir", p.patch_layout_workspaces_dir)
    )
    _mark_cfg(p, cfg, "patch_layout_workspaces_dir")
    p.patch_layout_successful_dir = str(
        cfg.get("patch_layout_successful_dir", p.patch_layout_successful_dir)
    )
    _mark_cfg(p, cfg, "patch_layout_successful_dir")
    p.patch_layout_unsuccessful_dir = str(
        cfg.get("patch_layout_unsuccessful_dir", p.patch_layout_unsuccessful_dir)
    )
    _mark_cfg(p, cfg, "patch_layout_unsuccessful_dir")

    p.lockfile_name = str(cfg.get("lockfile_name", p.lockfile_name))
    _mark_cfg(p, cfg, "lockfile_name")
    p.current_log_symlink_name = str(
        cfg.get("current_log_symlink_name", p.current_log_symlink_name)
    )
    _mark_cfg(p, cfg, "current_log_symlink_name")
    p.current_log_symlink_enabled = _as_bool(
        cfg, "current_log_symlink_enabled", p.current_log_symlink_enabled
    )
    _mark_cfg(p, cfg, "current_log_symlink_enabled")

    p.log_ts_format = str(cfg.get("log_ts_format", p.log_ts_format))
    _mark_cfg(p, cfg, "log_ts_format")
    p.log_template_issue = str(cfg.get("log_template_issue", p.log_template_issue))
    _mark_cfg(p, cfg, "log_template_issue")
    p.log_template_finalize = str(cfg.get("log_template_finalize", p.log_template_finalize))
    _mark_cfg(p, cfg, "log_template_finalize")

    p.failure_zip_name = str(cfg.get("failure_zip_name", p.failure_zip_name))
    _mark_cfg(p, cfg, "failure_zip_name")
    p.failure_zip_log_dir = str(cfg.get("failure_zip_log_dir", p.failure_zip_log_dir))
    _mark_cfg(p, cfg, "failure_zip_log_dir")
    p.failure_zip_patch_dir = str(cfg.get("failure_zip_patch_dir", p.failure_zip_patch_dir))
    _mark_cfg(p, cfg, "failure_zip_patch_dir")

    p.workspace_issue_dir_template = str(
        cfg.get("workspace_issue_dir_template", p.workspace_issue_dir_template)
    )
    _mark_cfg(p, cfg, "workspace_issue_dir_template")
    p.workspace_repo_dir_name = str(cfg.get("workspace_repo_dir_name", p.workspace_repo_dir_name))
    _mark_cfg(p, cfg, "workspace_repo_dir_name")
    p.workspace_meta_filename = str(cfg.get("workspace_meta_filename", p.workspace_meta_filename))
    _mark_cfg(p, cfg, "workspace_meta_filename")

    p.workspace_history_logs_dir = str(
        cfg.get("workspace_history_logs_dir", p.workspace_history_logs_dir)
    )
    _mark_cfg(p, cfg, "workspace_history_logs_dir")
    p.workspace_history_oldlogs_dir = str(
        cfg.get("workspace_history_oldlogs_dir", p.workspace_history_oldlogs_dir)
    )
    _mark_cfg(p, cfg, "workspace_history_oldlogs_dir")
    p.workspace_history_patches_dir = str(
        cfg.get("workspace_history_patches_dir", p.workspace_history_patches_dir)
    )
    _mark_cfg(p, cfg, "workspace_history_patches_dir")
    p.workspace_history_oldpatches_dir = str(
        cfg.get("workspace_history_oldpatches_dir", p.workspace_history_oldpatches_dir)
    )
    _mark_cfg(p, cfg, "workspace_history_oldpatches_dir")

    p.blessed_gate_outputs = _as_list_str(cfg, "blessed_gate_outputs", p.blessed_gate_outputs)
    _mark_cfg(p, cfg, "blessed_gate_outputs")
    p.scope_ignore_prefixes = _as_list_str(cfg, "scope_ignore_prefixes", p.scope_ignore_prefixes)
    _mark_cfg(p, cfg, "scope_ignore_prefixes")
    p.scope_ignore_suffixes = _as_list_str(cfg, "scope_ignore_suffixes", p.scope_ignore_suffixes)
    _mark_cfg(p, cfg, "scope_ignore_suffixes")
    p.scope_ignore_contains = _as_list_str(cfg, "scope_ignore_contains", p.scope_ignore_contains)
    _mark_cfg(p, cfg, "scope_ignore_contains")

    p.venv_bootstrap_mode = str(cfg.get("venv_bootstrap_mode", p.venv_bootstrap_mode))
    _mark_cfg(p, cfg, "venv_bootstrap_mode")
    p.venv_bootstrap_python = str(cfg.get("venv_bootstrap_python", p.venv_bootstrap_python))
    _mark_cfg(p, cfg, "venv_bootstrap_python")

    p.default_branch = str(cfg.get("default_branch", p.default_branch))
    _mark_cfg(p, cfg, "default_branch")
    p.success_archive_name = str(cfg.get("success_archive_name", p.success_archive_name))
    _mark_cfg(p, cfg, "success_archive_name")

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
    p.test_mode_isolate_patch_dir = _as_bool(
        cfg, "test_mode_isolate_patch_dir", p.test_mode_isolate_patch_dir
    )
    _mark_cfg(p, cfg, "test_mode_isolate_patch_dir")

    p.ascii_only_patch = _as_bool(cfg, "ascii_only_patch", p.ascii_only_patch)
    _mark_cfg(p, cfg, "ascii_only_patch")
    allowed_levels = ("debug", "verbose", "normal", "warning", "quiet")

    p.verbosity = str(cfg.get("verbosity", p.verbosity))
    _mark_cfg(p, cfg, "verbosity")
    if p.verbosity not in allowed_levels:
        raise RunnerError(
            "CONFIG",
            "INVALID_VERBOSITY",
            f"invalid verbosity={p.verbosity!r}; allowed: debug|verbose|normal|warning|quiet",
        )

    p.log_level = str(cfg.get("log_level", p.log_level))
    _mark_cfg(p, cfg, "log_level")
    if p.log_level not in allowed_levels:
        raise RunnerError(
            "CONFIG",
            "INVALID_LOG_LEVEL",
            f"invalid log_level={p.log_level!r}; allowed: debug|verbose|normal|warning|quiet",
        )

    p.console_color = str(cfg.get("console_color", p.console_color))
    _mark_cfg(p, cfg, "console_color")
    if p.console_color not in ("auto", "always", "never"):
        raise RunnerError(
            "CONFIG",
            "INVALID_CONSOLE_COLOR",
            f"invalid console_color={p.console_color!r}; allowed: auto|always|never",
        )

    # Phase 2: hardcoded layout/settings must be configurable (cfg + CLI overrides).
    p.patch_dir_name = _validate_basename(p.patch_dir_name, field="patch_dir_name")
    p.patch_layout_logs_dir = _validate_basename(
        p.patch_layout_logs_dir, field="patch_layout_logs_dir"
    )
    p.patch_layout_workspaces_dir = _validate_basename(
        p.patch_layout_workspaces_dir, field="patch_layout_workspaces_dir"
    )
    p.patch_layout_successful_dir = _validate_basename(
        p.patch_layout_successful_dir, field="patch_layout_successful_dir"
    )
    p.patch_layout_unsuccessful_dir = _validate_basename(
        p.patch_layout_unsuccessful_dir, field="patch_layout_unsuccessful_dir"
    )
    p.lockfile_name = _validate_basename(p.lockfile_name, field="lockfile_name")
    p.current_log_symlink_name = _validate_basename(
        p.current_log_symlink_name, field="current_log_symlink_name"
    )
    p.failure_zip_name = _validate_basename(p.failure_zip_name, field="failure_zip_name")

    p.failure_zip_log_dir = _validate_basename(p.failure_zip_log_dir, field="failure_zip_log_dir")
    p.failure_zip_patch_dir = _validate_basename(
        p.failure_zip_patch_dir, field="failure_zip_patch_dir"
    )

    p.workspace_issue_dir_template = str(p.workspace_issue_dir_template).strip() or "issue_{issue}"
    p.workspace_repo_dir_name = _validate_basename(
        p.workspace_repo_dir_name, field="workspace_repo_dir_name"
    )
    p.workspace_meta_filename = _validate_basename(
        p.workspace_meta_filename, field="workspace_meta_filename"
    )

    p.workspace_history_logs_dir = _validate_basename(
        p.workspace_history_logs_dir, field="workspace_history_logs_dir"
    )
    p.workspace_history_oldlogs_dir = _validate_basename(
        p.workspace_history_oldlogs_dir, field="workspace_history_oldlogs_dir"
    )
    p.workspace_history_patches_dir = _validate_basename(
        p.workspace_history_patches_dir, field="workspace_history_patches_dir"
    )
    p.workspace_history_oldpatches_dir = _validate_basename(
        p.workspace_history_oldpatches_dir, field="workspace_history_oldpatches_dir"
    )

    if "{ts}" not in p.log_template_issue or "{issue}" not in p.log_template_issue:
        raise RunnerError(
            "CONFIG",
            "INVALID",
            "log_template_issue must contain {issue} and {ts}",
        )
    if "{ts}" not in p.log_template_finalize:
        raise RunnerError("CONFIG", "INVALID", "log_template_finalize must contain {ts}")

    if p.venv_bootstrap_mode not in ("auto", "always", "never"):
        raise RunnerError(
            "CONFIG",
            "INVALID",
            f"invalid venv_bootstrap_mode={p.venv_bootstrap_mode!r}; allowed: auto|always|never",
        )
    # venv_bootstrap_python may be relative to repo root; validate non-empty only.
    if not str(p.venv_bootstrap_python).strip():
        raise RunnerError("CONFIG", "INVALID", "venv_bootstrap_python must be non-empty")

    p.no_op_fail = _as_bool(cfg, "no_op_fail", p.no_op_fail)
    _mark_cfg(p, cfg, "no_op_fail")
    p.allow_no_op = _as_bool(cfg, "allow_no_op", p.allow_no_op)
    _mark_cfg(p, cfg, "allow_no_op")
    p.enforce_allowed_files = _as_bool(cfg, "enforce_allowed_files", p.enforce_allowed_files)
    _mark_cfg(p, cfg, "enforce_allowed_files")

    p.run_all_tests = _as_bool(cfg, "run_all_tests", p.run_all_tests)
    _mark_cfg(p, cfg, "run_all_tests")
    p.compile_check = _as_bool(cfg, "compile_check", p.compile_check)
    _mark_cfg(p, cfg, "compile_check")
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
    p.gates_on_partial_apply = _as_bool(cfg, "gates_on_partial_apply", p.gates_on_partial_apply)
    _mark_cfg(p, cfg, "gates_on_partial_apply")
    p.gates_on_zero_apply = _as_bool(cfg, "gates_on_zero_apply", p.gates_on_zero_apply)
    _mark_cfg(p, cfg, "gates_on_zero_apply")

    p.gates_skip_ruff = _as_bool(cfg, "gates_skip_ruff", p.gates_skip_ruff)
    _mark_cfg(p, cfg, "gates_skip_ruff")
    p.gates_skip_pytest = _as_bool(cfg, "gates_skip_pytest", p.gates_skip_pytest)
    _mark_cfg(p, cfg, "gates_skip_pytest")
    p.gates_skip_mypy = _as_bool(cfg, "gates_skip_mypy", p.gates_skip_mypy)
    _mark_cfg(p, cfg, "gates_skip_mypy")

    p.gates_order = _as_list_str(cfg, "gates_order", p.gates_order)
    _mark_cfg(p, cfg, "gates_order")

    p.gate_badguys_runner = str(cfg.get("gate_badguys_runner", p.gate_badguys_runner))
    _mark_cfg(p, cfg, "gate_badguys_runner")
    if p.gate_badguys_runner not in ("auto", "on", "off"):
        raise RunnerError(
            "CONFIG",
            "INVALID",
            f"invalid gate_badguys_runner={p.gate_badguys_runner!r}; allowed: auto|on|off",
        )

    # gate_badguys_command: argv list without python prefix
    if "gate_badguys_command" in cfg:
        raw_cmd = cfg["gate_badguys_command"]
        if isinstance(raw_cmd, str):
            cmd_list = shlex.split(raw_cmd)
        elif isinstance(raw_cmd, list) and all(isinstance(x, str) for x in raw_cmd):
            cmd_list = raw_cmd
        else:
            raise RunnerError(
                "CONFIG",
                "INVALID",
                "gate_badguys_command must be a string or list[str]",
            )
        if not cmd_list:
            raise RunnerError("CONFIG", "INVALID", "gate_badguys_command must be non-empty")
        p.gate_badguys_command = cmd_list
        _mark_cfg(p, cfg, "gate_badguys_command")

    # gate_badguys_cwd: auto|workspace|clone|live
    if "gate_badguys_cwd" in cfg:
        p.gate_badguys_cwd = str(cfg["gate_badguys_cwd"]).strip().lower()
        _mark_cfg(p, cfg, "gate_badguys_cwd")
        if p.gate_badguys_cwd not in ("auto", "workspace", "clone", "live"):
            raise RunnerError(
                "CONFIG",
                "INVALID",
                (
                    f"invalid gate_badguys_cwd={p.gate_badguys_cwd!r}; "
                    "allowed: auto|workspace|clone|live"
                ),
            )

    p.compile_targets = _as_list_str(cfg, "compile_targets", p.compile_targets)
    _mark_cfg(p, cfg, "compile_targets")
    p.compile_exclude = _as_list_str(cfg, "compile_exclude", p.compile_exclude)
    _mark_cfg(p, cfg, "compile_exclude")

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

    p.rollback_workspace_on_fail = _as_rollback_mode(
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
        if not hasattr(p, k):
            continue
        cur = getattr(p, k)
        coerced = _coerce_override_value(cur, v)
        if isinstance(cur, list):
            # Append semantics for list fields.
            if isinstance(coerced, list):
                cur.extend(coerced)
            else:
                raise RunnerError("CONFIG", "INVALID", f"invalid list override: {coerced!r}")
        else:
            setattr(p, k, coerced)
        p._src[k] = "cli"


def policy_for_log(p: Policy) -> str:
    # Stable key order for audit logs.
    keys = sorted([k for k in p.__dict__ if k != "_src"])
    lines: list[str] = []
    for k in keys:
        v = getattr(p, k)
        src = p._src.get(k, "unknown")
        lines.append(f"{k}={v!r} (src={src})")
    return "\n".join(lines)
