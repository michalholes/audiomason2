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
from .errors import FinalizeError, SessionNotFoundError, StepSubmissionError
from .fingerprints import fingerprint_json, sha256_hex
from .job_requests import build_job_requests
from .models import CatalogModel, FlowModel, validate_models
from .plan import compute_plan
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


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: ConfigResolver | None = None) -> None:
        # Fallback resolver is for tests only. Real hosts must provide a resolver.
        self._resolver = resolver or ConfigResolver(cli_args={})
        self._fs = FileService.from_resolver(self._resolver)

    def create_session(
        self,
        root: str,
        relative_path: str,
        *,
        flow_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 1) Load models
        _emit("import.model.load", "model.load", {"root": root, "relative_path": relative_path})
        catalog_dict = read_json(self._fs, RootName.WIZARDS, "import/catalog/catalog.json")
        flow_dict = read_json(self._fs, RootName.WIZARDS, "import/flow/current.json")
        if flow_overrides:
            if not isinstance(flow_dict, dict) or not isinstance(flow_overrides, dict):
                raise ValueError("flow_overrides must be a dict")
            flow_dict = dict(flow_dict)
            flow_dict.update(flow_overrides)

        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)

        _emit(
            "import.model.validate",
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
                "import.session.resume",
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
            "import.session.start",
            "session.start",
            {
                "session_id": session_id,
                "root": root,
                "relative_path": relative_path,
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
            "source": {"root": root, "relative_path": relative_path},
            "current_step_id": flow.entry_step_id,
            "completed_step_ids": [],
            "inputs": {},
            "derived": {
                "discovery_fingerprint": discovery_fingerprint,
                "effective_config_fingerprint": effective_config_fingerprint,
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

    def _has_key(self, key: str) -> bool:
        try:
            self._resolver.resolve(key)
            return True
        except Exception:
            return False

    def get_state(self, session_id: str) -> dict[str, Any]:
        state = self._load_state(session_id)
        return state

    def get_step_definition(self, session_id: str, step_id: str) -> dict[str, Any]:
        """Return the catalog step definition for step_id.

        This is a UI helper. It does not perform any state transitions.
        """
        effective_model = self._load_effective_model(session_id)
        catalog_any = effective_model.get("catalog")
        if not isinstance(catalog_any, dict):
            raise ValueError("effective model missing catalog")
        catalog = CatalogModel.from_dict(cast(dict[str, Any], catalog_any))
        for step in catalog.steps:
            sid = step.get("step_id")
            if sid == step_id:
                return dict(step)
        raise ValueError("unknown step_id")

    def submit_step(self, session_id: str, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        state = self._load_state(session_id)
        if state.get("status") != "in_progress":
            raise StepSubmissionError("session is not in progress")

        _emit(
            "import.step.submit",
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
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload if isinstance(payload, dict) else {"_invalid_payload": True},
                result="rejected",
                error={"type": "StepSubmissionError", "message": "payload must be a dict"},
            )
            raise StepSubmissionError("payload must be a dict")

        effective_model = self._load_effective_model(session_id)
        catalog_dict_any = effective_model.get("catalog")
        flow_dict_any = effective_model.get("flow")

        if not isinstance(catalog_dict_any, dict) or not isinstance(flow_dict_any, dict):
            missing: list[str] = []
            if not isinstance(catalog_dict_any, dict):
                missing.append("catalog")
            if not isinstance(flow_dict_any, dict):
                missing.append("flow")
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload,
                result="rejected",
                error={
                    "type": "StepSubmissionError",
                    "message": "effective model missing required section(s): " + ", ".join(missing),
                },
            )
            raise StepSubmissionError(
                "effective model missing required section(s): " + ", ".join(missing)
            )

        catalog_dict = cast(dict[str, Any], catalog_dict_any)
        flow_dict = cast(dict[str, Any], flow_dict_any)
        catalog = CatalogModel.from_dict(catalog_dict)
        flow = FlowModel.from_dict(flow_dict)

        if step_id not in catalog.step_ids():
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload,
                result="rejected",
                error={
                    "type": "StepSubmissionError",
                    "message": "step_id does not exist in catalog",
                },
            )
            raise StepSubmissionError("unknown step_id")

        current = str(state.get("current_step_id") or flow.entry_step_id)
        if step_id != current:
            self._append_decision(
                session_id,
                step_id=step_id,
                payload=payload,
                result="rejected",
                error={
                    "type": "StepSubmissionError",
                    "message": "step_id must match current_step_id",
                },
            )
            raise StepSubmissionError("step_id must match current_step_id")

        inputs = dict(state.get("inputs") or {})
        inputs[step_id] = payload
        state["inputs"] = inputs

        completed = list(state.get("completed_step_ids") or [])
        if step_id not in completed:
            completed.append(step_id)
        state["completed_step_ids"] = completed

        # Move to next step deterministically.
        node = flow.node_map().get(step_id)
        if node is not None and node.next_step_id is not None:
            state["current_step_id"] = node.next_step_id
        else:
            state["current_step_id"] = step_id

        state["updated_at"] = _iso_utc_now()
        self._append_decision(
            session_id,
            step_id=step_id,
            payload=payload,
            result="accepted",
            error=None,
        )
        self._persist_state(session_id, state)
        return state

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
            "import.plan.compute",
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
        state = self._load_state(session_id)
        if state.get("status") != "in_progress":
            raise FinalizeError("session is not active")

        inputs = dict(state.get("inputs") or {})
        confirm = inputs.get("final_summary_confirm")
        if not (isinstance(confirm, dict) and confirm.get("confirm") is True):
            _emit(
                "import.validation.fail",
                "finalize.validate",
                {"session_id": session_id, "reason": "final_summary_confirm missing"},
            )
            raise FinalizeError("final_summary_confirm must be submitted with confirm=true")

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
            _emit(
                "import.validation.fail",
                "finalize.validate",
                {"session_id": session_id, "reason": "conflicts present"},
            )
            self._append_decision(
                session_id,
                step_id="__system__",
                payload={"event": "finalize"},
                result="rejected",
                error={"type": "FinalizeError", "message": "conflicts must be resolved"},
            )
            raise FinalizeError("conflicts must be resolved before finalize")

        _emit(
            "import.finalize.request",
            "finalize.request",
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

        # Ensure plan exists.
        plan_path = f"{session_dir}/plan.json"
        if self._fs.exists(RootName.WIZARDS, plan_path):
            plan = read_json(self._fs, RootName.WIZARDS, plan_path)
        else:
            plan = self.compute_plan(session_id)

        src = state.get("source") or {}
        src_root = str(src.get("root") or "")
        src_rel = str(src.get("relative_path") or "")
        created_at = _iso_utc_now()
        diagnostics_context = {
            "model_fingerprint": str(state.get("model_fingerprint") or ""),
            "discovery_fingerprint": str(
                state.get("derived", {}).get("discovery_fingerprint") or ""
            ),
            "effective_config_fingerprint": str(
                state.get("derived", {}).get("effective_config_fingerprint") or ""
            ),
        }

        job_requests = build_job_requests(
            session_id=session_id,
            root=src_root,
            relative_path=src_rel,
            created_at=created_at,
            diagnostics_context=diagnostics_context,
            plan=plan,
            inputs=inputs,
        )

        atomic_write_json(
            self._fs, RootName.WIZARDS, f"{session_dir}/job_requests.json", job_requests
        )

        state["status"] = "finalized"
        state["updated_at"] = _iso_utc_now()
        self._append_decision(
            session_id,
            step_id="__system__",
            payload={"event": "finalize"},
            result="accepted",
            error=None,
        )
        self._persist_state(session_id, state)

        _emit(
            "import.job.persist",
            "job.persist",
            {
                "session_id": session_id,
                "jobs": 1,
                **diagnostics_context,
            },
        )

        return {
            "session_id": session_id,
            "status": state.get("status"),
            "jobs": 1,
        }

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
