from __future__ import annotations

from pathlib import Path

import pytest
from am_patch.model import RunnerError

from am_patch.git_ops import git_commit, git_push


def test_git_commit_and_push_success(repo_root: Path, fake_deps) -> None:
    git_commit(fake_deps, repo_root, "msg")
    git_push(fake_deps, repo_root)


def test_git_commit_failure_raises(repo_root: Path, fake_deps) -> None:
    fake_deps.runner.set_failure(("git", "commit"), stderr="no")
    with pytest.raises(RunnerError):
        git_commit(fake_deps, repo_root, "msg")


def test_git_push_failure_raises(repo_root: Path, fake_deps) -> None:
    fake_deps.runner.set_failure(("git", "push"), stderr="no")
    with pytest.raises(RunnerError):
        git_push(fake_deps, repo_root)
