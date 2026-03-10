"""PHASE 2 job request generation for import wizard engine.

Job requests are derived from plan.json planned outputs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import fingerprint_json


def _policy_dict(inputs: dict[str, Any], key: str) -> dict[str, Any]:
    value = inputs.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _split_source_relative_path(source_relative_path: str) -> tuple[str, str]:
    rel = str(source_relative_path).replace("\\", "/").strip("/")
    if not rel:
        return "", ""
    parts = [part for part in rel.split("/") if part]
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[-1]


def _tag_values_for_action(
    *,
    source_relative_path: str,
    inputs: dict[str, Any],
    authority_meta: dict[str, Any] | None = None,
) -> dict[str, str]:
    authority = dict(authority_meta) if isinstance(authority_meta, dict) else {}
    author_name = str(authority.get("author_label") or "")
    book_title = str(authority.get("book_label") or "")
    if not author_name or not book_title:
        author_name, book_title = _split_source_relative_path(source_relative_path)
    values = {
        "title": book_title,
        "artist": author_name,
        "album": book_title,
        "album_artist": author_name,
    }
    id3_policy = _policy_dict(inputs, "id3_policy")
    values_any = id3_policy.get("values")
    if isinstance(values_any, dict):
        for key, value in values_any.items():
            text_value = str(value or "").strip()
            if text_value:
                values[str(key)] = text_value
    return {key: value for key, value in values.items() if value}


def _build_capabilities(
    *,
    root: str,
    source_relative_path: str,
    target_root: str,
    target_relative_path: str,
    inputs: dict[str, Any],
    authority_meta: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    audio_processing = _policy_dict(inputs, "audio_processing")
    covers_policy = _policy_dict(inputs, "covers_policy")
    conflict_policy = _policy_dict(inputs, "conflict_policy")
    delete_policy = _policy_dict(inputs, "delete_source_policy")

    cover_mode = str(covers_policy.get("mode") or "skip")
    conflict_mode = str(conflict_policy.get("mode") or "ask")
    tag_values = _tag_values_for_action(
        source_relative_path=source_relative_path,
        inputs=inputs,
        authority_meta=authority_meta,
    )

    capabilities: list[dict[str, Any]] = [
        {
            "kind": "audio.import",
            "order": 10,
            "plugin": "audio_processor",
            "options": {
                "bitrate": str(audio_processing.get("bitrate") or "128k"),
                "loudnorm": bool(audio_processing.get("loudnorm", False)),
                "split_chapters": bool(audio_processing.get("split_chapters", False)),
            },
        }
    ]
    if cover_mode != "skip":
        cover_cap: dict[str, Any] = {
            "kind": "cover.embed",
            "order": 20,
            "plugin": "cover_handler",
            "mode": cover_mode,
        }
        cover_url = str(covers_policy.get("url") or "")
        if cover_url:
            cover_cap["url"] = cover_url
        capabilities.append(cover_cap)

    capabilities.append(
        {
            "kind": "metadata.tags",
            "order": 30,
            "plugin": "id3_tagger",
            "field_map": {
                "title": "book_title",
                "artist": "author",
                "album": "book_title",
                "album_artist": "author",
            },
            "values": tag_values,
            "wipe_before_write": True,
            "preserve_cover": True,
        }
    )
    capabilities.append(
        {
            "kind": "publish.write",
            "order": 40,
            "root": target_root,
            "relative_path": target_relative_path,
            "overwrite": conflict_mode == "overwrite",
        }
    )

    delete_mode = str(delete_policy.get("mode") or "")
    delete_enabled = bool(delete_policy.get("enabled", False)) or delete_mode in {
        "delete",
        "after_publish",
        "always",
    }
    if delete_enabled:
        capabilities.append(
            {
                "kind": "source.delete",
                "order": 50,
                "root": root,
                "relative_path": source_relative_path,
                "enabled": True,
            }
        )
    return capabilities


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
    session_authority: dict[str, Any] | None = None,
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
    authority = dict(session_authority) if isinstance(session_authority, dict) else {}
    phase2_inputs_any = authority.get("phase2_inputs")
    phase2_inputs = dict(phase2_inputs_any) if isinstance(phase2_inputs_any, dict) else {}
    merged_inputs = {**phase2_inputs, **inputs}
    publish_policy = _policy_dict(merged_inputs, "publish_policy")
    target_root = str(publish_policy.get("target_root") or "")
    if target_root not in {"stage", "outbox"}:
        target_root = "stage" if mode == "stage" else "outbox"
    book_meta_any = authority.get("book_meta")
    book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}
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
                "capabilities": _build_capabilities(
                    root=root,
                    source_relative_path=src_rel,
                    target_root=target_root,
                    target_relative_path=tgt_rel,
                    inputs=merged_inputs,
                    authority_meta=book_meta.get(book_id),
                ),
            }
        )

    plan_fingerprint = fingerprint_json({"selected_books": selected_any})

    doc: dict[str, Any] = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": session_id,
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_summary": plan.get("summary", {}),
        "policies": dict(merged_inputs),
        "actions": actions,
        "diagnostics_context": dict(diagnostics_context),
        "plan_fingerprint": plan_fingerprint,
    }

    idem_payload = {
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_fingerprint": plan_fingerprint,
        "policies_fingerprint": fingerprint_json(merged_inputs),
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
