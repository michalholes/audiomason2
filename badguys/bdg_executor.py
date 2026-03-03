from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from badguys.bdg_evaluator import StepResult
from badguys.bdg_loader import BdgStep, BdgTest
from badguys.bdg_materializer import MaterializedAssets


def _subst_token(value: str, *, issue_id: str) -> str:
    if value == "${issue_id}":
        return str(issue_id)
    return value


def _safe_name(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in {"_", "-", "."}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _lock_path_for_test(repo_root: Path, *, test_id: str) -> Path:
    safe = _safe_name(test_id)
    return repo_root / "patches" / f"{safe}.lock"


def _outside_sentinel(repo_root: Path, *, issue_id: str) -> Path:
    return repo_root.parent / f"badguys_sentinel_issue_{issue_id}.txt"


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


def execute_bdg(
    *,
    repo_root: Path,
    cfg_runner_cmd: list[str],
    issue_id: str,
    bdg: BdgTest,
    mats: MaterializedAssets,
) -> list[StepResult]:
    results: List[StepResult] = []
    for step in bdg.steps:
        results.append(
            _exec_one(
                repo_root=repo_root,
                cfg_runner_cmd=cfg_runner_cmd,
                issue_id=issue_id,
                step=step,
                mats=mats,
                test_id=bdg.test_id,
            )
        )
    return results


def _exec_one(
    *,
    repo_root: Path,
    cfg_runner_cmd: list[str],
    issue_id: str,
    step: BdgStep,
    mats: MaterializedAssets,
    test_id: str,
) -> StepResult:
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
            name = test_id
        if not isinstance(name, str):
            raise SystemExit("FAIL: bdg: test_name must be string")
        log_dir = _logs_dir(repo_root)
        log_path = log_dir / f"{name}.log"
        if not log_path.exists():
            return StepResult(rc=1, stdout=None, stderr=f"missing log: {log_path}", value="")
        return StepResult(rc=0, stdout=None, stderr=None, value=log_path.read_text(encoding="utf-8"))

    if op == "LOCK_DELETE":
        lock_path = _lock_path_for_test(repo_root, test_id=test_id)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        return StepResult(rc=0, stdout=None, stderr=None, value=str(lock_path))

    if op == "LOCK_WRITE_STALE":
        lock_path = _lock_path_for_test(repo_root, test_id=test_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("pid=0\nstarted=0\n", encoding="utf-8")
        return StepResult(rc=0, stdout=None, stderr=None, value=str(lock_path))

    if op == "LOCK_ACQUIRE":
        ttl_seconds = p.get("ttl_seconds")
        on_conflict = p.get("on_conflict")
        if not isinstance(ttl_seconds, int):
            raise SystemExit("FAIL: bdg: ttl_seconds must be int")
        if on_conflict not in {"fail", "steal"}:
            raise SystemExit("FAIL: bdg: on_conflict must be 'fail' or 'steal'")
        lock_path = _lock_path_for_test(repo_root, test_id=test_id)
        from badguys._util import acquire_lock

        try:
            acquire_lock(repo_root, path=lock_path, ttl_seconds=ttl_seconds, on_conflict=on_conflict)
        except SystemExit as e:
            return StepResult(rc=1, stdout=None, stderr=str(e), value=str(lock_path))
        return StepResult(rc=0, stdout=None, stderr=None, value=str(lock_path))

    if op == "LOCK_RELEASE":
        lock_path = _lock_path_for_test(repo_root, test_id=test_id)
        from badguys._util import release_lock

        try:
            release_lock(repo_root, path=lock_path)
        except SystemExit as e:
            return StepResult(rc=1, stdout=None, stderr=str(e), value=str(lock_path))
        return StepResult(rc=0, stdout=None, stderr=None, value=str(lock_path))

    if op == "CLEAN_OUTSIDE_SENTINEL":
        sentinel = _outside_sentinel(repo_root, issue_id=issue_id)
        try:
            sentinel.unlink()
        except FileNotFoundError:
            pass
        return StepResult(rc=0, stdout=None, stderr=None, value=str(sentinel))

    if op == "ASSERT_NO_OUTSIDE_SENTINEL":
        sentinel = _outside_sentinel(repo_root, issue_id=issue_id)
        if sentinel.exists():
            return StepResult(rc=1, stdout=None, stderr="outside write detected", value=str(sentinel))
        return StepResult(rc=0, stdout=None, stderr=None, value=str(sentinel))


    if op == "DELETE_PATCHED_ZIP":
        patched_zip = repo_root / "patches" / "patched.zip"
        try:
            patched_zip.unlink()
        except FileNotFoundError:
            pass
        return StepResult(rc=0, stdout=None, stderr=None, value=str(patched_zip))

    if op == "ASSERT_NO_WORKSPACE_AND_NO_ARCHIVES":
        ws_dir = repo_root / "patches" / "workspaces" / f"issue_{issue_id}"
        patched_zip = repo_root / "patches" / "patched.zip"
        if ws_dir.exists():
            return StepResult(rc=1, stdout=None, stderr="workspace exists", value=str(ws_dir))
        if patched_zip.exists():
            return StepResult(rc=1, stdout=None, stderr="patched.zip exists", value=str(patched_zip))
        return StepResult(rc=0, stdout=None, stderr=None, value="OK")

    if op == "ASSERT_WORKSPACE_REPO_EXISTS":
        ws_repo = repo_root / "patches" / "workspaces" / f"issue_{issue_id}" / "repo"
        if not ws_repo.exists():
            return StepResult(rc=1, stdout=None, stderr="missing workspace repo", value=str(ws_repo))
        return StepResult(rc=0, stdout=None, stderr=None, value=str(ws_repo))

    if op == "GIT_STATUS_PORCELAIN":
        cp = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        lines = (cp.stdout or "").splitlines()
        out = [ln.rstrip("\n") for ln in lines if ln.strip()]
        return StepResult(rc=0, stdout=None, stderr=None, value=out)

    if op == "PREPARE_UNSUCCESSFUL_PATCH":
        marker_rel = p.get("marker_rel")
        marker_text = p.get("marker_text", "")
        if not isinstance(marker_rel, str):
            raise SystemExit("FAIL: bdg: marker_rel must be string")
        if not isinstance(marker_text, str):
            raise SystemExit("FAIL: bdg: marker_text must be string")
        unsucc_dir = repo_root / "patches" / "unsuccessful"
        unsucc_dir.mkdir(parents=True, exist_ok=True)
        name = f"issue_{issue_id}__badguys_rerun_latest__bdg.patch"
        patch_path = unsucc_dir / name
        patch_txt = (
            f"diff --git a/{marker_rel} b/{marker_rel}\n"
            "new file mode 100644\n"
            "index 0000000..1111111\n"
            f"--- /dev/null\n"
            f"+++ b/{marker_rel}\n"
            "@@ -0,0 +1 @@\n"
            f"+{marker_text}\n"
        )
        patch_path.write_text(patch_txt, encoding="utf-8")
        return StepResult(rc=0, stdout=None, stderr=None, value=str(patch_path))

    if op == "PREPARE_LATEST_BUNDLE_900":
        # This op is dedicated to test_900_commit_push_timestamp.
        issue = str(issue_id)
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        ws_repo = patches_dir / "workspaces" / f"issue_{issue}" / "repo"
        marker_rel = "badguys/artifacts/commit_marker.txt"
        seed_rel = "src/audiomason/_badguys_seed_fail.py"
        ws_marker = ws_repo / marker_rel
        ws_marker.parent.mkdir(parents=True, exist_ok=True)
        ws_marker.write_text(
            "badguys commit marker\n"
            "test\n",
            encoding="utf-8",
        )
        try:
            (ws_repo / seed_rel).unlink()
        except FileNotFoundError:
            pass
        old_line = "test\n"
        new_line = f"{issue}\n"
        patch_txt = (
            f"diff --git a/{marker_rel} b/{marker_rel}\n"
            "index 1111111..2222222 100644\n"
            f"--- a/{marker_rel}\n"
            f"+++ b/{marker_rel}\n"
            "@@ -1,2 +1,2 @@\n"
            " badguys commit marker\n"
            f"-{old_line}"
            f"+{new_line}"
        )
        unsucc_dir = patches_dir / "unsuccessful"
        unsucc_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = unsucc_dir / f"issue_{issue}__badguys_latest_bundle__bdg.zip"
        inner_name = f"issue_{issue}__badguys_fix_marker__bdg.patch"
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            info = zipfile.ZipInfo(inner_name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, patch_txt.encode("utf-8"))
        bundle_path.write_bytes(buf.getvalue())
        return StepResult(rc=0, stdout=None, stderr=None, value=str(bundle_path))

    raise SystemExit(f"FAIL: bdg: unsupported op: {op}")
