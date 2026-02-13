from __future__ import annotations

import hashlib
import importlib
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

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


def _run_id_for(root: str, rel: str, book_rel: str, mode: str) -> str:
    h = hashlib.sha256()
    for part in (root, "\n", rel, "\n", book_rel, "\n", mode):
        h.update(str(part).encode("utf-8"))
    return "run_" + h.hexdigest()[:12]


def _engine(request: Request) -> Any:
    fs = _get_file_service(request)
    return _mods()["ImportEngineService"](fs=fs)


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

    def _run_preflight(request: Request, *, root: str, path: str) -> dict[str, Any]:
        _emit_import_action(
            "import.preflight",
            operation="preflight",
            data={"status": "start", "root": root, "path": path},
        )
        mods = _mods()
        preflight_service_cls = mods["PreflightService"]
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        svc = preflight_service_cls(fs)

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

    @app.get("/api/import_wizard/preflight")
    def import_preflight_get(request: Request, root: str, path: str = ".") -> dict[str, Any]:
        return _run_preflight(request, root=root, path=path)

    @app.post("/api/import_wizard/preflight")
    def import_preflight_post(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path", ".")
        if not isinstance(root, str) or not root:
            raise HTTPException(status_code=400, detail="root is required")
        if not isinstance(path, str):
            path = "."
        return _run_preflight(request, root=root, path=path)

    @app.post("/api/import_wizard/start")
    def import_start(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        _emit_import_action("import.queue", operation="queue", data={"status": "start"})
        mods = _mods()
        preflight_service_cls = mods["PreflightService"]
        preflight_result_cls = mods["PreflightResult"]
        import_run_state_cls = mods["ImportRunState"]
        import_job_request_cls = mods["ImportJobRequest"]
        root = payload.get("root")
        path = payload.get("path", ".")
        book_rel = payload.get("book_rel_path")
        mode = payload.get("mode", "stage")
        parallelism_n = payload.get("parallelism_n", 1)

        if not isinstance(root, str) or not root:
            raise HTTPException(status_code=400, detail="root is required")
        if not isinstance(book_rel, str) or not book_rel:
            raise HTTPException(status_code=400, detail="book_rel_path is required")
        if not isinstance(mode, str) or not mode:
            mode = "stage"
        mode = mode.strip().lower()
        if mode not in {"stage", "inplace", "hybrid"}:
            raise HTTPException(status_code=400, detail="invalid mode")
        if not isinstance(parallelism_n, int) or parallelism_n <= 0:
            parallelism_n = 1

        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(str(path))

        try:
            preflight = preflight_service_cls(fs).run(r, rel)
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

        state = import_run_state_cls(
            source_selection_snapshot={
                "root": root,
                "source_root_rel_path": rel,
                "selected_book_rel_path": book_rel,
            },
            source_handling_mode=mode,
            parallelism_n=int(parallelism_n),
            global_options={},
        )

        preflight_one = preflight_result_cls(
            source_root_rel_path=preflight.source_root_rel_path,
            authors=[selected[0].author],
            books=selected,
            skipped=[],
        )

        engine = _engine(request)
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
        limit = 1
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
