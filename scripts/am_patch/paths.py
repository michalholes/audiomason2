from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    patch_dir: Path
    logs_dir: Path
    json_dir: Path
    workspaces_dir: Path
    successful_dir: Path
    unsuccessful_dir: Path
    artifacts_dir: Path
    lock_path: Path
    symlink_path: Path


def ensure_dirs(paths: Paths) -> None:
    for d in [
        paths.patch_dir,
        paths.logs_dir,
        paths.json_dir,
        paths.workspaces_dir,
        paths.successful_dir,
        paths.unsuccessful_dir,
        paths.artifacts_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)


def default_paths(
    repo_root: Path,
    patch_dir: Path,
    *,
    logs_dir_name: str = "logs",
    json_dir_name: str = "logs_json",
    workspaces_dir_name: str = "workspaces",
    successful_dir_name: str = "successful",
    unsuccessful_dir_name: str = "unsuccessful",
    lockfile_name: str = "am_patch.lock",
    current_log_symlink_name: str = "am_patch.log",
) -> Paths:
    logs_dir = patch_dir / logs_dir_name
    json_dir = patch_dir / json_dir_name
    workspaces_dir = patch_dir / workspaces_dir_name
    successful_dir = patch_dir / successful_dir_name
    unsuccessful_dir = patch_dir / unsuccessful_dir_name
    artifacts_dir = patch_dir / "artifacts"
    lock_path = patch_dir / lockfile_name
    symlink_path = patch_dir / current_log_symlink_name
    return Paths(
        repo_root=repo_root,
        patch_dir=patch_dir,
        logs_dir=logs_dir,
        json_dir=json_dir,
        workspaces_dir=workspaces_dir,
        successful_dir=successful_dir,
        unsuccessful_dir=unsuccessful_dir,
        artifacts_dir=artifacts_dir,
        lock_path=lock_path,
        symlink_path=symlink_path,
    )
