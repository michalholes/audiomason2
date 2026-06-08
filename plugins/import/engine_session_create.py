"""Session creation implementation extracted from engine.py.

This module exists primarily to keep plugins.import.engine below the MONOLITH
gate limits.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard, cast

from plugins.file_io.service.types import RootName

from . import discovery as discovery_mod
from .action_jobs import extract_action_job_requests
from .defaults import ensure_default_models
from .detached_runtime import build_detached_runtime_bootstrap
from .dsl.interpreter_v3 import run_automatic_steps
from .engine_actions_v3 import build_runtime_flow_model, initialize_state
from .engine_session_guards import validate_root_and_path
from .engine_util import (
    derive_selection_items,
    emit_required_event,
    ensure_session_state_fields,
    exception_envelope,
    inject_selection_items,
    iso_utc_now,
    sync_session_cursor,
)
from .errors import FinalizeError
from .fingerprints import fingerprint_json, sha256_hex
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


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list_if_valid(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    values = cast(list[object], value)
    items = [item for item in values if isinstance(item, str)]
    if len(items) != len(values):
        return None
    return items


def _sync_legacy_selection_from_phase1(state: dict[str, object]) -> None:
    vars_state = _as_str_object_dict(state.get("vars"))
    phase1_state = _as_str_object_dict(vars_state.get("phase1"))

    select_authors = _as_str_object_dict(phase1_state.get("select_authors"))
    selected_author_ids = _as_str_list_if_valid(select_authors.get("selected_ids"))
    if selected_author_ids is not None:
        state["selected_author_ids"] = selected_author_ids

    select_books = _as_str_object_dict(phase1_state.get("select_books"))
    selected_book_ids = _as_str_list_if_valid(select_books.get("selected_ids"))
    if selected_book_ids is not None:
        state["selected_book_ids"] = selected_book_ids


def _build_phase1_runtime_seed(discovery: list[dict[str, object]]) -> dict[str, object]:
    discovery_items = [dict(item) for item in discovery if _is_str_object_dict(item)]
    cover_item_modes = ["skip", "file", "embedded", "url"]

    return {
        "discovery_items": discovery_items,
        "authors": [],
        "books": [],
        "books_by_author": {},
        "select_authors": {
            "ordered_ids": [],
            "selected_ids": [],
            "selected_author_label_list": [],
            "selection_expr": "all",
            "autofill_if": False,
        },
        "select_books": {
            "ordered_ids": [],
            "filtered_ids": [],
            "selected_ids": [],
            "selected_book_label_list": [],
            "selected_source_relative_paths": [],
            "selection_expr": "all",
            "autofill_if": False,
        },
        "cover": {
            "item_modes": list(cover_item_modes),
            "per_source_allowed_modes": [],
            "per_source_hints": [],
        },
        "runtime": {},
    }


_V3_BOOTSTRAP_STEP_ID = "phase1_bootstrap"


def _has_step(effective_model: dict[str, object], *, step_id: str) -> bool:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return False
    steps = cast(list[object], steps_any)
    for step_any in steps:
        step = _as_str_object_dict(step_any)
        if str(step.get("step_id") or "") == step_id:
            return True
    return False


@dataclass(frozen=True)
class SessionStartContext:
    root: str
    relative_path: str
    mode: str
    wizard_definition: dict[str, object]
    effective_model: dict[str, object]
    discovery: list[dict[str, object]]
    model_fingerprint: str
    discovery_fingerprint: str
    effective_config: dict[str, object]
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
    flow_overrides: dict[str, object] | None,
) -> SessionStartContext:
    v = validate_root_and_path(root, relative_path)
    if isinstance(v, dict):
        raise ValueError(str(v.get("error") or "invalid root/path"))
    root, relative_path = v

    mode = engine.validate_mode(mode)

    fs = engine.get_file_service()
    ensure_default_models(fs)
    flow_cfg = read_json(fs, RootName.WIZARDS, "import/config/flow_config.json")
    flow_cfg_norm = engine.normalize_flow_config(flow_cfg)
    if flow_overrides is not None:
        flow_cfg_norm = engine.merge_flow_config_overrides(flow_cfg_norm, flow_overrides)

    wizard_definition = load_or_bootstrap_wizard_definition(
        fs,
        bootstrap_default_version=_preferred_bootstrap_default_version(engine=engine),
    )
    version_any = wizard_definition.get("version")
    version = version_any if isinstance(version_any, int) else 0
    if version == 3:
        effective_model = build_runtime_flow_model(wizard_definition=wizard_definition)
    else:
        effective_model = build_legacy_runtime_flow_model_from_definition(
            wizard_definition=wizard_definition,
            flow_config=flow_cfg_norm,
        )

    discovery = discovery_mod.run_discovery(fs, root=root, relative_path=relative_path)
    discovery_fingerprint = fingerprint_json(discovery)

    if effective_model.get("flowmodel_kind") != "dsl_step_graph_v3":
        authors_items, books_items = derive_selection_items(discovery)
        effective_model = inject_selection_items(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )

    model_fingerprint = fingerprint_json(effective_model)

    diagnostics_enabled = engine.resolve_bool("diagnostics.enabled", default=False)

    effective_config: dict[str, object] = {
        "version": 1,
        "flow_config": flow_cfg_norm,
        "diagnostics_enabled": diagnostics_enabled,
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
    flow_overrides: dict[str, object] | None,
) -> SessionStartContext | dict[str, object]:
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
        return exception_envelope(e)


def resolve_session_start_conflict(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, object] | None,
) -> SessionStartConflict | None:
    ctx = _build_session_start_context(
        engine=engine,
        root=root,
        relative_path=relative_path,
        mode=mode,
        flow_overrides=flow_overrides,
    )
    state_path = f"import/sessions/{ctx.session_id}/state.json"
    if not engine.file_exists(RootName.WIZARDS, state_path):
        return None
    return SessionStartConflict(
        root=ctx.root,
        relative_path=ctx.relative_path,
        mode=ctx.mode,
        session_id=ctx.session_id,
    )


def _session_diag(ctx: SessionStartContext) -> dict[str, object]:
    return {
        "session_id": ctx.session_id,
        "model_fingerprint": ctx.model_fingerprint,
        "discovery_fingerprint": ctx.discovery_fingerprint,
        "effective_config_fingerprint": ctx.effective_config_fingerprint,
    }


def _runtime_vars(*, engine: ImportWizardEngine) -> dict[str, object]:
    return {
        "runtime": {
            "detached_runtime": build_detached_runtime_bootstrap(fs=engine.get_file_service()),
        }
    }


def emit_session_start_diagnostics(*, ctx: SessionStartContext) -> None:
    diag = _session_diag(ctx)
    emit_required_event(
        "model.load",
        "model.load",
        {
            **diag,
            "root": ctx.root,
            "relative_path": ctx.relative_path,
            "mode": ctx.mode,
        },
    )
    emit_required_event(
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
) -> dict[str, object]:
    session_dir = f"import/sessions/{ctx.session_id}"
    state_path = f"{session_dir}/state.json"
    fs = engine.get_file_service()
    loaded_state_any = read_json(fs, RootName.WIZARDS, state_path)
    loaded_state = _as_str_object_dict(loaded_state_any)
    if not loaded_state:
        raise FinalizeError("session state must be an object")

    derived = _as_str_object_dict(loaded_state.get("derived"))
    emit_required_event(
        "session.resume",
        "session.resume",
        {
            "session_id": ctx.session_id,
            "model_fingerprint": loaded_state.get("model_fingerprint"),
            "discovery_fingerprint": derived.get("discovery_fingerprint"),
            "effective_config_fingerprint": derived.get("effective_config_fingerprint"),
        },
    )
    loaded_state = ensure_session_state_fields(loaded_state)
    runtime_fp = engine.runtime_effective_model_fingerprint(ctx.session_id)
    if runtime_fp and loaded_state.get("model_fingerprint") != runtime_fp:
        loaded_state["model_fingerprint"] = runtime_fp
    _sync_legacy_selection_from_phase1(loaded_state)
    return loaded_state


def create_new_session_from_context(
    *,
    engine: ImportWizardEngine,
    ctx: SessionStartContext,
) -> dict[str, object]:
    session_dir = f"import/sessions/{ctx.session_id}"
    state_path = f"{session_dir}/state.json"

    emit_required_event(
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

    fs = engine.get_file_service()
    atomic_write_json(
        fs, RootName.WIZARDS, f"{session_dir}/effective_model.json", ctx.effective_model
    )
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_workflow.json",
        ctx.wizard_definition,
    )
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_config.json",
        ctx.effective_config,
    )
    atomic_write_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json", ctx.discovery)

    action_jobs = extract_action_job_requests(ctx.effective_model)
    if action_jobs is not None:
        atomic_write_json(
            fs,
            RootName.WIZARDS,
            f"{session_dir}/action_jobs.json",
            action_jobs,
        )

    atomic_write_text(
        fs,
        RootName.WIZARDS,
        f"{session_dir}/discovery_fingerprint.txt",
        ctx.discovery_fingerprint + "\n",
    )
    atomic_write_text(
        fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_config_fingerprint.txt",
        ctx.effective_config_fingerprint + "\n",
    )

    created_at = iso_utc_now()
    steps_any = ctx.effective_model.get("steps")
    if not isinstance(steps_any, list) or not steps_any:
        raise FinalizeError("effective_model must contain at least one step")
    steps = cast(list[object], steps_any)
    first = _as_str_object_dict(steps[0])
    start_step_id = str(first.get("step_id") or "")
    if not start_step_id:
        raise FinalizeError("effective_model first step must have step_id")

    state: dict[str, object] = {
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

    if ctx.effective_model.get("flowmodel_kind") == "dsl_step_graph_v3":
        vars_state = _as_str_object_dict(state.get("vars"))
        vars_state.setdefault("author_loop", {"index": 0, "confirmed": {}})
        vars_state.setdefault("title_loop", {"index": 0, "confirmed": {}})
        vars_state.setdefault("cover_loop", {"index": 0, "confirmed": {}})
        vars_state["phase1"] = _build_phase1_runtime_seed(ctx.discovery)
        state["vars"] = vars_state
        if _has_step(ctx.effective_model, step_id=_V3_BOOTSTRAP_STEP_ID):
            state["current_step_id"] = _V3_BOOTSTRAP_STEP_ID
            sync_session_cursor(state, step_id=_V3_BOOTSTRAP_STEP_ID)
            state = run_automatic_steps(
                effective_model=ctx.effective_model,
                state=state,
                session_id=ctx.session_id,
            )
        else:
            state = initialize_state(
                state=state,
                effective_model=ctx.effective_model,
                session_id=ctx.session_id,
            )
    _sync_legacy_selection_from_phase1(state)
    atomic_write_json(fs, RootName.WIZARDS, state_path, state)
    engine.append_decision(
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
    flow_overrides: dict[str, object] | None,
) -> dict[str, object]:
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
    if engine.file_exists(RootName.WIZARDS, state_path):
        return resume_session_from_context(engine=engine, ctx=ctx)
    return create_new_session_from_context(engine=engine, ctx=ctx)
