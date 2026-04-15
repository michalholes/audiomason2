"""Session creation implementation extracted from engine.py.

This module exists primarily to keep plugins.import.engine below the MONOLITH
gate limits.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from plugins.file_io.service.types import RootName

from . import discovery as discovery_mod
from .action_jobs import extract_action_job_requests
from .defaults import ensure_default_models
from .detached_runtime import build_detached_runtime_bootstrap
from .engine_actions_v3 import build_runtime_flow_model, initialize_state
from .engine_session_guards import validate_root_and_path
from .engine_util import (
    _derive_selection_items,
    _emit_required,
    _ensure_session_state_fields,
    _exception_envelope,
    _inject_selection_items,
    _iso_utc_now,
)
from .errors import FinalizeError
from .fingerprints import fingerprint_json, sha256_hex
from .phase1_source_intake import build_phase1_projection, phase1_session_authority_applies
from .storage import (
    atomic_write_json,
    atomic_write_text,
    read_json,
)
from .wizard_definition_model import (
    build_legacy_runtime_flow_model_from_definition,
    load_or_bootstrap_wizard_definition,
)

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


@dataclass(frozen=True)
class SessionStartContext:
    root: str
    relative_path: str
    mode: str
    wizard_definition: dict[str, Any]
    effective_model: dict[str, Any]
    discovery: list[dict[str, Any]]
    model_fingerprint: str
    discovery_fingerprint: str
    effective_config: dict[str, Any]
    effective_config_fingerprint: str
    session_id: str


@dataclass(frozen=True)
class SessionStartConflict:
    root: str
    relative_path: str
    mode: str
    session_id: str


def _preferred_bootstrap_default_version(*, engine: ImportWizardEngine) -> int:
    del engine
    return 3


def _build_session_start_context(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, Any] | None,
) -> SessionStartContext:
    v = validate_root_and_path(root, relative_path)
    if isinstance(v, dict):
        raise ValueError(str(v.get("error") or "invalid root/path"))
    root, relative_path = v

    mode = engine._validate_mode(mode)

    ensure_default_models(engine._fs)
    flow_cfg = read_json(engine._fs, RootName.WIZARDS, "import/config/flow_config.json")
    flow_cfg_norm = engine._normalize_flow_config(flow_cfg)
    if flow_overrides is not None:
        flow_cfg_norm = engine._merge_flow_config_overrides(flow_cfg_norm, flow_overrides)

    wizard_definition = load_or_bootstrap_wizard_definition(
        engine._fs,
        bootstrap_default_version=_preferred_bootstrap_default_version(engine=engine),
    )
    if int(wizard_definition.get("version") or 0) == 3:
        effective_model = build_runtime_flow_model(wizard_definition=wizard_definition)
    else:
        effective_model = build_legacy_runtime_flow_model_from_definition(
            wizard_definition=wizard_definition,
            flow_config=flow_cfg_norm,
        )

    discovery = discovery_mod.run_discovery(engine._fs, root=root, relative_path=relative_path)
    discovery_fingerprint = fingerprint_json(discovery)

    authors_items, books_items = _derive_selection_items(discovery)
    if effective_model.get("flowmodel_kind") != "dsl_step_graph_v3":
        effective_model = _inject_selection_items(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )

    model_fingerprint = fingerprint_json(effective_model)

    effective_config: dict[str, Any] = {
        "version": 1,
        "flow_config": flow_cfg_norm,
        "diagnostics_enabled": bool(engine._resolver.resolve("diagnostics.enabled")[0])
        if engine._has_key("diagnostics.enabled")
        else False,
    }
    effective_config_fingerprint = fingerprint_json(effective_config)

    sid_src = "|".join(
        [
            f"root:{root}",
            f"path:{relative_path}",
            f"mode:{mode}",
            f"m:{model_fingerprint}",
            f"d:{discovery_fingerprint}",
            f"c:{effective_config_fingerprint}",
        ]
    )
    session_id = sha256_hex(sid_src.encode("utf-8"))[:16]
    return SessionStartContext(
        root=root,
        relative_path=relative_path,
        mode=mode,
        wizard_definition=wizard_definition,
        effective_model=effective_model,
        discovery=discovery,
        model_fingerprint=model_fingerprint,
        discovery_fingerprint=discovery_fingerprint,
        effective_config=effective_config,
        effective_config_fingerprint=effective_config_fingerprint,
        session_id=session_id,
    )


def resolve_session_start_context(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, Any] | None,
) -> SessionStartContext | dict[str, Any]:
    v = validate_root_and_path(root, relative_path)
    if isinstance(v, dict):
        return v
    try:
        return _build_session_start_context(
            engine=engine,
            root=root,
            relative_path=relative_path,
            mode=mode,
            flow_overrides=flow_overrides,
        )
    except Exception as e:
        return _exception_envelope(e)


def resolve_session_start_conflict(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, Any] | None,
) -> SessionStartConflict | None:
    ctx = _build_session_start_context(
        engine=engine,
        root=root,
        relative_path=relative_path,
        mode=mode,
        flow_overrides=flow_overrides,
    )
    state_path = f"import/sessions/{ctx.session_id}/state.json"
    if not engine._fs.exists(RootName.WIZARDS, state_path):
        return None
    return SessionStartConflict(
        root=ctx.root,
        relative_path=ctx.relative_path,
        mode=ctx.mode,
        session_id=ctx.session_id,
    )


def _session_diag(ctx: SessionStartContext) -> dict[str, Any]:
    return {
        "session_id": ctx.session_id,
        "model_fingerprint": ctx.model_fingerprint,
        "discovery_fingerprint": ctx.discovery_fingerprint,
        "effective_config_fingerprint": ctx.effective_config_fingerprint,
    }


def _runtime_vars(*, engine: ImportWizardEngine) -> dict[str, Any]:
    return {
        "runtime": {
            "detached_runtime": build_detached_runtime_bootstrap(fs=engine._fs),
        }
    }


def emit_session_start_diagnostics(*, ctx: SessionStartContext) -> None:
    diag = _session_diag(ctx)
    _emit_required(
        "model.load",
        "model.load",
        {
            **diag,
            "root": ctx.root,
            "relative_path": ctx.relative_path,
            "mode": ctx.mode,
        },
    )
    _emit_required(
        "model.validate",
        "model.validate",
        {
            **diag,
            "root": ctx.root,
            "relative_path": ctx.relative_path,
            "mode": ctx.mode,
        },
    )


def resume_session_from_context(
    *,
    engine: ImportWizardEngine,
    ctx: SessionStartContext,
) -> dict[str, Any]:
    session_dir = f"import/sessions/{ctx.session_id}"
    state_path = f"{session_dir}/state.json"
    loaded_state = read_json(engine._fs, RootName.WIZARDS, state_path)
    _emit_required(
        "session.resume",
        "session.resume",
        {
            "session_id": ctx.session_id,
            "model_fingerprint": loaded_state.get("model_fingerprint"),
            "discovery_fingerprint": loaded_state.get("derived", {}).get("discovery_fingerprint"),
            "effective_config_fingerprint": loaded_state.get("derived", {}).get(
                "effective_config_fingerprint"
            ),
        },
    )
    loaded_state = _ensure_session_state_fields(loaded_state)
    runtime_fp = engine._runtime_effective_model_fingerprint(ctx.session_id)
    if runtime_fp and loaded_state.get("model_fingerprint") != runtime_fp:
        loaded_state["model_fingerprint"] = runtime_fp
    if phase1_session_authority_applies(effective_model=ctx.effective_model):
        loaded_state.setdefault("vars", {})["phase1"] = build_phase1_projection(
            discovery=ctx.discovery,
            state=loaded_state,
            fs=engine._fs,
        )
    if ctx.effective_model.get("flowmodel_kind") == "dsl_step_graph_v3":
        from .engine_step_submit import _sync_v3_legacy_state

        loaded_state = _sync_v3_legacy_state(
            engine=engine,
            session_id=ctx.session_id,
            state=loaded_state,
        )
    engine._persist_state(ctx.session_id, loaded_state)
    return loaded_state


def create_new_session_from_context(
    *,
    engine: ImportWizardEngine,
    ctx: SessionStartContext,
) -> dict[str, Any]:
    session_dir = f"import/sessions/{ctx.session_id}"
    state_path = f"{session_dir}/state.json"

    _emit_required(
        "session.start",
        "session.start",
        {
            "session_id": ctx.session_id,
            "root": ctx.root,
            "relative_path": ctx.relative_path,
            "mode": ctx.mode,
            "model_fingerprint": ctx.model_fingerprint,
            "discovery_fingerprint": ctx.discovery_fingerprint,
            "effective_config_fingerprint": ctx.effective_config_fingerprint,
        },
    )

    atomic_write_json(
        engine._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json", ctx.effective_model
    )
    atomic_write_json(
        engine._fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_workflow.json",
        ctx.wizard_definition,
    )
    atomic_write_json(
        engine._fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_config.json",
        ctx.effective_config,
    )
    atomic_write_json(engine._fs, RootName.WIZARDS, f"{session_dir}/discovery.json", ctx.discovery)

    action_jobs = extract_action_job_requests(ctx.effective_model)
    if action_jobs is not None:
        atomic_write_json(
            engine._fs,
            RootName.WIZARDS,
            f"{session_dir}/action_jobs.json",
            action_jobs,
        )

    atomic_write_text(
        engine._fs,
        RootName.WIZARDS,
        f"{session_dir}/discovery_fingerprint.txt",
        ctx.discovery_fingerprint + "\n",
    )
    atomic_write_text(
        engine._fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_config_fingerprint.txt",
        ctx.effective_config_fingerprint + "\n",
    )

    created_at = _iso_utc_now()
    steps_any = ctx.effective_model.get("steps")
    if not isinstance(steps_any, list) or not steps_any:
        raise FinalizeError("effective_model must contain at least one step")
    first = steps_any[0] if isinstance(steps_any[0], dict) else {}
    start_step_id = str(first.get("step_id") or "")
    if not start_step_id:
        raise FinalizeError("effective_model first step must have step_id")

    state: dict[str, Any] = {
        "session_id": ctx.session_id,
        "session_state_version": 1,
        "created_at": created_at,
        "updated_at": created_at,
        "model_fingerprint": ctx.model_fingerprint,
        "phase": 1,
        "mode": ctx.mode,
        "source": {
            "root": ctx.root,
            "relative_path": ctx.relative_path,
        },
        "current_step_id": start_step_id,
        "cursor": {"step_id": start_step_id},
        "completed_step_ids": [],
        "answers": {},
        "vars": _runtime_vars(engine=engine),
        "jobs": {"emitted": [], "submitted": []},
        "trace": [],
        "inputs": {},
        "computed": {},
        "selected_author_ids": [],
        "selected_book_ids": [],
        "effective_author_title": {},
        "derived": {
            "discovery_fingerprint": ctx.discovery_fingerprint,
            "effective_config_fingerprint": ctx.effective_config_fingerprint,
            "conflict_fingerprint": "",
        },
        "conflicts": {
            "present": False,
            "items": [],
            "resolved": True,
            "policy": "ask",
        },
        "status": "in_progress",
        "errors": [],
    }

    if phase1_session_authority_applies(effective_model=ctx.effective_model):
        state["vars"] = {
            **_runtime_vars(engine=engine),
            "phase1": build_phase1_projection(
                discovery=ctx.discovery,
                state=state,
                fs=engine._fs,
            ),
        }
    if (
        isinstance(ctx.effective_model, dict)
        and ctx.effective_model.get("flowmodel_kind") == "dsl_step_graph_v3"
    ):
        from .engine_step_submit import _sync_v3_legacy_state

        state = initialize_state(
            state=state,
            effective_model=ctx.effective_model,
            session_id=ctx.session_id,
        )
        if phase1_session_authority_applies(effective_model=ctx.effective_model):
            state.setdefault("vars", {}).update(_runtime_vars(engine=engine))
            state.setdefault("vars", {})["phase1"] = build_phase1_projection(
                discovery=ctx.discovery,
                state=state,
                fs=engine._fs,
            )
        state = _sync_v3_legacy_state(
            engine=engine,
            session_id=ctx.session_id,
            state=state,
        )
    atomic_write_json(engine._fs, RootName.WIZARDS, state_path, state)
    engine._append_decision(
        ctx.session_id,
        step_id="__system__",
        payload={
            "event": "session.created",
            "root": ctx.root,
            "relative_path": ctx.relative_path,
        },
        result="accepted",
        error=None,
    )
    return state


def create_session_impl(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    ctx = resolve_session_start_context(
        engine=engine,
        root=root,
        relative_path=relative_path,
        mode=mode,
        flow_overrides=flow_overrides,
    )
    if isinstance(ctx, dict):
        return ctx

    emit_session_start_diagnostics(ctx=ctx)

    state_path = f"import/sessions/{ctx.session_id}/state.json"
    if engine._fs.exists(RootName.WIZARDS, state_path):
        return resume_session_from_context(engine=engine, ctx=ctx)
    return create_new_session_from_context(engine=engine, ctx=ctx)
