from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from .app_support import _err, _ok, _utc_now, read_tail
from .command_parse import (
    CommandParseError,
    build_canonical_command,
    parse_runner_command,
)
from .issue_alloc import allocate_next_issue_id
from .job_store import list_job_jsons, load_job_json
from .models import JobMode, JobRecord
from .queue import new_job_id


def _job_jsonl_path_from_fields(self, job_id: str, mode: str, issue_id: str) -> Path:
    d = self.jobs_root / str(job_id)
    if mode in ("finalize_live", "finalize_workspace"):
        return d / "am_patch_finalize.jsonl"
    issue_s = str(issue_id or "")
    if issue_s.isdigit():
        return d / ("am_patch_issue_" + issue_s + ".jsonl")
    return d / "am_patch_finalize.jsonl"


def _load_job_from_disk(self, job_id: str) -> JobRecord | None:
    raw = load_job_json(self.jobs_root, job_id)
    if raw is None:
        return None
    try:
        # The on-disk schema matches JobRecord.to_json().
        return JobRecord(**raw)
    except Exception:
        # Be tolerant: return minimal info if schema drifted.
        try:
            jid = str(raw.get("job_id", job_id))
            created = str(raw.get("created_utc", ""))
            mode = str(raw.get("mode", "patch"))
            issue = str(raw.get("issue_id", ""))
            commit = str(raw.get("commit_message", ""))
            patch = str(raw.get("patch_path", ""))
            raw_cmd = str(raw.get("raw_command", ""))
            canon = raw.get("canonical_command")
            if not isinstance(canon, list):
                canon = []
            status = str(raw.get("status", "unknown"))
            jr = JobRecord(
                job_id=jid,
                created_utc=created,
                mode=mode,  # type: ignore[arg-type]
                issue_id=issue,
                commit_message=commit,
                patch_path=patch,
                raw_command=raw_cmd,
                canonical_command=[str(x) for x in canon],
            )
            jr.status = status  # type: ignore[assignment]
            jr.started_utc = raw.get("started_utc")
            jr.ended_utc = raw.get("ended_utc")
            jr.return_code = raw.get("return_code")
            jr.error = raw.get("error")
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
        if mode in ("finalize_live", "finalize_workspace", "rerun_latest"):
            canonical = build_canonical_command(runner_prefix, mode, "", "", "")
        else:
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
            if not commit_message or not patch_path:
                return _err("Missing commit_message or patch_path", status=400)
            canonical = build_canonical_command(
                runner_prefix, mode, issue_id, commit_message, patch_path
            )

    job_id = new_job_id()
    job = JobRecord(
        job_id=job_id,
        created_utc=_utc_now(),
        mode=mode,
        issue_id=issue_id,
        commit_message=commit_message,
        patch_path=patch_path,
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
    return _ok({"jobs": [j.to_json() for j in jobs]})


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
    return _ok({"job_id": job_id, "tail": read_tail(log_path, lines)})


def api_jobs_cancel(self, job_id: str) -> tuple[int, bytes]:
    ok = self.queue.cancel(job_id)
    if not ok:
        return _err("Cannot cancel", status=409)
    return _ok({"job_id": job_id})
