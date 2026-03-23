"""start_processing implementation extracted from engine.py.

This module exists primarily to keep plugins.import.engine below the MONOLITH
gate limits.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service.types import RootName

from . import engine_diagnostics_required as diagnostics_required
from .detached_runtime import build_detached_runtime_bootstrap
from .engine_util import _emit_required, _exception_envelope, _iso_utc_now
from .errors import FinalizeError, error_envelope, invariant_violation, validation_error
from .fingerprints import fingerprint_json
from .job_requests import build_job_requests, planned_units_count
from .phase1_source_intake import build_phase1_projection, phase1_session_authority_applies
from .serialization import canonical_serialize
from .storage import atomic_write_json, read_json

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


_PHASE2_AUDIO_SUFFIXES = {".m4a", ".m4b", ".mp3", ".opus"}


def _iter_phase2_audio_sources(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in _PHASE2_AUDIO_SUFFIXES else []
    return [
        path
        for path in sorted(source_path.rglob("*"))
        if path.is_file() and path.suffix.lower() in _PHASE2_AUDIO_SUFFIXES
    ]


def _phase2_explicit_outputs_for_source(source_path: Path) -> list[str]:
    outputs: list[str] = []
    for source_file in _iter_phase2_audio_sources(source_path):
        relative_parent = (
            source_file.relative_to(source_path).parent if source_path.is_dir() else Path()
        )
        output_name = (
            source_file.name if source_file.suffix.lower() == ".mp3" else f"{source_file.stem}.mp3"
        )
        rel_path = normalize_relative_path(str(relative_parent / output_name))
        if rel_path:
            outputs.append(rel_path)
    return outputs


def _phase2_rename_by_book(
    *,
    engine: ImportWizardEngine,
    state: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fs = engine.get_file_service()
    state_source_any = state.get("source")
    state_source = dict(state_source_any) if isinstance(state_source_any, dict) else {}
    plan_source_any = plan.get("source")
    plan_source = dict(plan_source_any) if isinstance(plan_source_any, dict) else {}

    source_root_text = str(
        state_source.get("root") or state.get("root") or plan_source.get("root") or ""
    ).strip()
    if not source_root_text:
        raise FinalizeError(
            "phase2 source root is missing; "
            "expected state.source.root, state.root, or plan.source.root"
        )
    source_root = RootName(source_root_text)
    source_base_rel = normalize_relative_path(
        str(
            state_source.get("relative_path")
            or state.get("relative_path")
            or plan_source.get("relative_path")
            or ""
        )
    )

    phase1_any = (state.get("vars") or {}).get("phase1")
    phase1 = dict(phase1_any) if isinstance(phase1_any, dict) else {}
    book_meta_any = phase1.get("book_meta")
    book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}

    selected_any = plan.get("selected_books")
    selected = selected_any if isinstance(selected_any, list) else []

    rename_by_book: dict[str, dict[str, Any]] = {}
    for item in selected:
        if not isinstance(item, dict):
            continue
        book_id = str(item.get("book_id") or "")
        source_rel = normalize_relative_path(str(item.get("source_relative_path") or ""))
        if not book_id:
            continue
        scoped_source_value = (
            f"{source_base_rel}/{source_rel}"
            if source_base_rel and source_rel
            else source_base_rel or source_rel
        )
        scoped_source_rel = normalize_relative_path(scoped_source_value)
        source_path = fs.resolve_abs_path(source_root, scoped_source_rel)
        outputs = _phase2_explicit_outputs_for_source(source_path)
        if not outputs:
            authority_any = book_meta.get(book_id)
            authority = dict(authority_any) if isinstance(authority_any, dict) else {}
            author_label = str(authority.get("author_label") or "").strip()
            book_label = str(authority.get("book_label") or "").strip()
            if not author_label or not book_label:
                label_source = (
                    normalize_relative_path(str(item.get("proposed_target_relative_path") or ""))
                    or source_rel
                )
                label_parts = [part for part in label_source.split("/") if part]
                if len(label_parts) >= 2:
                    author_label = author_label or label_parts[-2]
                    book_label = book_label or label_parts[-1]
                elif len(label_parts) == 1:
                    author_label = author_label or label_parts[0]
                    book_label = book_label or label_parts[0]
            if not author_label or not book_label:
                raise FinalizeError(
                    f"phase2 rename authority missing for {book_id}; expected "
                    "scanned audio outputs, phase1 book_meta labels, or plan path labels"
                )
            fallback_rel = normalize_relative_path(f"{author_label} - {book_label}.mp3")
            outputs = [fallback_rel] if fallback_rel else []
        if outputs:
            rename_by_book[book_id] = {
                "mode": "explicit_relative_paths",
                "outputs": outputs,
            }
    return rename_by_book


def _validate_start_processing_body(body: dict[str, Any]) -> dict[str, Any] | None:
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
    return None


def _merge_session_job_state(
    *,
    state: dict[str, Any],
    job_id: str,
    mark_submitted: bool,
) -> dict[str, Any]:
    jobs_any = state.get("jobs")
    jobs = dict(jobs_any) if isinstance(jobs_any, dict) else {}

    emitted_any = jobs.get("emitted")
    emitted = list(emitted_any) if isinstance(emitted_any, list) else []
    if job_id not in emitted:
        emitted.append(job_id)

    submitted_any = jobs.get("submitted")
    submitted = list(submitted_any) if isinstance(submitted_any, list) else []
    if mark_submitted and job_id not in submitted:
        submitted.append(job_id)

    jobs["emitted"] = emitted
    jobs["submitted"] = submitted
    state["jobs"] = jobs
    state["updated_at"] = _iso_utc_now()
    return state


def _record_session_job_state(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    state: dict[str, Any],
    job_id: str,
    mark_submitted: bool,
    reload_state: bool = False,
) -> dict[str, Any]:
    latest_state = state
    if reload_state:
        latest_state = engine._load_state(session_id)
    latest_state = _merge_session_job_state(
        state=latest_state,
        job_id=job_id,
        mark_submitted=mark_submitted,
    )
    engine._persist_state(session_id, latest_state)
    return latest_state


def _build_start_processing_result(
    *,
    state: dict[str, Any],
    job_id: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    result = {"job_ids": [job_id], "batch_size": planned_units_count(plan)}
    finalize_any = (state.get("computed") or {}).get("finalize")
    if isinstance(finalize_any, dict):
        result["finalize"] = dict(finalize_any)
    return result


def _load_job_requests_idempotent(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    state: dict[str, Any],
    body: dict[str, Any],
) -> dict[str, Any]:
    validation = _validate_start_processing_body(body)
    if validation is not None:
        return validation

    session_dir = f"import/sessions/{session_id}"
    job_path = f"{session_dir}/job_requests.json"
    if not engine._fs.exists(RootName.WIZARDS, job_path):
        raise FinalizeError("job_requests.json is missing")

    job_requests_any = read_json(engine._fs, RootName.WIZARDS, job_path)
    if not isinstance(job_requests_any, dict):
        raise FinalizeError("job_requests.json is invalid")
    idem_key = str(job_requests_any.get("idempotency_key") or "")
    if not idem_key:
        raise FinalizeError("job_requests.json missing idempotency_key")

    job_id = engine._get_or_create_job(session_id, state, idem_key)
    state = _record_session_job_state(
        engine=engine,
        session_id=session_id,
        state=state,
        job_id=job_id,
        mark_submitted=False,
    )

    jobs_any = state.get("jobs")
    jobs = jobs_any if isinstance(jobs_any, dict) else {}
    submitted_any = jobs.get("submitted")
    submitted = submitted_any if isinstance(submitted_any, list) else []
    if job_id not in submitted:
        try:
            diagnostics_required.submit_process_job(engine=engine, job_id=job_id, verbosity=1)
        except Exception as e:
            return _exception_envelope(e)
        state = _record_session_job_state(
            engine=engine,
            session_id=session_id,
            state=state,
            job_id=job_id,
            mark_submitted=True,
            reload_state=True,
        )

    plan_path = f"{session_dir}/plan.json"
    plan_any = (
        read_json(engine._fs, RootName.WIZARDS, plan_path)
        if engine._fs.exists(RootName.WIZARDS, plan_path)
        else {}
    )
    plan = plan_any if isinstance(plan_any, dict) else {}
    return _build_start_processing_result(state=state, job_id=job_id, plan=plan)


def start_processing_impl(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    try:
        state = engine._load_state(session_id)
        phase = int(state.get("phase") or 1)
        session_dir = f"import/sessions/{session_id}"
        job_path = f"{session_dir}/job_requests.json"
        if phase == 2 and engine._fs.exists(RootName.WIZARDS, job_path):
            return _load_job_requests_idempotent(
                engine=engine,
                session_id=session_id,
                state=state,
                body=body,
            )
        if state.get("status") != "in_progress":
            raise FinalizeError("session is not active")

        validation = _validate_start_processing_body(body)
        if validation is not None:
            return validation

        effective_model = engine._load_effective_model(session_id)
        if phase1_session_authority_applies(effective_model=effective_model):
            session_dir = f"import/sessions/{session_id}"
            discovery_any = read_json(engine._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            if isinstance(discovery_any, list) and all(
                isinstance(item, dict) for item in discovery_any
            ):
                state.setdefault("vars", {})["phase1"] = build_phase1_projection(
                    discovery=discovery_any,
                    state=state,
                )
                engine._persist_state(session_id, state)
        phase1_any = state.get("vars", {}).get("phase1")
        phase1 = dict(phase1_any) if isinstance(phase1_any, dict) else {}
        runtime_any = phase1.get("runtime")
        runtime = dict(runtime_any) if isinstance(runtime_any, dict) else {}
        final = runtime.get("final_summary_confirm")
        if not (isinstance(final, dict) and final.get("confirm_start") is True):
            return validation_error(
                message="final_summary_confirm must be submitted with confirm=true",
                path="$.vars.phase1.runtime.final_summary_confirm.confirm_start",
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
        atomic_write_json(
            engine._fs,
            RootName.WIZARDS,
            f"{session_dir}/conflicts.json",
            current_conflicts,
        )
        state["updated_at"] = _iso_utc_now()
        engine._persist_state(session_id, state)

        if policy == "ask" and current_conflicts:
            step_order = engine._session_step_order(session_id)
            if "resolve_conflicts_batch" not in step_order:
                return invariant_violation(
                    message="resolve_conflicts_batch missing under ask policy",
                    path="$.workflow.steps",
                    reason="resolve_conflicts_batch_missing",
                    meta={"policy": policy},
                )

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
        phase1_with_rename = dict(phase1)
        phase1_with_rename["rename_by_book"] = _phase2_rename_by_book(
            engine=engine,
            state=state,
            plan=plan,
        )
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
            detached_runtime=build_detached_runtime_bootstrap(fs=engine.get_file_service()),
            session_authority=phase1_with_rename,
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
        state = _record_session_job_state(
            engine=engine,
            session_id=session_id,
            state=state,
            job_id=job_id,
            mark_submitted=False,
        )

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

        jobs_any = state.get("jobs")
        jobs = jobs_any if isinstance(jobs_any, dict) else {}
        submitted_any = jobs.get("submitted")
        submitted = submitted_any if isinstance(submitted_any, list) else []
        if job_id not in submitted:
            try:
                diagnostics_required.submit_process_job(engine=engine, job_id=job_id, verbosity=1)
            except Exception as e:
                return _exception_envelope(e)
            state = _record_session_job_state(
                engine=engine,
                session_id=session_id,
                state=state,
                job_id=job_id,
                mark_submitted=True,
                reload_state=True,
            )

        return _build_start_processing_result(state=state, job_id=job_id, plan=plan)
    except Exception as e:
        return _exception_envelope(e)
