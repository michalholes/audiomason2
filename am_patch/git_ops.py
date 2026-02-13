from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .compat import import_legacy
from .deps import Deps
from .model import RunnerError


def git_commit(deps: Deps, repo_root: Path, message: str) -> None:
    res = deps.runner.run(["git", "commit", "-am", message], cwd=repo_root)
    if res.returncode != 0:
        raise RunnerError(res.stderr.strip() or res.stdout.strip() or "git commit failed")


def git_push(deps: Deps, repo_root: Path) -> None:
    res = deps.runner.run(["git", "push"], cwd=repo_root)
    if res.returncode != 0:
        raise RunnerError(res.stderr.strip() or res.stdout.strip() or "git push failed")


# Legacy compatibility for scripts runner.
try:
    _legacy = import_legacy("git_ops")
    fetch = _legacy.fetch  # type: ignore[attr-defined]
    current_branch = _legacy.current_branch  # type: ignore[attr-defined]
    head_sha = _legacy.head_sha  # type: ignore[attr-defined]
    origin_ahead_count = _legacy.origin_ahead_count  # type: ignore[attr-defined]
    require_branch = _legacy.require_branch  # type: ignore[attr-defined]
    require_up_to_date = _legacy.require_up_to_date  # type: ignore[attr-defined]
    file_diff_since = _legacy.file_diff_since  # type: ignore[attr-defined]
    commit = _legacy.commit  # type: ignore[attr-defined]
    push = _legacy.push  # type: ignore[attr-defined]
    files_changed_since = _legacy.files_changed_since  # type: ignore[attr-defined]
    git_archive = _legacy.git_archive  # type: ignore[attr-defined]
    commit_changed_files_name_status = _legacy.commit_changed_files_name_status  # type: ignore[attr-defined]
except Exception:
    pass
