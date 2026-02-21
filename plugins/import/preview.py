"""Preview artifact generation for the import wizard.

Preview artifacts are isolated engine-owned JSON documents written under:
  import/previews/<preview_id>.json

They must not modify session snapshots.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plugins.file_io.service.types import RootName

from .fingerprints import fingerprint_json
from .storage import atomic_write_json

if TYPE_CHECKING:  # pragma: no cover
    from .engine import ImportWizardEngine


def write_preview_artifact(
    *,
    fs: Any,
    session_id: str,
    step_id: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    """Write a preview artifact and return a small response envelope."""

    preview_id = fingerprint_json(
        {
            "session_id": session_id,
            "step_id": step_id,
            "payload": payload,
        }
    )

    doc: dict[str, Any] = {
        "version": 1,
        "preview_id": preview_id,
        "session_id": session_id,
        "step_id": step_id,
        "payload": payload,
    }

    rel_path = f"import/previews/{preview_id}.json"
    atomic_write_json(fs, RootName.WIZARDS, rel_path, doc)
    return {"preview_id": preview_id, "path": f"wizards:{rel_path}"}


def preview_action_impl(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    step_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Implementation for ImportWizardEngine.preview_action.

    Uses the engine's existing payload validation and must not mutate the session.
    """

    from .errors import StepSubmissionError, invariant_violation

    state = engine._load_state(session_id)
    if int(state.get("phase") or 1) == 2:
        return invariant_violation(
            message="session is locked (phase 2)",
            path="$.phase",
            reason="phase_locked",
            meta={},
        )
    if state.get("status") != "in_progress":
        raise StepSubmissionError("session is not in progress")

    if not isinstance(payload, dict):
        raise StepSubmissionError("payload must be an object")

    effective_model = engine._load_effective_model(session_id)
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        raise StepSubmissionError("effective model missing steps")

    steps = [s for s in steps_any if isinstance(s, dict)]
    step_ids = {str(s.get("step_id")) for s in steps if isinstance(s.get("step_id"), str)}
    if step_id not in step_ids:
        raise StepSubmissionError("unknown step_id")

    current = str(state.get("current_step_id") or "select_authors")
    if step_id != current:
        raise StepSubmissionError("step_id must match current_step_id")

    schema: dict[str, Any] | None = None
    for s in steps:
        if s.get("step_id") == step_id:
            schema = s
            break
    if schema is None:
        raise StepSubmissionError("unknown step_id")

    if step_id in {"plan_preview_batch", "processing"}:
        raise StepSubmissionError("computed-only step cannot be previewed")

    preview_action_any = schema.get("preview_action")
    if preview_action_any is None:
        raise StepSubmissionError("step has no preview_action")
    if not isinstance(preview_action_any, dict):
        raise StepSubmissionError("step.preview_action must be an object")

    normalized_payload = engine._validate_and_canonicalize_payload(
        step_id=step_id,
        schema=schema,
        payload=payload,
        state=state,
    )

    return write_preview_artifact(
        fs=engine._fs,
        session_id=session_id,
        step_id=step_id,
        payload=normalized_payload,
    )
