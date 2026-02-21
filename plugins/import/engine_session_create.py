"""Session creation implementation extracted from engine.py.

This module exists primarily to keep plugins.import.engine below the MONOLITH
gate limits.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.file_io.service.types import RootName

from . import discovery as discovery_mod
from .action_jobs import extract_action_job_requests
from .defaults import ensure_default_models
from .engine_session_guards import validate_root_and_path
from .engine_util import (
    _derive_selection_items,
    _emit_required,
    _ensure_session_state_fields,
    _inject_selection_items,
    _iso_utc_now,
)
from .errors import FinalizeError
from .fingerprints import fingerprint_json, sha256_hex
from .flow_runtime import build_flow_model
from .models import CatalogModel, FlowModel, validate_models
from .storage import (
    atomic_write_json,
    atomic_write_text,
    read_json,
)
from .wizard_definition_model import (
    build_effective_workflow_snapshot,
    load_or_bootstrap_wizard_definition,
)

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def create_session_impl(
    *,
    engine: ImportWizardEngine,
    root: str,
    relative_path: str,
    mode: str,
    flow_overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    v = validate_root_and_path(root, relative_path)
    if isinstance(v, dict):
        return v
    root, relative_path = v

    mode = engine._validate_mode(mode)

    # 1) Load models
    ensure_default_models(engine._fs)
    catalog_dict = read_json(engine._fs, RootName.WIZARDS, "import/catalog/catalog.json")
    flow_dict = read_json(engine._fs, RootName.WIZARDS, "import/flow/current.json")
    flow_cfg = read_json(engine._fs, RootName.WIZARDS, "import/config/flow_config.json")

    flow_cfg_norm = engine._normalize_flow_config(flow_cfg)
    if flow_overrides is not None:
        # Legacy testing hook only. Overrides may only toggle optional steps.
        flow_cfg_norm = engine._merge_flow_config_overrides(flow_cfg_norm, flow_overrides)

    catalog = CatalogModel.from_dict(catalog_dict)
    flow = FlowModel.from_dict(flow_dict)
    validate_models(catalog, flow)

    wizard_definition = load_or_bootstrap_wizard_definition(engine._fs)
    step_order = build_effective_workflow_snapshot(
        wizard_definition=wizard_definition,
        flow_config=flow_cfg_norm,
    )

    effective_model = build_flow_model(
        catalog=catalog,
        flow_config=flow_cfg_norm,
        step_order=step_order,
    )

    # 2) Discovery
    discovery = discovery_mod.run_discovery(engine._fs, root=root, relative_path=relative_path)
    discovery_fingerprint = fingerprint_json(discovery)

    authors_items, books_items = _derive_selection_items(discovery)
    effective_model = _inject_selection_items(
        effective_model=effective_model,
        authors_items=authors_items,
        books_items=books_items,
    )

    model_fingerprint = fingerprint_json(effective_model)

    # 3) Effective config snapshot (only keys engine uses)
    effective_config: dict[str, Any] = {
        "version": 1,
        "flow_config": flow_cfg_norm,
        "diagnostics_enabled": bool(engine._resolver.resolve("diagnostics.enabled")[0])
        if engine._has_key("diagnostics.enabled")
        else False,
    }
    effective_config_fingerprint = fingerprint_json(effective_config)

    # 4) Deterministic session_id
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

    diag = {
        "session_id": session_id,
        "model_fingerprint": model_fingerprint,
        "discovery_fingerprint": discovery_fingerprint,
        "effective_config_fingerprint": effective_config_fingerprint,
    }
    _emit_required(
        "model.load",
        "model.load",
        {**diag, "root": root, "relative_path": relative_path, "mode": mode},
    )
    _emit_required(
        "model.validate",
        "model.validate",
        {**diag, "root": root, "relative_path": relative_path, "mode": mode},
    )

    session_dir = f"import/sessions/{session_id}"
    state_path = f"{session_dir}/state.json"

    if engine._fs.exists(RootName.WIZARDS, state_path):
        loaded_state = read_json(engine._fs, RootName.WIZARDS, state_path)
        _emit_required(
            "session.resume",
            "session.resume",
            {
                "session_id": session_id,
                "model_fingerprint": loaded_state.get("model_fingerprint"),
                "discovery_fingerprint": loaded_state.get("derived", {}).get(
                    "discovery_fingerprint"
                ),
                "effective_config_fingerprint": loaded_state.get("derived", {}).get(
                    "effective_config_fingerprint"
                ),
            },
        )
        loaded_state = _ensure_session_state_fields(loaded_state)

        # Snapshot artifacts are immutable (spec 10.9). Resume MUST NOT modify them.
        # However, state.json is allowed to track the runtime-effective model fingerprint
        # (selection items reinjected from discovery.json), even if an older snapshot
        # on disk is missing those items.
        runtime_fp = engine._runtime_effective_model_fingerprint(session_id)
        if runtime_fp and loaded_state.get("model_fingerprint") != runtime_fp:
            loaded_state["model_fingerprint"] = runtime_fp
        engine._persist_state(session_id, loaded_state)
        return loaded_state

    # 5) Persist frozen artifacts
    _emit_required(
        "session.start",
        "session.start",
        {
            "session_id": session_id,
            "root": root,
            "relative_path": relative_path,
            "mode": mode,
            "model_fingerprint": model_fingerprint,
            "discovery_fingerprint": discovery_fingerprint,
            "effective_config_fingerprint": effective_config_fingerprint,
        },
    )

    atomic_write_json(
        engine._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json", effective_model
    )
    atomic_write_json(
        engine._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json", effective_config
    )
    atomic_write_json(engine._fs, RootName.WIZARDS, f"{session_dir}/discovery.json", discovery)

    action_jobs = extract_action_job_requests(effective_model)
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
        discovery_fingerprint + "\n",
    )
    atomic_write_text(
        engine._fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_config_fingerprint.txt",
        effective_config_fingerprint + "\n",
    )

    created_at = _iso_utc_now()

    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list) or not steps_any:
        raise FinalizeError("effective_model must contain at least one step")
    first = steps_any[0] if isinstance(steps_any[0], dict) else {}
    start_step_id = str(first.get("step_id") or "")
    if not start_step_id:
        raise FinalizeError("effective_model first step must have step_id")

    state: dict[str, Any] = {
        "session_id": session_id,
        "created_at": created_at,
        "updated_at": created_at,
        "model_fingerprint": model_fingerprint,
        "phase": 1,
        "mode": mode,
        "source": {"root": root, "relative_path": relative_path},
        "current_step_id": start_step_id,
        "completed_step_ids": [],
        "answers": {},
        "inputs": {},
        "computed": {},
        "selected_author_ids": [],
        "selected_book_ids": [],
        "effective_author_title": {},
        "derived": {
            "discovery_fingerprint": discovery_fingerprint,
            "effective_config_fingerprint": effective_config_fingerprint,
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

    atomic_write_json(engine._fs, RootName.WIZARDS, state_path, state)
    engine._append_decision(
        session_id,
        step_id="__system__",
        payload={"event": "session.created", "root": root, "relative_path": relative_path},
        result="accepted",
        error=None,
    )

    return state
