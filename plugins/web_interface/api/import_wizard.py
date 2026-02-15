from __future__ import annotations

import asyncio
import hashlib
import importlib
from collections.abc import Iterable
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.web_observability import web_operation

_IMPORT_MODS: dict[str, Any] | None = None

BOOK_ONLY_LABEL = "<book-only>"


def _import_plugin() -> dict[str, Any]:
    """Import the import plugin modules.

    The plugin package is named 'import' which collides with Python syntax,
    therefore we must use importlib.
    """

    return {
        "PreflightService": importlib.import_module(
            "plugins.import.preflight.service"
        ).PreflightService,
        "PreflightResult": importlib.import_module(
            "plugins.import.preflight.types"
        ).PreflightResult,
        "BookPreflight": importlib.import_module("plugins.import.preflight.types").BookPreflight,
        "ImportEngineService": importlib.import_module(
            "plugins.import.services.engine_service"
        ).ImportEngineService,
        "ImportJobRequest": importlib.import_module("plugins.import.engine.types").ImportJobRequest,
        "ImportRunState": importlib.import_module(
            "plugins.import.session_store.types"
        ).ImportRunState,
        "WizardDefaultsStore": importlib.import_module(
            "plugins.import.session_store.service"
        ).WizardDefaultsStore,
        "ProcessedRegistry": importlib.import_module(
            "plugins.import.processed_registry.service"
        ).ProcessedRegistry,
        "fingerprint_key": importlib.import_module(
            "plugins.import.processed_registry.service"
        ).fingerprint_key,
    }


def _mods() -> dict[str, Any]:
    global _IMPORT_MODS
    if _IMPORT_MODS is None:
        _IMPORT_MODS = _import_plugin()
    return _IMPORT_MODS


def _emit_import_action(event_name: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event_name,
            component="web_interface.import_wizard",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event_name, env)
    except Exception:
        return


def _error_detail(operation: str, exc: Exception) -> dict[str, Any]:
    return {
        "operation": operation,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


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


def _parse_root(root: str) -> RootName:
    try:
        return RootName(root)
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid root") from e


def _norm_rel_path(p: str) -> str:
    p = p.strip()
    if not p:
        return "."
    p = p.lstrip("/")
    parts = [x for x in p.split("/") if x not in {"", "."}]
    if any(x == ".." for x in parts):
        raise HTTPException(status_code=400, detail="invalid path")
    return "/".join(parts) if parts else "."


def _normalize_audio_processing_options(options: dict[str, Any]) -> dict[str, Any]:
    """Normalize PHASE 1 audio processing options.

    This produces a deterministic shape for PHASE 2 consumption.
    Missing or invalid values are replaced with safe defaults.
    """

    ap = options.get("audio_processing")
    if not isinstance(ap, dict):
        return {}

    enabled = bool(ap.get("enabled"))
    if not enabled:
        return {}

    # Explicit PHASE 1 confirmation is required for any destructive processing.
    confirmed = bool(ap.get("confirmed"))

    bitrate_kbps_raw: object | None = ap.get("bitrate_kbps")
    try:
        if isinstance(bitrate_kbps_raw, int):
            bitrate_kbps_i = bitrate_kbps_raw
        elif isinstance(bitrate_kbps_raw, str):
            bitrate_kbps_i = int(bitrate_kbps_raw.strip())
        elif bitrate_kbps_raw is None:
            raise TypeError
        else:
            bitrate_kbps_i = int(str(bitrate_kbps_raw).strip())
    except (TypeError, ValueError):
        bitrate_kbps_i = 96
    if bitrate_kbps_i <= 0:
        bitrate_kbps_i = 96

    mode = str(ap.get("bitrate_mode") or "cbr").strip().lower()
    if mode not in {"cbr", "vbr"}:
        mode = "cbr"

    loudnorm = bool(ap.get("loudnorm"))

    return {
        "audio_processing": {
            "enabled": True,
            "confirmed": bool(confirmed),
            "bitrate_kbps": int(bitrate_kbps_i),
            "bitrate_mode": mode,
            "loudnorm": bool(loudnorm),
        }
    }


def _run_id_for(root: str, rel: str, book_rel: str, mode: str) -> str:
    h = hashlib.sha256()
    for part in (root, "\n", rel, "\n", book_rel, "\n", mode):
        h.update(str(part).encode("utf-8"))
    return "run_" + h.hexdigest()[:12]


def _engine(request: Request) -> Any:
    fs = _get_file_service(request)
    return _mods()["ImportEngineService"](fs=fs)


def _registry(request: Request) -> Any:
    fs = _get_file_service(request)
    return _mods()["ProcessedRegistry"](fs)


IMPORT_WIZARD_NAME = "import_wizard"


def _defaults_store(request: Request) -> Any:
    fs = _get_file_service(request)
    return _mods()["WizardDefaultsStore"](fs)


def _preset_defaults_for(mode: str) -> dict[str, Any]:
    # Preset defaults are conservative and non-destructive.
    # Conflict policy remains "ask" by default.
    return {
        "conflict_policy": {"mode": "ask"},
        "options": {
            "audio_processing": {
                "enabled": False,
                "confirmed": False,
                "bitrate_kbps": 96,
                "bitrate_mode": "cbr",
                "loudnorm": False,
            }
        },
    }


def _merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    from typing import cast

    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        existing = out.get(k)
        if isinstance(v, dict) and isinstance(existing, dict):
            out[k] = _merge_dict(cast(dict[str, Any], existing), cast(dict[str, Any], v))
        else:
            out[k] = v
    return out


def _effective_defaults_for(request: Request, mode: str) -> dict[str, Any]:
    preset = _preset_defaults_for(mode)
    saved = _defaults_store(request).get(IMPORT_WIZARD_NAME, mode)
    if isinstance(saved, dict):
        return _merge_dict(preset, saved)
    return preset


def _preflight_service(request: Request) -> Any:
    mods = _mods()
    fs = _get_file_service(request)
    # Web Import Wizard deep enrichment uses best-effort external lookup by default.
    return mods["PreflightService"](fs, enable_lookup=True)


def _serialize_index(res: Any) -> dict[str, Any]:
    return {
        "source_root_rel_path": res.source_root_rel_path,
        "signature": res.signature,
        "changed": bool(res.changed),
        "last_scan_ts": res.last_scan_ts,
        "deep_scan_state": {
            "state": res.deep_scan_state.state,
            "signature": res.deep_scan_state.signature,
            "last_scan_ts": res.deep_scan_state.last_scan_ts,
            "scanned_items": res.deep_scan_state.scanned_items,
            "total_items": res.deep_scan_state.total_items,
            "last_error": res.deep_scan_state.last_error,
        },
        "root_items": [
            {
                "rel_path": it.rel_path,
                "item_type": it.item_type,
                "size": it.size,
                "mtime": it.mtime,
            }
            for it in res.root_items
        ],
        "authors": list(res.authors),
        "books": [
            {
                "book_ref": b.book_ref,
                "unit_type": b.unit_type,
                "author": b.author,
                "book": b.book,
                "rel_path": b.rel_path,
                "suggested_author": b.suggested_author,
                "suggested_title": b.suggested_title,
                "cover_candidates": b.cover_candidates or [],
                "rename_preview": b.rename_preview or None,
                "fingerprint": ""
                if b.fingerprint is None
                else _mods()["fingerprint_key"](
                    algo=b.fingerprint.algo,
                    value=b.fingerprint.value,
                ),
                "meta": b.meta or None,
            }
            for b in res.books
        ],
    }


def mount_import_wizard(app: FastAPI) -> None:
    def _serialize_preflight(res: Any) -> dict[str, Any]:
        authors = list(res.authors)
        has_book_only = any(getattr(b, "author", "") == "" for b in res.books)
        if has_book_only and BOOK_ONLY_LABEL not in authors:
            authors.append(BOOK_ONLY_LABEL)

        return {
            "source_root_rel_path": res.source_root_rel_path,
            "authors": authors,
            "books": [
                {
                    "author": b.author,
                    "book": b.book,
                    "rel_path": b.rel_path,
                    "suggested_author": b.suggested_author,
                    "suggested_title": b.suggested_title,
                    "cover_candidates": b.cover_candidates or [],
                    "rename_preview": b.rename_preview or None,
                    "fingerprint": ""
                    if b.fingerprint is None
                    else _mods()["fingerprint_key"](
                        algo=b.fingerprint.algo,
                        value=b.fingerprint.value,
                    ),
                }
                for b in res.books
            ],
            "skipped": [
                {
                    "rel_path": s.rel_path,
                    "entry_type": s.entry_type,
                    "reason": s.reason,
                }
                for s in getattr(res, "skipped", []) or []
            ],
        }

    def _task_key(root: str, path: str) -> str:
        return f"{root}:{path}"

    def _get_tasks(app: FastAPI) -> dict[str, asyncio.Task[None]]:
        tasks = getattr(app.state, "import_wizard_deep_tasks", None)
        if isinstance(tasks, dict):
            return tasks
        tasks = {}
        app.state.import_wizard_deep_tasks = tasks
        return tasks

    def _start_deep_scan(app: FastAPI, *, fs: FileService, root: RootName, rel: str) -> None:
        # Fire-and-forget; never block request handling.
        key = _task_key(str(root.value), rel)
        tasks = _get_tasks(app)
        existing = tasks.get(key)
        if existing is not None and not existing.done():
            return

        async def _runner() -> None:
            # Deep enrichment in the Web Import Wizard context enables external
            # lookup by default, but remains strictly best-effort and fail-safe.
            svc = _mods()["PreflightService"](fs, enable_lookup=True)
            try:
                await asyncio.to_thread(svc.run_deep_enrichment_if_needed, root, rel)
            finally:
                # Keep task slot but let it complete.
                pass

        tasks[key] = asyncio.create_task(_runner())

    def _run_preflight(request: Request, *, root: str, path: str) -> dict[str, Any]:
        _emit_import_action(
            "import.preflight",
            operation="preflight",
            data={"status": "start", "root": root, "path": path},
        )
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        # Web Import Wizard context: external lookup MUST be enabled by default
        # (best-effort, fail-safe).
        svc = _preflight_service(request)

        try:
            res = svc.run(r, rel)
        except HTTPException as e:
            _emit_import_action(
                "import.preflight",
                operation="preflight",
                data={
                    "status": "failed",
                    "http_status": int(getattr(e, "status_code", 0) or 0),
                    "detail": getattr(e, "detail", None),
                },
            )
            raise
        except Exception as e:
            _emit_import_action(
                "import.preflight",
                operation="preflight",
                data={"status": "failed", **_error_detail("preflight", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("preflight", e)) from e

        _emit_import_action(
            "import.preflight",
            operation="preflight",
            data={"status": "succeeded", "authors_n": len(res.authors), "books_n": len(res.books)},
        )
        return _serialize_preflight(res)

    @app.get("/api/import_wizard/index")
    def import_index_get(request: Request, root: str, path: str = ".") -> dict[str, Any]:
        fs = _get_file_service(request)
        svc = _preflight_service(request)
        with web_operation(
            request,
            name="import_wizard.index",
            ctx={"root": root, "path": path},
            component="web_interface.import_wizard",
        ):
            root_name = _parse_root(root)
            rel = path

            try:
                res = svc.fast_index(root_name, rel)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=_error_detail("index", e)) from e

            # Ensure book-only label appears in authors list when needed.
            authors = list(res.authors)
            has_book_only = any(getattr(b, "author", "") == "" for b in res.books)
            if has_book_only and BOOK_ONLY_LABEL not in authors:
                authors.append(BOOK_ONLY_LABEL)
                authors.sort()
                res = type(res)(
                    source_root_rel_path=res.source_root_rel_path,
                    signature=res.signature,
                    changed=res.changed,
                    last_scan_ts=res.last_scan_ts,
                    deep_scan_state=res.deep_scan_state,
                    root_items=res.root_items,
                    authors=authors,
                    books=res.books,
                )

            # Trigger deep scan in background when index signature changed.
            if bool(res.changed):
                _start_deep_scan(request.app, fs=fs, root=root_name, rel=rel)

            return _serialize_index(res)

    @app.get("/api/import_wizard/enrichment_status")
    def import_enrichment_status_get(
        request: Request, root: str, path: str = "."
    ) -> dict[str, Any]:
        svc = _preflight_service(request)
        with web_operation(
            request,
            name="import_wizard.enrichment_status",
            ctx={"root": root, "path": path},
            component="web_interface.import_wizard",
        ):
            try:
                st = svc.get_deep_scan_state()
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=_error_detail("enrichment_status", e)
                ) from e
            return {
                "state": st.state,
                "signature": st.signature,
                "last_scan_ts": st.last_scan_ts,
                "scanned_items": st.scanned_items,
                "total_items": st.total_items,
                "last_error": st.last_error,
            }

    @app.on_event("startup")
    async def _import_wizard_startup() -> None:
        # Best-effort: trigger background deep scan for default inbox root.
        try:
            resolver = getattr(app.state, "config_resolver", None)
            if not isinstance(resolver, ConfigResolver):
                resolver = ConfigResolver()
                app.state.config_resolver = resolver
            fs = getattr(app.state, "file_service", None)
            if not isinstance(fs, FileService):
                fs = FileService.from_resolver(resolver)
                app.state.file_service = fs
            root_name = RootName("inbox")
            rel = "."
            # Build/update index quickly, then start deep scan if needed.
            svc = _mods()["PreflightService"](fs)
            await asyncio.to_thread(svc.fast_index, root_name, rel)
            _start_deep_scan(app, fs=fs, root=root_name, rel=rel)
        except Exception:
            return

    @app.get("/api/import_wizard/preflight")
    def import_preflight_get(request: Request, root: str, path: str = ".") -> dict[str, Any]:
        with web_operation(
            request,
            name="import_wizard.preflight",
            ctx={"root": root, "path": path},
            component="web_interface.import_wizard",
        ):
            return _run_preflight(request, root=root, path=path)

    @app.post("/api/import_wizard/preflight")
    def import_preflight_post(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path", ".")
        if not isinstance(root, str) or not root:
            raise HTTPException(status_code=400, detail="root is required")
        if not isinstance(path, str):
            path = "."
        with web_operation(
            request,
            name="import_wizard.preflight",
            ctx={"root": root, "path": path},
            component="web_interface.import_wizard",
        ):
            return _run_preflight(request, root=root, path=path)

    @app.get("/api/import_wizard/processed_registry")
    def import_processed_registry(request: Request) -> dict[str, Any]:
        with web_operation(
            request,
            name="import_wizard.processed_registry",
            ctx={},
            component="web_interface.import_wizard",
        ):
            reg = _registry(request)
            try:
                raw_items = reg.list_processed()
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=_error_detail("processed_registry", e)
                ) from e

            # Stable schema: UI consumes "keys" (list[str]) of processed fingerprint keys.
            # Keep "items" for backwards compatibility.
            keys_set: set[str] = set()

            # reg.list_processed() is expected to return a collection of key strings,
            # but older/alternate implementations may return dict-shaped outputs.
            iterable: Iterable[object]
            if isinstance(raw_items, dict):
                iterable = raw_items.keys()
            elif raw_items is None:
                iterable = ()
            else:
                iterable = cast(Iterable[object], raw_items)

            for v in iterable:
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        keys_set.add(s)
                elif isinstance(v, dict):
                    # Defensive compatibility: accept objects like {"key": "..."}.
                    cand = v.get("key") or v.get("identity_key") or v.get("fingerprint_key")
                    if isinstance(cand, str):
                        s = cand.strip()
                        if s:
                            keys_set.add(s)

            keys = sorted(keys_set)
            return {"keys": keys, "items": keys, "count": len(keys)}

    @app.post("/api/import_wizard/unmark_processed")
    def import_unmark_processed(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            fp = payload.get("fingerprint")
            if isinstance(fp, dict):
                algo = fp.get("algo")
                value = fp.get("value")
                if isinstance(algo, str) and isinstance(value, str):
                    key = _mods()["fingerprint_key"](algo=algo, value=value)
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(status_code=400, detail="key is required")

        with web_operation(
            request,
            name="import_wizard.unmark_processed",
            ctx={"key": key},
            component="web_interface.import_wizard",
        ):
            reg = _registry(request)
            try:
                reg.unmark_processed(str(key))
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=_error_detail("unmark_processed", e)
                ) from e
            return {"ok": True}

    @app.get("/api/import_wizard/defaults")
    def import_defaults_get(request: Request, mode: str = "stage") -> dict[str, Any]:
        if not isinstance(mode, str) or not mode.strip():
            mode = "stage"
        mode = mode.strip().lower()
        if mode not in {"stage", "inplace", "hybrid"}:
            raise HTTPException(status_code=400, detail="invalid mode")

        with web_operation(
            request,
            name="import_wizard.defaults_get",
            ctx={"mode": mode},
            component="web_interface.import_wizard",
        ):
            store = _defaults_store(request)
            preset = _preset_defaults_for(mode)
            saved = store.get(IMPORT_WIZARD_NAME, mode)
            effective = _merge_dict(preset, saved) if isinstance(saved, dict) else preset
            return {
                "wizard": IMPORT_WIZARD_NAME,
                "mode": mode,
                "preset": preset,
                "saved": saved,
                "effective": effective,
            }

    @app.post("/api/import_wizard/defaults/save")
    def import_defaults_save(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("mode", "stage")
        defaults = payload.get("defaults")
        if not isinstance(mode, str) or not mode.strip():
            mode = "stage"
        mode = mode.strip().lower()
        if mode not in {"stage", "inplace", "hybrid"}:
            raise HTTPException(status_code=400, detail="invalid mode")
        if not isinstance(defaults, dict):
            raise HTTPException(status_code=400, detail="defaults is required")

        # Only accept the known top-level keys for now.
        out: dict[str, Any] = {}
        if isinstance(defaults.get("conflict_policy"), dict):
            out["conflict_policy"] = defaults["conflict_policy"]
        if isinstance(defaults.get("options"), dict):
            out["options"] = defaults["options"]

        with web_operation(
            request,
            name="import_wizard.defaults_save",
            ctx={"mode": mode},
            component="web_interface.import_wizard",
        ):
            _defaults_store(request).put(IMPORT_WIZARD_NAME, mode, out)
            return {"ok": True}

    @app.post("/api/import_wizard/defaults/reset")
    def import_defaults_reset(
        request: Request, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        mode = "stage"
        if isinstance(payload, dict) and isinstance(payload.get("mode"), str):
            mode = str(payload.get("mode") or "stage")
        mode = mode.strip().lower()
        if mode not in {"stage", "inplace", "hybrid"}:
            raise HTTPException(status_code=400, detail="invalid mode")

        with web_operation(
            request,
            name="import_wizard.defaults_reset",
            ctx={"mode": mode},
            component="web_interface.import_wizard",
        ):
            _defaults_store(request).reset(IMPORT_WIZARD_NAME, mode)
            return {"ok": True}

    @app.post("/api/import_wizard/start")
    def import_start(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        _emit_import_action("import.queue", operation="queue", data={"status": "start"})
        mods = _mods()
        preflight_result_cls = mods["PreflightResult"]
        import_run_state_cls = mods["ImportRunState"]
        import_job_request_cls = mods["ImportJobRequest"]
        root = payload.get("root")
        path = payload.get("path", ".")
        book_rel = payload.get("book_rel_path")
        mode = payload.get("mode", "stage")
        conflict_policy = payload.get("conflict_policy")
        options = payload.get("options")

        if not isinstance(root, str) or not root:
            raise HTTPException(status_code=400, detail="root is required")
        if not isinstance(book_rel, str) or not book_rel:
            raise HTTPException(status_code=400, detail="book_rel_path is required")
        if not isinstance(mode, str) or not mode:
            mode = "stage"
        mode = mode.strip().lower()
        if mode not in {"stage", "inplace", "hybrid"}:
            raise HTTPException(status_code=400, detail="invalid mode")
        # Conflict policy is PHASE 1 owned. Default is ask, but PHASE 2 job creation
        # requires a resolved policy (non-interactive).
        if not isinstance(conflict_policy, dict):
            conflict_policy = {"mode": "ask"}
        mode_val = str(conflict_policy.get("mode", "ask")).strip().lower()
        if mode_val == "ask":
            raise HTTPException(
                status_code=409,
                detail={"error": "conflict_policy_unresolved", "conflict_policy": conflict_policy},
            )

        # Mode-driven parallelism contract (Issue 503).
        # - stage: parallelism=2
        # - inplace: parallelism=1
        parallelism_n = 2 if mode == "stage" else 1

        # Options are a free-form dict, stored in the run state for PHASE 2.
        # Normalize known option groups for deterministic PHASE 2 consumption.
        if not isinstance(options, dict):
            options = {}
        norm_opts: dict[str, Any] = {}
        norm_opts.update(_normalize_audio_processing_options(options))
        # If audio processing was enabled but not explicitly confirmed, block PHASE 2.
        ap = norm_opts.get("audio_processing")
        if isinstance(ap, dict) and ap.get("enabled") and not ap.get("confirmed"):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "audio_processing_unconfirmed",
                    "audio_processing": ap,
                },
            )
        # Preserve remaining caller-provided options for future extension.
        for k, v in options.items():
            if k in norm_opts:
                continue
            norm_opts[k] = v
        options = norm_opts

        r = _parse_root(root)
        rel = _norm_rel_path(str(path))

        try:
            # Web Import Wizard context: external lookup MUST be enabled by default
            # (best-effort, fail-safe).
            preflight = _preflight_service(request).run(r, rel)
        except Exception as e:
            _emit_import_action(
                "import.queue",
                operation="queue",
                data={"status": "failed", **_error_detail("preflight", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("preflight", e)) from e

        selected = [b for b in preflight.books if b.rel_path == book_rel]
        if not selected:
            raise HTTPException(status_code=404, detail="book not found in preflight")
        run_id = _run_id_for(root, rel, book_rel, mode)

        engine = _engine(request)
        existing_job_ids: list[str] = []
        try:
            for job in engine.jobs.list_jobs():
                if job.meta.get("kind") != "import":
                    continue
                if job.meta.get("run_id") != run_id:
                    continue
                existing_job_ids.append(str(job.job_id))
        except Exception as e:
            raise HTTPException(status_code=500, detail=_error_detail("status", e)) from e

        if existing_job_ids:
            existing_job_ids.sort()
            if mode == "stage":
                # Resume is supported only in stage mode.
                return {"run_id": run_id, "job_ids": existing_job_ids, "resumed": True}
            raise HTTPException(status_code=409, detail="resume_not_supported_in_inplace")

        state = import_run_state_cls(
            source_selection_snapshot={
                "root": root,
                "source_root_rel_path": rel,
                "selected_book_rel_path": book_rel,
            },
            source_handling_mode=mode,
            parallelism_n=int(parallelism_n),
            global_options=options,
            conflict_policy=conflict_policy,
        )

        preflight_one = preflight_result_cls(
            source_root_rel_path=preflight.source_root_rel_path,
            authors=[selected[0].author],
            books=selected,
            skipped=[],
        )
        decisions = engine.resolve_book_decisions(preflight=preflight_one, state=state)
        try:
            job_ids = engine.start_import_job(
                import_job_request_cls(
                    run_id=run_id,
                    source_root=root,
                    state=state,
                    decisions=decisions,
                )
            )
        except Exception as e:
            _emit_import_action(
                "import.queue",
                operation="queue",
                data={"status": "failed", **_error_detail("start_import_job", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("start_import_job", e)) from e

        _emit_import_action(
            "import.queue",
            operation="queue",
            data={"status": "succeeded", "run_id": run_id, "job_ids_n": len(job_ids)},
        )
        return {"run_id": run_id, "job_ids": job_ids}

    @app.get("/api/import_wizard/status")
    def import_status(request: Request, run_id: str) -> dict[str, Any]:
        if not isinstance(run_id, str) or not run_id.strip():
            raise HTTPException(status_code=400, detail="run_id is required")

        engine = _engine(request)
        job_ids: list[str] = []
        counts: dict[str, int] = {}

        try:
            for job in engine.jobs.list_jobs():
                if job.meta.get("kind") != "import":
                    continue
                if job.meta.get("run_id") != run_id:
                    continue
                job_ids.append(str(job.job_id))
                st = str(job.state)
                counts[st] = counts.get(st, 0) + 1
        except Exception as e:
            raise HTTPException(status_code=500, detail=_error_detail("status", e)) from e

        job_ids.sort()
        return {"run_id": run_id, "job_ids": job_ids, "counts": counts}

    @app.post("/api/import_wizard/run_pending")
    def import_run_pending(
        request: Request, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        _emit_import_action("import.run", operation="run_pending", data={"status": "start"})
        limit = 2
        if isinstance(payload, dict) and isinstance(payload.get("limit"), int):
            limit = int(payload["limit"]) or 1
        if limit <= 0:
            limit = 1

        engine = _engine(request)
        try:
            ran = engine.run_pending(limit=limit)
        except Exception as e:
            _emit_import_action(
                "import.run",
                operation="run_pending",
                data={"status": "failed", **_error_detail("run_pending", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("run_pending", e)) from e

        _emit_import_action(
            "import.run",
            operation="run_pending",
            data={"status": "succeeded", "ran_n": len(ran)},
        )
        return {"ran": ran}

    @app.post("/api/import_wizard/pause_queue")
    def import_pause_queue(request: Request) -> dict[str, Any]:
        _emit_import_action("import.pause", operation="pause_queue", data={"status": "start"})
        engine = _engine(request)
        try:
            engine.pause_queue()
        except Exception as e:
            _emit_import_action(
                "import.pause",
                operation="pause_queue",
                data={"status": "failed", **_error_detail("pause_queue", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("pause_queue", e)) from e
        _emit_import_action("import.pause", operation="pause_queue", data={"status": "succeeded"})
        return {"ok": True}

    @app.post("/api/import_wizard/resume_queue")
    def import_resume_queue(request: Request) -> dict[str, Any]:
        _emit_import_action("import.resume", operation="resume_queue", data={"status": "start"})
        engine = _engine(request)
        try:
            engine.resume_queue()
        except Exception as e:
            _emit_import_action(
                "import.resume",
                operation="resume_queue",
                data={"status": "failed", **_error_detail("resume_queue", e)},
            )
            raise HTTPException(status_code=500, detail=_error_detail("resume_queue", e)) from e
        _emit_import_action("import.resume", operation="resume_queue", data={"status": "succeeded"})
        return {"ok": True}
