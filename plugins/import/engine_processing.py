"""start_processing implementation extracted from engine.py.

This module exists primarily to keep plugins.import.engine below the MONOLITH
gate limits.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.file_io.service.types import RootName

from .engine_util import _emit_required, _exception_envelope, _iso_utc_now
from .errors import FinalizeError, error_envelope, invariant_violation, validation_error
from .fingerprints import fingerprint_json
from .job_requests import build_job_requests, planned_units_count
from .serialization import canonical_serialize
from .storage import atomic_write_json, read_json

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def start_processing_impl(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    try:
        state = engine._load_state(session_id)
        if int(state.get("phase") or 1) == 2:
            return engine._start_processing_idempotent(session_id, state, body)
        if state.get("status") != "in_progress":
            raise FinalizeError("session is not active")

        if not isinstance(body, dict):
            raise ValueError("body must be an object")
        confirm = body.get("confirm")
        if confirm is not True:
            return validation_error(
                message="confirm must be true",
                path="$.confirm",
                reason="missing_or_false",
                meta={},
            )

        runtime_inputs = dict(state.get("inputs") or {})
        final = runtime_inputs.get("final_summary_confirm")
        if not (isinstance(final, dict) and final.get("confirm_start") is True):
            return validation_error(
                message="final_summary_confirm must be submitted with confirm=true",
                path="$.inputs.final_summary_confirm.confirm_start",
                reason="missing_or_false",
                meta={},
            )

        _emit_required(
            "finalize.request",
            "finalize.request",
            {
                "session_id": session_id,
                "mode": str(state.get("mode") or ""),
                "model_fingerprint": str(state.get("model_fingerprint") or ""),
                "discovery_fingerprint": str(
                    state.get("derived", {}).get("discovery_fingerprint") or ""
                ),
                "effective_config_fingerprint": str(
                    state.get("derived", {}).get("effective_config_fingerprint") or ""
                ),
                "conflict_fingerprint": str(
                    state.get("derived", {}).get("conflict_fingerprint") or ""
                ),
            },
        )

        # Conflict policy re-check.
        # Must be based on a fresh deterministic scan immediately before job creation.
        conflicts = state.get("conflicts")
        policy = str(conflicts.get("policy") or "ask") if isinstance(conflicts, dict) else "ask"
        preview_fp = str(state.get("derived", {}).get("conflict_fingerprint") or "")
        current_conflicts = engine._scan_conflicts(session_id, state)
        current_fp = fingerprint_json(current_conflicts)

        resolved = engine._resolve_flag_for_scan(
            state=state,
            policy=policy,
            current_fp=current_fp,
            current_conflicts=current_conflicts,
        )

        # Persist current conflicts to session state (UI must see the latest scan).
        state.setdefault("derived", {})["conflict_fingerprint"] = current_fp
        state["conflicts"] = {
            "present": bool(current_conflicts),
            "items": current_conflicts,
            "resolved": resolved,
            "policy": str((state.get("conflicts") or {}).get("policy") or "ask"),
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(
            engine._fs,
            RootName.WIZARDS,
            f"{session_dir}/conflicts.json",
            current_conflicts,
        )
        state["updated_at"] = _iso_utc_now()
        engine._persist_state(session_id, state)

        if policy == "ask" and current_conflicts and not resolved:
            return error_envelope(
                "CONFLICTS_UNRESOLVED",
                "conflicts must be resolved before processing",
                details=[
                    {
                        "path": "$.conflicts",
                        "reason": "conflicts_unresolved",
                        "meta": {"policy": policy},
                    }
                ],
            )

        if policy != "ask" and preview_fp and current_fp != preview_fp:
            return invariant_violation(
                message="conflict scan changed since preview",
                path="$.conflicts",
                reason="conflicts_changed",
                meta={"preview": preview_fp, "current": current_fp},
            )

        # Ensure plan exists.
        plan_path = f"{session_dir}/plan.json"
        if engine._fs.exists(RootName.WIZARDS, plan_path):
            plan = read_json(engine._fs, RootName.WIZARDS, plan_path)
        else:
            plan = engine.compute_plan(session_id)

        src = state.get("source") or {}
        src_root = str(src.get("root") or "")
        src_rel = str(src.get("relative_path") or "")
        diagnostics_context = {
            "model_fingerprint": str(state.get("model_fingerprint") or ""),
            "discovery_fingerprint": str(
                state.get("derived", {}).get("discovery_fingerprint") or ""
            ),
            "effective_config_fingerprint": str(
                state.get("derived", {}).get("effective_config_fingerprint") or ""
            ),
            "conflict_fingerprint": str(state.get("derived", {}).get("conflict_fingerprint") or ""),
        }

        policy_inputs = dict(state.get("answers") or {})
        job_requests = build_job_requests(
            session_id=session_id,
            root=src_root,
            relative_path=src_rel,
            mode=str(state.get("mode") or ""),
            diagnostics_context=diagnostics_context,
            config_fingerprint=str(
                state.get("derived", {}).get("effective_config_fingerprint") or ""
            ),
            plan=plan,
            inputs=policy_inputs,
        )

        job_path = f"{session_dir}/job_requests.json"
        job_bytes = canonical_serialize(job_requests)

        # Test seam: unit tests monkeypatch plugins.import.engine.atomic_write_text.
        # Keep the call routed via the engine module, not a direct import.
        from . import engine as eng_mod

        eng_mod.atomic_write_text(
            engine._fs,
            RootName.WIZARDS,
            job_path,
            job_bytes.decode("utf-8"),
        )

        job_any = read_json(engine._fs, RootName.WIZARDS, job_path)
        if not isinstance(job_any, dict):
            raise FinalizeError("job_requests.json is invalid")
        idem_key = str(job_any.get("idempotency_key") or "")
        if not idem_key:
            raise FinalizeError("job_requests.json missing idempotency_key")

        engine._enter_phase_2(session_id, state)
        state = engine._load_state(session_id)

        job_id = engine._get_or_create_job(session_id, state, idem_key)

        _emit_required(
            "job.create",
            "job.create",
            {
                "session_id": session_id,
                "job_id": job_id,
                "idempotency_key": idem_key,
                "mode": str(state.get("mode") or ""),
                "model_fingerprint": str(state.get("model_fingerprint") or ""),
                "discovery_fingerprint": str(
                    state.get("derived", {}).get("discovery_fingerprint") or ""
                ),
                "effective_config_fingerprint": str(
                    state.get("derived", {}).get("effective_config_fingerprint") or ""
                ),
                "conflict_fingerprint": str(
                    state.get("derived", {}).get("conflict_fingerprint") or ""
                ),
            },
        )

        return {"job_ids": [job_id], "batch_size": planned_units_count(plan)}
    except Exception as e:
        return _exception_envelope(e)
