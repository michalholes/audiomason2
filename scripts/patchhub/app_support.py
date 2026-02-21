from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .models import RunEntry


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


def read_tail_jsonl(path: Path, lines: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = max(1, min(int(lines), 5000))

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    out: list[dict[str, Any]] = []
    parts = text.splitlines()
    for s in parts[-lines:]:
        s = s.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(cast(dict[str, Any], obj))
    return out


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


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ascii_sanitize(s: str) -> str:
    out = []
    for ch in s:
        if ord(ch) < 128:
            out.append(ch)
        else:
            out.append(" ")
    return "".join(out)


def _find_latest_artifact_rel(patches_root: Path, dir_name: str, contains: str) -> str | None:
    d = patches_root / dir_name
    if not d.exists() or not d.is_dir():
        return None
    best = None
    best_m = -1.0
    for p in d.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if contains not in name:
            continue
        try:
            st = p.stat()
        except Exception:
            continue
        if st.st_mtime > best_m:
            best_m = st.st_mtime
            best = name
    if not best:
        return None
    return str(Path(dir_name) / best)


def _decorate_run(
    run: RunEntry,
    *,
    patches_root: Path,
    success_zip_rel: str,
) -> RunEntry:
    run.success_zip_rel_path = success_zip_rel
    issue_key = f"issue_{run.issue_id}"

    # Archived patch: try result-specific dir first, then both.
    if run.result == "success":
        run.archived_patch_rel_path = _find_latest_artifact_rel(
            patches_root, "successful", issue_key
        )
    elif run.result in ("fail", "canceled"):
        run.archived_patch_rel_path = _find_latest_artifact_rel(
            patches_root, "unsuccessful", issue_key
        )

    if not run.archived_patch_rel_path:
        run.archived_patch_rel_path = _find_latest_artifact_rel(
            patches_root, "successful", issue_key
        ) or _find_latest_artifact_rel(patches_root, "unsuccessful", issue_key)

    run.diff_bundle_rel_path = _find_latest_artifact_rel(
        patches_root, "artifacts", f"issue_{run.issue_id}_diff"
    )
    return run


def _iter_canceled_runs(patches_root: Path) -> list[RunEntry]:
    jobs_root = patches_root / "artifacts" / "web_jobs"
    if not jobs_root.exists() or not jobs_root.is_dir():
        return []

    out: list[RunEntry] = []
    for d in jobs_root.iterdir():
        if not d.is_dir():
            continue
        job_json = d / "job.json"
        if not job_json.exists() or not job_json.is_file():
            continue
        try:
            raw = json.loads(job_json.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        if str(raw.get("status", "")) != "canceled":
            continue
        issue_s = str(raw.get("issue_id", ""))
        try:
            issue_id = int(issue_s)
        except Exception:
            continue

        log_path = d / "runner.log"
        rel = str(
            Path("artifacts")
            / "web_jobs"
            / d.name
            / ("runner.log" if log_path.exists() else "job.json")
        )
        try:
            st = (log_path if log_path.exists() else job_json).stat()
        except Exception:
            continue
        out.append(
            RunEntry(
                issue_id=issue_id,
                log_rel_path=rel,
                result="canceled",
                result_line="RESULT: CANCELED",
                mtime_utc=_utc_iso(st.st_mtime),
            )
        )

    out.sort(key=lambda r: (r.mtime_utc, r.issue_id), reverse=True)
    return out
