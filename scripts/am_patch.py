#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import os
import shlex
import shutil
import sys
from contextlib import suppress
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
        print(f"[am_patch_v2] ERROR: venv python not found: {venv_py}", file=sys.stderr)
        print(
            "[am_patch_v2] Hint: create venv at repo/.venv and install dev deps "
            "(ruff/pytest/mypy).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    cur = Path(sys.executable).resolve()
    if mode == "always" or ".venv" not in str(cur):
        os.environ["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"
        os.execv(str(venv_py), [str(venv_py), *argv])


_maybe_bootstrap_venv(sys.argv)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from am_patch import git_ops
from am_patch.archive import archive_patch, make_failure_zip
from am_patch.audit_rubric_check import check_audit_rubric_coverage
from am_patch.cli import parse_args
from am_patch.config import (
    Policy,
    apply_cli_overrides,
    build_policy,
    load_config,
    policy_for_log,
    resolve_config_path,
)
from am_patch.console import stdout_color_enabled, wrap_green, wrap_red
from am_patch.errors import RunnerError, fingerprint
from am_patch.gates import run_badguys, run_gates
from am_patch.lock import FileLock
from am_patch.log import Logger, new_log_file
from am_patch.manifest import load_files
from am_patch.patch_exec import precheck_patch_script, run_patch, run_unified_patch_bundle
from am_patch.patch_select import PatchSelectError, choose_default_patch_input, decide_unified_mode
from am_patch.paths import default_paths, ensure_dirs
from am_patch.promote import promote_files
from am_patch.scope import blessed_gate_outputs_in, changed_paths, enforce_scope_delta
from am_patch.state import load_state, save_state, update_union
from am_patch.status import StatusReporter
from am_patch.version import RUNNER_VERSION
from am_patch.workspace import (
    create_checkpoint,
    delete_workspace,
    drop_checkpoint,
    ensure_workspace,
    open_existing_workspace,
    rollback_to_checkpoint,
)


def _fs_junk_ignore_partition(
    paths: list[str],
    *,
    ignore_prefixes: tuple[str, ...] | list[str],
    ignore_suffixes: tuple[str, ...] | list[str],
    ignore_contains: tuple[str, ...] | list[str],
) -> tuple[list[str], list[str]]:
    """Partition paths into (kept, ignored) for workspace->live promotion hygiene."""
    prefixes = tuple(ignore_prefixes)
    suffixes = tuple(ignore_suffixes)
    contains = tuple(ignore_contains)
    kept: list[str] = []
    ignored: list[str] = []
    for p in paths:
        pp = p.strip()
        if not pp:
            continue
        is_ignored = False
        for pre in prefixes:
            if pp == pre.rstrip("/") or pp.startswith(pre):
                is_ignored = True
                break
        if not is_ignored and any(c in pp for c in contains):
            is_ignored = True
        if not is_ignored:
            for suf in suffixes:
                if pp.endswith(suf):
                    is_ignored = True
                    break
        if is_ignored:
            ignored.append(pp)
        else:
            kept.append(pp)

    # unique preserve order
    def _uniq(xs: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    return _uniq(kept), _uniq(ignored)


def _run_post_success_audit(logger: Logger, repo_root: Path, policy: Policy) -> None:
    """Run audit/audit_report.py after a successful push (best effort, deterministic)."""
    logger.section("AUDIT")
    if not policy.post_success_audit:
        logger.line("audit_report=SKIP (post_success_audit=false)")
        return

    r = logger.run_logged([sys.executable, "-u", "audit/audit_report.py"], cwd=repo_root)
    if r.returncode != 0:
        raise RunnerError("AUDIT", "AUDIT_REPORT_FAILED", "audit/audit_report.py failed")


def _resolve_repo_root() -> Path:
    import subprocess

    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    if p.returncode == 0 and p.stdout.strip():
        return Path(p.stdout.strip())
    return Path.cwd()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _select_latest_issue_patch(*, patch_dir: Path, issue_id: str, hint_name: str | None) -> Path:
    """Select the most recent patch script for ISSUE_ID from patches/, patches/successful/,
    patches/unsuccessful/.

    If hint_name is provided, it is treated as a filename hint (basename). The selection
    prefers that exact name and its archive variants (stem_vN.py). If no hint is provided,
    any script starting with "issue_<id>" is eligible.

    Selection order: newest mtime wins; ties broken by lexical path.
    """
    dirs = [patch_dir, patch_dir / "successful", patch_dir / "unsuccessful"]

    def iter_files(d: Path) -> list[Path]:
        """Return candidate archived patch inputs for -l.

        Supported inputs:
        - *.py   (patch script)
        - *.patch (unified diff)
        - *.zip  (bundle containing at least one *.patch entry)
        """
        import zipfile

        try:
            out: list[Path] = []
            for p in d.iterdir():
                if not p.is_file():
                    continue
                if p.suffix in (".py", ".patch"):
                    out.append(p)
                    continue
                if p.suffix == ".zip":
                    try:
                        with zipfile.ZipFile(p, "r") as z:
                            if any(n.endswith(".patch") for n in z.namelist()):
                                out.append(p)
                    except zipfile.BadZipFile:
                        # Ignore invalid zip files in archive dirs (deterministic: not candidates).
                        continue
            return out
        except FileNotFoundError:
            return []

    issue_prefix = f"issue_{issue_id}"
    hint_stem: str | None = None
    if hint_name:
        bn = Path(hint_name).name
        hint_stem = Path(bn).stem

    cands: list[Path] = []
    for d in dirs:
        for p in iter_files(d):
            name = p.name
            # If a hint_name was provided (explicit patch filename), select by basename
            # (and its _vN archive variants) regardless of ISSUE_ID prefix.
            if hint_stem is not None:
                if p.stem == hint_stem:
                    cands.append(p)
                    continue
                if p.stem.startswith(f"{hint_stem}_v"):
                    tail = p.stem[len(hint_stem) + 2 :]
                    if tail.isdigit():
                        cands.append(p)
                        continue
                continue

            # Otherwise (no hint), select by ISSUE_ID prefix.
            if not name.startswith(issue_prefix):
                continue
            cands.append(p)

    if not cands:
        raise RunnerError(
            "PREFLIGHT", "MANIFEST", f"-l: no archived patch scripts found for issue_id={issue_id}"
        )

    cands.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    return cands[0]


def _workspace_history_dirs(
    ws_root: Path,
    *,
    history_logs_dir: str = "logs",
    history_oldlogs_dir: str = "oldlogs",
    history_patches_dir: str = "patches",
    history_oldpatches_dir: str = "oldpatches",
) -> tuple[Path, Path, Path, Path]:
    logs_dir = ws_root / history_logs_dir
    oldlogs_dir = ws_root / history_oldlogs_dir
    patches_dir = ws_root / history_patches_dir
    oldpatches_dir = ws_root / history_oldpatches_dir
    for d in [logs_dir, oldlogs_dir, patches_dir, oldpatches_dir]:
        d.mkdir(parents=True, exist_ok=True)
    return logs_dir, oldlogs_dir, patches_dir, oldpatches_dir


def _rotate_current_dir(cur_dir: Path, old_dir: Path, prev_attempt: int) -> None:
    if prev_attempt <= 0:
        return
    old_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(cur_dir.glob("*")):
        if not p.is_file():
            continue
        new_name = f"{p.stem}_[attempt{prev_attempt}]{p.suffix}"
        p.replace(old_dir / new_name)


def _workspace_store_current_patch(
    ws,
    patch_script: Path,
    *,
    history_logs_dir: str,
    history_oldlogs_dir: str,
    history_patches_dir: str,
    history_oldpatches_dir: str,
) -> None:
    logs_dir, oldlogs_dir, patches_dir, oldpatches_dir = _workspace_history_dirs(
        ws.root,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )
    _ = logs_dir
    _ = oldlogs_dir

    prev_attempt = int(ws.attempt) - 1
    _rotate_current_dir(patches_dir, oldpatches_dir, prev_attempt)

    # Keep the current patch under its original filename (no suffix).
    dst = patches_dir / patch_script.name
    shutil.copy2(patch_script, dst)


def _workspace_store_current_log(
    ws,
    log_path: Path,
    *,
    history_logs_dir: str,
    history_oldlogs_dir: str,
    history_patches_dir: str,
    history_oldpatches_dir: str,
) -> None:
    logs_dir, oldlogs_dir, patches_dir, oldpatches_dir = _workspace_history_dirs(
        ws.root,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )
    _ = patches_dir
    _ = oldpatches_dir

    prev_attempt = int(ws.attempt) - 1
    _rotate_current_dir(logs_dir, oldlogs_dir, prev_attempt)

    # Keep the current log under its original filename (no suffix).
    dst = logs_dir / log_path.name
    shutil.copy2(log_path, dst)


def main(argv: list[str]) -> int:
    cli = parse_args(argv)

    defaults = Policy()
    config_path = resolve_config_path(cli.config_path, _REPO_ROOT, Path(__file__).resolve().parent)
    cfg, used_cfg = load_config(config_path)
    policy = build_policy(defaults, cfg)

    apply_cli_overrides(
        policy,
        {
            "run_all_tests": cli.run_all_tests,
            "verbosity": getattr(cli, "verbosity", None),
            "console_color": getattr(cli, "console_color", None),
            "allow_no_op": cli.allow_no_op,
            "skip_up_to_date": cli.skip_up_to_date,
            "allow_non_main": cli.allow_non_main,
            "no_rollback": cli.no_rollback,
            "success_archive_name": getattr(cli, "success_archive_name", None),
            "update_workspace": cli.update_workspace,
            "gates_allow_fail": cli.allow_gates_fail,
            "gates_skip_ruff": cli.skip_ruff,
            "gates_skip_pytest": cli.skip_pytest,
            "gates_skip_mypy": cli.skip_mypy,
            "gates_skip_docs": getattr(cli, "skip_docs", None),
            "gates_order": (
                []
                if (
                    getattr(cli, "gates_order", None) is not None
                    and str(cli.gates_order).strip() == ""
                )
                else ([s.strip().lower() for s in str(cli.gates_order).split(",") if s.strip()])
                if getattr(cli, "gates_order", None) is not None
                else None
            ),
            "gate_docs_include": (
                []
                if (
                    getattr(cli, "docs_include", None) is not None
                    and str(cli.docs_include).strip() == ""
                )
                else ([s.strip() for s in str(cli.docs_include).split(",") if s.strip()])
                if getattr(cli, "docs_include", None) is not None
                else None
            ),
            "gate_docs_exclude": (
                []
                if (
                    getattr(cli, "docs_exclude", None) is not None
                    and str(cli.docs_exclude).strip() == ""
                )
                else ([s.strip() for s in str(cli.docs_exclude).split(",") if s.strip()])
                if getattr(cli, "docs_exclude", None) is not None
                else None
            ),
            "ruff_autofix_legalize_outside": getattr(cli, "ruff_autofix_legalize_outside", None),
            "soft_reset_workspace": cli.soft_reset_workspace,
            "enforce_allowed_files": cli.enforce_allowed_files,
            # New safety + gate controls
            "rollback_workspace_on_fail": getattr(cli, "rollback_workspace_on_fail", None),
            "live_repo_guard": getattr(cli, "live_repo_guard", None),
            "patch_jail": getattr(cli, "patch_jail", None),
            "patch_jail_unshare_net": getattr(cli, "patch_jail_unshare_net", None),
            "ruff_format": getattr(cli, "ruff_format", None),
            "pytest_use_venv": getattr(cli, "pytest_use_venv", None),
            "compile_check": getattr(cli, "compile_check", None),
            "post_success_audit": getattr(cli, "post_success_audit", None),
            "test_mode": getattr(cli, "test_mode", None),
            "unified_patch": getattr(cli, "unified_patch", None),
            "unified_patch_strip": getattr(cli, "patch_strip", None),
            "overrides": getattr(cli, "overrides", None),
        },
    )

    # Group B: map extra CLI flags onto policy keys (symmetry helpers)
    if getattr(cli, "require_push_success", None):
        policy.allow_push_fail = False
        policy._src["allow_push_fail"] = "cli"
    if getattr(cli, "disable_promotion", None):
        policy.commit_and_push = False
        policy._src["commit_and_push"] = "cli"
    if getattr(cli, "allow_live_changed", None):
        policy.fail_if_live_files_changed = False
        policy._src["fail_if_live_files_changed"] = "cli"
        policy.live_changed_resolution = "overwrite_live"
        policy._src["live_changed_resolution"] = "cli"
    if getattr(cli, "keep_workspace", None):
        policy.delete_workspace_on_success = False
        policy._src["delete_workspace_on_success"] = "cli"
    if getattr(cli, "allow_outside_files", None):
        policy.allow_outside_files = True
        policy._src["allow_outside_files"] = "cli"
    if getattr(cli, "allow_declared_untouched", None):
        policy.allow_declared_untouched = True
        policy._src["allow_declared_untouched"] = "cli"

    if cli.mode == "show_config":
        # Print the same effective config/policy that is normally logged at the start of a run.
        # No workspace, no log file, no side effects.
        print(f"config_path={config_path} used={used_cfg}")
        print(policy_for_log(policy))
        return 0

    if policy.test_mode and cli.mode != "workspace":
        raise SystemExit("test-mode is supported only in workspace mode")

    repo_root = Path(policy.repo_root) if policy.repo_root else _resolve_repo_root()
    patch_root = Path(policy.patch_dir) if policy.patch_dir else (repo_root / policy.patch_dir_name)
    isolated_work_patch_dir: Path | None = None
    patch_dir = patch_root
    if (
        policy.test_mode
        and getattr(policy, "test_mode_isolate_patch_dir", True)
        and policy.patch_dir is None
        and cli.issue_id is not None
    ):
        isolated_work_patch_dir = (
            patch_root / "_test_mode" / f"issue_{cli.issue_id}_pid_{os.getpid()}"
        )
        patch_dir = isolated_work_patch_dir
    paths = default_paths(
        repo_root=repo_root,
        patch_dir=patch_root,
        logs_dir_name=policy.patch_layout_logs_dir,
        workspaces_dir_name=policy.patch_layout_workspaces_dir,
        successful_dir_name=policy.patch_layout_successful_dir,
        unsuccessful_dir_name=policy.patch_layout_unsuccessful_dir,
        lockfile_name=policy.lockfile_name,
        current_log_symlink_name=policy.current_log_symlink_name,
    )
    ensure_dirs(paths)

    log_path = new_log_file(
        paths.logs_dir,
        issue_id=cli.issue_id,
        ts_format=policy.log_ts_format,
        issue_template=policy.log_template_issue,
        finalize_template=policy.log_template_finalize,
    )
    verbosity = getattr(policy, "verbosity", "verbose")
    tee_to_screen = verbosity in ("verbose", "debug")
    logger = Logger(
        log_path=log_path,
        symlink_path=paths.symlink_path,
        tee_to_screen=tee_to_screen,
        symlink_enabled=policy.current_log_symlink_enabled,
        symlink_target_rel=Path(policy.patch_layout_logs_dir) / log_path.name,
    )

    status = StatusReporter(enabled=verbosity in ("normal", "verbose", "debug"))
    status.start()

    color_enabled = stdout_color_enabled(getattr(policy, "console_color", "auto"))

    def _screen_line(line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def _stage_do(stage: str) -> None:
        status.set_stage(stage)
        if verbosity == "normal":
            _screen_line(f"DO: {stage}")

    def _stage_ok(stage: str) -> None:
        if verbosity == "normal":
            _screen_line(f"{wrap_green('OK', color_enabled)}: {stage}")

    def _stage_fail(stage: str) -> None:
        if verbosity == "normal":
            _screen_line(f"{wrap_red('FAIL', color_enabled)}: {stage}")

    def _gate_progress(token: str) -> None:
        kind, _, stage = token.partition(":")
        if not stage:
            return
        status.set_stage(stage)
        if verbosity != "normal":
            return
        if kind in ("DO", "OK", "FAIL"):
            label = kind
            if kind == "OK":
                label = wrap_green(kind, color_enabled)
            elif kind == "FAIL":
                label = wrap_red(kind, color_enabled)
            _screen_line(f"{label}: {stage}")

    def _is_runner_path(rel: str) -> bool:
        p = (rel or "").strip().replace("\\", "/").lstrip("/")
        if not p:
            return False
        return (
            p == "scripts/am_patch.py"
            or p.startswith("scripts/am_patch/")
            or p
            in (
                "scripts/am_patch.md",
                "scripts/am_patch_specification.md",
                "scripts/am_patch_instructions.md",
            )
        )

    def _runner_touched(paths: list[str]) -> bool:
        return any(_is_runner_path(p) for p in paths)

    def _maybe_run_badguys(
        *,
        cwd: Path,
        decision_paths: list[str],
    ) -> None:
        mode = str(getattr(policy, "gate_badguys_runner", "auto") or "auto").strip().lower()
        if mode not in ("auto", "on", "off"):
            mode = "auto"

        if mode == "off":
            logger.line("gate_badguys=SKIP (disabled_by_policy)")
            return

        if mode == "auto" and not _runner_touched(decision_paths):
            logger.line("gate_badguys=SKIP (runner_not_touched)")
            return

        # mode == "on" OR (auto and runner_touched)
        reason = "forced_on" if mode == "on" else "runner_touched"
        logger.line(f"gate_badguys=DO ({reason})")
        stage = "GATE_BADGUYS"
        _gate_progress(f"DO:{stage}")
        # When running badguys from the live repo root (repo_root), badguys will
        # spawn nested am_patch runs. Those nested runs must not fight with this
        # parent runner's lock. Also, in workspace mode, we must test the patched
        # runner (workspace repo) instead of the live tree.
        #
        # Strategy:
        # - If badguys are invoked in a workspace repo (cwd != repo_root), run them
        #   directly there (they will naturally test the patched runner).
        # - If badguys are invoked in the live repo root (cwd == repo_root), clone
        #   the live repo into an isolated workspace subdir and run badguys there.
        #   This tests the current live state while avoiding lock conflicts.
        # badguys command/cwd are controllable via cfg and CLI.
        raw_cmd = getattr(policy, "gate_badguys_command", None)
        command: list[str]
        if raw_cmd is None:
            command = ["badguys/badguys.py", "-q"]
        elif isinstance(raw_cmd, str):
            command = shlex.split(raw_cmd)
        else:
            command = [str(x) for x in raw_cmd]
        if not command:
            command = ["badguys/badguys.py", "-q"]

        cwd_mode = str(getattr(policy, "gate_badguys_cwd", "auto") or "auto").strip().lower()
        if cwd_mode not in ("auto", "workspace", "clone", "live"):
            cwd_mode = "auto"
        logger.line(f"gate_badguys_cwd={cwd_mode}")

        run_cwd = cwd
        isolated_repo: Path | None = None
        if cwd_mode == "clone" or (cwd_mode == "auto" and cwd.resolve() == repo_root.resolve()):
            tag = f"{cli.mode}_{cli.issue_id or 'noissue'}"
            isolated_repo = paths.workspaces_dir / "_badguys_gate" / tag
            # Deterministic: always recreate.
            if isolated_repo.exists():
                shutil.rmtree(isolated_repo)
            isolated_repo.parent.mkdir(parents=True, exist_ok=True)
            src_repo = repo_root if cwd.resolve() == repo_root.resolve() else cwd
            logger.line(f"gate_badguys_repo=CLONE {src_repo} -> {isolated_repo}")
            r = logger.run_logged(
                ["git", "clone", "--no-hardlinks", str(src_repo), str(isolated_repo)],
                cwd=paths.workspaces_dir,
            )
            if r.returncode != 0:
                raise RunnerError("GATES", "GATES", "badguys clone failed")
            run_cwd = isolated_repo
        elif cwd_mode == "live":
            run_cwd = repo_root
            logger.line(f"gate_badguys_repo=LIVE {repo_root}")
        else:
            logger.line(f"gate_badguys_repo=CWD {cwd}")

        ok = False
        try:
            ok = run_badguys(logger, cwd=run_cwd, repo_root=repo_root, command=command)
        finally:
            if isolated_repo is not None:
                if ok:
                    shutil.rmtree(isolated_repo, ignore_errors=True)
                else:
                    logger.line(f"gate_badguys_repo_kept={isolated_repo}")
        _gate_progress(f"OK:{stage}" if ok else f"FAIL:{stage}")
        if not ok:
            raise RunnerError("GATES", "GATES", "gate failed: badguys")

    if verbosity == "normal":
        _screen_line(f"RUN: issue={cli.issue_id or 'unknown'} mode={cli.mode} verbosity=normal")
        _screen_line(f"LOG: {log_path}")

    lock = FileLock(paths.lock_path)
    exit_code: int = 0
    patch_script: Path | None = None
    used_patch_for_zip: Path | None = None
    files_for_fail_zip: list[str] = []
    failed_patch_blobs_for_zip: list[tuple[str, bytes]] = []
    patch_applied_successfully: bool = False
    rollback_ckpt_for_posthook = None
    rollback_ws_for_posthook = None

    delete_workspace_after_archive: bool = False
    ws_for_posthook = None
    push_ok_for_posthook: bool | None = None
    final_commit_sha: str | None = None
    final_pushed_files: list[str] | None = None
    final_fail_stage: str | None = None
    final_fail_reason: str | None = None
    primary_fail_stage: str | None = None
    primary_fail_reason: str | None = None
    secondary_failures: list[tuple[str, str]] = []
    try:
        logger.section("AM_PATCH START")
        logger.line(f"RUNNER_VERSION={RUNNER_VERSION}")
        logger.line(f"repo_root={repo_root}")
        logger.line(f"patch_dir={patch_dir}")
        if patch_dir != patch_root:
            logger.line(f"patch_root={patch_root}")
        logger.line(f"config_path={config_path} used={used_cfg}")
        logger.line(f"log_path={log_path}")
        logger.line(f"symlink_path={paths.symlink_path} -> logs/{log_path.name}")
        logger.section("EFFECTIVE CONFIG")
        logger.line(policy_for_log(policy))

        lock.acquire()

        if cli.mode == "finalize_workspace":
            # Finalize an existing workspace: gates in workspace, then promote to live, then
            # gates+commit+push in live.
            issue_id = cli.issue_id
            assert issue_id is not None

            ws = open_existing_workspace(
                logger,
                paths.workspaces_dir,
                issue_id,
                issue_dir_template=policy.workspace_issue_dir_template,
                repo_dir_name=policy.workspace_repo_dir_name,
                meta_filename=policy.workspace_meta_filename,
            )
            logger.section("FINALIZE WORKSPACE")
            logger.line(f"workspace_root={ws.root}")
            logger.line(f"workspace_repo={ws.repo}")
            logger.line(f"workspace_meta={ws.meta_path}")
            logger.line(f"workspace_base_sha={ws.base_sha}")

            # Commit message is always sourced from workspace meta.json.
            if not ws.message or not str(ws.message).strip():
                raise RunnerError(
                    "PREFLIGHT", "WORKSPACE", "workspace meta.json missing non-empty message"
                )

            # Gates in workspace first.

            decision_paths_ws = changed_paths(logger, ws.repo)

            run_gates(
                logger,
                cwd=ws.repo,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                docs_include=policy.gate_docs_include,
                docs_exclude=policy.gate_docs_exclude,
                docs_required_files=policy.gate_docs_required_files,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
                decision_paths=decision_paths_ws,
                progress=_gate_progress,
            )

            _maybe_run_badguys(cwd=ws.repo, decision_paths=decision_paths_ws)

            changed_all = changed_paths(logger, ws.repo)
            promote_list, ignored = _fs_junk_ignore_partition(
                changed_all,
                ignore_prefixes=policy.scope_ignore_prefixes,
                ignore_suffixes=policy.scope_ignore_suffixes,
                ignore_contains=policy.scope_ignore_contains,
            )
            logger.section("PROMOTION PLAN")
            logger.line(f"changed_all={changed_all}")
            logger.line(f"ignored_paths={ignored}")
            logger.line(f"files_to_promote={promote_list}")
            if not promote_list:
                raise RunnerError("PREFLIGHT", "WORKSPACE", "no promotable workspace changes")

            promote_files(
                logger=logger,
                workspace_repo=ws.repo,
                live_repo=repo_root,
                base_sha=ws.base_sha,
                files_to_promote=promote_list,
                fail_if_live_changed=policy.fail_if_live_files_changed,
                live_changed_resolution=policy.live_changed_resolution,
            )

            # Gates in live repo.
            decision_paths_live = list(promote_list)
            run_gates(
                logger,
                cwd=repo_root,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                docs_include=policy.gate_docs_include,
                docs_exclude=policy.gate_docs_exclude,
                docs_required_files=policy.gate_docs_required_files,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
                decision_paths=decision_paths_live,
                progress=_gate_progress,
            )

            sha: str | None = None

            _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_live)

            sha: str | None = None
            push_ok: bool | None = None
            if policy.commit_and_push:
                sha = git_ops.commit(logger, repo_root, str(ws.message), stage_all=False)
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )
                final_commit_sha = sha

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={sha}")
                if push_ok is True:
                    logger.line("push=OK")
                else:
                    if policy.allow_push_fail:
                        logger.line("push=FAILED_ALLOWED")
                    else:
                        logger.line("push=FAILED")
            else:
                logger.line("commit_sha=SKIPPED")
                logger.line("push=SKIPPED")

            # Cleanup: mirror workspace-mode behavior.
            # Delete workspace on success unless policy.delete_workspace_on_success is false.
            #
            # When promotion is disabled (no commit/push), keep the workspace even if the
            # default policy would delete it. This avoids losing an easy re-run path while
            # the live repo has uncommitted changes.
            workspace_deleted = False
            if policy.delete_workspace_on_success and policy.commit_and_push:
                delete_workspace(logger, ws)
                workspace_deleted = True
            elif policy.delete_workspace_on_success and not policy.commit_and_push:
                logger.line("workspace_delete=SKIPPED (disable-promotion)")

            # Post-success audit: show current audit progress after SUCCESS and workspace cleanup.
            # Runs on the live repo (repo_root), not the workspace.
            if push_ok is True and workspace_deleted:
                _run_post_success_audit(logger, repo_root, policy)

            return 0

        if cli.mode == "finalize":
            git_ops.fetch(logger, repo_root)
            if policy.require_up_to_date and not policy.skip_up_to_date:
                git_ops.require_up_to_date(logger, repo_root, policy.default_branch)
            if policy.enforce_main_branch and not policy.allow_non_main:
                git_ops.require_branch(logger, repo_root, policy.default_branch)

            decision_paths_finalize = changed_paths(logger, repo_root)

            run_gates(
                logger,
                cwd=repo_root,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                docs_include=policy.gate_docs_include,
                docs_exclude=policy.gate_docs_exclude,
                docs_required_files=policy.gate_docs_required_files,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
                decision_paths=decision_paths_finalize,
                progress=_gate_progress,
            )

            _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_finalize)

            sha: str | None = None

            push_ok: bool | None = None
            if policy.commit_and_push:
                sha = git_ops.commit(logger, repo_root, cli.message or "finalize")
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )
                final_commit_sha = sha

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={sha}")
                if push_ok is True:
                    logger.line("push=OK")
                else:
                    if policy.allow_push_fail:
                        logger.line("push=FAILED_ALLOWED")
                    else:
                        logger.line("push=FAILED")
            else:
                logger.line("commit_sha=SKIPPED")
                logger.line("push=SKIPPED")

            # Wire finalize results into the unified end-of-run summary.
            push_ok_for_posthook = push_ok
            if push_ok is True and sha:
                try:
                    ns = git_ops.commit_changed_files_name_status(logger, repo_root, sha)
                    final_pushed_files = [f"{st} {p}" for (st, p) in ns]
                except Exception:
                    # Best-effort only; never override SUCCESS contract.
                    final_pushed_files = None

            if push_ok is True:
                _run_post_success_audit(logger, repo_root, policy)
            return 0

        issue_id = cli.issue_id
        assert issue_id is not None

        patch_script: Path | None = None

        if getattr(cli, "load_latest_patch", None):
            hint_name = Path(cli.patch_script).name if cli.patch_script else None
            patch_script = _select_latest_issue_patch(
                patch_dir=patch_root, issue_id=issue_id, hint_name=hint_name
            )
        elif cli.patch_script:
            raw = Path(cli.patch_script)
            if raw.is_absolute():
                patch_script = raw
            else:
                # Accept either:
                #  - a path relative to CWD (e.g. patches/issue_999.py), OR
                #  - a bare filename resolved under patch_dir (e.g. issue_999.py).
                cand_cwd = (Path.cwd() / raw).resolve()
                cand_patchdir = (patch_root / raw).resolve()
                if cand_cwd.exists() and _is_under(cand_cwd, patch_root):
                    patch_script = cand_cwd
                elif cand_patchdir.exists():
                    patch_script = cand_patchdir
                else:
                    raise RunnerError(
                        "PREFLIGHT",
                        "MANIFEST",
                        f"patch script not found (tried: {cand_cwd} and {cand_patchdir})",
                    )
        else:
            try:
                patch_script = choose_default_patch_input(patch_root, issue_id)
            except PatchSelectError as e:
                raise RunnerError("PREFLIGHT", "MANIFEST", str(e)) from e

        if not patch_script.exists():
            raise RunnerError("PREFLIGHT", "MANIFEST", f"patch script not found: {patch_script}")

        # Enforce patch script location: must be under patch_root.
        if not _is_under(patch_script, patch_root):
            raise RunnerError(
                "PREFLIGHT",
                "PATCH_PATH",
                f"patch script must be under {patch_root} (got {patch_script})",
            )
        try:
            unified_mode = decide_unified_mode(
                patch_script, explicit_unified=bool(getattr(policy, "unified_patch", False))
            )
        except PatchSelectError as e:
            raise RunnerError("PREFLIGHT", "PATCH_PATH", str(e)) from e

        if not unified_mode:
            precheck_patch_script(patch_script, ascii_only=policy.ascii_only_patch)

        # Audit rubric guard (future-proofing): fail fast when new audit domains are added
        # but audit/audit_rubric.yaml does not contain the required runtime evidence commands.
        if getattr(policy, "audit_rubric_guard", True):
            missing = check_audit_rubric_coverage(repo_root)
            if missing:
                # Build a deterministic, copy-paste friendly guidance message.
                lines: list[str] = []
                lines.append(
                    "audit rubric guard failed: missing required runtime evidence commands in "
                    "audit/audit_rubric.yaml"
                )
                lines.append("")
                lines.append(
                    "Add these command(s) to audit/audit_rubric.yaml (under "
                    "runtime_evidence.commands, and mark required: true):"
                )
                lines.append("")
                for m in missing:
                    lines.append(
                        f"- domain={m.domain} cli={m.cli_name} caps={','.join(m.capabilities)}"
                    )
                    for c in m.missing_commands:
                        lines.append(f"  - {c} --format yaml")
                lines.append("")
                lines.append("Then re-run runtime evidence to verify:")
                lines.append(
                    "  python3 audit/run_runtime_evidence.py --repo . --rubric "
                    "audit/audit_rubric.yaml"
                )
                raise RunnerError("PREFLIGHT", "CONFIG", "\n".join(lines))

        # Git preflight (live repo)
        git_ops.fetch(logger, repo_root)
        if policy.require_up_to_date and not policy.skip_up_to_date:
            git_ops.require_up_to_date(logger, repo_root, policy.default_branch)
        if policy.enforce_main_branch and not policy.allow_non_main:
            git_ops.require_branch(logger, repo_root, policy.default_branch)

        base_sha = git_ops.head_sha(logger, repo_root)
        files_current = [] if unified_mode else load_files(patch_script)

        logger.section("DECLARED FILES")
        for _p in files_current:
            logger.line(_p)

        ws = ensure_workspace(
            logger=logger,
            workspaces_dir=paths.workspaces_dir,
            issue_id=issue_id,
            live_repo=repo_root,
            base_sha=base_sha,
            update=policy.update_workspace,
            soft_reset=policy.soft_reset_workspace,
            message=cli.message,
            issue_dir_template=policy.workspace_issue_dir_template,
            repo_dir_name=policy.workspace_repo_dir_name,
            meta_filename=policy.workspace_meta_filename,
            history_logs_dir=policy.workspace_history_logs_dir,
            history_oldlogs_dir=policy.workspace_history_oldlogs_dir,
            history_patches_dir=policy.workspace_history_patches_dir,
            history_oldpatches_dir=policy.workspace_history_oldpatches_dir,
        )
        ws_for_posthook = ws
        _workspace_store_current_patch(
            ws,
            patch_script,
            history_logs_dir=policy.workspace_history_logs_dir,
            history_oldlogs_dir=policy.workspace_history_oldlogs_dir,
            history_patches_dir=policy.workspace_history_patches_dir,
            history_oldpatches_dir=policy.workspace_history_oldpatches_dir,
        )
        logger.section("WORKSPACE META")
        logger.line(f"workspace_root={ws.root}")
        logger.line(f"workspace_repo={ws.repo}")
        logger.line(f"workspace_base_sha={ws.base_sha}")
        logger.line(f"attempt={ws.attempt}")

        # Load per-issue cumulative state (allowed union).
        st = load_state(ws.root, ws.base_sha)
        logger.section("ISSUE STATE (before)")
        logger.line(f"allowed_union={sorted(st.allowed_union)}")

        # Optional live repo guard (must stay unchanged until promotion).
        live_guard_before: str | None = None
        if policy.live_repo_guard:
            logger.section("LIVE REPO GUARD (before)")
            r = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_before = r.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_before)}")

        ckpt = create_checkpoint(logger, ws.repo, enabled=policy.rollback_workspace_on_fail)

        # Baseline changes BEFORE running patch (so scope is delta).
        before = changed_paths(logger, ws.repo)

        try:
            touched_for_zip: list[str] = []
            failed_patch_blobs: list[tuple[str, bytes]] = []
            patch_applied_any = False

            _stage_do("PATCH_APPLY")

            if unified_mode:
                res = run_unified_patch_bundle(
                    logger,
                    patch_script,
                    workspace_repo=ws.repo,
                    policy=policy,
                )
                patch_applied_any = res.applied_ok > 0
                files_current = list(res.declared_files)
                touched_for_zip = list(res.touched_files)
                failed_patch_blobs = [(f.name, f.data) for f in res.failures]

                if res.failures:
                    primary_fail_stage = "PATCH"
                    primary_fail_reason = "patch apply failed"

                # For patched.zip on failure: always include touched targets and failed patch blobs.
                # This must be available even if scope enforcement fails later.
                files_for_fail_zip = sorted(set(touched_for_zip) | set(files_current))
                failed_patch_blobs_for_zip = list(failed_patch_blobs)
                patch_applied_successfully = patch_applied_any

            else:
                run_patch(logger, patch_script, workspace_repo=ws.repo, policy=policy)
                patch_applied_any = True

            after = changed_paths(logger, ws.repo)
            touched: list[str] = []
            try:
                touched = enforce_scope_delta(
                    logger,
                    files_current=files_current,
                    before=before,
                    after=after,
                    no_op_fail=policy.no_op_fail,
                    allow_no_op=policy.allow_no_op,
                    allow_outside_files=policy.allow_outside_files,
                    allowed_union=st.allowed_union,
                    declared_untouched_fail=policy.declared_untouched_fail,
                    allow_declared_untouched=policy.allow_declared_untouched,
                    blessed_outputs=policy.blessed_gate_outputs,
                    ignore_prefixes=policy.scope_ignore_prefixes,
                    ignore_suffixes=policy.scope_ignore_suffixes,
                    ignore_contains=policy.scope_ignore_contains,
                )
            except RunnerError as _scope_e:
                if primary_fail_stage is None:
                    raise
                logger.section("SECONDARY FAILURE")
                logger.line(str(_scope_e))
                secondary_failures.append((str(_scope_e.stage), str(_scope_e.message)))

            if primary_fail_stage is None:
                _stage_ok("PATCH_APPLY")
            else:
                _stage_fail("PATCH_APPLY")

            # Snapshot dirty paths immediately after patch (before gates).
            dirty_after_patch = list(after)

            # For patched.zip on failure: include changed files plus all touched targets
            # (including failed patches).
            files_for_fail_zip = sorted(set(touched) | set(touched_for_zip))
            failed_patch_blobs_for_zip = list(failed_patch_blobs)
            patch_applied_successfully = patch_applied_any

        except Exception:
            _stage_fail("PATCH_APPLY")
            # Defer rollback until after diagnostics archive is created.
            rollback_ckpt_for_posthook = ckpt
            rollback_ws_for_posthook = ws
            raise

        # Live repo guard: after patching (before gates) if scope includes patch.
        if (
            policy.live_repo_guard
            and live_guard_before is not None
            and policy.live_repo_guard_scope == "patch"
        ):
            logger.section("LIVE REPO GUARD (after patch)")
            r2 = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_after = r2.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_after)}")
            if live_guard_after != live_guard_before:
                raise RunnerError(
                    "SECURITY",
                    "LIVE_REPO_CHANGED",
                    "live repo changed during patching (expected no changes)",
                )

        # Update union AFTER patch success (even if this run was noop with -n).
        st = update_union(st, files_current)
        if policy.allow_outside_files:
            # Spec: -a must also legalize any touched paths into allowed_union for this ISSUE_ID.
            st = update_union(st, touched)
            logger.line(f"legalized_outside_files={sorted(set(touched) - set(files_current))}")
        save_state(ws.root, st)
        logger.section("ISSUE STATE (after)")
        logger.line(f"allowed_union={sorted(st.allowed_union)}")

        defer_patch_apply_failure = False
        if primary_fail_stage is not None:
            if secondary_failures:
                logger.section("SECONDARY FAILURES (summary)")
                for stg, msg in secondary_failures:
                    logger.line(f"{stg}: {msg}")

            if not patch_applied_any:
                # Nothing was applied; fail immediately.
                # Defer rollback until after diagnostics archive is created.
                rollback_ckpt_for_posthook = ckpt
                rollback_ws_for_posthook = ws
                raise RunnerError(
                    "PATCH", "PATCH_APPLY", primary_fail_reason or "patch apply failed"
                )

            # Partial apply: keep going so gates can run for diagnostics, but the run
            # must still end as FAIL with PATCH_APPLY as the primary reason.
            defer_patch_apply_failure = True

        # Gates in workspace (NO rollback)
        run_gates(
            logger,
            cwd=ws.repo,
            repo_root=repo_root,
            run_all=policy.run_all_tests,
            compile_check=policy.compile_check,
            compile_targets=policy.compile_targets,
            compile_exclude=policy.compile_exclude,
            allow_fail=policy.gates_allow_fail,
            skip_ruff=policy.gates_skip_ruff,
            skip_pytest=policy.gates_skip_pytest,
            skip_mypy=policy.gates_skip_mypy,
            skip_docs=policy.gates_skip_docs,
            docs_include=policy.gate_docs_include,
            docs_exclude=policy.gate_docs_exclude,
            docs_required_files=policy.gate_docs_required_files,
            ruff_format=policy.ruff_format,
            ruff_autofix=policy.ruff_autofix,
            ruff_targets=policy.ruff_targets,
            pytest_targets=policy.pytest_targets,
            mypy_targets=policy.mypy_targets,
            gates_order=policy.gates_order,
            pytest_use_venv=policy.pytest_use_venv,
            decision_paths=touched,
            progress=_gate_progress,
        )

        _maybe_run_badguys(cwd=ws.repo, decision_paths=touched)

        # Live repo guard: optionally also after gates.
        if (
            policy.live_repo_guard
            and live_guard_before is not None
            and policy.live_repo_guard_scope == "patch_and_gates"
        ):
            logger.section("LIVE REPO GUARD (after gates)")
            r2 = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_after = r2.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_after)}")
            if live_guard_after != live_guard_before:
                raise RunnerError(
                    "SECURITY",
                    "LIVE_REPO_CHANGED",
                    "live repo changed during patching/gates (expected no changes)",
                )

        if policy.test_mode:
            logger.section("TEST MODE")
            logger.line("TEST_MODE=1")
            logger.line("TEST_MODE_STOP=AFTER_WORKSPACE_GATES_AND_LIVE_GUARD")
            logger.line(
                "STOP: test mode (no promotion, no live gates, no commit/push, no archives)"
            )
            return 0

        # Determine what to promote/commit: all current dirty paths within allowed_union.
        dirty_all = changed_paths(logger, ws.repo)

        # Ruff autofix may introduce additional changes after the patch. When enabled,
        # automatically legalize ruff-only changes outside FILES (bounded to ruff_targets).
        if policy.ruff_autofix and getattr(policy, "ruff_autofix_legalize_outside", True):
            patch_set = set(dirty_after_patch)
            now_set = set(dirty_all)
            ruff_only = sorted(p for p in (now_set - patch_set) if p)
            if ruff_only:

                def _under_targets(rel: str) -> bool:
                    for t in policy.ruff_targets:
                        t = (t or "").strip().rstrip("/")
                        if not t:
                            continue
                        if rel == t or rel.startswith(t + "/"):
                            return True
                    return False

                legalized = sorted([p for p in ruff_only if _under_targets(p)])
                if legalized:
                    st = update_union(st, legalized)
                    save_state(ws.root, st)
                    logger.line(f"legalized_ruff_autofix_files={legalized}")
        if defer_patch_apply_failure:
            # Ensure failure archive includes any gate-induced changes.
            files_for_fail_zip = sorted(set(files_for_fail_zip) | set(dirty_all))
            # Defer rollback until after diagnostics archive is created.
            rollback_ckpt_for_posthook = ckpt
            rollback_ws_for_posthook = ws
            raise RunnerError("PATCH", "PATCH_APPLY", primary_fail_reason or "patch apply failed")

        allowed_union = set(st.allowed_union)
        dirty_allowed = [p for p in dirty_all if p in allowed_union]
        dirty_blessed = blessed_gate_outputs_in(
            dirty_all, blessed_outputs=policy.blessed_gate_outputs
        )
        # Promote allowed_union paths + blessed gate outputs (without requiring -a).
        to_promote: list[str] = []
        seen_tp: set[str] = set()
        for pp in dirty_allowed + dirty_blessed:
            if pp in seen_tp:
                continue
            seen_tp.add(pp)
            to_promote.append(pp)

        logger.section("PROMOTION PLAN")
        logger.line(f"dirty_all={dirty_all}")
        logger.line(f"dirty_allowed={dirty_allowed}")
        logger.line(f"dirty_blessed={dirty_blessed}")
        logger.line(f"files_to_promote={to_promote}")

        promote_files(
            logger=logger,
            workspace_repo=ws.repo,
            live_repo=repo_root,
            base_sha=ws.base_sha,
            files_to_promote=to_promote,
            fail_if_live_changed=policy.fail_if_live_files_changed
            and (not policy.update_workspace),
            live_changed_resolution=policy.live_changed_resolution,
        )

        sha = ""
        decision_paths_post_promote = list(to_promote)
        _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_post_promote)

        sha = ""
        push_ok: bool | None = None
        if policy.commit_and_push:
            sha = git_ops.commit(
                logger,
                repo_root,
                (ws.message or f"Issue {issue_id}: apply patch"),
                stage_all=False,
            )
            final_commit_sha = sha
            push_ok = git_ops.push(
                logger, repo_root, policy.default_branch, allow_fail=policy.allow_push_fail
            )

            if push_ok is True and sha:
                try:
                    ns = git_ops.commit_changed_files_name_status(logger, repo_root, sha)
                    final_pushed_files = [f"{st} {p}" for (st, p) in ns]
                except Exception:
                    # Best-effort only; never override SUCCESS contract.
                    final_pushed_files = None

        push_ok_for_posthook = push_ok

        used_patch_for_zip = archive_patch(logger, patch_script, paths.successful_dir)

        drop_checkpoint(logger, ws.repo, ckpt)

        delete_workspace_after_archive = bool(policy.delete_workspace_on_success)

        logger.section("SUCCESS")
        if sha:
            logger.line(f"commit_sha={sha}")
        if policy.commit_and_push:
            if push_ok is True:
                logger.line("push=OK")
            elif push_ok is False:
                if policy.allow_push_fail:
                    logger.line("push=FAILED_ALLOWED")
                else:
                    logger.line("push=FAILED")
            else:
                logger.line("push=UNKNOWN")
        else:
            logger.line("push=SKIPPED")
        return 0

    except RunnerError as e:
        exit_code = 1
        logger.section("FAILURE")
        logger.line(str(e))
        logger.line(fingerprint(e))

        # Contract: map internal error to stable STAGE/REASON for final summary.
        final_fail_stage = str(e.stage)
        final_fail_reason = str(e.message)
        if e.stage == "GATES":
            msg = str(e.message)
            gate = None
            if "gate failed:" in msg:
                gate = msg.split("gate failed:", 1)[1].strip().split()[0]
            elif "gates failed:" in msg:
                gate = msg.split("gates failed:", 1)[1].strip().split(",")[0].strip()
            if gate:
                final_fail_stage = f"GATE_{gate.upper()}"
                final_fail_reason = f"{gate} failed"
            else:
                final_fail_stage = "GATES"
                final_fail_reason = "gates failed"
        elif e.stage == "PATCH":
            final_fail_stage = "PATCH_APPLY"
            final_fail_reason = "patch apply failed"
        elif e.stage == "PREFLIGHT":
            final_fail_stage = "PREFLIGHT"
            final_fail_reason = "invalid inputs"
        elif e.stage in ("PROMOTION", "SCOPE"):
            final_fail_stage = "PROMOTE" if e.stage == "PROMOTION" else "SCOPE"
            final_fail_reason = "promotion failed" if e.stage == "PROMOTION" else "scope failed"

        return 1
    finally:
        # Posthook: always create an archive after a workspace-mode run.
        # - on failure: patched.zip (as before)
        # - on success: patched_success.zip
        try:
            if cli.mode in ("workspace", "finalize", "finalize_workspace") and (
                not policy.test_mode
            ):
                issue_id = cli.issue_id or "unknown"

                archived_path: Path | None = used_patch_for_zip if cli.mode == "workspace" else None

                # Post-success audit (if enabled by workflow). If audit fails, treat as failure and
                # produce diagnostics archive instead of success archive.
                if exit_code == 0 and push_ok_for_posthook is True:
                    try:
                        _run_post_success_audit(logger, repo_root, policy)
                    except Exception as _audit_e:
                        exit_code = 1
                        logger.section("AUDIT")
                        logger.line(f"post_success_audit_failed={_audit_e!r}")
                if cli.mode == "workspace":
                    if exit_code == 0:
                        # Best effort: if caller returned success before archiving, archive now.
                        if (
                            archived_path is None
                            and patch_script is not None
                            and patch_script.exists()
                        ):
                            archived_path = archive_patch(
                                logger, patch_script, paths.successful_dir
                            )
                    else:
                        # Failure: archive the exact patch script selected for this run into
                        # unsuccessful/.
                        ps: Path | None = None
                        if patch_script is not None:
                            ps = patch_script
                        else:
                            if cli.patch_script:
                                raw = Path(cli.patch_script)
                                if raw.is_absolute():
                                    ps = raw
                                else:
                                    cand_repo = (repo_root / raw).resolve()
                                    cand_patchdir = (paths.patch_dir / raw).resolve()
                                    ps = cand_repo if cand_repo.exists() else cand_patchdir
                            else:
                                ps = (paths.patch_dir / f"issue_{issue_id}.py").resolve()

                        candidates: list[Path] = []
                        if ps is not None:
                            candidates.append(ps)
                            candidates.append((paths.patch_dir / ps.name).resolve())

                        seen: set[str] = set()
                        uniq: list[Path] = []
                        for c in candidates:
                            k = str(c)
                            if k not in seen:
                                seen.add(k)
                                uniq.append(c)

                        for c in uniq:
                            if c.exists():
                                archived_path = archive_patch(logger, c, paths.unsuccessful_dir)
                                break

                        if archived_path is None:
                            logger.section("ARCHIVE PATCH")
                            logger.line(f"no patch script found to archive; tried: {uniq}")

                # Post-success audit (if enabled by workflow). If audit fails, treat as failure and
                # produce diagnostics archive instead of success archive.
                if exit_code == 0 and push_ok_for_posthook is True:
                    try:
                        _run_post_success_audit(logger, repo_root, policy)
                    except Exception as _audit_e:
                        exit_code = 1
                        logger.section("AUDIT")
                        logger.line(f"post_success_audit_failed={_audit_e!r}")
                if exit_code == 0:
                    # Success: create git-archive snapshot of final repo state (no log inside).
                    # Success: create git-archive snapshot of final repo state.
                    repo_name = repo_root.name
                    branch_name = git_ops.current_branch(logger, repo_root).strip()
                    if branch_name == "HEAD":
                        branch_name = "detached"

                    template = policy.success_archive_name
                    try:
                        rendered = template.format(repo=repo_name, branch=branch_name)
                    except Exception as e:
                        raise RunnerError(
                            "POSTHOOK",
                            "CONFIG",
                            f"invalid success_archive_name template: {template!r} ({e!r})",
                        ) from e

                    name = Path(rendered).name
                    if not name.lower().endswith(".zip"):
                        name = f"{name}.zip"
                    zip_path = paths.patch_dir / name
                    git_ops.git_archive(logger, repo_root, zip_path, treeish="HEAD")
                else:
                    # Failure: create diagnostics archive with log + subset of repo files.
                    zip_path = paths.patch_dir / policy.failure_zip_name

                    include_patch_paths: list[Path] = []
                    include_patch_blobs: list[tuple[str, bytes]] = []

                    # Include patch script only when patching did not apply.
                    if (
                        not patch_applied_successfully
                        and archived_path is not None
                        and archived_path.exists()
                        and not unified_mode
                    ):
                        include_patch_paths.append(archived_path)

                    # Unified patch mode: include only failed .patch inputs (not the original zip).
                    for name, data in failed_patch_blobs_for_zip:
                        include_patch_blobs.append((name, data))

                    ws_repo = (
                        ws_for_posthook.repo
                        if ws_for_posthook is not None
                        else (paths.workspaces_dir / f"issue_{issue_id}" / "repo")
                    )

                    make_failure_zip(
                        logger,
                        zip_path,
                        workspace_repo=ws_repo,
                        log_path=log_path,
                        include_repo_files=files_for_fail_zip,
                        include_patch_blobs=include_patch_blobs,
                        include_patch_paths=include_patch_paths,
                        log_dir_name=policy.failure_zip_log_dir,
                        patch_dir_name=policy.failure_zip_patch_dir,
                    )
                # Deferred rollback after diagnostics archive.
                # Keeps workspace available for zip creation.
                if (
                    exit_code != 0
                    and rollback_ws_for_posthook is not None
                    and rollback_ckpt_for_posthook is not None
                    and getattr(policy, "rollback_workspace_on_fail", False)
                ):
                    rollback_to_checkpoint(
                        logger,
                        rollback_ws_for_posthook.repo,
                        rollback_ckpt_for_posthook,
                    )

                if (
                    exit_code == 0
                    and delete_workspace_after_archive
                    and ws_for_posthook is not None
                ):
                    delete_workspace(logger, ws_for_posthook)
        except Exception as _e:
            try:
                logger.section("POSTHOOK-ERROR")
                logger.line(repr(_e))
            except Exception:
                pass

        if cli.mode == "workspace" and policy.test_mode:
            try:
                logger.section("TEST MODE CLEANUP")
                if ws_for_posthook is None:
                    logger.line("workspace_present=0")
                else:
                    logger.line("workspace_present=1")
                    logger.line(f"workspace_root={ws_for_posthook.root}")
                    logger.line("workspace_delete=1")
                    delete_workspace(logger, ws_for_posthook)
            except Exception as _e2:
                try:
                    logger.section("TEST_MODE_CLEANUP_ERROR")
                    logger.line(repr(_e2))
                except Exception:
                    pass

        with suppress(Exception):
            status.stop()
        with suppress(Exception):
            lock.release()
        logger.close()

        # Final on-screen summary (contract).
        try:
            if exit_code == 0:
                sys.stdout.write(f"RESULT: {wrap_green('SUCCESS', color_enabled)}\n")
                if push_ok_for_posthook is True and final_pushed_files is not None:
                    sys.stdout.write("FILES:\n\n")
                    for line in final_pushed_files:
                        sys.stdout.write(f"{line}\n")
                if final_commit_sha:
                    sys.stdout.write(f"COMMIT: {final_commit_sha}\n")
                else:
                    sys.stdout.write("COMMIT: (none)\n")
                if policy.commit_and_push:
                    if push_ok_for_posthook is True:
                        sys.stdout.write(f"PUSH: {wrap_green('OK', color_enabled)}\n")
                    elif push_ok_for_posthook is False:
                        sys.stdout.write(f"PUSH: {wrap_red('FAIL', color_enabled)}\n")
                    else:
                        sys.stdout.write("PUSH: UNKNOWN\n")
                sys.stdout.write(f"LOG: {log_path}\n")
            else:
                sys.stdout.write(f"RESULT: {wrap_red('FAIL', color_enabled)}\n")
                stage = final_fail_stage or "INTERNAL"
                reason = final_fail_reason or "unexpected error"
                sys.stdout.write(f"STAGE: {stage}\n")
                sys.stdout.write(f"REASON: {reason}\n")
                sys.stdout.write(f"LOG: {log_path}\n")
            sys.stdout.flush()
        except Exception:
            pass

        if policy.test_mode and isolated_work_patch_dir is not None:
            with suppress(Exception):
                shutil.rmtree(isolated_work_patch_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
