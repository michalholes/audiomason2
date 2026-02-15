from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .command_parse import CommandParseError, build_canonical_command, parse_runner_command
from .config import AppConfig
from .fs_jail import FsJail, FsJailError, list_dir, safe_rename
from .indexing import compute_stats, iter_runs
from .issue_alloc import allocate_next_issue_id
from .models import JobMode, JobRecord
from .queue import JobQueue, new_job_id


def _json_bytes(obj: Any, status: int = 200) -> tuple[int, bytes]:
    return status, json.dumps(obj, ensure_ascii=True, indent=2).encode("utf-8")


def _err(msg: str, status: int = 400) -> tuple[int, bytes]:
    return _json_bytes({"ok": False, "error": msg}, status=status)


def _ok(obj: dict[str, Any] | None = None) -> tuple[int, bytes]:
    out: dict[str, Any] = {"ok": True}
    if obj:
        out.update(obj)
    return _json_bytes(out, status=200)


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    lines = max(1, min(int(lines), 5000))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def compute_success_archive_rel(
    repo_root: Path, runner_config_toml: Path, patches_root_rel: str
) -> str:
    import subprocess
    import tomllib

    raw = tomllib.loads(runner_config_toml.read_text(encoding="utf-8"))
    name = raw.get("paths", {}).get("success_archive_name")
    if not name:
        name = "{repo}-{branch}.zip"

    repo = repo_root.name
    branch = "main"
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo_root), text=True
        ).strip()
        if out and out != "HEAD":
            branch = out
        else:
            branch = str(raw.get("git", {}).get("default_branch") or "main")
    except Exception:
        branch = str(raw.get("git", {}).get("default_branch") or "main")

    name = name.replace("{repo}", repo).replace("{branch}", branch)
    name = os.path.basename(name)
    if not name.endswith(".zip"):
        name = f"{name}.zip"
    return str(Path(patches_root_rel) / name)


class App:
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

        from .runner_exec import RunnerExecutor

        self.queue = JobQueue(
            repo_root=repo_root,
            lock_path=self.jail.lock_path(),
            jobs_root=self.jobs_root,
            executor=RunnerExecutor(),
        )

    def shutdown(self) -> None:
        self.queue.stop()

    # ---------------- API ----------------

    def api_config(self) -> tuple[int, bytes]:
        runner_cfg_path = (self.repo_root / self.cfg.runner.runner_config_toml).resolve()
        success_rel = compute_success_archive_rel(
            self.repo_root, runner_cfg_path, self.cfg.paths.patches_root
        )

        data: dict[str, Any] = {
            "server": {"host": self.cfg.server.host, "port": self.cfg.server.port},
            "runner": {
                "command": self.cfg.runner.command,
                "default_verbosity": self.cfg.runner.default_verbosity,
                "queue_enabled": self.cfg.runner.queue_enabled,
                "runner_config_toml": self.cfg.runner.runner_config_toml,
                "success_archive_rel": success_rel,
            },
            "paths": {
                "patches_root": self.cfg.paths.patches_root,
                "upload_dir": self.cfg.paths.upload_dir,
                "allow_crud": self.cfg.paths.allow_crud,
                "crud_allowlist": self.cfg.paths.crud_allowlist,
            },
            "upload": {
                "max_bytes": self.cfg.upload.max_bytes,
                "allowed_extensions": self.cfg.upload.allowed_extensions,
                "ascii_only_names": self.cfg.upload.ascii_only_names,
            },
            "issue": {
                "default_regex": self.cfg.issue.default_regex,
                "allocation_start": self.cfg.issue.allocation_start,
                "allocation_max": self.cfg.issue.allocation_max,
            },
            "indexing": {
                "log_filename_regex": self.cfg.indexing.log_filename_regex,
                "stats_windows_days": self.cfg.indexing.stats_windows_days,
            },
        }
        return _json_bytes(data)

    def api_parse_command(self, body: dict[str, Any]) -> tuple[int, bytes]:
        raw = str(body.get("raw", ""))
        try:
            parsed = parse_runner_command(raw)
        except CommandParseError as e:
            return _err(str(e), status=400)

        return _ok(
            {
                "parsed": {
                    "mode": parsed.mode,
                    "issue_id": parsed.issue_id,
                    "commit_message": parsed.commit_message,
                    "patch_path": parsed.patch_path,
                },
                "canonical": {
                    "argv": parsed.canonical_argv,
                },
            }
        )

    def api_fs_list(self, rel_path: str) -> tuple[int, bytes]:
        try:
            p = self.jail.resolve_rel(rel_path)
        except FsJailError as e:
            return _err(str(e), status=400)
        if not p.exists() or not p.is_dir():
            return _err("Not a directory", status=404)
        return _ok({"path": rel_path, "items": list_dir(p)})

    def api_fs_download(self, rel_path: str) -> tuple[int, bytes] | None:
        # handled in server layer (stream bytes)
        return None

    def api_fs_mkdir(self, body: dict[str, Any]) -> tuple[int, bytes]:
        rel = str(body.get("path", ""))
        try:
            self.jail.assert_crud_allowed(rel)
            p = self.jail.resolve_rel(rel)
        except FsJailError as e:
            return _err(str(e), status=400)
        p.mkdir(parents=True, exist_ok=True)
        return _ok({"path": rel})

    def api_fs_rename(self, body: dict[str, Any]) -> tuple[int, bytes]:
        src_rel = str(body.get("src", ""))
        dst_rel = str(body.get("dst", ""))
        try:
            self.jail.assert_crud_allowed(src_rel)
            self.jail.assert_crud_allowed(dst_rel)
            src = self.jail.resolve_rel(src_rel)
            dst = self.jail.resolve_rel(dst_rel)
        except FsJailError as e:
            return _err(str(e), status=400)
        if not src.exists():
            return _err("Source not found", status=404)
        safe_rename(src, dst)
        return _ok({"src": src_rel, "dst": dst_rel})

    def api_fs_delete(self, body: dict[str, Any]) -> tuple[int, bytes]:
        rel = str(body.get("path", ""))
        try:
            self.jail.assert_crud_allowed(rel)
            p = self.jail.resolve_rel(rel)
        except FsJailError as e:
            return _err(str(e), status=400)
        if not p.exists():
            return _ok({"path": rel, "deleted": False})
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return _ok({"path": rel, "deleted": True})

    def api_fs_unzip(self, body: dict[str, Any]) -> tuple[int, bytes]:
        zip_rel = str(body.get("zip_path", ""))
        dest_rel = str(body.get("dest_dir", ""))
        try:
            self.jail.assert_crud_allowed(zip_rel)
            self.jail.assert_crud_allowed(dest_rel)
            zip_p = self.jail.resolve_rel(zip_rel)
            dest_p = self.jail.resolve_rel(dest_rel)
        except FsJailError as e:
            return _err(str(e), status=400)
        if not zip_p.exists():
            return _err("Zip not found", status=404)
        dest_p.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_p, "r") as z:
            z.extractall(dest_p)
        return _ok({"zip_path": zip_rel, "dest_dir": dest_rel})

    def api_runs(self, qs: dict[str, str]) -> tuple[int, bytes]:
        runs = iter_runs(self.patches_root, self.cfg.indexing.log_filename_regex)

        issue_id = qs.get("issue_id")
        result = qs.get("result")
        limit = int(qs.get("limit", "100"))

        if issue_id:
            try:
                iid = int(issue_id)
            except ValueError:
                return _err("Invalid issue_id", status=400)
            runs = [r for r in runs if r.issue_id == iid]
        if result:
            if result not in ("success", "fail", "unknown", "canceled"):
                return _err("Invalid result filter", status=400)

            runs = (
                []
                if result == "canceled"
                else [
                    r
                    for r in runs
                    if r.result == cast(Literal["success", "fail", "unknown"], result)
                ]
            )

        runs = runs[: max(1, min(limit, 500))]
        return _ok({"runs": [r.__dict__ for r in runs]})

    def api_runner_tail(self, qs: dict[str, str]) -> tuple[int, bytes]:
        lines = int(qs.get("lines", "200"))
        tail = read_tail(self.patches_root / "am_patch.log", lines)
        return _ok({"path": str(Path(self.cfg.paths.patches_root) / "am_patch.log"), "tail": tail})

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
        jobs = [j.to_json() for j in self.queue.list_jobs()]
        return _ok({"jobs": jobs})

    def api_jobs_get(self, job_id: str) -> tuple[int, bytes]:
        job = self.queue.get_job(job_id)
        if job is None:
            return _err("Not found", status=404)
        return _ok({"job": job.to_json()})

    def api_jobs_log_tail(self, job_id: str, qs: dict[str, str]) -> tuple[int, bytes]:
        job = self.queue.get_job(job_id)
        if job is None:
            return _err("Not found", status=404)
        lines = int(qs.get("lines", "200"))
        log_path = self.jobs_root / job_id / "runner.log"
        return _ok({"job_id": job_id, "tail": read_tail(log_path, lines)})

    def api_jobs_cancel(self, job_id: str) -> tuple[int, bytes]:
        ok = self.queue.cancel(job_id)
        if not ok:
            return _err("Cannot cancel", status=409)
        return _ok({"job_id": job_id})

    def api_upload_patch(self, filename: str, data: bytes) -> tuple[int, bytes]:
        if self.cfg.upload.ascii_only_names and not _is_ascii(filename):
            return _err("Filename must be ASCII", status=400)
        if len(data) > self.cfg.upload.max_bytes:
            return _err("File too large", status=413)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.cfg.upload.allowed_extensions:
            return _err("File extension not allowed", status=400)

        upload_rel = self.cfg.paths.upload_dir
        prefix = self.cfg.paths.patches_root.rstrip("/")
        if upload_rel == prefix:
            rel = ""
        elif upload_rel.startswith(prefix + "/"):
            rel = upload_rel[len(prefix) + 1 :]
        else:
            return _err("upload_dir must be under patches_root", status=500)

        upload_dir = self.jail.resolve_rel(rel)
        upload_dir.mkdir(parents=True, exist_ok=True)

        dst = upload_dir / os.path.basename(filename)
        dst.write_bytes(data)

        rel = str(Path(self.cfg.paths.upload_dir) / dst.name)
        return _ok({"stored_rel_path": rel, "bytes": len(data)})

    # ---------------- UI pages ----------------

    def render_template(self, name: str) -> str:
        tpl = (Path(__file__).resolve().parent / "templates" / name).read_text(encoding="utf-8")
        return tpl

    def render_index(self) -> str:
        return self.render_template("index.html")

    def render_debug(self) -> str:
        return self.render_template("debug.html")

    def diagnostics(self) -> dict[str, Any]:
        runs = iter_runs(self.patches_root, self.cfg.indexing.log_filename_regex)
        stats = compute_stats(runs, self.cfg.indexing.stats_windows_days)
        qstate = self.queue.state()
        lock_held = False
        try:
            from .queue import is_lock_held

            lock_held = is_lock_held(self.jail.lock_path())
        except Exception:
            lock_held = False

        usage = shutil.disk_usage(str(self.patches_root))
        return {
            "queue": {"queued": qstate.queued, "running": qstate.running},
            "lock": {
                "path": str(Path(self.cfg.paths.patches_root) / "am_patch.lock"),
                "held": lock_held,
            },
            "disk": {"total": int(usage.total), "used": int(usage.used), "free": int(usage.free)},
            "runs": {"count": len(runs)},
            "stats": {
                "all_time": stats.all_time.__dict__,
                "windows": [w.__dict__ for w in stats.windows],
            },
        }
