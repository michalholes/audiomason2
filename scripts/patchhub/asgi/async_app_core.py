from __future__ import annotations

from pathlib import Path
from typing import Any

from patchhub import (
    app_api_amp as _amp,
)
from patchhub import (
    app_api_core as _core,
)
from patchhub import (
    app_api_fs as _fs,
)
from patchhub import (
    app_api_jobs as _jobs,
)
from patchhub import (
    app_api_upload as _upload,
)
from patchhub import (
    app_api_workspaces as _workspaces,
)
from patchhub import (
    app_ui as _ui,
)
from patchhub import (
    proc_resources,
)
from patchhub.config import AppConfig
from patchhub.fs_jail import FsJail

from .async_jobs_runs_indexer import AsyncJobsRunsIndexer
from .async_offload import to_thread
from .async_queue import AsyncJobQueue
from .async_runner_exec import AsyncRunnerExecutor


class AsyncAppCore:
    def __init__(self, *, repo_root: Path, cfg: Any) -> None:
        self.repo_root = repo_root
        self.cfg = cfg
        if not isinstance(cfg, AppConfig):
            raise TypeError("cfg must be patchhub.config.AppConfig")
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
            ipc_handshake_wait_s=cfg.runner.ipc_handshake_wait_s,
            post_exit_grace_s=cfg.runner.post_exit_grace_s,
            terminate_grace_s=cfg.runner.terminate_grace_s,
        )

        self.indexer = AsyncJobsRunsIndexer(core=self)

    async def startup(self) -> None:
        await self.queue.start()
        await self.indexer.start()

    async def shutdown(self) -> None:
        await self.indexer.stop()
        await self.queue.stop()

    _autofill_scan_dir_rel = _core._autofill_scan_dir_rel
    _derive_from_filename = _core._derive_from_filename

    api_config = _core.api_config
    api_patches_latest = _core.api_patches_latest
    api_parse_command = _core.api_parse_command
    api_runs = _core.api_runs
    api_runner_tail = _core.api_runner_tail

    api_amp_schema = _amp.api_amp_schema
    api_amp_config_get = _amp.api_amp_config_get
    api_amp_config_post = _amp.api_amp_config_post

    async def diagnostics(self) -> dict[str, object]:
        qstate: Any | None
        try:
            qstate = await self.queue.state()
        except Exception:
            qstate = None

        queued = int(getattr(qstate, "queued", 0) or 0) if qstate is not None else 0
        running = int(getattr(qstate, "running", 0) or 0) if qstate is not None else 0

        def _sync_part() -> dict[str, object]:
            lock_held = False
            try:
                from patchhub.job_ids import is_lock_held

                lock_held = is_lock_held(self.jail.lock_path())
            except Exception:
                lock_held = False

            runs = _core.iter_runs(self.patches_root, self.cfg.indexing.log_filename_regex)
            stats = _core.compute_stats(runs, self.cfg.indexing.stats_windows_days)
            usage = _core.shutil.disk_usage(str(self.patches_root))
            return {
                "lock": {
                    "path": str(Path(self.cfg.paths.patches_root) / "am_patch.lock"),
                    "held": lock_held,
                },
                "disk": {
                    "total": int(usage.total),
                    "used": int(usage.used),
                    "free": int(usage.free),
                },
                "resources": proc_resources.snapshot(),
                "runs": {"count": len(runs)},
                "stats": {
                    "all_time": stats.all_time.__dict__,
                    "windows": [w.__dict__ for w in stats.windows],
                },
            }

        sync_part: dict[str, object]
        try:
            sync_part = await to_thread(_sync_part)
        except Exception:
            sync_part = {
                "lock": {"path": "", "held": False},
                "disk": {"total": 0, "used": 0, "free": 0},
                "runs": {"count": 0},
                "stats": {"all_time": {}, "windows": []},
                "resources": {},
            }

        return {"queue": {"queued": queued, "running": running}, **sync_part}

    api_fs_list = _fs.api_fs_list
    api_fs_read_text = _fs.api_fs_read_text
    api_fs_stat = _fs.api_fs_stat
    api_fs_download = _fs.api_fs_download
    api_fs_mkdir = _fs.api_fs_mkdir
    api_fs_rename = _fs.api_fs_rename
    api_fs_delete = _fs.api_fs_delete
    api_fs_unzip = _fs.api_fs_unzip

    _job_jsonl_path_from_fields = _jobs._job_jsonl_path_from_fields
    _load_job_from_disk = _jobs._load_job_from_disk
    _job_jsonl_path = _jobs._job_jsonl_path
    _pick_tail_job = _jobs._pick_tail_job
    api_patch_zip_manifest = _jobs.api_patch_zip_manifest
    api_jobs_get = _jobs.api_jobs_get

    api_upload_patch = _upload.api_upload_patch
    api_workspaces = _workspaces.api_workspaces

    render_template = _ui.render_template
    render_index = _ui.render_index
    render_debug = _ui.render_debug
