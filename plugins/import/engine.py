"""Import Wizard Engine (plugin: import).

Implements PHASE 0 discovery, model load/validate, session lifecycle, and
minimal plan/job request generation.

No UI is implemented here.

ASCII-only.
"""

from __future__ import annotations

from typing import Any, cast

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from . import flow_config_api
from .defaults import ensure_default_models
from .engine_diagnostics_required import create_process_job
from .engine_processing import start_processing_impl
from .engine_session_create import create_session_impl
from .engine_util import (
    _derive_selection_items,
    _emit_required,
    _ensure_session_state_fields,
    _exception_envelope,
    _inject_selection_items,
    _iso_utc_now,
    _parse_selection_expr,
)
from .errors import (
    FinalizeError,
    SessionNotFoundError,
    StepSubmissionError,
    ascii_message,
    invariant_violation,
    validation_error,
)
from .field_schema_validation import validate_step_fields
from .fingerprints import fingerprint_json
from .flow_runtime import (
    CONDITIONAL_STEP_IDS,
    build_flow_model,
)
from .job_requests import planned_units_count
from .models import CatalogModel, FlowModel, validate_models
from .plan import PlanSelectionError, compute_plan
from .preview import preview_action_impl
from .storage import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    read_json,
)
from .wizard_definition_model import (
    build_effective_workflow_snapshot,
    load_or_bootstrap_wizard_definition,
)

# Test seam: unit tests monkeypatch plugins.import.engine.get_event_bus.
get_event_bus: Any = None

__all__ = [
    "ImportWizardEngine",
    "atomic_write_text",
]


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: Any) -> None:
        self._resolver = resolver
        self._fs = FileService.from_resolver(self._resolver)

    def get_file_service(self) -> FileService:
        """Return the file service used by this engine.

        This is a plugin-internal helper for CLI/editor tooling.
        """
        return self._fs

    def get_flow_model(self) -> dict[str, Any]:
        """Return FlowModel JSON for the current configuration (spec 10.5)."""
        ensure_default_models(self._fs)
        catalog_dict = read_json(self._fs, RootName.WIZARDS, "import/catalog/catalog.json")
        flow_dict = read_json(self._fs, RootName.WIZARDS, "import/flow/current.json")
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")

        flow_cfg_norm = self._normalize_flow_config(flow_cfg)

        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)
        validate_models(catalog, flow)

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

    def create_session(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return self._create_session_impl(
                root,
                relative_path,
                mode=mode,
                flow_overrides=flow_overrides,
            )
        except Exception as e:
            return _exception_envelope(e)

    def _create_session_impl(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return create_session_impl(
            engine=self,
            root=root,
            relative_path=relative_path,
            mode=mode,
            flow_overrides=flow_overrides,
        )

    def validate_catalog(self, catalog_json: Any) -> dict[str, Any]:
        """Validate catalog JSON using engine invariants.

        Returns {"ok": True} on success, or a canonical error envelope.
        """
        try:
            if not isinstance(catalog_json, dict):
                raise ValueError("catalog_json must be an object")
            _ = CatalogModel.from_dict(catalog_json)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def validate_flow(self, flow_json: Any, catalog_json: Any) -> dict[str, Any]:
        """Validate flow JSON against the catalog using engine invariants.

        Returns {"ok": True} on success, or a canonical error envelope.
        """
        try:
            if not isinstance(catalog_json, dict):
                raise ValueError("catalog_json must be an object")
            if not isinstance(flow_json, dict):
                raise ValueError("flow_json must be an object")
            catalog = CatalogModel.from_dict(catalog_json)
            flow = FlowModel.from_dict(flow_json)
            validate_models(catalog, flow)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def validate_flow_config(self, flow_config_json: Any) -> dict[str, Any]:
        """Validate FlowConfig JSON.

        FlowConfig v1 governance:
        - version=1
        - optional step toggles only: steps.{step_id}.enabled (bool)
        - required steps may not be disabled
        """
        try:
            if not isinstance(flow_config_json, dict):
                raise ValueError("flow_config_json must be an object")
            _ = self._normalize_flow_config(flow_config_json)
            return {"ok": True}
        except Exception as e:
            return _exception_envelope(e)

    def get_flow_config(self) -> dict[str, Any]:
        return flow_config_api.get_flow_config(self)

    def set_flow_config(self, flow_config_json: Any) -> dict[str, Any]:
        return flow_config_api.set_flow_config(self, flow_config_json)

    def reset_flow_config(self) -> dict[str, Any]:
        return flow_config_api.reset_flow_config(self)

    def preview_effective_model(self, catalog_json: Any, flow_json: Any) -> dict[str, Any]:
        """Return the effective model that would be frozen for new sessions."""
        if not isinstance(catalog_json, dict):
            raise ValueError("catalog_json must be an object")
        if not isinstance(flow_json, dict):
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

    def get_state(self, session_id: str) -> dict[str, Any]:
        try:
            return self._load_state(session_id)
        except Exception as e:
            return _exception_envelope(e)

    def get_step_definition(self, session_id: str, step_id: str) -> dict[str, Any]:
        """Return the catalog step definition for step_id.

        This is a UI helper. It does not perform any state transitions.
        """
        try:
            effective_model = self._load_effective_model(session_id)
            steps_any = effective_model.get("steps")
            if not isinstance(steps_any, list):
                raise ValueError("effective model missing steps")
            for step in steps_any:
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    return dict(step)
            raise ValueError("unknown step_id")
        except Exception as e:
            return _exception_envelope(e)

    def submit_step(self, session_id: str, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if int(state.get("phase") or 1) == 2:
                return invariant_violation(
                    message="session is locked (phase 2)",
                    path="$.phase",
                    reason="phase_locked",
                    meta={},
                )
            if state.get("status") != "in_progress":
                raise StepSubmissionError("session is not in progress")

            _emit_required(
                "step.submit",
                "step.submit",
                {
                    "session_id": session_id,
                    "step_id": step_id,
                    "model_fingerprint": state.get("model_fingerprint"),
                    "discovery_fingerprint": state.get("derived", {}).get("discovery_fingerprint"),
                    "effective_config_fingerprint": state.get("derived", {}).get(
                        "effective_config_fingerprint"
                    ),
                },
            )

            if not isinstance(payload, dict):
                raise StepSubmissionError("payload must be an object")

            effective_model = self._load_effective_model(session_id)
            steps_any = effective_model.get("steps")
            if not isinstance(steps_any, list):
                raise StepSubmissionError("effective model missing steps")
            steps = [s for s in steps_any if isinstance(s, dict)]
            flow_cfg_norm = self._load_effective_flow_config(session_id)

            step_ids = {str(s.get("step_id")) for s in steps if isinstance(s.get("step_id"), str)}
            if step_id not in step_ids and step_id not in CONDITIONAL_STEP_IDS:
                raise StepSubmissionError("unknown step_id")

            current = str(state.get("current_step_id") or "select_authors")
            if step_id != current:
                raise StepSubmissionError("step_id must match current_step_id")

            schema = None
            for step in steps:
                if step.get("step_id") == step_id:
                    schema = step
                    break
            if schema is None:
                raise StepSubmissionError("unknown step_id")

            if step_id in {"plan_preview_batch", "processing"}:
                raise StepSubmissionError("computed-only step cannot be submitted")

            normalized_payload = self._validate_and_canonicalize_payload(
                step_id=step_id,
                schema=schema,
                payload=payload,
                state=state,
            )

            if step_id == "conflict_policy":
                self._apply_conflict_policy(state, normalized_payload)
            if step_id == "resolve_conflicts_batch":
                self._apply_conflict_resolve(state, normalized_payload)
                self._persist_conflict_resolution(session_id, state, normalized_payload)

            answers = dict(state.get("answers") or {})
            answers[step_id] = normalized_payload
            state["answers"] = answers

            # Backward compatibility: maintain legacy inputs mirror.
            inputs = dict(state.get("inputs") or {})
            inputs[step_id] = normalized_payload
            state["inputs"] = inputs

            if step_id == "select_authors":
                sel = normalized_payload.get("selection")
                if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                    state["selected_author_ids"] = list(sel)

            if step_id == "select_books":
                sel = normalized_payload.get("selection")
                if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                    state["selected_book_ids"] = list(sel)

            if step_id == "effective_author_title":
                state["effective_author_title"] = dict(normalized_payload)

            completed = list(state.get("completed_step_ids") or [])
            if step_id not in completed:
                completed.append(step_id)
            state["completed_step_ids"] = completed

            next_step = self._next_step_after_submit(
                step_id=step_id,
                state=state,
                flow_cfg_norm=flow_cfg_norm,
            )

            state["current_step_id"] = self._auto_advance_computed_steps(
                session_id=session_id,
                state=state,
                next_step_id=next_step,
                flow_cfg_norm=flow_cfg_norm,
            )

            state["updated_at"] = _iso_utc_now()
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=normalized_payload,
                result="accepted",
                error=None,
            )
            self._persist_state(session_id, state)
            return state
        except Exception as e:
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload if isinstance(payload, dict) else {"_invalid_payload": True},
                result="rejected",
                error={
                    "type": e.__class__.__name__,
                    "message": ascii_message(str(e) or e.__class__.__name__),
                },
            )
            return _exception_envelope(e)

    def preview_action(
        self,
        session_id: str,
        step_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return preview_action_impl(
                engine=self,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
            )
        except Exception as e:
            return _exception_envelope(e)

    def _auto_advance_computed_steps(
        self,
        *,
        session_id: str,
        state: dict[str, Any],
        next_step_id: str,
        flow_cfg_norm: dict[str, Any],
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
            state["updated_at"] = _iso_utc_now()
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

    def _apply_conflict_policy(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        raw_mode = payload.get("mode")
        if not isinstance(raw_mode, str) or not raw_mode.strip():
            raise StepSubmissionError("conflict_policy.mode must be a non-empty string")
        mode = raw_mode.strip().lower()
        try:
            mode.encode("ascii")
        except UnicodeEncodeError as e:
            raise StepSubmissionError("conflict_policy.mode must be ASCII-only") from e

        policy = "ask" if mode == "ask" else mode

        conflicts = state.get("conflicts")
        conflicts = conflicts if isinstance(conflicts, dict) else {}

        conflicts["policy"] = policy

        items = conflicts.get("items")
        present = bool(conflicts.get("present"))
        if isinstance(items, list):
            present = present or bool(items)

        if policy != "ask":
            conflicts["resolved"] = True
        else:
            conflicts["resolved"] = bool(conflicts.get("resolved")) if present else True

        state["conflicts"] = conflicts

    def _apply_conflict_resolve(self, state: dict[str, Any], payload: dict[str, Any]) -> None:
        conflicts = state.get("conflicts")
        if not isinstance(conflicts, dict):
            raise StepSubmissionError("conflicts missing from state")

        policy = str(conflicts.get("policy") or "ask")
        if policy != "ask":
            conflicts["resolved"] = True
            state["conflicts"] = conflicts
            return

        confirm = payload.get("confirm")
        if confirm is not True:
            raise StepSubmissionError("resolve_conflicts_batch.confirm must be true")

        conflicts["resolved"] = True
        state["conflicts"] = conflicts

    def _persist_conflict_resolution(
        self,
        session_id: str,
        state: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        conflicts = state.get("conflicts")
        if not isinstance(conflicts, dict):
            return
        record = {
            "at": _iso_utc_now(),
            "policy": str(conflicts.get("policy") or ""),
            "conflict_fingerprint": str(state.get("derived", {}).get("conflict_fingerprint") or ""),
            "payload": dict(payload),
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/conflicts_resolution.json",
            record,
        )

    def _validate_and_canonicalize_payload(
        self,
        *,
        step_id: str,
        schema: dict[str, Any],
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
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

        normalized: dict[str, Any] = {}
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
                if isinstance(constraints, dict):
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
                if not isinstance(value, list):
                    raise StepSubmissionError(f"field '{name}' must be list")
                normalized[name] = value
                continue

            raise StepSubmissionError(f"unsupported field type: {ftype}")

        return normalized

    def _canonicalize_multi_select(
        self,
        *,
        name: str,
        field: dict[str, Any],
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> list[str]:
        # Source items are taken from field.items when present, otherwise from discovery.
        items: list[dict[str, Any]] = []
        items_any = field.get("items")
        if (
            isinstance(items_any, list)
            and items_any
            and all(isinstance(x, dict) for x in items_any)
        ):
            items = [cast(dict[str, Any], x) for x in items_any]
        else:
            session_dir = f"import/sessions/{state.get('session_id')}"
            discovery_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            if isinstance(discovery_any, list) and all(isinstance(x, dict) for x in discovery_any):
                items = [cast(dict[str, Any], x) for x in discovery_any]

        ordered_ids: list[str] = []
        for it in items:
            item_id = it.get("item_id")
            if isinstance(item_id, str):
                ordered_ids.append(item_id)

        if not ordered_ids:
            raise StepSubmissionError(f"field '{name}' has no selectable items")

        if f"{name}_ids" in payload:
            raw = payload.get(f"{name}_ids")
            if not (isinstance(raw, list) and all(isinstance(x, str) for x in raw)):
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

        indices = _parse_selection_expr(expr, max_index=len(ordered_ids))
        # Stable selection: preserve discovery order while honoring indices.
        selected_indices = set(indices)
        selected_ids: list[str] = []
        for idx, item_id in enumerate(ordered_ids, start=1):
            if idx in selected_indices:
                selected_ids.append(item_id)
        return selected_ids

    def apply_action(self, session_id: str, action: str) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if int(state.get("phase") or 1) == 2:
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
                state["updated_at"] = _iso_utc_now()
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

            state["updated_at"] = _iso_utc_now()
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
            return _exception_envelope(e)

    def compute_plan(self, session_id: str) -> dict[str, Any]:
        state = self._load_state(session_id)

        _emit_required(
            "plan.compute",
            "plan.compute",
            {
                "session_id": session_id,
                "model_fingerprint": state.get("model_fingerprint"),
                "discovery_fingerprint": state.get("derived", {}).get("discovery_fingerprint"),
                "effective_config_fingerprint": state.get("derived", {}).get(
                    "effective_config_fingerprint"
                ),
            },
        )

        session_dir = f"import/sessions/{session_id}"
        discovery = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
        src = state.get("source") or {}
        src_root = str(src.get("root") or "")
        src_rel = str(src.get("relative_path") or "")
        plan = compute_plan(
            session_id=session_id,
            root=src_root,
            relative_path=src_rel,
            discovery=discovery,
            inputs=dict(state.get("answers") or {}),
            selected_book_ids=list(state.get("selected_book_ids") or []),
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/plan.json", plan)

        computed = dict(state.get("computed") or {})
        summary_any = plan.get("summary") if isinstance(plan, dict) else None
        sel_any = plan.get("selected_policies") if isinstance(plan, dict) else None
        summary = summary_any if isinstance(summary_any, dict) else {}
        selected_policies = sel_any if isinstance(sel_any, dict) else {}
        computed["plan_summary"] = {
            "files": int(summary.get("files") or 0),
            "dirs": int(summary.get("dirs") or 0),
            "bundles": int(summary.get("bundles") or 0),
            "selected_policies": dict(selected_policies),
        }
        state["computed"] = computed

        # Update conflict fingerprint during plan preview.
        self._update_conflicts(session_id, state)
        state["updated_at"] = _iso_utc_now()
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "plan.computed"},
            result="accepted",
            error=None,
        )
        self._persist_state(session_id, state)
        return plan

    def finalize(self, session_id: str) -> dict[str, Any]:
        # finalize() is a legacy entry point kept for compatibility.
        # Per spec: job_requests.json may only be created by start_processing(confirm=true).
        return invariant_violation(
            message="finalize is not supported; use start_processing(confirm=true)",
            path="$.finalize",
            reason="legacy_operation",
            meta={},
        )

    def start_processing(self, session_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return start_processing_impl(engine=self, session_id=session_id, body=body)

    def _start_processing_idempotent(
        self, session_id: str, state: dict[str, Any], body: dict[str, Any]
    ) -> dict[str, Any]:
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

        session_dir = f"import/sessions/{session_id}"
        job_path = f"{session_dir}/job_requests.json"
        if not self._fs.exists(RootName.WIZARDS, job_path):
            raise FinalizeError("job_requests.json is missing")

        job_requests_any = read_json(self._fs, RootName.WIZARDS, job_path)
        if not isinstance(job_requests_any, dict):
            raise FinalizeError("job_requests.json is invalid")
        idem_key = str(job_requests_any.get("idempotency_key") or "")
        if not idem_key:
            raise FinalizeError("job_requests.json missing idempotency_key")

        job_id = self._get_or_create_job(session_id, state, idem_key)
        plan_path = f"{session_dir}/plan.json"
        plan = (
            read_json(self._fs, RootName.WIZARDS, plan_path)
            if self._fs.exists(RootName.WIZARDS, plan_path)
            else {}
        )
        plan = plan if isinstance(plan, dict) else {}

        return {"job_ids": [job_id], "batch_size": planned_units_count(plan)}

    def _resolve_flag_for_scan(
        self,
        *,
        state: dict[str, Any],
        policy: str,
        current_fp: str,
        current_conflicts: list[dict[str, Any]],
    ) -> bool:
        if policy != "ask":
            return True
        if not current_conflicts:
            return True

        prev = state.get("conflicts")
        prev_resolved = bool(prev.get("resolved")) if isinstance(prev, dict) else False
        prev_fp = str(state.get("derived", {}).get("conflict_fingerprint") or "")
        if current_fp != prev_fp:
            return False
        return prev_resolved

    def _enter_phase_2(self, session_id: str, state: dict[str, Any]) -> None:
        effective_model = self._load_effective_model(session_id)
        catalog_any = effective_model.get("catalog")
        step_ids: set[str] = set()
        if isinstance(catalog_any, dict):
            try:
                catalog = CatalogModel.from_dict(cast(dict[str, Any], catalog_any))
                step_ids = catalog.step_ids()
            except Exception:
                step_ids = set()

        if "processing" in step_ids:
            state["current_step_id"] = "processing"

        state["phase"] = 2
        state["status"] = "processing"
        state["updated_at"] = _iso_utc_now()
        self._persist_state(session_id, state)

    def _validate_mode(self, mode: str) -> str:
        mode = str(mode)
        if mode not in {"stage", "inplace"}:
            raise ValueError("mode must be 'stage' or 'inplace'")
        return mode

    def _load_effective_flow_config(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        cfg_any = read_json(self._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json")
        if not isinstance(cfg_any, dict):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        flow_cfg_any = cfg_any.get("flow_config")
        if not isinstance(flow_cfg_any, dict):
            return {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        return flow_cfg_any

    def _session_step_order(self, session_id: str) -> list[str]:
        effective = read_json(
            self._fs,
            RootName.WIZARDS,
            f"import/sessions/{session_id}/effective_model.json",
        )
        steps_any = effective.get("steps") if isinstance(effective, dict) else None
        if not isinstance(steps_any, list):
            return []
        out: list[str] = []
        for s in steps_any:
            if not isinstance(s, dict):
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
        state: dict[str, Any],
        flow_cfg_norm: dict[str, Any],
    ) -> str:
        # Spec 10.3.4 conditional conflict path.
        if step_id == "resolve_conflicts_batch":
            return "final_summary_confirm"

        if step_id == "final_summary_confirm":
            inputs = state.get("inputs") or {}
            payload = inputs.get("final_summary_confirm") if isinstance(inputs, dict) else None
            confirm = payload.get("confirm_start") if isinstance(payload, dict) else None
            if confirm is not True:
                return "final_summary_confirm"

            conflicts = state.get("conflicts")
            policy = "ask"
            if isinstance(conflicts, dict):
                policy = str(conflicts.get("policy") or "ask")

            if policy != "ask":
                return "processing"

            # conflict_mode == ask: perform deterministic scan here (spec 10.3.4).
            self._update_conflicts(str(state.get("session_id") or ""), state)
            conflicts2 = state.get("conflicts")
            present = bool(conflicts2.get("present")) if isinstance(conflicts2, dict) else False
            resolved = bool(conflicts2.get("resolved")) if isinstance(conflicts2, dict) else True
            if present and not resolved:
                return "resolve_conflicts_batch"
            return "processing"

        # Default: strictly linear ordering, derived from the session snapshot.
        session_id = str(state.get("session_id") or "")
        return self._move_linear(
            session_id=session_id,
            current=step_id,
            direction="next",
        )

    def _is_step_enabled(self, step_id: str, flow_cfg_norm: dict[str, Any]) -> bool:
        steps_any = flow_cfg_norm.get("steps")
        if not isinstance(steps_any, dict):
            return True
        cfg_any = steps_any.get(step_id)
        if not isinstance(cfg_any, dict):
            return True
        enabled = cfg_any.get("enabled")
        if enabled is None:
            return True
        return bool(enabled)

    def _coerce_start_step(self, flow: FlowModel, flow_cfg_norm: dict[str, Any]) -> str:
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
        flow_cfg_norm: dict[str, Any],
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

    def _normalize_flow_config(self, raw: Any) -> dict[str, Any]:
        return flow_config_api.normalize_flow_config(raw)

    def _merge_flow_config_overrides(
        self, base: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        return flow_config_api.merge_flow_config_overrides(base, overrides)

    def _scan_conflicts(self, session_id: str, state: dict[str, Any]) -> list[dict[str, str]]:
        from .conflicts import scan_conflicts

        session_dir = f"import/sessions/{session_id}"
        plan_path = f"{session_dir}/plan.json"
        if not self._fs.exists(RootName.WIZARDS, plan_path):
            _ = self.compute_plan(session_id)

        plan = read_json(self._fs, RootName.WIZARDS, plan_path)
        plan = plan if isinstance(plan, dict) else {}

        mode = self._validate_mode(str(state.get("mode") or "stage"))
        items = scan_conflicts(self._fs, plan=plan, mode=mode)
        return [cast(dict[str, str], it) for it in items]

    def _update_conflicts(self, session_id: str, state: dict[str, Any]) -> None:
        items = self._scan_conflicts(session_id, state)
        fp = fingerprint_json(items)
        policy = str((state.get("conflicts") or {}).get("policy") or "ask")
        resolved = self._resolve_flag_for_scan(
            state=state,
            policy=policy,
            current_fp=fp,
            current_conflicts=items,
        )

        state.setdefault("derived", {})["conflict_fingerprint"] = fp
        state["conflicts"] = {
            "present": bool(items),
            "items": items,
            "resolved": resolved,
            "policy": policy,
        }
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/conflicts.json", items)

    def _get_or_create_job(self, session_id: str, state: dict[str, Any], idem_key: str) -> str:
        session_dir = f"import/sessions/{session_id}"
        idem_path = f"{session_dir}/idempotency.json"
        mapping: dict[str, str] = {}
        if self._fs.exists(RootName.WIZARDS, idem_path):
            loaded = read_json(self._fs, RootName.WIZARDS, idem_path)
            if isinstance(loaded, dict):
                mapping = {str(k): str(v) for k, v in loaded.items()}

        if idem_key in mapping and mapping[idem_key]:
            return mapping[idem_key]

        meta = {
            "source": "import",
            "session_id": session_id,
            "idempotency_key": idem_key,
            "effective_config_fingerprint": str(
                state.get("derived", {}).get("effective_config_fingerprint") or ""
            ),
            "model_fingerprint": str(state.get("model_fingerprint") or ""),
            "discovery_fingerprint": str(
                state.get("derived", {}).get("discovery_fingerprint") or ""
            ),
            "job_requests_path": f"wizards:{session_dir}/job_requests.json",
        }
        job_id = create_process_job(meta=meta)
        mapping[idem_key] = job_id
        atomic_write_json(self._fs, RootName.WIZARDS, idem_path, mapping)
        return job_id

    def _load_state(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"
        if not self._fs.exists(RootName.WIZARDS, state_path):
            raise SessionNotFoundError(f"session not found: {session_id}")
        state = read_json(self._fs, RootName.WIZARDS, state_path)
        if isinstance(state, dict):
            state = _ensure_session_state_fields(state)
            self._persist_state(session_id, state)
        return state

    def _persist_state(self, session_id: str, state: dict[str, Any]) -> None:
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/state.json", state)

    def _runtime_effective_model_fingerprint(self, session_id: str) -> str:
        """Return fingerprint for the runtime-effective model for a session.

        The snapshot effective_model.json is immutable, but runtime selection items may be
        derived from discovery.json when rendering. state.json model_fingerprint is allowed
        to reflect this runtime-effective model.
        """
        model_any = self._load_effective_model(session_id)
        if isinstance(model_any, dict):
            return fingerprint_json(model_any)
        return ""

    def _effective_model_with_runtime_selection_items(
        self, session_id: str, effective_model: dict[str, Any]
    ) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        discovery_path = f"{session_dir}/discovery.json"

        if not self._fs.exists(RootName.WIZARDS, discovery_path):
            return effective_model

        discovery_any = read_json(self._fs, RootName.WIZARDS, discovery_path)
        if not isinstance(discovery_any, list):
            return effective_model

        authors_items, books_items = _derive_selection_items(discovery_any)
        return _inject_selection_items(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )

    def _load_effective_model(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        model_any = read_json(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/effective_model.json",
        )
        if isinstance(model_any, dict):
            return self._effective_model_with_runtime_selection_items(session_id, model_any)
        return model_any

    def _append_decision(
        self,
        session_id: str,
        *,
        step_id: str,
        payload: dict[str, Any],
        result: str,
        error: dict[str, Any] | None,
    ) -> None:
        session_dir = f"import/sessions/{session_id}"
        entry: dict[str, Any] = {
            "at": _iso_utc_now(),
            "step_id": step_id,
            "payload": dict(payload),
            "result": result,
        }
        if error is not None:
            entry["error"] = dict(error)
        append_jsonl(self._fs, RootName.WIZARDS, f"{session_dir}/decisions.jsonl", entry)
