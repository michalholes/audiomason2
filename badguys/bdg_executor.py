from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from badguys.bdg_evaluator import StepResult
from badguys.bdg_loader import BdgStep, BdgTest
from badguys.bdg_materializer import MaterializedAssets



def _subst_token(value: str, *, issue_id: str) -> str:
    if value == "${issue_id}":
        return str(issue_id)
    return value


def _logs_dir(repo_root: Path) -> Path:
    cfg_path = repo_root / "badguys" / "config.toml"
    raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    logs_rel = raw.get("suite", {}).get("logs_dir", "badguys/per_run_logs")
    return repo_root / Path(str(logs_rel))

@dataclass(frozen=True)
class ExecOutcome:
    ok: bool
    results: List[StepResult]
    messages: List[str]


def execute_bdg(*, repo_root: Path, cfg_runner_cmd: list[str], issue_id: str, bdg: BdgTest,
                mats: MaterializedAssets) -> list[StepResult]:
    results: List[StepResult] = []
    for step in bdg.steps:
        results.append(_exec_one(repo_root=repo_root, cfg_runner_cmd=cfg_runner_cmd, issue_id=issue_id,
                                 step=step, mats=mats))
    return results


def _exec_one(*, repo_root: Path, cfg_runner_cmd: list[str], issue_id: str, step: BdgStep,
              mats: MaterializedAssets) -> StepResult:
    op = step.op
    p = step.params

    if op == "RUN_RUNNER":
        input_asset = p.get("input_asset")
        if input_asset is not None and not isinstance(input_asset, str):
            raise SystemExit("FAIL: bdg: input_asset must be string")
        extra_args = p.get("extra_args", [])
        if not (isinstance(extra_args, list) and all(isinstance(x, str) for x in extra_args)):
            raise SystemExit("FAIL: bdg: extra_args must be list[str]")
        argv = list(cfg_runner_cmd)
        argv.extend([_subst_token(a, issue_id=issue_id) for a in extra_args])
        if input_asset:
            path = mats.files.get(input_asset)
            if path is None:
                raise SystemExit(f"FAIL: bdg: missing materialized asset: {input_asset}")
            argv.append(str(path))
        cp = subprocess.run(argv, cwd=str(repo_root), text=True, capture_output=True)
        return StepResult(rc=int(cp.returncode), stdout=cp.stdout, stderr=cp.stderr, value=None)

    if op == "DISCOVER_TESTS":
        from badguys.discovery import discover_tests

        include = p.get("include", [])
        exclude = p.get("exclude", [])
        if not (isinstance(include, list) and all(isinstance(x, str) for x in include)):
            raise SystemExit("FAIL: bdg: include must be list[str]")
        if not (isinstance(exclude, list) and all(isinstance(x, str) for x in exclude)):
            raise SystemExit("FAIL: bdg: exclude must be list[str]")
        try:
            tests = discover_tests(
                repo_root=repo_root,
                config_path=Path("badguys/config.toml"),
                cli_commit_limit=None,
                cli_include=list(include),
                cli_exclude=list(exclude),
            )
        except SystemExit as e:
            return StepResult(rc=2, stdout=None, stderr=str(e), value=None)
        names = [t.name for t in tests]
        return StepResult(rc=0, stdout=None, stderr=None, value=names)


    if op == "BUILD_CFG":
        input_asset = p.get("input_asset")
        if not isinstance(input_asset, str):
            raise SystemExit("FAIL: bdg: BUILD_CFG requires input_asset")
        cfg_path = mats.files.get(input_asset)
        if cfg_path is None:
            raise SystemExit(f"FAIL: bdg: missing materialized asset: {input_asset}")

        cli_runner_verbosity = p.get("cli_runner_verbosity")
        cli_console_verbosity = p.get("cli_console_verbosity")
        cli_log_verbosity = p.get("cli_log_verbosity")
        cli_commit_limit = p.get("cli_commit_limit")

        for key, val in [
            ("cli_runner_verbosity", cli_runner_verbosity),
            ("cli_console_verbosity", cli_console_verbosity),
            ("cli_log_verbosity", cli_log_verbosity),
        ]:
            if val is not None and not isinstance(val, str):
                raise SystemExit(f"FAIL: bdg: {key} must be string or omitted")
        if cli_commit_limit is not None and not isinstance(cli_commit_limit, int):
            raise SystemExit("FAIL: bdg: cli_commit_limit must be int or omitted")

        from badguys.run_suite import _make_cfg

        cfg = _make_cfg(
            repo_root,
            cfg_path.relative_to(repo_root),
            cli_runner_verbosity,
            cli_console_verbosity,
            cli_log_verbosity,
            cli_commit_limit,
        )
        joined = " ".join(cfg.runner_cmd)
        return StepResult(rc=0, stdout=None, stderr=None, value=joined)

    if op == "READ_STEP_LOG":
        name = p.get("test_name")
        if name is None:
            name = bdg.test_id
        if not isinstance(name, str):
            raise SystemExit("FAIL: bdg: test_name must be string")
        log_dir = _logs_dir(repo_root)
        log_path = log_dir / f"{name}.log"
        if not log_path.exists():
            return StepResult(rc=1, stdout=None, stderr=f"missing log: {log_path}", value="")
        return StepResult(rc=0, stdout=None, stderr=None, value=log_path.read_text(encoding="utf-8"))


    raise SystemExit(f"FAIL: bdg: unsupported op: {op}")