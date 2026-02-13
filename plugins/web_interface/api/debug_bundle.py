from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigResolver
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

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


def _tail_lines_from_bytes(data: bytes, *, max_lines: int) -> bytes:
    if max_lines <= 0:
        return b""
    # Decode with replacement, then re-encode to keep text-friendly tail files.
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    tail = lines[-max_lines:]
    return ("\n".join(tail) + "\n").encode("utf-8")


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
        jobs_n: int = 50,
    ) -> StreamingResponse:
        """Download a deterministic debug bundle as a ZIP."""
        if logs_tail_lines < 0 or jobs_n < 0:
            raise HTTPException(status_code=400, detail="invalid params")

        resolver = _get_resolver(request)
        fs = _get_file_service(request)

        # Collect content.
        meta: dict[str, Any] = {
            "logs_tail_lines": int(logs_tail_lines),
            "jobs_n": int(jobs_n),
            "included": {},
            "omitted": {},
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            _zip_add_bytes(
                z,
                "debug_bundle/config/effective_config.json",
                _effective_config_json(resolver).encode("utf-8"),
            )

            _zip_add_bytes(
                z,
                "debug_bundle/plugins/plugins.json",
                json.dumps(_plugin_info(request), indent=2, sort_keys=True).encode("utf-8") + b"\n",
            )

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
                    _zip_add_bytes(
                        z,
                        "debug_bundle/ui/ui_overrides.json",
                        (json.dumps(_sanitize(obj), indent=2, sort_keys=True) + "\n").encode(
                            "utf-8"
                        ),
                    )
                    meta["included"]["ui_overrides"] = {"root": "config", "rel": ui_rel}
                else:
                    meta["omitted"]["ui_overrides"] = "not_found"
            except Exception as e:
                meta["omitted"]["ui_overrides"] = f"error:{type(e).__name__}"

            # Logs: system log (path may live under a root)
            try:
                sys_path = resolver.resolve_system_log_path()
            except Exception:
                sys_path = None
            ok, detail = _try_include_abs_file(
                fs,
                abs_path=sys_path if isinstance(sys_path, str) else None,
                name_in_zip="debug_bundle/logs/system.log.tail",
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
                meta["included"]["system_log"] = info
            else:
                meta["omitted"]["system_log"] = detail

            # Logs: diagnostics.jsonl (stage root)
            diag_rel = "diagnostics/diagnostics.jsonl"
            try:
                if fs.exists(RootName.STAGE, diag_rel):
                    raw = fs.tail_bytes(RootName.STAGE, diag_rel, max_bytes=2_000_000)
                    _zip_add_bytes(
                        z,
                        "debug_bundle/logs/diagnostics.jsonl.tail",
                        _tail_lines_from_bytes(raw, max_lines=int(logs_tail_lines)),
                    )
                    meta["included"]["diagnostics_jsonl"] = {"root": "stage", "rel": diag_rel}
                else:
                    meta["omitted"]["diagnostics_jsonl"] = "not_found"
            except Exception as e:
                meta["omitted"]["diagnostics_jsonl"] = f"error:{type(e).__name__}"

            # Jobs snapshot (jobs root)
            job_entries = []
            try:
                for ent in fs.list_dir(RootName.JOBS, ".", recursive=True):
                    if ent.is_dir:
                        continue
                    if ent.rel_path.endswith(".json") and not ent.rel_path.endswith(".tmp"):
                        job_entries.append(ent)
            except Exception:
                job_entries = []

            # newest first (mtime desc), then rel_path for tie stability
            job_entries.sort(key=lambda e: (-(e.mtime or 0.0), e.rel_path))
            selected = job_entries[: int(jobs_n)]
            meta["included"]["jobs"] = {"count": len(selected)}

            for ent in selected:
                base = ent.rel_path.split("/")[-1]
                zip_name = f"debug_bundle/jobs/{base}"
                try:
                    with fs.open_read(RootName.JOBS, ent.rel_path) as f:
                        data = f.read()
                    _zip_add_bytes(z, zip_name, data)
                except Exception:
                    # best-effort: skip file
                    continue

                # job log next to json (same stem + .log)
                if base.endswith(".json"):
                    log_rel = ent.rel_path[: -len(".json")] + ".log"
                    if fs.exists(RootName.JOBS, log_rel):
                        try:
                            with fs.open_read(RootName.JOBS, log_rel) as f:
                                log_data = f.read()
                            _zip_add_bytes(z, f"debug_bundle/jobs/{Path(log_rel).name}", log_data)
                        except Exception:
                            pass

            _zip_add_bytes(
                z,
                "debug_bundle/meta.json",
                (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )

        buf.seek(0)

        ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"audiomason_debug_bundle_{ts}.zip"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(buf, media_type="application/zip", headers=headers)
