"""Import Wizard Engine (plugin: import).

Implements PHASE 0 discovery, model load/validate, session lifecycle, and
minimal plan/job request generation.

No UI is implemented here.

ASCII-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service import FileService, RootName

from . import discovery as discovery_mod
from .defaults import ensure_default_models
from .errors import (
    FinalizeError,
    ImportWizardError,
    SessionNotFoundError,
    StepSubmissionError,
    error_envelope,
    invariant_violation,
    validation_error,
)
from .fingerprints import fingerprint_json, sha256_hex
from .job_requests import build_job_requests
from .models import _REQUIRED_STEP_IDS, CatalogModel, FlowModel, validate_models
from .plan import compute_plan
from .serialization import canonical_serialize
from .storage import append_jsonl, atomic_write_json, atomic_write_text, read_json


def _emit(event: str, operation: str, data: dict[str, Any]) -> None:
    try:
        get_event_bus().publish(
            event,
            build_envelope(
                event=event,
                component="import",
                operation=operation,
                data=data,
            ),
        )
    except Exception:
        # Fail-safe: diagnostics must never crash processing.
        return


def _iso_utc_now() -> str:
    # RFC3339 / ISO-8601 in UTC (Z suffix).
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _exception_envelope(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, SessionNotFoundError):
        return error_envelope(
            "NOT_FOUND",
            str(exc) or "not found",
            details=[{"path": "$.session_id", "reason": "not_found", "meta": {}}],
        )
    if isinstance(exc, (StepSubmissionError, ValueError)):
        return validation_error(
            message=str(exc) or "validation error",
            path="$",
            reason="validation_error",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, FinalizeError):
        return invariant_violation(
            message=str(exc) or "invariant violation",
            path="$",
            reason="invariant_violation",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, ImportWizardError):
        return error_envelope(
            "INTERNAL_ERROR",
            str(exc) or "internal error",
            details=[
                {
                    "path": "$.error",
                    "reason": "internal_error",
                    "meta": {"type": exc.__class__.__name__},
                }
            ],
        )
    return error_envelope(
        "INTERNAL_ERROR",
        str(exc) or "internal error",
        details=[
            {
                "path": "$.error",
                "reason": "internal_error",
                "meta": {"type": exc.__class__.__name__},
            }
        ],
    )


def _parse_selection_expr(expr: str, *, max_index: int | None) -> list[int]:
    text = expr.strip().lower()
    if text == "all":
        if max_index is None:
            # Caller must provide max_index to expand "all".
            raise ValueError("selection 'all' requires a known max_index")
        return list(range(1, max_index + 1))

    ids: set[int] = set()
    for raw in text.split(","):
        tok = raw.strip()
        if not tok:
            continue
        if "-" in tok:
            parts = [p.strip() for p in tok.split("-", 1)]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"invalid range token: {tok}")
            try:
                start = int(parts[0])
                end = int(parts[1])
            except ValueError as e:
                raise ValueError(f"invalid range token: {tok}") from e
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"invalid range token: {tok}")
            for i in range(start, end + 1):
                ids.add(i)
        else:
            try:
                i = int(tok)
            except ValueError as e:
                raise ValueError(f"invalid selection token: {tok}") from e
            if i <= 0:
                raise ValueError(f"invalid selection token: {tok}")
            ids.add(i)

    result = sorted(ids)
    if max_index is not None and any(i > max_index for i in result):
        raise ValueError("selection out of range")
    return result


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: ConfigResolver | None = None) -> None:
        # Fallback resolver is for tests only. Real hosts must provide a resolver.
        self._resolver = resolver or ConfigResolver(cli_args={})
        self._fs = FileService.from_resolver(self._resolver)

    def get_file_service(self) -> FileService:
        """Return the file service used by this engine.

        This is a plugin-internal helper for CLI/editor tooling.
        """
        return self._fs

    def create_session(
        self,
        root: str,
        relative_path: str,
        *,
        mode: str = "stage",
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mode = self._validate_mode(mode)
        # 1) Load models
        _emit("model.load", "model.load", {"root": root, "relative_path": relative_path})
        ensure_default_models(self._fs)
        catalog_dict = read_json(self._fs, RootName.WIZARDS, "import/catalog/catalog.json")
        flow_dict = read_json(self._fs, RootName.WIZARDS, "import/flow/current.json")
        flow_cfg = read_json(self._fs, RootName.WIZARDS, "import/config/flow_config.json")

        flow_cfg_norm = self._normalize_flow_config(flow_cfg)
        if flow_overrides is not None:
            # Legacy testing hook only. Overrides may only toggle optional steps.
            flow_cfg_norm = self._merge_flow_config_overrides(flow_cfg_norm, flow_overrides)

        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)

        _emit(
            "model.validate",
            "model.validate",
            {"root": root, "relative_path": relative_path},
        )
        validate_models(catalog, flow)

        effective_model: dict[str, Any] = {
            "version": 1,
            "catalog": catalog_dict,
            "flow": flow_dict,
        }
        model_fingerprint = fingerprint_json(effective_model)

        # 2) Discovery
        discovery = discovery_mod.run_discovery(self._fs, root=root, relative_path=relative_path)
        discovery_fingerprint = fingerprint_json(discovery)

        # 3) Effective config snapshot (only keys engine uses)
        effective_config: dict[str, Any] = {
            "version": 1,
            "flow_config": flow_cfg_norm,
            "diagnostics_enabled": bool(self._resolver.resolve("diagnostics.enabled")[0])
            if self._has_key("diagnostics.enabled")
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

        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"

        if self._fs.exists(RootName.WIZARDS, state_path):
            loaded_state = read_json(self._fs, RootName.WIZARDS, state_path)
            _emit(
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
            return loaded_state

        # 5) Persist frozen artifacts
        _emit(
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
            self._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json", effective_model
        )
        atomic_write_json(
            self._fs, RootName.WIZARDS, f"{session_dir}/effective_config.json", effective_config
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/discovery.json", discovery)

        atomic_write_text(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/discovery_fingerprint.txt",
            discovery_fingerprint + "\n",
        )
        atomic_write_text(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/effective_config_fingerprint.txt",
            effective_config_fingerprint + "\n",
        )

        created_at = _iso_utc_now()

        state: dict[str, Any] = {
            "session_id": session_id,
            "created_at": created_at,
            "updated_at": created_at,
            "model_fingerprint": model_fingerprint,
            "phase": 1,
            "mode": mode,
            "source": {"root": root, "relative_path": relative_path},
            "current_step_id": flow.entry_step_id,
            "completed_step_ids": [],
            "inputs": {},
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

        atomic_write_json(self._fs, RootName.WIZARDS, state_path, state)
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "session.created", "root": root, "relative_path": relative_path},
            result="accepted",
            error=None,
        )

        return state

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

    def preview_effective_model(self, catalog_json: Any, flow_json: Any) -> dict[str, Any]:
        """Return the effective model that would be frozen for new sessions."""
        if not isinstance(catalog_json, dict):
            raise ValueError("catalog_json must be an object")
        if not isinstance(flow_json, dict):
            raise ValueError("flow_json must be an object")
        catalog = CatalogModel.from_dict(catalog_json)
        flow = FlowModel.from_dict(flow_json)
        validate_models(catalog, flow)
        _ = (catalog, flow)
        return {"version": 1, "catalog": catalog_json, "flow": flow_json}

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
            catalog_any = effective_model.get("catalog")
            if not isinstance(catalog_any, dict):
                raise ValueError("effective model missing catalog")
            catalog = CatalogModel.from_dict(cast(dict[str, Any], catalog_any))

            _emit(
                "step.view",
                "step.view",
                {
                    "session_id": session_id,
                    "step_id": step_id,
                },
            )
            for step in catalog.steps:
                sid = step.get("step_id")
                if sid == step_id:
                    return dict(step)
            raise ValueError("unknown step_id")
        except Exception as e:
            return _exception_envelope(e)

    def submit_step(self, session_id: str, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            state = self._load_state(session_id)
            if state.get("status") != "in_progress":
                raise StepSubmissionError("session is not in progress")

            _emit(
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
            catalog_dict_any = effective_model.get("catalog")
            flow_dict_any = effective_model.get("flow")

            if not isinstance(catalog_dict_any, dict) or not isinstance(flow_dict_any, dict):
                raise StepSubmissionError("effective model missing required sections")

            catalog_dict = cast(dict[str, Any], catalog_dict_any)
            flow_dict = cast(dict[str, Any], flow_dict_any)
            catalog = CatalogModel.from_dict(catalog_dict)
            flow = FlowModel.from_dict(flow_dict)

            if step_id not in catalog.step_ids():
                raise StepSubmissionError("unknown step_id")

            current = str(state.get("current_step_id") or flow.entry_step_id)
            if step_id != current:
                raise StepSubmissionError("step_id must match current_step_id")

            schema = None
            for step in catalog.steps:
                if step.get("step_id") == step_id:
                    schema = step
                    break
            if schema is None:
                raise StepSubmissionError("unknown step_id")

            if bool(schema.get("computed_only")):
                raise StepSubmissionError("computed-only step cannot be submitted")

            normalized_payload = self._validate_and_canonicalize_payload(
                step_id=step_id,
                schema=schema,
                payload=payload,
                state=state,
            )

            inputs = dict(state.get("inputs") or {})
            inputs[step_id] = normalized_payload
            state["inputs"] = inputs

            completed = list(state.get("completed_step_ids") or [])
            if step_id not in completed:
                completed.append(step_id)
            state["completed_step_ids"] = completed

            # Move to next step deterministically.
            node = flow.node_map().get(step_id)
            next_step = node.next_step_id if node is not None else None

            # Conditional insertion: resolve_conflicts_batch only after final_summary_confirm.
            if step_id == "final_summary_confirm":
                conflicts = state.get("conflicts")
                if isinstance(conflicts, dict):
                    present = bool(conflicts.get("present"))
                    policy = str(conflicts.get("policy") or "")
                    resolved = bool(conflicts.get("resolved"))
                else:
                    present = False
                    policy = ""
                    resolved = True
                if present and policy == "ask" and not resolved:
                    next_step = "resolve_conflicts_batch"
                else:
                    next_step = None

            state["current_step_id"] = next_step or step_id

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
                error={"type": e.__class__.__name__, "message": str(e) or e.__class__.__name__},
            )
            return _exception_envelope(e)

    def _validate_and_canonicalize_payload(
        self,
        *,
        step_id: str,
        schema: dict[str, Any],
        payload: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        fields_any = schema.get("fields")
        if not isinstance(fields_any, list):
            raise StepSubmissionError("step schema is invalid")
        fields: list[dict[str, Any]] = [f for f in fields_any if isinstance(f, dict)]

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
        if isinstance(items_any, list) and all(isinstance(x, dict) for x in items_any):
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
        state = self._load_state(session_id)
        if state.get("status") != "in_progress":
            return state

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

        effective_model = self._load_effective_model(session_id)
        flow = FlowModel.from_dict(effective_model["flow"])
        node_map = flow.node_map()

        current = str(state.get("current_step_id") or flow.entry_step_id)
        node = node_map.get(current)
        if node is None:
            # Reset to entry if current unknown.
            state["current_step_id"] = flow.entry_step_id
        else:
            if action == "next" and node.next_step_id is not None:
                state["current_step_id"] = node.next_step_id
            elif action == "back" and node.prev_step_id is not None:
                state["current_step_id"] = node.prev_step_id

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

    def compute_plan(self, session_id: str) -> dict[str, Any]:
        state = self._load_state(session_id)

        _emit(
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
            inputs=dict(state.get("inputs") or {}),
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/plan.json", plan)

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
        try:
            state = self._load_state(session_id)
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

            inputs = dict(state.get("inputs") or {})
            final = inputs.get("final_summary_confirm")
            if not (isinstance(final, dict) and final.get("confirm") is True):
                return validation_error(
                    message="final_summary_confirm must be submitted with confirm=true",
                    path="$.inputs.final_summary_confirm.confirm",
                    reason="missing_or_false",
                    meta={},
                )

            _emit(
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

            current_conflicts = self._scan_conflicts(state)
            current_fp = fingerprint_json(current_conflicts)

            # Persist current conflicts to session state (UI must see the latest scan).
            state.setdefault("derived", {})["conflict_fingerprint"] = current_fp
            state["conflicts"] = {
                "present": bool(current_conflicts),
                "items": current_conflicts,
                "resolved": not bool(current_conflicts),
                "policy": str((state.get("conflicts") or {}).get("policy") or "ask"),
            }
            session_dir = f"import/sessions/{session_id}"
            atomic_write_json(
                self._fs,
                RootName.WIZARDS,
                f"{session_dir}/conflicts.json",
                current_conflicts,
            )
            state["updated_at"] = _iso_utc_now()
            self._persist_state(session_id, state)

            if policy == "ask" and current_conflicts:
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
                return error_envelope(
                    "CONFLICTS_CHANGED",
                    "conflict scan changed since preview",
                    details=[
                        {
                            "path": "$.conflicts",
                            "reason": "conflicts_changed",
                            "meta": {"preview": preview_fp, "current": current_fp},
                        }
                    ],
                )

            # Ensure plan exists.
            plan_path = f"{session_dir}/plan.json"
            if self._fs.exists(RootName.WIZARDS, plan_path):
                plan = read_json(self._fs, RootName.WIZARDS, plan_path)
            else:
                plan = self.compute_plan(session_id)

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
                "conflict_fingerprint": str(
                    state.get("derived", {}).get("conflict_fingerprint") or ""
                ),
            }

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
                inputs=inputs,
            )

            job_path = f"{session_dir}/job_requests.json"
            job_bytes = canonical_serialize(job_requests)
            atomic_write_text(self._fs, RootName.WIZARDS, job_path, job_bytes.decode("utf-8"))

            idem_key = str(job_requests.get("idempotency_key") or "")
            job_id = self._get_or_create_job(session_id, state, idem_key)

            _emit(
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

            return {"job_ids": [job_id], "batch_size": 1}
        except Exception as e:
            return _exception_envelope(e)

    def _validate_mode(self, mode: str) -> str:
        mode = str(mode)
        if mode not in {"stage", "inplace"}:
            raise ValueError("mode must be 'stage' or 'inplace'")
        return mode

    def _normalize_flow_config(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ValueError("flow_config must be an object")
        version = raw.get("version")
        if version != 1:
            raise ValueError("flow_config.version must be 1")

        steps_any = raw.get("steps", {})
        if steps_any is None:
            steps_any = {}
        if not isinstance(steps_any, dict):
            raise ValueError("flow_config.steps must be an object")

        steps: dict[str, Any] = {}
        for step_id, cfg in steps_any.items():
            if not isinstance(step_id, str) or not step_id:
                raise ValueError("flow_config.steps keys must be non-empty strings")
            if not isinstance(cfg, dict):
                raise ValueError("flow_config.steps.<step_id> must be an object")
            enabled = cfg.get("enabled")
            if enabled is not None and not isinstance(enabled, bool):
                raise ValueError("flow_config.steps.<step_id>.enabled must be bool")
            if enabled is False and step_id in _REQUIRED_STEP_IDS:
                raise ValueError(f"required step may not be disabled: {step_id}")
            if enabled is None:
                continue
            steps[step_id] = {"enabled": bool(enabled)}

        defaults_any = raw.get("defaults", {})
        ui_any = raw.get("ui", {})
        if defaults_any is None:
            defaults_any = {}
        if ui_any is None:
            ui_any = {}
        if not isinstance(defaults_any, dict):
            raise ValueError("flow_config.defaults must be an object")
        if not isinstance(ui_any, dict):
            raise ValueError("flow_config.ui must be an object")

        return {"version": 1, "steps": steps, "defaults": defaults_any, "ui": ui_any}

    def _merge_flow_config_overrides(
        self, base: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(overrides, dict):
            raise ValueError("flow_overrides must be an object")
        if "steps" not in overrides:
            return base
        merged = dict(base)
        steps = dict(cast(dict[str, Any], merged.get("steps") or {}))
        raw_steps = overrides.get("steps")
        if not isinstance(raw_steps, dict):
            raise ValueError("flow_overrides.steps must be an object")
        for step_id, cfg in raw_steps.items():
            if not isinstance(step_id, str) or not step_id:
                raise ValueError("flow_overrides.steps keys must be strings")
            if not isinstance(cfg, dict):
                raise ValueError("flow_overrides.steps.<step_id> must be an object")
            enabled = cfg.get("enabled")
            if enabled is None:
                continue
            if not isinstance(enabled, bool):
                raise ValueError("flow_overrides.steps.<step_id>.enabled must be bool")
            if enabled is False and step_id in _REQUIRED_STEP_IDS:
                raise ValueError(f"required step may not be disabled: {step_id}")
            steps[step_id] = {"enabled": bool(enabled)}
        merged["steps"] = steps
        return merged

    def _scan_conflicts(self, state: dict[str, Any]) -> list[dict[str, str]]:
        from .conflicts import scan_conflicts

        src = state.get("source") or {}
        root = str(src.get("root") or "")
        rel = str(src.get("relative_path") or "")
        mode = self._validate_mode(str(state.get("mode") or "stage"))
        return scan_conflicts(self._fs, root=root, relative_path=rel, mode=mode)

    def _update_conflicts(self, session_id: str, state: dict[str, Any]) -> None:
        items = self._scan_conflicts(state)
        fp = fingerprint_json(items)
        state.setdefault("derived", {})["conflict_fingerprint"] = fp
        state["conflicts"] = {
            "present": bool(items),
            "items": items,
            "resolved": not bool(items),
            "policy": str((state.get("conflicts") or {}).get("policy") or "ask"),
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

        from audiomason.core.jobs.api import JobService
        from audiomason.core.jobs.model import JobType

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
        job = JobService().create_job(JobType.PROCESS, meta=meta)
        mapping[idem_key] = job.job_id
        atomic_write_json(self._fs, RootName.WIZARDS, idem_path, mapping)
        return job.job_id

    def _load_state(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        state_path = f"{session_dir}/state.json"
        if not self._fs.exists(RootName.WIZARDS, state_path):
            raise SessionNotFoundError(f"session not found: {session_id}")
        return read_json(self._fs, RootName.WIZARDS, state_path)

    def _persist_state(self, session_id: str, state: dict[str, Any]) -> None:
        session_dir = f"import/sessions/{session_id}"
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/state.json", state)

    def _load_effective_model(self, session_id: str) -> dict[str, Any]:
        session_dir = f"import/sessions/{session_id}"
        return read_json(self._fs, RootName.WIZARDS, f"{session_dir}/effective_model.json")

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
