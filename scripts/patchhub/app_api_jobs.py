from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any, cast

from .app_support import _err, _ok, _utc_now, read_tail
from .command_parse import (
    CommandParseError,
    build_canonical_command,
    parse_runner_command,
)
from .issue_alloc import allocate_next_issue_id
from .job_ids import new_job_id
from .job_store import list_job_jsons, load_job_json
from .models import (
    JobMode,
    JobRecord,
    compute_commit_summary,
    compute_patch_basename,
    job_to_list_item_json,
)
from .zip_commit_message import (
    ZipCommitConfig,
    ZipIssueConfig,
    read_commit_message_from_zip_path,
    read_issue_number_from_zip_path,
)


def _try_fill_commit_from_zip(self, patch_path: str) -> str:
    if not self.cfg.autofill.zip_commit_enabled:
        return ""
    if Path(patch_path).suffix.lower() != ".zip":
        return ""
    prefix = self.cfg.paths.patches_root.rstrip("/")
    rel = patch_path
    if rel.startswith(prefix + "/"):
        rel = rel[len(prefix) + 1 :]
    try:
        zpath = self.jail.resolve_rel(rel)
    except Exception:
        return ""
    if not zpath.exists() or not zpath.is_file():
        return ""
    zcfg = ZipCommitConfig(
        enabled=True,
        filename=self.cfg.autofill.zip_commit_filename,
        max_bytes=self.cfg.autofill.zip_commit_max_bytes,
        max_ratio=self.cfg.autofill.zip_commit_max_ratio,
    )
    msg, _err_reason = read_commit_message_from_zip_path(zpath, zcfg)
    return msg or ""


def _try_fill_issue_from_zip(self, patch_path: str) -> str:
    if not self.cfg.autofill.zip_issue_enabled:
        return ""
    if Path(patch_path).suffix.lower() != ".zip":
        return ""
    prefix = self.cfg.paths.patches_root.rstrip("/")
    rel = patch_path
    if rel.startswith(prefix + "/"):
        rel = rel[len(prefix) + 1 :]
    try:
        zpath = self.jail.resolve_rel(rel)
    except Exception:
        return ""
    if not zpath.exists() or not zpath.is_file():
        return ""
    zcfg = ZipIssueConfig(
        enabled=True,
        filename=self.cfg.autofill.zip_issue_filename,
        max_bytes=self.cfg.autofill.zip_issue_max_bytes,
        max_ratio=self.cfg.autofill.zip_issue_max_ratio,
    )
    zid, _err_reason = read_issue_number_from_zip_path(zpath, zcfg)
    return zid or ""


def _job_jsonl_path_from_fields(self, job_id: str, mode: str, issue_id: str) -> Path:
    d = self.jobs_root / str(job_id)
    if mode in ("finalize_live", "finalize_workspace"):
        return d / "am_patch_finalize.jsonl"
    issue_s = str(issue_id or "")
    if issue_s.isdigit():
        return d / ("am_patch_issue_" + issue_s + ".jsonl")
    return d / "am_patch_finalize.jsonl"


def _load_job_from_disk(self, job_id: str) -> JobRecord | None:
    job_id = str(job_id)
    if not job_id:
        return None

    cache_any: Any = getattr(self, "_disk_job_cache", None)
    cache: dict[str, tuple[int, JobRecord]]
    if isinstance(cache_any, dict):
        cache = cast(dict[str, tuple[int, JobRecord]], cache_any)
    else:
        cache = {}
        self._disk_job_cache = cache

    job_json_path = self.jobs_root / job_id / "job.json"
    if not job_json_path.exists() or not job_json_path.is_file():
        cache.pop(job_id, None)
        return None
    try:
        st = job_json_path.stat()
    except Exception:
        return None

    cached = cache.get(job_id)
    if cached is not None and cached[0] == st.st_mtime_ns:
        return cached[1]

    raw = load_job_json(self.jobs_root, job_id)
    if raw is None:
        cache.pop(job_id, None)
        return None
    try:
        # The on-disk schema matches JobRecord.to_json().
        job = JobRecord(**raw)
        cache[job_id] = (st.st_mtime_ns, job)
        return job
    except Exception:
        # Be tolerant: return minimal info if schema drifted.
        try:
            jid = str(raw.get("job_id", job_id))
            created = str(raw.get("created_utc", ""))
            mode = str(raw.get("mode", "patch"))
            issue = str(raw.get("issue_id", ""))
            commit_summary = str(raw.get("commit_summary", ""))
            patch_basename = raw.get("patch_basename")
            if patch_basename is not None:
                patch_basename = str(patch_basename)
            raw_cmd = str(raw.get("raw_command", ""))
            canon = raw.get("canonical_command")
            if not isinstance(canon, list):
                canon = []
            status = str(raw.get("status", "unknown"))

            if not commit_summary:
                commit_message = str(raw.get("commit_message", ""))
                commit_summary = compute_commit_summary(commit_message)
                if not commit_summary:
                    commit_summary = f"({mode})"
            if not patch_basename:
                patch_path = str(raw.get("patch_path", ""))
                patch_basename = compute_patch_basename(patch_path)
            jr = JobRecord(
                job_id=jid,
                created_utc=created,
                mode=mode,  # type: ignore[arg-type]
                issue_id=issue,
                commit_summary=commit_summary,
                patch_basename=patch_basename,
                raw_command=raw_cmd,
                canonical_command=[str(x) for x in canon],
            )
            jr.status = status  # type: ignore[assignment]
            jr.started_utc = raw.get("started_utc")
            jr.ended_utc = raw.get("ended_utc")
            jr.return_code = raw.get("return_code")
            jr.error = raw.get("error")
            jr.cancel_requested_utc = raw.get("cancel_requested_utc")
            jr.cancel_ack_utc = raw.get("cancel_ack_utc")
            jr.cancel_source = raw.get("cancel_source")
            cache[job_id] = (st.st_mtime_ns, jr)
            return jr
        except Exception:
            return None


def _job_jsonl_path(self, job: JobRecord) -> Path:
    d = self.jobs_root / job.job_id
    if job.mode in ("finalize_live", "finalize_workspace"):
        return d / "am_patch_finalize.jsonl"
    issue_s = str(job.issue_id or "")
    if issue_s.isdigit():
        return d / f"am_patch_issue_{issue_s}.jsonl"
    return d / "am_patch_finalize.jsonl"


def _pick_tail_job(self) -> JobRecord | None:
    jobs = self.queue.list_jobs()
    for j in jobs:
        if j.status == "running":
            return j
    return jobs[0] if jobs else None


def api_jobs_enqueue(self, body: dict[str, Any]) -> tuple[int, bytes]:
    mode_s = str(body.get("mode", "patch"))
    if mode_s not in ("patch", "repair", "finalize_live", "finalize_workspace", "rerun_latest"):
        return _err("Invalid mode", status=400)
    mode: JobMode = cast(JobMode, mode_s)

    runner_prefix = self.cfg.runner.command

    issue_id = str(body.get("issue_id", ""))
    commit_message = str(body.get("commit_message", ""))
    patch_path = str(body.get("patch_path", ""))
    raw_command = str(body.get("raw_command", ""))

    if raw_command:
        try:
            parsed = parse_runner_command(raw_command)
        except CommandParseError as e:
            return _err(str(e), status=400)
        if parsed.mode != mode and parsed.mode != "patch":
            # Allow parsing a patch command and submitting as repair.
            pass
        canonical = parsed.canonical_argv
        issue_id = parsed.issue_id or issue_id
        commit_message = parsed.commit_message or commit_message
        patch_path = parsed.patch_path or patch_path
    else:
        if mode == "finalize_live":
            if not commit_message:
                return _err("Missing finalize_live message", status=400)
            canonical = build_canonical_command(runner_prefix, mode, "", commit_message, "")
        elif mode == "finalize_workspace":
            if not issue_id or not issue_id.isdigit():
                return _err("Missing/invalid issue_id", status=400)
            canonical = build_canonical_command(runner_prefix, mode, issue_id, "", "")
        elif mode == "rerun_latest":
            canonical = build_canonical_command(runner_prefix, mode, "", "", "")
        else:
            if not issue_id and patch_path:
                issue_id = _try_fill_issue_from_zip(self, patch_path)
            if not issue_id:
                # Auto-allocate for standard patch.
                issue_id = str(
                    allocate_next_issue_id(
                        self.patches_root,
                        self.cfg.issue.default_regex,
                        self.cfg.issue.allocation_start,
                        self.cfg.issue.allocation_max,
                    )
                )
            if not patch_path:
                return _err("Missing patch_path", status=400)
            if not commit_message:
                commit_message = _try_fill_commit_from_zip(self, patch_path)
            if not commit_message:
                return _err("Missing commit_message", status=400)
            canonical = build_canonical_command(
                runner_prefix, mode, issue_id, commit_message, patch_path
            )

    commit_summary = compute_commit_summary(commit_message)
    if not commit_summary:
        commit_summary = f"({mode})"
    patch_basename = compute_patch_basename(patch_path)

    job_id = new_job_id()
    job = JobRecord(
        job_id=job_id,
        created_utc=_utc_now(),
        mode=mode,
        issue_id=issue_id,
        commit_summary=commit_summary,
        patch_basename=patch_basename,
        raw_command=raw_command,
        canonical_command=canonical,
    )
    self.queue.enqueue(job)
    return _ok({"job_id": job_id, "job": job.to_json()})


def api_jobs_list(self) -> tuple[int, bytes]:
    mem = self.queue.list_jobs()
    mem_by_id = {j.job_id: j for j in mem}
    disk_raw = list_job_jsons(self.jobs_root, limit=200)
    disk: list[JobRecord] = []
    for r in disk_raw:
        jid = str(r.get("job_id", ""))
        if not jid or jid in mem_by_id:
            continue
        j = self._load_job_from_disk(jid)
        if j is not None:
            disk.append(j)

    jobs = mem + disk
    jobs.sort(key=lambda j: str(j.created_utc or ""), reverse=True)
    return _ok({"jobs": [job_to_list_item_json(j) for j in jobs]})


def api_jobs_get(self, job_id: str) -> tuple[int, bytes]:
    job = self.queue.get_job(job_id)
    if job is None:
        job = self._load_job_from_disk(job_id)
    if job is None:
        return _err("Not found", status=404)
    return _ok({"job": job.to_json()})


def api_jobs_log_tail(self, job_id: str, qs: dict[str, str]) -> tuple[int, bytes]:
    job = self.queue.get_job(job_id)
    if job is None:
        job = self._load_job_from_disk(job_id)
    if job is None:
        return _err("Not found", status=404)
    lines = int(qs.get("lines", "200"))
    log_path = self.jobs_root / str(job_id) / "runner.log"
    tail = read_tail(
        log_path,
        lines,
        max_bytes=self.cfg.server.tail_max_bytes,
        cache_max_entries=self.cfg.server.tail_cache_max_entries,
    )
    return _ok({"job_id": job_id, "tail": tail})


def _run_queue_bool_sync(
    fn: Callable[[str], Awaitable[bool]],
    job_id: str,
) -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        coro = cast("Coroutine[Any, Any, bool]", fn(job_id))
        return bool(asyncio.run(coro))
    raise RuntimeError("Legacy jobs API cannot run inside an active event loop")


def api_jobs_cancel(self, job_id: str) -> tuple[int, bytes]:
    try:
        ok = _run_queue_bool_sync(self.queue.cancel, job_id)
    except Exception:
        return _err("Cannot cancel", status=409)
    if not ok:
        return _err("Cannot cancel", status=409)
    return _ok({"job_id": job_id})


def api_jobs_hard_stop(self, job_id: str) -> tuple[int, bytes]:
    try:
        ok = _run_queue_bool_sync(self.queue.hard_stop, job_id)
    except Exception:
        return _err("Cannot hard stop", status=409)
    if not ok:
        return _err("Cannot hard stop", status=409)
    return _ok({"job_id": job_id})
