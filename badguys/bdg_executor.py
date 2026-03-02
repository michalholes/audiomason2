from __future__ import annotations

import subprocess
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
        tests = discover_tests(
            repo_root=repo_root,
            config_path=Path("badguys/config.toml"),
            cli_commit_limit=None,
            cli_include=list(include),
            cli_exclude=list(exclude),
        )
        names = [t.name for t in tests]
        return StepResult(rc=0, stdout=None, stderr=None, value=names)

    raise SystemExit(f"FAIL: bdg: unsupported op: {op}")