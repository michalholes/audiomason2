"""Import run state persistence service.

Storage is performed via file_io capability (FileService) under the JOBS root.
No direct filesystem access is permitted.

ASCII-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from .types import ImportRunState, PreflightCacheMetadata, ProcessedRegistryPolicy

_BASE_DIR = "import/session_store"
_STATE_DIR = f"{_BASE_DIR}/run_state"

_DEFAULTS_DIR = f"{_BASE_DIR}/defaults"


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.session_store",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        # Diagnostics are fail-safe.
        return


class ImportRunStateStore:
    """Persist ImportRunState keyed by wizard job id."""

    def __init__(self, fs: FileService) -> None:
        self._fs = fs
        if not self._fs.exists(RootName.JOBS, _STATE_DIR):
            self._fs.mkdir(RootName.JOBS, _STATE_DIR, parents=True, exist_ok=True)

    def put(self, run_id: str, state: ImportRunState) -> None:
        _emit_diag("boundary.start", operation="put", data={"run_id": run_id})
        rel = self._rel_path(run_id)
        payload = _encode_state(state)
        with self._fs.open_write(RootName.JOBS, rel, overwrite=True, mkdir_parents=True) as f:
            f.write(payload)
        _emit_diag("boundary.end", operation="put", data={"run_id": run_id, "status": "succeeded"})

    def get(self, run_id: str) -> ImportRunState | None:
        _emit_diag("boundary.start", operation="get", data={"run_id": run_id})
        rel = self._rel_path(run_id)
        if not self._fs.exists(RootName.JOBS, rel):
            _emit_diag(
                "boundary.end", operation="get", data={"run_id": run_id, "status": "succeeded"}
            )
            return None
        with self._fs.open_read(RootName.JOBS, rel) as f:
            data = f.read().decode("utf-8")
        obj = json.loads(data)
        state = _decode_state(obj)
        _emit_diag("boundary.end", operation="get", data={"run_id": run_id, "status": "succeeded"})
        return state

    def delete(self, run_id: str) -> None:
        _emit_diag("boundary.start", operation="delete", data={"run_id": run_id})
        rel = self._rel_path(run_id)
        if self._fs.exists(RootName.JOBS, rel):
            self._fs.delete_file(RootName.JOBS, rel)
        _emit_diag(
            "boundary.end", operation="delete", data={"run_id": run_id, "status": "succeeded"}
        )

    @staticmethod
    def _rel_path(run_id: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch in "_-.") else "_" for ch in run_id)
        return f"{_STATE_DIR}/{safe}.json"


class WizardDefaultsStore:
    """Persist wizard defaults (per wizard + per mode).

    This store is intended for PHASE 1 UI-owned defaults such as conflict policy
    selections or option toggles. It must not contain processing results.

    Storage location: JOBS root under import/session_store/defaults.
    """

    def __init__(self, fs: FileService) -> None:
        self._fs = fs
        if not self._fs.exists(RootName.JOBS, _DEFAULTS_DIR):
            self._fs.mkdir(RootName.JOBS, _DEFAULTS_DIR, parents=True, exist_ok=True)

    def get(self, wizard: str, mode: str) -> dict[str, Any] | None:
        _emit_diag(
            "boundary.start", operation="defaults.get", data={"wizard": wizard, "mode": mode}
        )
        rel = self._rel_path(wizard, mode)
        if not self._fs.exists(RootName.JOBS, rel):
            _emit_diag(
                "boundary.end",
                operation="defaults.get",
                data={"wizard": wizard, "mode": mode, "status": "succeeded", "hit": False},
            )
            return None
        with self._fs.open_read(RootName.JOBS, rel) as f:
            data = f.read().decode("utf-8")
        try:
            obj = json.loads(data)
        except Exception:
            obj = None
        out = obj if isinstance(obj, dict) else None
        _emit_diag(
            "boundary.end",
            operation="defaults.get",
            data={"wizard": wizard, "mode": mode, "status": "succeeded", "hit": bool(out)},
        )
        return out

    def put(self, wizard: str, mode: str, defaults: dict[str, Any]) -> None:
        _emit_diag(
            "boundary.start", operation="defaults.put", data={"wizard": wizard, "mode": mode}
        )
        rel = self._rel_path(wizard, mode)
        payload = _encode_json_obj(defaults)
        with self._fs.open_write(RootName.JOBS, rel, overwrite=True, mkdir_parents=True) as f:
            f.write(payload)
        _emit_diag(
            "boundary.end",
            operation="defaults.put",
            data={"wizard": wizard, "mode": mode, "status": "succeeded"},
        )

    def reset(self, wizard: str, mode: str) -> None:
        _emit_diag(
            "boundary.start", operation="defaults.reset", data={"wizard": wizard, "mode": mode}
        )
        rel = self._rel_path(wizard, mode)
        if self._fs.exists(RootName.JOBS, rel):
            self._fs.delete_file(RootName.JOBS, rel)
        _emit_diag(
            "boundary.end",
            operation="defaults.reset",
            data={"wizard": wizard, "mode": mode, "status": "succeeded"},
        )

    @staticmethod
    def _rel_path(wizard: str, mode: str) -> str:
        wiz = "".join(
            ch if (ch.isalnum() or ch in "_-.") else "_" for ch in str(wizard or "wizard")
        )
        m = "".join(ch if (ch.isalnum() or ch in "_-.") else "_" for ch in str(mode or "mode"))
        return f"{_DEFAULTS_DIR}/{wiz}__{m}.json"


def _encode_json_obj(obj: dict[str, Any]) -> bytes:
    txt = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return txt.encode("utf-8")


def _encode_state(state: ImportRunState) -> bytes:
    obj = asdict(state)
    txt = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return txt.encode("utf-8")


def _decode_state(obj: dict[str, Any]) -> ImportRunState:
    # Accepts future extension fields by ignoring unknown keys at this layer.
    prp_obj = obj.get("processed_registry_policy")
    prp = (
        ProcessedRegistryPolicy(**prp_obj)
        if isinstance(prp_obj, dict)
        else ProcessedRegistryPolicy()
    )

    pcm_obj = obj.get("preflight_cache")
    pcm = (
        PreflightCacheMetadata(**pcm_obj) if isinstance(pcm_obj, dict) else PreflightCacheMetadata()
    )

    mode = obj.get("source_handling_mode") or "stage"
    if mode not in ("stage", "inplace", "hybrid"):
        mode = "stage"

    par = obj.get("parallelism_n")
    try:
        parallelism_n = int(par) if par is not None else 1
    except Exception:
        parallelism_n = 1

    return ImportRunState(
        source_selection_snapshot=obj.get("source_selection_snapshot") or {},
        source_handling_mode=mode,  # type: ignore[arg-type]
        parallelism_n=parallelism_n,
        global_options=obj.get("global_options"),
        conflict_policy=obj.get("conflict_policy"),
        filename_normalization_policy=obj.get("filename_normalization_policy"),
        defaults_memory=obj.get("defaults_memory"),
        processed_registry_policy=prp,
        public_db_lookup=obj.get("public_db_lookup"),
        preflight_cache=pcm,
    )
