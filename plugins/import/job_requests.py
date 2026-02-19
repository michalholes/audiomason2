"""PHASE 2 job request generation for import wizard engine.

Job requests are derived from plan.json planned outputs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import fingerprint_json


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

    selected_any = plan.get("selected_books")
    if not isinstance(selected_any, list):
        selected_any = []

    if not selected_any:
        src_any = plan.get("source")
        if isinstance(src_any, dict):
            rel_any = src_any.get("relative_path")
            if isinstance(rel_any, str) and rel_any.strip():
                selected_any = [
                    {
                        "book_id": f"implicit:{rel_any.strip()}",
                        "source_relative_path": rel_any.strip(),
                        "proposed_target_relative_path": rel_any.strip(),
                    }
                ]

    actions: list[dict[str, Any]] = []
    target_root = "stage" if mode == "stage" else "outbox"
    for it in selected_any:
        if not isinstance(it, dict):
            continue
        book_id = it.get("book_id")
        src_rel = it.get("source_relative_path")
        tgt_rel = it.get("proposed_target_relative_path")
        if not isinstance(book_id, str) or not book_id:
            continue
        if not isinstance(src_rel, str) or not isinstance(tgt_rel, str):
            continue
        actions.append(
            {
                "type": "import.book",
                "book_id": book_id,
                "source": {"root": root, "relative_path": src_rel},
                "target": {"root": target_root, "relative_path": tgt_rel},
            }
        )

    doc: dict[str, Any] = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": session_id,
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_summary": plan.get("summary", {}),
        "policies": dict(inputs),
        "actions": actions,
        "diagnostics_context": dict(diagnostics_context),
    }

    idem_payload = {
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_fingerprint": fingerprint_json({"selected_books": selected_any}),
        "policies_fingerprint": fingerprint_json(inputs),
    }
    doc["idempotency_key"] = fingerprint_json(idem_payload)
    return doc


def planned_units_count(plan: dict[str, Any]) -> int:
    selected_any = plan.get("selected_books")
    if isinstance(selected_any, list) and selected_any:
        return len([it for it in selected_any if isinstance(it, dict)])
    src_any = plan.get("source")
    if isinstance(src_any, dict):
        rel_any = src_any.get("relative_path")
        if isinstance(rel_any, str) and rel_any.strip():
            return 1
    return 0
