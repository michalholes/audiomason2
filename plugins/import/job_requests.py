"""PHASE 2 job request generation for import wizard engine.

Job requests are derived from plan.json planned outputs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import fingerprint_json

_METADATA_FIELD_MAP = {
    "title": "book_title",
    "artist": "author",
    "album": "book_title",
    "album_artist": "author",
}


def _policy_dict(inputs: dict[str, Any], key: str) -> dict[str, Any]:
    value = inputs.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _tag_values_for_action(
    *,
    inputs: dict[str, Any],
    authority_meta: dict[str, Any] | None = None,
) -> dict[str, str]:
    authority = dict(authority_meta) if isinstance(authority_meta, dict) else {}
    author_name = str(authority.get("author_label") or "")
    book_title = str(authority.get("book_label") or "")
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


def _action_authority(
    *,
    book_meta: dict[str, Any] | None,
    tag_values: dict[str, str],
    target_root: str,
    target_relative_path: str,
) -> dict[str, Any]:
    book = dict(book_meta) if isinstance(book_meta, dict) else {}
    return {
        "book": book,
        "metadata_tags": {
            "field_map": dict(_METADATA_FIELD_MAP),
            "values": dict(tag_values),
        },
        "publish": {
            "root": target_root,
            "relative_path": target_relative_path,
        },
    }


def _build_capabilities(
    *,
    root: str,
    source_relative_path: str,
    target_root: str,
    target_relative_path: str,
    inputs: dict[str, Any],
    tag_values: dict[str, str],
) -> list[dict[str, Any]]:
    audio_processing = _policy_dict(inputs, "audio_processing")
    covers_policy = _policy_dict(inputs, "covers_policy")
    conflict_policy = _policy_dict(inputs, "conflict_policy")
    delete_policy = _policy_dict(inputs, "delete_source_policy")

    cover_mode = str(covers_policy.get("mode") or "skip")
    conflict_mode = str(conflict_policy.get("mode") or "ask")

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
            "field_map": dict(_METADATA_FIELD_MAP),
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

    actions: list[dict[str, Any]] = []
    authority = dict(session_authority) if isinstance(session_authority, dict) else {}
    phase1_runtime_any = authority.get("runtime")
    phase1_runtime = dict(phase1_runtime_any) if isinstance(phase1_runtime_any, dict) else {}
    phase2_inputs_any = authority.get("phase2_inputs")
    phase2_inputs = dict(phase2_inputs_any) if isinstance(phase2_inputs_any, dict) else {}
    del inputs
    publish_policy = _policy_dict(phase2_inputs, "publish_policy")
    target_root = str(publish_policy.get("target_root") or "")
    if target_root not in {"stage", "outbox"}:
        target_root = "stage" if mode == "stage" else "outbox"
    book_meta_any = authority.get("book_meta")
    book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}
    selected_book_meta: dict[str, dict[str, Any]] = {}
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
        authority_meta_any = book_meta.get(book_id)
        authority_meta = dict(authority_meta_any) if isinstance(authority_meta_any, dict) else {}
        if authority_meta:
            selected_book_meta[book_id] = dict(authority_meta)
        tag_values = _tag_values_for_action(inputs=phase2_inputs, authority_meta=authority_meta)
        actions.append(
            {
                "type": "import.book",
                "book_id": book_id,
                "source": {"root": root, "relative_path": src_rel},
                "target": {"root": target_root, "relative_path": tgt_rel},
                "authority": _action_authority(
                    book_meta=authority_meta,
                    tag_values=tag_values,
                    target_root=target_root,
                    target_relative_path=tgt_rel,
                ),
                "capabilities": _build_capabilities(
                    root=root,
                    source_relative_path=src_rel,
                    target_root=target_root,
                    target_relative_path=tgt_rel,
                    inputs=phase2_inputs,
                    tag_values=tag_values,
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
        "policies": dict(phase2_inputs),
        "actions": actions,
        "authority": {
            "phase1": {
                "runtime": dict(phase1_runtime),
                "selected_books": selected_book_meta,
            }
        },
        "diagnostics_context": dict(diagnostics_context),
        "plan_fingerprint": plan_fingerprint,
    }

    idem_payload = {
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_fingerprint": plan_fingerprint,
        "policies_fingerprint": fingerprint_json(phase2_inputs),
    }
    doc["idempotency_key"] = fingerprint_json(idem_payload)
    return doc


def planned_units_count(plan: dict[str, Any]) -> int:
    selected_any = plan.get("selected_books")
    if not isinstance(selected_any, list):
        return 0
    return len([it for it in selected_any if isinstance(it, dict)])
