from __future__ import annotations

from pathlib import Path

from .errors import RunnerError
from .log import Logger


def _git(logger: Logger, repo: Path, args: list[str]) -> str:
    r = logger.run_logged(["git", *args], cwd=repo)
    if r.returncode != 0:
        raise RunnerError("PREFLIGHT", "GIT", f"git {' '.join(args)} failed (rc={r.returncode})")
    return (r.stdout or "").strip()


def fetch(logger: Logger, repo: Path) -> None:
    _git(logger, repo, ["fetch", "--prune"])


def current_branch(logger: Logger, repo: Path) -> str:
    return _git(logger, repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()


def head_sha(logger: Logger, repo: Path) -> str:
    return _git(logger, repo, ["rev-parse", "HEAD"]).strip()


def origin_ahead_count(logger: Logger, repo: Path, branch: str) -> int:
    # number of commits in origin/<branch> not in local <branch>
    out = _git(logger, repo, ["rev-list", "--count", f"{branch}..origin/{branch}"])
    try:
        return int(out)
    except ValueError as err:
        raise RunnerError("PREFLIGHT", "GIT", f"unexpected rev-list output: {out!r}") from err


def require_branch(logger: Logger, repo: Path, branch: str) -> None:
    b = current_branch(logger, repo)
    if b != branch:
        raise RunnerError("PREFLIGHT", "GIT", f"must be on branch {branch}, but is {b}")


def require_up_to_date(logger: Logger, repo: Path, branch: str) -> None:
    ahead = origin_ahead_count(logger, repo, branch)
    if ahead > 0:
        raise RunnerError("PREFLIGHT", "GIT", f"origin/{branch} is ahead by {ahead} commits")


def file_diff_since(logger: Logger, repo: Path, base_sha: str, paths: list[str]) -> list[str]:
    # return list of files that changed in repo since base_sha (repo-relative)
    r = logger.run_logged(
        ["git", "diff", "--name-only", f"{base_sha}..HEAD", "--", *paths], cwd=repo
    )
    if r.returncode != 0:
        raise RunnerError("PROMOTION", "GIT", f"git diff failed (rc={r.returncode})")
    return [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]


def commit(logger: Logger, repo: Path, message: str) -> str:
    r1 = logger.run_logged(["git", "status", "--porcelain"], cwd=repo)
    if r1.returncode != 0:
        raise RunnerError("PROMOTION", "GIT", "git status failed")
    if not (r1.stdout or "").strip():
        raise RunnerError("PROMOTION", "NOOP", "no changes to commit")
    r2 = logger.run_logged(["git", "add", "-A"], cwd=repo)
    if r2.returncode != 0:
        raise RunnerError("PROMOTION", "GIT", "git add failed")
    r3 = logger.run_logged(["git", "commit", "-m", message], cwd=repo)
    if r3.returncode != 0:
        raise RunnerError("PROMOTION", "GIT", "git commit failed")
    return head_sha(logger, repo)


def push(logger: Logger, repo: Path, branch: str, *, allow_fail: bool = True) -> bool:
    r = logger.run_logged(["git", "push", "origin", branch], cwd=repo)
    if r.returncode == 0:
        return True
    if allow_fail:
        logger.line("WARNING: git push failed (allowed); local commit remains")
        return False
    raise RunnerError("PROMOTION", "GIT", "git push failed")


def files_changed_since(logger: Logger, repo: Path, base_sha: str, files: list[str]) -> list[str]:
    changed: list[str] = []
    for f in files:
        r = logger.run_logged(
            ["git", "diff", "--name-only", f"{base_sha}..HEAD", "--", f], cwd=repo
        )
        if r.returncode != 0:
            continue
        if (r.stdout or "").strip():
            changed.append(f)
    return changed
