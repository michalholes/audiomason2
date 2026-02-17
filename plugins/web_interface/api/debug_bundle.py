from __future__ import annotations

import io
import json
import re
import socket
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigResolver
from audiomason.core.orchestration import Orchestrator
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.status import build_status
from .roots import _resolve_show_jobs_root

_FIXED_ZIP_DT = (2000, 1, 1, 0, 0, 0)


_SECRET_KEY_RE = re.compile(
    r"""(?ix)
    (token|password|passwd|secret|api[_-]?key|access[_-]?key|auth|credential)
    """
)


def _get_resolver(request: Request) -> ConfigResolver:
    resolver = getattr(request.app.state, "config_resolver", None)
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _get_file_service(request: Request) -> FileService:
    fs = getattr(request.app.state, "file_service", None)
    if isinstance(fs, FileService):
        return fs
    resolver = _get_resolver(request)
    fs = FileService.from_resolver(resolver)
    request.app.state.file_service = fs
    return fs


def _sanitize(obj: Any) -> Any:
    """Redact known secrets from dict/list structures."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                out[k] = "***REDACTED***"
            else:
                out[k] = _sanitize(v)
        return out
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _effective_config_json(resolver: ConfigResolver) -> str:
    resolved = resolver.resolve_all()
    # ConfigResolver returns key->ConfigSource(value, source). Build a flat map of values.
    out: dict[str, Any] = {}
    for k, src in resolved.items():
        try:
            out[k] = src.value
        except Exception:
            out[k] = None
    return json.dumps(_sanitize(out), indent=2, sort_keys=True) + "\n"


def _zip_add_bytes(z: zipfile.ZipFile, path: str, data: bytes) -> None:
    zi = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_DT)
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


def _zip_add_text(z: zipfile.ZipFile, path: str, text: str) -> None:
    _zip_add_bytes(z, path, text.encode("utf-8"))


def _tail_lines_from_bytes(data: bytes, *, max_lines: int) -> bytes:
    if max_lines <= 0:
        return b""
    # Decode with replacement, then re-encode to keep text-friendly tail files.
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-max_lines:]
    return ("\n".join(tail) + "\n").encode("utf-8")


def _try_find_git_sha() -> str | None:
    # Best-effort only; no subprocess.
    # Walk up from this file looking for .git/HEAD.
    here = Path(__file__).resolve()
    for p in [here, *here.parents[:8]]:
        head = p / ".git" / "HEAD"
        if not head.exists():
            continue
        try:
            head_text = head.read_text(encoding="utf-8").strip()
        except Exception:
            return None
        if head_text.startswith("ref: "):
            ref = head_text.split("ref: ", 1)[1].strip()
            ref_path = p / ".git" / ref
            try:
                return ref_path.read_text(encoding="utf-8").strip()[:40] or None
            except Exception:
                return None
        return head_text[:40] or None
    return None


def _api_roots(request: Request, resolver: ConfigResolver) -> dict[str, Any]:
    show_jobs = _resolve_show_jobs_root(resolver)
    items: list[dict[str, str]] = [
        {"id": "inbox", "label": "Inbox"},
        {"id": "stage", "label": "Stage"},
    ]
    if show_jobs:
        items.append({"id": "jobs", "label": "Jobs"})
    items.append({"id": "outbox", "label": "Outbox"})
    return {"items": items}


def _api_jobs() -> dict[str, Any]:
    orch = Orchestrator()
    jobs = [j.to_dict() for j in orch.list_jobs()]
    # stable ordering
    jobs.sort(key=lambda x: x.get("job_id") or "")
    return {"items": jobs}


def _try_include_abs_file(
    fs: FileService,
    *,
    abs_path: str | None,
    name_in_zip: str,
    max_lines: int,
    max_bytes: int,
) -> tuple[bool, str]:
    if not abs_path:
        return (False, "missing_path")
    try:
        p = Path(abs_path).expanduser().resolve()
    except Exception:
        return (False, "invalid_path")

    # Only include if the path is under one of the configured roots.
    for root in RootName:
        try:
            base = fs.root_dir(root).resolve()
        except Exception:
            continue
        try:
            p.relative_to(base)
        except Exception:
            continue

        rel = str(p.relative_to(base))
        if not fs.exists(root, rel):
            return (False, "not_found")
        try:
            _ = fs.tail_bytes(root, rel, max_bytes=max_bytes)
        except Exception:
            return (False, "read_failed")
        return (True, json.dumps({"root": root.value, "rel": rel, "zip": name_in_zip}))

    return (False, "outside_roots")


def _plugin_info(request: Request) -> dict[str, Any]:
    loader = getattr(request.app.state, "plugin_loader", None)
    if loader is None:
        return {"loaded": [], "manifests": {}}

    loaded: list[str] = []
    manifests: dict[str, Any] = {}
    try:
        loaded = list(loader.list_plugins())
    except Exception:
        loaded = []

    for name in loaded:
        try:
            man = loader.get_manifest(name)
            if is_dataclass(man) and not isinstance(man, type):
                manifests[name] = asdict(man)
            elif is_dataclass(man):
                manifests[name] = {"dataclass": getattr(man, "__name__", str(man))}
            elif isinstance(man, dict):
                manifests[name] = man
            else:
                manifests[name] = {"value": str(man)}
        except Exception:
            # best-effort only
            continue

    return _sanitize({"loaded": loaded, "manifests": manifests})


def mount_debug_bundle(app: FastAPI) -> None:
    @app.get("/api/debug/bundle")
    def api_debug_bundle(
        request: Request,
        logs_tail_lines: int = 2000,
    ) -> StreamingResponse:
        """Download a deterministic debug bundle as a ZIP."""
        if logs_tail_lines < 0:
            raise HTTPException(status_code=400, detail="invalid params")

        resolver = _get_resolver(request)
        fs = _get_file_service(request)

        now = datetime.now(tz=UTC)

        # Collect content.
        manifest: dict[str, Any] = {
            "version": 1,
            "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hostname": socket.gethostname(),
            "stage_dir": str(fs.root_dir(RootName.STAGE)),
            "git_sha": _try_find_git_sha(),
            "params": {"logs_tail_lines": int(logs_tail_lines)},
            "included": {},
            "omitted": {},
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            _zip_add_text(z, "config/effective_config.json", _effective_config_json(resolver))
            manifest["included"]["effective_config"] = {"path": "config/effective_config.json"}

            _zip_add_text(
                z,
                "plugins/plugins.json",
                json.dumps(_plugin_info(request), indent=2, sort_keys=True) + "\n",
            )
            manifest["included"]["plugins"] = {"path": "plugins/plugins.json"}

            # UI overrides (config root)
            ui_rel = "web_interface_ui.json"
            try:
                if fs.exists(RootName.CONFIG, ui_rel):
                    with fs.open_read(RootName.CONFIG, ui_rel) as f:
                        raw = f.read()
                    try:
                        obj = json.loads(raw.decode("utf-8"))
                    except Exception:
                        obj = {"raw": raw.decode("utf-8", errors="replace")[:200000]}
                    _zip_add_text(
                        z,
                        "ui/ui_overrides.json",
                        json.dumps(_sanitize(obj), indent=2, sort_keys=True) + "\n",
                    )
                    manifest["included"]["ui_overrides"] = {"root": "config", "rel": ui_rel}
                else:
                    manifest["omitted"]["ui_overrides"] = "not_found"
            except Exception as e:
                manifest["omitted"]["ui_overrides"] = f"error:{type(e).__name__}"

            # Logs: system log (path may live under a root)
            try:
                sys_path = resolver.resolve_system_log_path()
            except Exception:
                sys_path = None
            ok, detail = _try_include_abs_file(
                fs,
                abs_path=sys_path if isinstance(sys_path, str) else None,
                name_in_zip="logs/system.log",
                max_lines=int(logs_tail_lines),
                max_bytes=2_000_000,
            )
            if ok:
                # re-read using info encoded in detail for determinism
                info = json.loads(detail)
                raw = fs.tail_bytes(RootName(info["root"]), info["rel"], max_bytes=2_000_000)
                _zip_add_bytes(
                    z, info["zip"], _tail_lines_from_bytes(raw, max_lines=int(logs_tail_lines))
                )
                manifest["included"]["system_log"] = info
            else:
                manifest["omitted"]["system_log"] = detail

            # Logs: diagnostics.jsonl (stage root)
            diag_rel = "diagnostics/diagnostics.jsonl"
            try:
                if fs.exists(RootName.STAGE, diag_rel):
                    raw = fs.tail_bytes(RootName.STAGE, diag_rel, max_bytes=2_000_000)
                    _zip_add_bytes(
                        z,
                        "diagnostics/diagnostics.jsonl",
                        _tail_lines_from_bytes(raw, max_lines=int(logs_tail_lines)),
                    )
                    manifest["included"]["diagnostics_jsonl"] = {"root": "stage", "rel": diag_rel}
                else:
                    manifest["omitted"]["diagnostics_jsonl"] = "not_found"
            except Exception as e:
                manifest["omitted"]["diagnostics_jsonl"] = f"error:{type(e).__name__}"

            # API snapshots
            try:
                _zip_add_text(
                    z,
                    "api/status.json",
                    json.dumps(build_status(), indent=2, sort_keys=True) + "\n",
                )
                manifest["included"]["api_status"] = {"path": "api/status.json"}
            except Exception as e:
                manifest["omitted"]["api_status"] = f"error:{type(e).__name__}"

            try:
                _zip_add_text(
                    z,
                    "api/roots.json",
                    json.dumps(_api_roots(request, resolver), indent=2, sort_keys=True) + "\n",
                )
                manifest["included"]["api_roots"] = {"path": "api/roots.json"}
            except Exception as e:
                manifest["omitted"]["api_roots"] = f"error:{type(e).__name__}"

            try:
                _zip_add_text(
                    z, "api/jobs.json", json.dumps(_api_jobs(), indent=2, sort_keys=True) + "\n"
                )
                manifest["included"]["api_jobs"] = {"path": "api/jobs.json"}
            except Exception as e:
                manifest["omitted"]["api_jobs"] = f"error:{type(e).__name__}"

            # Notes
            notes = (
                "Repro notes\n"
                "\n"
                "1) Start the web interface (audiomason web).\n"
                "2) Download the bundle: GET /api/debug/bundle\n"
                "   - logs_tail_lines: number of tail lines for log-like files (default 2000).\n"
                "\n"
                "Bundle contents are best-effort; missing system.log is not an error.\n"
            )
            _zip_add_text(z, "notes.txt", notes)
            manifest["included"]["notes"] = {"path": "notes.txt"}

            _zip_add_text(z, "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        buf.seek(0)

        headers = {"Content-Disposition": 'attachment; filename="audiomason_debug_bundle.zip"'}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)
