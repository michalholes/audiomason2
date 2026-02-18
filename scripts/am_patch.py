#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_read_cfg(cfg_path: Path) -> dict[str, object]:
    try:
        import tomllib

        data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _bootstrap_get_arg(argv: list[str], name: str) -> str | None:
    try:
        i = argv.index(name)
    except ValueError:
        return None
    if i + 1 >= len(argv):
        return None
    return argv[i + 1]


def _bootstrap_venv_policy(argv: list[str]) -> tuple[str, str]:
    # Defaults match Policy defaults.
    mode = "auto"
    py_rel = ".venv/bin/python"

    # CLI-only config selection for bootstrap.
    cfg_arg = _bootstrap_get_arg(argv, "--config")
    cfg_path = Path(cfg_arg) if cfg_arg else (_REPO_ROOT / "scripts" / "am_patch" / "am_patch.toml")
    if cfg_path and not cfg_path.is_absolute():
        cfg_path = _REPO_ROOT / cfg_path

    cfg = _bootstrap_read_cfg(cfg_path)
    flat: dict[str, object] = {}
    if isinstance(cfg, dict):
        # Flatten top-level sections into a single mapping (same convention as runner
        # config loader).
        for k, v in cfg.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    flat[str(kk)] = vv
            else:
                flat[str(k)] = v

    if isinstance(flat.get("venv_bootstrap_mode"), str):
        mode = str(flat["venv_bootstrap_mode"]).strip()
    if isinstance(flat.get("venv_bootstrap_python"), str):
        py_rel = str(flat["venv_bootstrap_python"]).strip() or py_rel

    # CLI overrides for bootstrap only (do not require importing runner modules).
    cli_mode = _bootstrap_get_arg(argv, "--venv-bootstrap-mode")
    if cli_mode:
        mode = cli_mode.strip()
    cli_py = _bootstrap_get_arg(argv, "--venv-bootstrap-python")
    if cli_py:
        py_rel = cli_py.strip() or py_rel

    return mode, py_rel


def _maybe_bootstrap_venv(argv: list[str]) -> None:
    if os.environ.get("AM_PATCH_VENV_BOOTSTRAPPED") == "1":
        return

    mode, py_rel = _bootstrap_venv_policy(argv)
    if mode not in ("auto", "always", "never"):
        # Invalid bootstrap mode: keep legacy behavior to avoid hard failure before config parse.
        mode = "auto"
    if mode == "never":
        return

    venv_py = Path(py_rel)
    venv_py = venv_py if venv_py.is_absolute() else (_REPO_ROOT / venv_py)

    if not venv_py.exists():
        if mode == "always":
            print(f"[am_patch_v2] ERROR: venv python not found: {venv_py}", file=sys.stderr)
            print(
                "[am_patch_v2] Hint: create venv at repo/.venv and install dev deps "
                "(ruff/pytest/mypy).",
                file=sys.stderr,
            )
            raise SystemExit(2)
        # mode == 'auto': keep running under current interpreter.
        return

    cur = Path(sys.executable).resolve()
    if mode == "always" or ".venv" not in str(cur):
        os.environ["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"
        os.execv(str(venv_py), [str(venv_py), *argv])


_maybe_bootstrap_venv(sys.argv)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from am_patch.config import (
    Policy,
)
from am_patch.engine import (
    build_effective_policy,
    build_paths_and_logger,
    finalize_and_report,
    run_mode,
)
from am_patch.fs_junk import fs_junk_ignore_partition
from am_patch.log import Logger
from am_patch.patch_archive_select import select_latest_issue_patch
from am_patch.post_success_audit import run_post_success_audit
from am_patch.repo_root import is_under, resolve_repo_root

# NOTE: Any change that alters runner behavior MUST bump RUNNER_VERSION and MUST update
# the runner specification under scripts/ (e.g., scripts/am_patch_specification.md).
from am_patch.workspace_history import (
    rotate_current_dir,
    workspace_history_dirs,
    workspace_store_current_log,
    workspace_store_current_patch,
)


def _fs_junk_ignore_partition(
    paths: list[str],
    *,
    ignore_prefixes: tuple[str, ...] | list[str],
    ignore_suffixes: tuple[str, ...] | list[str],
    ignore_contains: tuple[str, ...] | list[str],
) -> tuple[list[str], list[str]]:
    return fs_junk_ignore_partition(
        paths,
        ignore_prefixes=ignore_prefixes,
        ignore_suffixes=ignore_suffixes,
        ignore_contains=ignore_contains,
    )


def _run_post_success_audit(logger: Logger, repo_root: Path, policy: Policy) -> None:
    return run_post_success_audit(logger, repo_root, policy)


def _resolve_repo_root() -> Path:
    return resolve_repo_root()


def _is_under(child: Path, parent: Path) -> bool:
    return is_under(child, parent)


def _select_latest_issue_patch(*, patch_dir: Path, issue_id: str, hint_name: str | None) -> Path:
    return select_latest_issue_patch(patch_dir=patch_dir, issue_id=issue_id, hint_name=hint_name)


def _workspace_history_dirs(
    ws_root: Path,
    *,
    history_logs_dir: str = "logs",
    history_oldlogs_dir: str = "oldlogs",
    history_patches_dir: str = "patches",
    history_oldpatches_dir: str = "oldpatches",
) -> tuple[Path, Path, Path, Path]:
    return workspace_history_dirs(
        ws_root,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )


def _rotate_current_dir(cur_dir: Path, old_dir: Path, prev_attempt: int) -> None:
    return rotate_current_dir(cur_dir, old_dir, prev_attempt)


def _workspace_store_current_patch(
    ws,
    patch_script: Path,
    *,
    history_logs_dir: str,
    history_oldlogs_dir: str,
    history_patches_dir: str,
    history_oldpatches_dir: str,
) -> None:
    return workspace_store_current_patch(
        ws,
        patch_script,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )


def _workspace_store_current_log(
    ws,
    log_path: Path,
    *,
    history_logs_dir: str,
    history_oldlogs_dir: str,
    history_patches_dir: str,
    history_oldpatches_dir: str,
) -> None:
    return workspace_store_current_log(
        ws,
        log_path,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )


def main(argv: list[str]) -> int:
    res = build_effective_policy(argv)
    if isinstance(res, int):
        return res
    cli, policy, config_path, used_cfg = res
    ctx = build_paths_and_logger(cli, policy, config_path, used_cfg)
    result = run_mode(ctx)
    return finalize_and_report(ctx, result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
