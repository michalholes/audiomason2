"""Import Wizard Engine (plugin: import).

Implements PHASE 0 discovery, model load/validate, session lifecycle, and
minimal plan/job request generation.

No UI is implemented here.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from audiomason.core.config import ConfigResolver
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from . import flow_config_api
from .defaults import ensure_default_models
from .detached_runtime import serialize_detached_runtime_bootstrap
from .engine_actions_v3 import apply_action_v3, build_runtime_flow_model, is_v3_effective_model
from .engine_diagnostics_required import create_process_job
from .engine_processing import start_processing_impl
from .engine_session_create import create_session_impl
from .engine_step_submit import submit_step_impl
from .engine_steps_api import get_step_definition_impl
from .engine_util import (
    derive_selection_items,
    emit_required_event,
    ensure_session_state_fields,
    exception_envelope,
    inject_selection_items,
    iso_utc_now,
    parse_selection_expr,
)
from .engine_validation_api import (
    validate_catalog_impl,
    validate_flow_config_impl,
    validate_flow_impl,
)
from .errors import (
    FinalizeError,
    SessionNotFoundError,
    StepSubmissionError,
    invariant_violation,
    validation_error,
)
from .field_schema_validation import validate_step_fields
from .fingerprints import fingerprint_json
from .flow_config_validation import normalize_flow_config
from .flow_graph import MAX_TRANSITION_HOPS, normalize_to_graph, select_next_step
from .flow_graph_state_view import build_flow_graph_state_view
from .flow_runtime import (
    build_flow_model,
)
from .job_requests import planned_units_count
from .models import CatalogModel, FlowModel, validate_models
from .plan import PlanSelectionError, compute_plan
from .preview import preview_action_impl
from .session_effective_model import load_effective_model_json
from .storage import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    read_json,
)
from .wizard_definition_model import (
    build_effective_workflow_snapshot,
    build_legacy_runtime_flow_model_from_definition,
    load_or_bootstrap_wizard_definition,
    validate_wizard_definition_structure,
)


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


# Test seam: unit tests monkeypatch plugins.import.engine.get_event_bus.
get_event_bus: object = None

__all__ = [
    "ImportWizardEngine",
    "atomic_write_text",
]


def _wizard_definition_known_step_ids(wizard_definition: dict[str, object]) -> set[str]:
    version_any = wizard_definition.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1

    if version == 1:
        steps_any = wizard_definition.get("steps")
        if not _is_object_list(steps_any):
            return set()
        return {
            str(step.get("step_id") or "")
            for step in steps_any
            if _is_str_object_dict(step) and isinstance(step.get("step_id"), str)
        }

    graph_any = wizard_definition.get("graph") if version == 2 else wizard_definition
    nodes_any = graph_any.get("nodes") if _is_str_object_dict(graph_any) else None
    if not _is_object_list(nodes_any):
        return set()
    return {
        str(node.get("step_id") or "")
        for node in nodes_any
        if _is_str_object_dict(node) and isinstance(node.get("step_id"), str)
    }


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: ConfigResolver) -> None:
        self._resolver = resolver
        self._fs = FileService.from_resolver(self._resolver)

    def get_file_service(self) -> FileService:
        """Return the file service used by this engine.

        This is a plugin-internal helper for CLI/editor tooling.
        """
        return self._fs

    def file_exists(self, root: RootName, relative_path: str) -> bool:
        return self._fs.exists(root, relative_path)

    def delete_path(self, root: RootName, relative_path: str, *, missing_ok: bool) -> None:
        self._fs.delete_path(root, relative_path, missing_ok=missing_ok)

    def has_key(self, key: str) -> bool:
        return self._has_key(key)

    def resolve_bool(self, key: str, *, default: bool = False) -> bool:
        try:
            value, _ = self._resolver.resolve(key)
            return bool(value)
        except Exception:
            return default

    def load_state(self, session_id: str) -> dict[str, object]:
        return self._load_state(session_id)

    def persist_state(self, session_id: str, state: dict[str, object]) -> None:
        self._persist_state(session_id, state)

    def load_effective_model(self, session_id: str) -> dict[str, object]:
        return self._load_effective_model(session_id)

    def append_decision(
        self,
        session_id: str,
        *,
        step_id: str,
        payload: dict[str, object],
        result: str,
        error: dict[str, object] | None,
    ) -> None:
        self._append_decision(
            session_id,
            step_id=step_id,
            payload=payload,
            result=result,
            error=error,
        )

    def validate_mode(self, mode: str) -> str:
        return self._validate_mode(mode)

    def normalize_flow_config(self, raw: object) -> dict[str, object]:
        return self._normalize_flow_config(raw)

    def merge_flow_config_overrides(
        self, base: dict[str, object], overrides: dict[str, object]
    ) -> dict[str, object]:
        return self._merge_flow_config_overrides(base, overrides)

    def load_effective_flow_config(self, session_id: str) -> dict[str, object]:
        return self._load_effective_flow_config(session_id)

    def runtime_effective_model_fingerprint(self, session_id: str) -> str:
        return self._runtime_effective_model_fingerprint(session_id)

    def get_or_create_job(self, session_id: str, state: dict[str, object], idem_key: str) -> str:
        return self._get_or_create_job(session_id, state, idem_key)

    def scan_conflicts(self, session_id: str, state: dict[str, object]) -> list[dict[str, object]]:
        return self._scan_conflicts(session_id, state)

    def resolve_flag_for_scan(
        self,
        *,
        state: dict[str, object],
        policy: str,
        current_fp: str,
        current_conflicts: list[dict[str, object]],
    ) -> bool:
        return self._resolve_flag_for_scan(
            state=state,
            policy=policy,
            current_fp=current_fp,
            current_conflicts=current_conflicts,
        )

    def session_step_order(self, session_id: str) -> list[str]:
        return self._session_step_order(session_id)

    def enter_phase_2(self, session_id: str, state: dict[str, object]) -> None:
        self._enter_phase_2(session_id, state)

    def next_step_after_submit(
        self,
        *,
        step_id: str,
        state: dict[str, object],
        flow_cfg_norm: dict[str, object],
    ) -> str:
        return self._next_step_after_submit(
            step_id=step_id,
            state=state,
            flow_cfg_norm=flow_cfg_norm,
        )

    def auto_advance_computed_steps(
        self,
        *,
        session_id: str,
        state: dict[str, object],
        next_step_id: str,
        flow_cfg_norm: dict[str, object],
    ) -> str:
        return self._auto_advance_computed_steps(
            session_id=session_id,
            state=state,
            next_step_id=next_step_id,
            flow_cfg_norm=flow_cfg_norm,
        )

    def validate_and_canonicalize_payload(
        self,
        *,
        step_id: str,
        schema: dict[str, object],
        payload: dict[str, object],
        state: dict[str, object],
    ) -> dict[str, object]:
        return self._validate_and_canonicalize_payload(
            step_id=step_id,
            schema=schema,
            payload=payload,
            state=state,
        )

    def get_flow_model(self) -> dict[str, object]:
        """Return FlowModel JSON for the current configuration (spec 10.5)."""
        ensure_default_models(self._fs)
        wizard_definition = load_or_bootstrap_wizard_definition(self._fs)
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")
        flow_cfg_norm = self._normalize_flow_config(flow_cfg)
        if _to_int_or_default(wizard_definition.get("version"), 0) == 3:
            return build_runtime_flow_model(wizard_definition=wizard_definition)
        return build_legacy_runtime_flow_model_from_definition(
            wizard_definition=wizard_definition,
            flow_config=flow_cfg_norm,
        )

    def create_session(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            return self._create_session_impl(
                root,
                relative_path,
                mode=mode,
                flow_overrides=flow_overrides,
            )
        except Exception as e:
            return exception_envelope(e)

    def _create_session_impl(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return create_session_impl(
            engine=self,
            root=root,
            relative_path=relative_path,
            mode=mode,
            flow_overrides=flow_overrides,
        )

    def validate_catalog(self, catalog_json: object) -> dict[str, object]:
        return validate_catalog_impl(engine=self, catalog_json=catalog_json)

    def validate_flow(self, flow_json: object, catalog_json: object) -> dict[str, object]:
        return validate_flow_impl(engine=self, flow_json=flow_json, catalog_json=catalog_json)

    def validate_flow_config(self, flow_config_json: object) -> dict[str, object]:
        return validate_flow_config_impl(engine=self, flow_config_json=flow_config_json)

    def get_flow_config(self) -> dict[str, object]:
        return flow_config_api.get_flow_config(self)

    def set_flow_config(self, flow_config_json: object) -> dict[str, object]:
        return flow_config_api.set_flow_config(self, flow_config_json)

    def reset_flow_config(self) -> dict[str, object]:
        return flow_config_api.reset_flow_config(self)

    def preview_effective_model(self, catalog_json: object, flow_json: object) -> dict[str, object]:
        """Return the effective model that would be frozen for new sessions."""
        if not _is_str_object_dict(catalog_json):
            raise ValueError("catalog_json must be an object")
        if not _is_str_object_dict(flow_json):
            raise ValueError("flow_json must be an object")
        catalog = CatalogModel.from_dict(catalog_json)
        flow = FlowModel.from_dict(flow_json)
        validate_models(catalog, flow)
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")
        flow_cfg_norm = self._normalize_flow_config(flow_cfg)
        wizard_definition = load_or_bootstrap_wizard_definition(self._fs)
        step_order = build_effective_workflow_snapshot(
            wizard_definition=wizard_definition,
            flow_config=flow_cfg_norm,
        )
        return build_flow_model(
            catalog=catalog,
            flow_config=flow_cfg_norm,
            step_order=step_order,
        )

    def _has_key(self, key: str) -> bool:
        try:
            self._resolver.resolve(key)
            return True
        except Exception:
            return False

    def get_state(self, session_id: str) -> dict[str, object]:
        try:
            state = self._load_state(session_id)
            out = dict(state)
            out["effective_model"] = load_effective_model_json(fs=self._fs, session_id=session_id)
            return out
        except Exception as e:
            return exception_envelope(e)

    def get_step_definition(self, session_id: str, step_id: str) -> dict[str, object]:
        return get_step_definition_impl(engine=self, session_id=session_id, step_id=step_id)

    def submit_step(
        self, session_id: str, step_id: str, payload: dict[str, object]
    ) -> dict[str, object]:
        return submit_step_impl(
            engine=self, session_id=session_id, step_id=step_id, payload=payload
        )

    def preview_action(
        self,
        session_id: str,
        step_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        try:
            return preview_action_impl(
                engine=self,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
            )
        except Exception as e:
            return exception_envelope(e)

    def _auto_advance_computed_steps(
        self,
        *,
        session_id: str,
        state: dict[str, object],
        next_step_id: str,
        flow_cfg_norm: dict[str, object],
    ) -> str:
        """Advance past computed-only steps deterministically (spec 10.3.2/10.3.3).

        Renderers must never be forced to "submit" a computed-only step.
        """

        if next_step_id != "plan_preview_batch":
            return next_step_id

        # plan_preview_batch is computed-only (spec 10.3.1). Compute and advance.
        # Special rule: if plan preview fails due to invalid selection, transition back.
        state["current_step_id"] = "plan_preview_batch"
        self._persist_state(session_id, state)
        try:
            self.compute_plan(session_id)
        except PlanSelectionError:
            state["current_step_id"] = "select_books"
            state["updated_at"] = iso_utc_now()
            self._persist_state(session_id, state)
            return "select_books"

        except Exception:
            # Non-selection failures must not change the UI state.
            raise

        return self._move_linear(
            session_id=session_id,
            current="plan_preview_batch",
            direction="next",
        )

    def _validate_and_canonicalize_payload(
        self,
        *,
        step_id: str,
        schema: dict[str, object],
        payload: dict[str, object],
        state: dict[str, object],
    ) -> dict[str, object]:
        fields_any = schema.get("fields")
        fields = validate_step_fields(step_id=step_id, fields_any=fields_any)

        allowed: set[str] = set()
        for f in fields:
            name_any = f.get("name")
            ftype_any = f.get("type")
            if not isinstance(name_any, str) or not name_any:
                continue
            allowed.add(name_any)
            if ftype_any == "multi_select_indexed":
                allowed.add(f"{name_any}_expr")
                allowed.add(f"{name_any}_ids")

        unknown = sorted(set(payload.keys()) - allowed)
        if unknown:
            raise StepSubmissionError("unknown field(s): " + ", ".join(unknown))

        normalized: dict[str, object] = {}
        for f in fields:
            name = f.get("name")
            ftype = f.get("type")
            required = bool(f.get("required"))
            if not isinstance(name, str) or not isinstance(ftype, str):
                continue
            if required and not any(k in payload for k in (name, f"{name}_expr", f"{name}_ids")):
                raise StepSubmissionError(f"missing required field: {name}")

            if ftype in {"toggle", "confirm"}:
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, bool):
                    raise StepSubmissionError(f"field '{name}' must be bool")
                normalized[name] = value
                continue

            if ftype == "number":
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, int):
                    raise StepSubmissionError(f"field '{name}' must be int")
                constraints = f.get("constraints")
                if _is_str_object_dict(constraints):
                    mn = constraints.get("min")
                    mx = constraints.get("max")
                    if isinstance(mn, int) and value < mn:
                        raise StepSubmissionError(f"field '{name}' must be >= {mn}")
                    if isinstance(mx, int) and value > mx:
                        raise StepSubmissionError(f"field '{name}' must be <= {mx}")
                normalized[name] = value
                continue

            if ftype in {"text", "select"}:
                if name not in payload:
                    continue
                value = payload[name]
                if not isinstance(value, str):
                    raise StepSubmissionError(f"field '{name}' must be str")
                normalized[name] = value
                continue

            if ftype == "multi_select_indexed":
                ids = self._canonicalize_multi_select(
                    name=name, field=f, payload=payload, state=state
                )
                normalized[name] = ids
                continue

            if ftype == "table_edit":
                if name not in payload:
                    continue
                value = payload[name]
                if not _is_object_list(value):
                    raise StepSubmissionError(f"field '{name}' must be list")
                normalized[name] = value
                continue

            raise StepSubmissionError(f"unsupported field type: {ftype}")

        return normalized

    def _canonicalize_multi_select(
        self,
        *,
        name: str,
        field: dict[str, object],
        payload: dict[str, object],
        state: dict[str, object],
    ) -> list[str]:
        # Source items are taken from field.items when present, otherwise from discovery.
        items: list[dict[str, object]] = []
        items_any = field.get("items")
        if (
            _is_object_list(items_any)
            and items_any
            and all(_is_str_object_dict(x) for x in items_any)
        ):
            items = _as_dict_list(items_any)
        else:
            session_dir = f"import/sessions/{state.get('session_id')}"
            discovery_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            if _is_object_list(discovery_any) and all(
                _is_str_object_dict(x) for x in discovery_any
            ):
                items = _as_dict_list(discovery_any)

        ordered_ids: list[str] = []
        for it in items:
            item_id = it.get("item_id")
            if isinstance(item_id, str):
                ordered_ids.append(item_id)

        if not ordered_ids:
            raise StepSubmissionError(f"field '{name}' has no selectable items")

        if f"{name}_ids" in payload:
            raw = payload.get(f"{name}_ids")
            if not (_is_object_list(raw) and all(isinstance(x, str) for x in raw)):
                raise StepSubmissionError(f"field '{name}_ids' must be list[str]")
            requested = [str(x) for x in raw]
            unknown = sorted({x for x in requested if x not in set(ordered_ids)})
            if unknown:
                raise StepSubmissionError(f"unknown id(s) in '{name}_ids'")
            # Stable selection: preserve discovery order.
            selected_set = set(requested)
            return [x for x in ordered_ids if x in selected_set]

        expr_key = f"{name}_expr"
        if expr_key not in payload and name in payload and isinstance(payload.get(name), str):
            # Backward compatibility: allow a plain string value as expr.
            payload = dict(payload)
            payload[expr_key] = payload[name]

        if expr_key not in payload:
            raise StepSubmissionError(f"missing '{expr_key}' or '{name}_ids'")
        expr = payload.get(expr_key)
        if not isinstance(expr, str):
            raise StepSubmissionError(f"field '{expr_key}' must be str")

        indices = parse_selection_expr(expr, max_index=len(ordered_ids))
        # Stable selection: preserve discovery order while honoring indices.
        selected_indices = set(indices)
        selected_ids: list[str] = []
        for idx, item_id in enumerate(ordered_ids, start=1):
            if idx in selected_indices:
                selected_ids.append(item_id)
        return selected_ids

    def apply_action(self, session_id: str, action: str) -> dict[str, object]:
        try:
            effective_model = self._load_effective_model(session_id)
            if is_v3_effective_model(effective_model):
                return apply_action_v3(engine=self, session_id=session_id, action=str(action))
            state = self._load_state(session_id)
            if _to_int_or_default(state.get("phase"), 1) == 2:
                return invariant_violation(
                    message="session is locked (phase 2)",
                    path="$.phase",
                    reason="phase_locked",
                    meta={},
                )
            if state.get("status") != "in_progress":
                return invariant_violation(
                    message="session is not in progress",
                    path="$.status",
                    reason="status_not_in_progress",
                    meta={},
                )

            action = str(action)
            if action not in {"next", "back", "cancel"}:
                raise StepSubmissionError("invalid action")

            if action == "cancel":
                state["status"] = "aborted"
                state["updated_at"] = iso_utc_now()
                self._append_decision(
                    session_id,
                    step_id="__system__",
                    payload={"action": "cancel"},
                    result="accepted",
                    error=None,
                )
                self._persist_state(session_id, state)
                return state

            flow_cfg_norm = self._load_effective_flow_config(session_id)
            current = str(state.get("current_step_id") or "select_authors")
            direction = "next" if action == "next" else "back"

            next_step_id = self._move_linear(
                session_id=session_id,
                current=current,
                direction=direction,
            )

            if direction == "next":
                state["current_step_id"] = self._auto_advance_computed_steps(
                    session_id=session_id,
                    state=state,
                    next_step_id=next_step_id,
                    flow_cfg_norm=flow_cfg_norm,
                )
            else:
                # Computed-only steps must not be the UI current step.
                if next_step_id == "plan_preview_batch":
                    state["current_step_id"] = "select_books"
                else:
                    state["current_step_id"] = next_step_id

            state["updated_at"] = iso_utc_now()
            self._append_decision(
                session_id,
                step_id="__system__",
                payload={"action": action, "from": current, "to": state.get("current_step_id")},
                result="accepted",
                error=None,
            )
            self._persist_state(session_id, state)
            return state
        except Exception as e:
            return exception_envelope(e)

    def compute_plan(self, session_id: str) -> dict[str, object]:
        state = self._load_state(session_id)
        derived = _as_str_object_dict(state.get("derived"))

        emit_required_event(
            "plan.compute",
            "plan.compute",
            {
                "session_id": session_id,
                "model_fingerprint": state.get("model_fingerprint"),
                "discovery_fingerprint": derived.get("discovery_fingerprint"),
                "effective_config_fingerprint": derived.get("effective_config_fingerprint"),
            },
        )

        session_dir = f"import/sessions/{session_id}"
        discovery_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
        discovery = _as_dict_list(discovery_any)
        src = _as_str_object_dict(state.get("source"))
        src_root = str(src.get("root") or "")
        src_rel = str(src.get("relative_path") or "")
        vars_doc = _as_str_object_dict(state.get("vars"))
        session_authority = _as_str_object_dict(vars_doc.get("phase1"))
        select_books_authority = _as_str_object_dict(session_authority.get("select_books"))
        selected_book_ids = _as_str_list(select_books_authority.get("selected_ids"))
        plan = compute_plan(
            session_id=session_id,
            root=src_root,
            relative_path=src_rel,
            discovery=discovery,
            inputs=_as_str_object_dict(state.get("answers")),
            selected_book_ids=selected_book_ids,
            session_authority=session_authority,
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/plan.json", plan)

        computed = _as_str_object_dict(state.get("computed"))
        summary_any = plan.get("summary") if _is_str_object_dict(plan) else None
        sel_any = plan.get("selected_policies") if _is_str_object_dict(plan) else None
        summary = summary_any if _is_str_object_dict(summary_any) else {}
        selected_policies = sel_any if _is_str_object_dict(sel_any) else {}
        computed["plan_summary"] = {
            "files": _to_int_or_default(summary.get("files"), 0),
            "dirs": _to_int_or_default(summary.get("dirs"), 0),
            "bundles": _to_int_or_default(summary.get("bundles"), 0),
            "selected_policies": dict(selected_policies),
        }
        state["computed"] = computed

        # Update conflict fingerprint during plan preview.
        self._update_conflicts(session_id, state)
        state["updated_at"] = iso_utc_now()
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "plan.computed"},
            result="accepted",
            error=None,
        )
        self._persist_state(session_id, state)
        return plan

    def finalize(self, session_id: str) -> dict[str, object]:
        # finalize() is a legacy entry point kept for compatibility.
        # Per spec: job_requests.json may only be created by start_processing(confirm=true).
        return invariant_violation(
            message="finalize is not supported; use start_processing(confirm=true)",
            path="$.finalize",
            reason="legacy_operation",
            meta={},
        )

    def start_processing(self, session_id: str, body: dict[str, object]) -> dict[str, object]:
        return start_processing_impl(engine=self, session_id=session_id, body=body)

    def _start_processing_idempotent(
        self, session_id: str, state: dict[str, object], body: dict[str, object]
    ) -> dict[str, object]:
        if not _is_str_object_dict(body):
            raise ValueError("body must be an object")
        confirm = body.get("confirm")
        if confirm is not True:
            return validation_error(
                message="confirm must be true",
                path="$.confirm",
                reason="missing_or_false",
                meta={},
            )

        session_dir = f"import/sessions/{session_id}"
        job_path = f"{session_dir}/job_requests.json"
        if not self._fs.exists(RootName.WIZARDS, job_path):
            raise FinalizeError("job_requests.json is missing")

        job_requests_any = read_json(self._fs, RootName.WIZARDS, job_path)
        if not _is_str_object_dict(job_requests_any):
            raise FinalizeError("job_requests.json is invalid")
        idem_key = str(job_requests_any.get("idempotency_key") or "")
        if not idem_key:
            raise FinalizeError("job_requests.json missing idempotency_key")

        job_id = self._get_or_create_job(session_id, state, idem_key)
        plan_path = f"{session_dir}/plan.json"
        plan_any: object = (
            read_json(self._fs, RootName.WIZARDS, plan_path)
            if self._fs.exists(RootName.WIZARDS, plan_path)
            else {}
        )
        plan = _as_str_object_dict(plan_any)

        result: dict[str, object] = {"job_ids": [job_id], "batch_size": planned_units_count(plan)}
        finalize_any = _as_str_object_dict(state.get("computed")).get("finalize")
        if _is_str_object_dict(finalize_any):
            result["finalize"] = dict(finalize_any)
        return result

    def _resolve_flag_for_scan(
        self,
        *,
        state: dict[str, object],
        policy: str,
        current_fp: str,
        current_conflicts: list[dict[str, object]],
    ) -> bool:
        if policy != "ask":
            return True
        if not current_conflicts:
            return True

        prev = state.get("conflicts")
        prev_resolved = bool(prev.get("resolved")) if _is_str_object_dict(prev) else False
        prev_fp = str(_as_str_object_dict(state.get("derived")).get("conflict_fingerprint") or "")
        if current_fp != prev_fp:
            return False
        return prev_resolved

    def _enter_phase_2(self, session_id: str, state: dict[str, object]) -> None:
        effective_model = self._load_effective_model(session_id)
        catalog_any = effective_model.get("catalog")
        step_ids: set[str] = set()
        if _is_str_object_dict(catalog_any):
            try:
                catalog = CatalogModel.from_dict(catalog_any)
                step_ids = catalog.step_ids()
            except Exception:
                step_ids = set()

        if "processing" in step_ids:
            state["current_step_id"] = "processing"

        state["phase"] = 2
        state["status"] = "processing"
        state["updated_at"] = iso_utc_now()
        self._persist_state(session_id, state)

    def _validate_mode(self, mode: str) -> str:
        mode = str(mode)
        if mode not in {"stage", "inplace"}:
            raise ValueError("mode must be 'stage' or 'inplace'")
        return mode

    def _load_effective_flow_config(self, session_id: str) -> dict[str, object]:
        session_dir = f"import/sessions/{session_id}"
        cfg_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json")
        if not _is_str_object_dict(cfg_any):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        flow_cfg_any = cfg_any.get("flow_config")
        if not _is_str_object_dict(flow_cfg_any):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        return flow_cfg_any

    def _load_session_wizard_definition_snapshot(
        self, session_id: str, state: dict[str, object]
    ) -> dict[str, object]:
        derived_any = state.get("derived")
        derived: dict[str, object] = derived_any if _is_str_object_dict(derived_any) else {}
        snap_any = derived.get("wizard_definition_snapshot")
        if _is_str_object_dict(snap_any):
            if "flow_transition_hops" not in derived:
                derived["flow_transition_hops"] = 0
            return snap_any

        wd = load_or_bootstrap_wizard_definition(self._fs)
        validate_wizard_definition_structure(wd)

        derived["wizard_definition_snapshot"] = wd
        derived["wizard_definition_fingerprint"] = fingerprint_json(wd)
        derived["flow_transition_hops"] = 0
        state["derived"] = derived
        self._persist_state(session_id, state)
        return wd

    def _session_step_order(self, session_id: str) -> list[str]:
        effective = read_json(
            self._fs,
            RootName.WIZARDS,
            f"import/sessions/{session_id}/effective_model.json",
        )
        steps_any = effective.get("steps") if _is_str_object_dict(effective) else None
        if not _is_object_list(steps_any):
            return []
        out: list[str] = []
        for s in steps_any:
            if not _is_str_object_dict(s):
                continue
            sid = s.get("step_id")
            if isinstance(sid, str) and sid:
                out.append(sid)
        return out

    def _move_linear(
        self,
        *,
        session_id: str,
        current: str,
        direction: str,
    ) -> str:
        linear = self._session_step_order(session_id)
        if not linear:
            return current or "select_authors"
        if current not in linear:
            return linear[0]
        idx = linear.index(current)
        if direction == "next":
            return linear[min(idx + 1, len(linear) - 1)]
        return linear[max(idx - 1, 0)]

    def _next_step_after_submit(
        self,
        *,
        step_id: str,
        state: dict[str, object],
        flow_cfg_norm: dict[str, object],
    ) -> str:
        session_id = str(state.get("session_id") or "")

        derived_any = state.get("derived")
        derived: dict[str, object] = derived_any if _is_str_object_dict(derived_any) else {}
        hops_any = derived.get("flow_transition_hops")
        hops = int(hops_any) if isinstance(hops_any, int) and not isinstance(hops_any, bool) else 0
        hops += 1
        if hops > MAX_TRANSITION_HOPS:
            raise FinalizeError("CYCLE_DETECTED: hop_limit")
        derived["flow_transition_hops"] = hops
        state["derived"] = derived

        # Conflict scan side effect is engine-owned (spec 10.3.4) but branching is graph-owned.
        if step_id == "final_summary_confirm":
            inputs = _as_str_object_dict(state.get("inputs"))
            payload = inputs.get("final_summary_confirm")
            confirm = payload.get("confirm_start") if _is_str_object_dict(payload) else None
            if confirm is True:
                conflicts = state.get("conflicts")
                policy = "ask"
                if _is_str_object_dict(conflicts):
                    policy = str(conflicts.get("policy") or "ask")
                if policy == "ask":
                    self._update_conflicts(session_id, state)

        wd = self._load_session_wizard_definition_snapshot(session_id, state)
        known_step_ids = _wizard_definition_known_step_ids(wd)
        graph = normalize_to_graph(wd, known_step_ids=known_step_ids)

        state_view = build_flow_graph_state_view(state)

        def is_enabled(sid: str) -> bool:
            return self._is_step_enabled(sid, flow_cfg_norm)

        def debug_log(kind: str, payload: dict[str, object]) -> None:
            emit_required_event(
                "flow_graph.debug",
                "flow_graph.debug",
                {
                    "session_id": session_id,
                    "kind": kind,
                    "payload": dict(payload),
                },
            )

        return select_next_step(
            graph,
            current_step_id=step_id,
            state_view=state_view,
            is_step_enabled=is_enabled,
            debug_log=debug_log,
        )

    def _is_step_enabled(self, step_id: str, flow_cfg_norm: dict[str, object]) -> bool:
        steps_any = flow_cfg_norm.get("steps")
        if not _is_str_object_dict(steps_any):
            return True
        cfg_any = steps_any.get(step_id)
        if not _is_str_object_dict(cfg_any):
            return True
        enabled = cfg_any.get("enabled")
        if enabled is None:
            return True
        return bool(enabled)

    def _coerce_start_step(self, flow: FlowModel, flow_cfg_norm: dict[str, object]) -> str:
        entry = str(flow.entry_step_id)
        if self._is_step_enabled(entry, flow_cfg_norm):
            return entry
        next_enabled = self._next_enabled_step(
            flow, entry, direction="next", flow_cfg_norm=flow_cfg_norm
        )
        return next_enabled or entry

    def _next_enabled_step(
        self,
        flow: FlowModel,
        from_step_id: str,
        *,
        direction: str,
        flow_cfg_norm: dict[str, object],
    ) -> str | None:
        if direction not in {"next", "back"}:
            raise ValueError("direction must be 'next' or 'back'")

        node_map = flow.node_map()
        visited: set[str] = set()
        cur = from_step_id
        while True:
            if cur in visited:
                return None
            visited.add(cur)

            node = node_map.get(cur)
            if node is None:
                return None
            candidate = node.next_step_id if direction == "next" else node.prev_step_id
            if candidate is None:
                return None
            if self._is_step_enabled(candidate, flow_cfg_norm):
                return candidate
            cur = candidate

    def _normalize_flow_config(self, raw: object) -> dict[str, object]:
        return normalize_flow_config(raw)

    def _merge_flow_config_overrides(
        self, base: dict[str, object], overrides: dict[str, object]
    ) -> dict[str, object]:
        return flow_config_api.merge_flow_config_overrides(base, overrides)

    def _scan_conflicts(self, session_id: str, state: dict[str, object]) -> list[dict[str, object]]:
        from .conflicts import scan_conflicts

        session_dir = f"import/sessions/{session_id}"
        plan_path = f"{session_dir}/plan.json"
        if not self._fs.exists(RootName.WIZARDS, plan_path):
            _ = self.compute_plan(session_id)

        plan = read_json(self._fs, RootName.WIZARDS, plan_path)
        plan = plan if _is_str_object_dict(plan) else {}

        mode = self._validate_mode(str(state.get("mode") or "stage"))
        items_any = scan_conflicts(self._fs, plan=plan, mode=mode)
        return _as_dict_list(items_any)

    def _update_conflicts(self, session_id: str, state: dict[str, object]) -> None:
        items = self._scan_conflicts(session_id, state)
        fp = fingerprint_json(items)
        answers = _as_str_object_dict(state.get("answers"))
        conflict_policy = _as_str_object_dict(answers.get("conflict_policy"))
        existing_conflicts = _as_str_object_dict(state.get("conflicts"))
        policy = str(conflict_policy.get("mode") or existing_conflicts.get("policy") or "ask")
        resolved = self._resolve_flag_for_scan(
            state=state,
            policy=policy,
            current_fp=fp,
            current_conflicts=items,
        )

        derived = _as_str_object_dict(state.get("derived"))
        derived["conflict_fingerprint"] = fp
        state["derived"] = derived
        state["conflicts"] = {
            "present": bool(items),
            "items": items,
            "resolved": resolved,
            "policy": policy,
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/conflicts.json", items)

    def _get_or_create_job(self, session_id: str, state: dict[str, object], idem_key: str) -> str:
        # Invariants must be validated before job creation.
        wd = self._load_session_wizard_definition_snapshot(session_id, state)
        known_step_ids = _wizard_definition_known_step_ids(wd)
        _ = normalize_to_graph(wd, known_step_ids=known_step_ids)
        _ = self._normalize_flow_config(self._load_effective_flow_config(session_id))

        session_dir = f"import/sessions/{session_id}"
        idem_path = f"{session_dir}/idempotency.json"
        mapping: dict[str, str] = {}
        if self._fs.exists(RootName.WIZARDS, idem_path):
            loaded = read_json(self._fs, RootName.WIZARDS, idem_path)
            if _is_str_object_dict(loaded):
                mapping = {str(k): str(v) for k, v in loaded.items()}

        if idem_key in mapping and mapping[idem_key]:
            return mapping[idem_key]

        derived = _as_str_object_dict(state.get("derived"))
        meta: dict[str, object] = {
            "source": "import",
            "session_id": session_id,
            "idempotency_key": idem_key,
            "effective_config_fingerprint": str(derived.get("effective_config_fingerprint") or ""),
            "model_fingerprint": str(state.get("model_fingerprint") or ""),
            "discovery_fingerprint": str(derived.get("discovery_fingerprint") or ""),
            "job_requests_path": f"wizards:{session_dir}/job_requests.json",
            "detached_runtime_json": serialize_detached_runtime_bootstrap(fs=self._fs),
        }
        job_id = create_process_job(meta=meta)
        mapping[idem_key] = job_id
        atomic_write_json(self._fs, RootName.WIZARDS, idem_path, mapping)
        return job_id

    def _load_state(self, session_id: str) -> dict[str, object]:
        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"
        if not self._fs.exists(RootName.WIZARDS, state_path):
            raise SessionNotFoundError(f"session not found: {session_id}")
        state_any = read_json(self._fs, RootName.WIZARDS, state_path)
        if not _is_str_object_dict(state_any):
            raise FinalizeError("state.json is invalid")

        state = ensure_session_state_fields(state_any)
        answers = _as_str_object_dict(state.get("answers"))
        conflict_policy = _as_str_object_dict(answers.get("conflict_policy"))
        conflicts = _as_str_object_dict(state.get("conflicts"))
        conflicts["policy"] = str(conflict_policy.get("mode") or conflicts.get("policy") or "ask")
        state["conflicts"] = conflicts
        return state

    def _persist_state(self, session_id: str, state: dict[str, object]) -> None:
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/state.json", state)

    def _runtime_effective_model_fingerprint(self, session_id: str) -> str:
        """Return fingerprint for the runtime-effective model for a session.

        The snapshot effective_model.json is immutable, but runtime selection items may be
        derived from discovery.json when rendering. state.json model_fingerprint is allowed
        to reflect this runtime-effective model.
        """
        model_any = self._load_effective_model(session_id)
        if _is_str_object_dict(model_any):
            return fingerprint_json(model_any)
        return ""

    def _effective_model_with_runtime_selection_items(
        self, session_id: str, effective_model: dict[str, object]
    ) -> dict[str, object]:
        if effective_model.get("flowmodel_kind") == "dsl_step_graph_v3":
            return effective_model

        session_dir = f"import/sessions/{session_id}"
        discovery_path = f"{session_dir}/discovery.json"

        if not self._fs.exists(RootName.WIZARDS, discovery_path):
            return effective_model

        discovery_any = read_json(self._fs, RootName.WIZARDS, discovery_path)
        if not _is_object_list(discovery_any):
            return effective_model

        discovery = _as_dict_list(discovery_any)
        authors_items, books_items = derive_selection_items(discovery)
        return inject_selection_items(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )

    def _load_effective_model(self, session_id: str) -> dict[str, object]:
        session_dir = f"import/sessions/{session_id}"
        model_any = read_json(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/effective_model.json",
        )
        if _is_str_object_dict(model_any):
            return self._effective_model_with_runtime_selection_items(session_id, model_any)
        raise FinalizeError("effective_model.json is invalid")

    def _append_decision(
        self,
        session_id: str,
        *,
        step_id: str,
        payload: dict[str, object],
        result: str,
        error: dict[str, object] | None,
    ) -> None:
        session_dir = f"import/sessions/{session_id}"
        entry: dict[str, object] = {
            "at": iso_utc_now(),
            "step_id": step_id,
            "payload": dict(payload),
            "result": result,
        }
        if error is not None:
            entry["error"] = dict(error)
        append_jsonl(self._fs, RootName.WIZARDS, f"{session_dir}/decisions.jsonl", entry)
