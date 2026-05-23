from __future__ import annotations

import io
import json
import re
import socket
import zipfile
from collections.abc import Mapping
from dataclasses import is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigResolver
from audiomason.core.orchestration import Orchestrator
from audiomason.core.serde import json_loads_object
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


@runtime_checkable
class _PluginLoaderView(Protocol):
    def list_plugins(self) -> list[str]: ...

    def get_manifest(self, name: str) -> object: ...


class _StateView(Protocol):
    config_resolver: object
    file_service: object
    plugin_loader: object


def _dict_str_object(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            out[key] = item
    return out


def _to_str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _job_id_key(item: dict[str, object]) -> str:
    job_id = _to_str_or_none(item.get("job_id"))
    return job_id or ""


def _get_resolver(request: Request) -> ConfigResolver:
    state = cast(_StateView, request.state)
    try:
        resolver = state.config_resolver
    except Exception:
        resolver = None
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _get_file_service(request: Request) -> FileService:
    state = cast(_StateView, request.state)
    try:
        fs = state.file_service
    except Exception:
        fs = None
    if isinstance(fs, FileService):
        return fs
    resolver = _get_resolver(request)
    fs = FileService.from_resolver(resolver)
    state.file_service = fs
    return fs


def _sanitize(obj: object) -> object:
    """Redact known secrets from dict/list structures."""
    if isinstance(obj, dict):
        out: dict[str, object] = {}
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
    out: dict[str, object] = {}
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


def _api_roots(request: Request, resolver: ConfigResolver) -> dict[str, object]:
    show_jobs = _resolve_show_jobs_root(resolver)
    items: list[dict[str, str]] = [
        {"id": "inbox", "label": "Inbox"},
        {"id": "stage", "label": "Stage"},
    ]
    if show_jobs:
        items.append({"id": "jobs", "label": "Jobs"})
    items.append({"id": "outbox", "label": "Outbox"})
    return {"items": items}


def _api_jobs() -> dict[str, object]:
    orch = Orchestrator()
    jobs: list[dict[str, object]] = [j.to_dict() for j in orch.list_jobs()]
    # stable ordering
    jobs.sort(key=_job_id_key)
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
        detail: dict[str, str] = {"root": str(root.value), "rel": rel, "zip": name_in_zip}
        return (True, json.dumps(detail))

    return (False, "outside_roots")


def _plugin_info(request: Request) -> dict[str, object]:
    state = cast(_StateView, request.state)
    try:
        loader_obj = state.plugin_loader
    except Exception:
        loader_obj = None
    if not isinstance(loader_obj, _PluginLoaderView):
        return {"loaded": [], "manifests": {}}

    loaded: list[str] = []
    manifests: dict[str, object] = {}
    try:
        loaded = list(loader_obj.list_plugins())
    except Exception:
        loaded = []

    for name in loaded:
        try:
            man = loader_obj.get_manifest(name)
            if is_dataclass(man):
                manifests[name] = {"dataclass": type(man).__name__}
            elif isinstance(man, Mapping):
                manifests[name] = _dict_str_object(man)
            else:
                manifests[name] = {"value": str(man)}
        except Exception:
            # best-effort only
            continue

    return _dict_str_object(_sanitize({"loaded": loaded, "manifests": manifests}))


def mount_debug_bundle(app: FastAPI) -> None:
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

        included: dict[str, object] = {}
        omitted: dict[str, object] = {}

        # Collect content.
        manifest: dict[str, object] = {
            "version": 1,
            "timestamp_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "hostname": socket.gethostname(),
            "stage_dir": str(fs.root_dir(RootName.STAGE)),
            "git_sha": _try_find_git_sha(),
            "params": {"logs_tail_lines": int(logs_tail_lines)},
            "included": included,
            "omitted": omitted,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            _zip_add_text(z, "config/effective_config.json", _effective_config_json(resolver))
            included["effective_config"] = {"path": "config/effective_config.json"}

            _zip_add_text(
                z,
                "plugins/plugins.json",
                json.dumps(_plugin_info(request), indent=2, sort_keys=True) + "\n",
            )
            included["plugins"] = {"path": "plugins/plugins.json"}

            # UI overrides (config root)
            ui_rel = "web_interface_ui.json"
            try:
                if fs.exists(RootName.CONFIG, ui_rel):
                    with fs.open_read(RootName.CONFIG, ui_rel) as f:
                        raw = f.read()
                    try:
                        obj = json_loads_object(raw.decode("utf-8"))
                    except Exception:
                        obj = {"raw": raw.decode("utf-8", errors="replace")[:200000]}
                    _zip_add_text(
                        z,
                        "ui/ui_overrides.json",
                        json.dumps(_sanitize(obj), indent=2, sort_keys=True) + "\n",
                    )
                    included["ui_overrides"] = {"root": "config", "rel": ui_rel}
                else:
                    omitted["ui_overrides"] = "not_found"
            except Exception as e:
                omitted["ui_overrides"] = f"error:{type(e).__name__}"

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
                parsed_info = _dict_str_object(json_loads_object(detail))
                root_name = _to_str_or_none(parsed_info.get("root"))
                rel_path = _to_str_or_none(parsed_info.get("rel"))
                zip_name = _to_str_or_none(parsed_info.get("zip"))
                if root_name is None or rel_path is None or zip_name is None:
                    omitted["system_log"] = "invalid_detail"
                else:
                    raw = fs.tail_bytes(RootName(root_name), rel_path, max_bytes=2_000_000)
                    _zip_add_bytes(
                        z, zip_name, _tail_lines_from_bytes(raw, max_lines=int(logs_tail_lines))
                    )
                    included["system_log"] = {
                        "root": root_name,
                        "rel": rel_path,
                        "zip": zip_name,
                    }
            else:
                omitted["system_log"] = detail

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
                    included["diagnostics_jsonl"] = {"root": "stage", "rel": diag_rel}
                else:
                    omitted["diagnostics_jsonl"] = "not_found"
            except Exception as e:
                omitted["diagnostics_jsonl"] = f"error:{type(e).__name__}"

            # API snapshots
            try:
                _zip_add_text(
                    z,
                    "api/status.json",
                    json.dumps(build_status(), indent=2, sort_keys=True) + "\n",
                )
                included["api_status"] = {"path": "api/status.json"}
            except Exception as e:
                omitted["api_status"] = f"error:{type(e).__name__}"

            try:
                _zip_add_text(
                    z,
                    "api/roots.json",
                    json.dumps(_api_roots(request, resolver), indent=2, sort_keys=True) + "\n",
                )
                included["api_roots"] = {"path": "api/roots.json"}
            except Exception as e:
                omitted["api_roots"] = f"error:{type(e).__name__}"

            try:
                _zip_add_text(
                    z, "api/jobs.json", json.dumps(_api_jobs(), indent=2, sort_keys=True) + "\n"
                )
                included["api_jobs"] = {"path": "api/jobs.json"}
            except Exception as e:
                omitted["api_jobs"] = f"error:{type(e).__name__}"

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
            included["notes"] = {"path": "notes.txt"}

            _zip_add_text(z, "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

        buf.seek(0)

        headers = {"Content-Disposition": 'attachment; filename="audiomason_debug_bundle.zip"'}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)

    app.add_api_route("/api/debug/bundle", api_debug_bundle, methods=["GET"])
