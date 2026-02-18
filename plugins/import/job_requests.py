"""PHASE 2 job request generation for import wizard engine.

Minimal baseline: creates a single no-op job request with diagnostics_context.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def build_job_requests(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    mode: str,
    diagnostics_context: dict[str, str],
    config_fingerprint: str,
    plan: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    mode = str(mode)
    if mode not in {"stage", "inplace"}:
        raise ValueError("mode must be 'stage' or 'inplace'")

    doc: dict[str, Any] = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": session_id,
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "actions": [
            {
                "type": "import.batch",
                "source": {"root": root, "relative_path": relative_path},
                "target": {"root": "stage" if mode == "stage" else "outbox"},
                "plan_summary": plan.get("summary", {}),
            }
        ],
        "diagnostics_context": dict(diagnostics_context),
    }

    # Idempotency key is derived from canonical content.
    from .fingerprints import fingerprint_json

    doc["idempotency_key"] = fingerprint_json(doc)
    return doc
