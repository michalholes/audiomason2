from __future__ import annotations

from pathlib import Path

from patchhub import app_api_core as _core
from patchhub import app_api_fs as _fs
from patchhub import app_api_jobs as _jobs
from patchhub import app_api_upload as _upload
from patchhub import app_ui as _ui
from patchhub.config import AppConfig
from patchhub.fs_jail import FsJail

from .async_queue import AsyncJobQueue
from .async_runner_exec import AsyncRunnerExecutor


class AsyncAppCore:
    def __init__(self, repo_root: Path, cfg: AppConfig) -> None:
        self.repo_root = repo_root
        self.cfg = cfg
        self.jail = FsJail(
            repo_root=repo_root,
            patches_root_rel=cfg.paths.patches_root,
            crud_allowlist=cfg.paths.crud_allowlist,
            allow_crud=cfg.paths.allow_crud,
        )
        self.patches_root = self.jail.patches_root()
        self.jobs_root = self.patches_root / "artifacts" / "web_jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)

        self.queue = AsyncJobQueue(
            repo_root=repo_root,
            lock_path=self.jail.lock_path(),
            jobs_root=self.jobs_root,
            executor=AsyncRunnerExecutor(),
        )

    async def startup(self) -> None:
        await self.queue.start()

    async def shutdown(self) -> None:
        await self.queue.stop()

    _autofill_scan_dir_rel = _core._autofill_scan_dir_rel
    _derive_from_filename = _core._derive_from_filename

    api_config = _core.api_config
    api_patches_latest = _core.api_patches_latest
    api_parse_command = _core.api_parse_command
    api_runs = _core.api_runs
    api_runner_tail = _core.api_runner_tail
    diagnostics = _core.diagnostics

    api_fs_list = _fs.api_fs_list
    api_fs_read_text = _fs.api_fs_read_text
    api_fs_download = _fs.api_fs_download
    api_fs_mkdir = _fs.api_fs_mkdir
    api_fs_rename = _fs.api_fs_rename
    api_fs_delete = _fs.api_fs_delete
    api_fs_unzip = _fs.api_fs_unzip

    _job_jsonl_path_from_fields = _jobs._job_jsonl_path_from_fields
    _load_job_from_disk = _jobs._load_job_from_disk
    _job_jsonl_path = _jobs._job_jsonl_path
    _pick_tail_job = _jobs._pick_tail_job

    api_upload_patch = _upload.api_upload_patch

    render_template = _ui.render_template
    render_index = _ui.render_index
    render_debug = _ui.render_debug
