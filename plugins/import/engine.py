"""Import Wizard Engine (plugin: import).

Implements PHASE 0 discovery, model load/validate, session lifecycle, and
minimal plan/job request generation.

No UI is implemented here.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

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


class ImportWizardEngine:
    """Data-defined import wizard engine."""

    def __init__(self, *, resolver: ConfigResolver | None = None) -> None:
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
            "version": "0.1.0",
            "catalog": catalog_dict,
            "flow": flow_dict,
        }
        model_fingerprint = fingerprint_json(effective_model)

        # 2) Discovery
        discovery = discovery_mod.run_discovery(self._fs, root=root, relative_path=relative_path)
        discovery_fingerprint = fingerprint_json(discovery)

        # 3) Effective config snapshot (only keys engine uses)
        effective_config: dict[str, Any] = {
            "version": "0.1.0",
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

        state: dict[str, Any] = {
            "session_id": session_id,
            "source": {"root": root, "relative_path": relative_path},
            "model_fingerprint": model_fingerprint,
            "current_step_id": flow.entry_step_id,
            "inputs": {},
            "derived": {
                "discovery_fingerprint": discovery_fingerprint,
                "effective_config_fingerprint": effective_config_fingerprint,
            },
            "conflicts": [],
            "status": "active",
            "decisions_seq": 0,
        }

        atomic_write_json(self._fs, RootName.WIZARDS, state_path, state)
        append_jsonl(
            self._fs,
            RootName.WIZARDS,
            f"{session_dir}/decisions.jsonl",
            {"seq": 0, "event": "session.created", "session_id": session_id},
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

    def submit_step(self, session_id: str, step_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise StepSubmissionError("payload must be a dict")

        state = self._load_state(session_id)
        if state.get("status") != "active":
            raise StepSubmissionError("session is not active")

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

        inputs = dict(state.get("inputs") or {})
        inputs[step_id] = payload
        state["inputs"] = inputs
        state["current_step_id"] = step_id

        self._bump_decision(state, session_id, {"event": "step.submitted", "step_id": step_id})
        self._persist_state(session_id, state)
        return state

    def apply_action(self, session_id: str, action: str) -> dict[str, Any]:
        state = self._load_state(session_id)
        if state.get("status") != "active":
            return state

        action = str(action)
        if action not in {"next", "back", "cancel"}:
            raise StepSubmissionError("invalid action")

        if action == "cancel":
            state["status"] = "cancelled"
            self._bump_decision(state, session_id, {"event": "session.cancelled"})
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

        self._bump_decision(state, session_id, {"event": f"action.{action}", "from": current})
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
        plan = compute_plan(
            session_id=session_id,
            root=str(src.get("root") or ""),
            relative_path=str(src.get("relative_path") or ""),
            discovery=discovery,
            inputs=dict(state.get("inputs") or {}),
        )
        atomic_write_json(self._fs, RootName.WIZARDS, f"{session_dir}/plan.json", plan)
        self._bump_decision(state, session_id, {"event": "plan.computed"})
        self._persist_state(session_id, state)
        return plan

    def finalize(self, session_id: str) -> dict[str, Any]:
        state = self._load_state(session_id)
        if state.get("status") != "active":
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

        if state.get("conflicts"):
            _emit(
                "import.validation.fail",
                "finalize.validate",
                {"session_id": session_id, "reason": "conflicts present"},
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
            root=str(src.get("root") or ""),
            relative_path=str(src.get("relative_path") or ""),
            diagnostics_context=diagnostics_context,
            plan=plan,
        )

        atomic_write_json(
            self._fs, RootName.WIZARDS, f"{session_dir}/job_requests.json", job_requests
        )

        state["status"] = "finalized"
        self._bump_decision(state, session_id, {"event": "session.finalized"})
        self._persist_state(session_id, state)

        _emit(
            "import.job.persist",
            "job.persist",
            {
                "session_id": session_id,
                "jobs": len(job_requests),
                **diagnostics_context,
            },
        )

        return {
            "session_id": session_id,
            "status": state.get("status"),
            "jobs": len(job_requests),
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

    def _bump_decision(self, state: dict[str, Any], session_id: str, entry: dict[str, Any]) -> None:
        seq = int(state.get("decisions_seq") or 0) + 1
        state["decisions_seq"] = seq
        session_dir = f"import/sessions/{session_id}"
        append = dict(entry)
        append["seq"] = seq
        append["session_id"] = session_id
        append_jsonl(self._fs, RootName.WIZARDS, f"{session_dir}/decisions.jsonl", append)
